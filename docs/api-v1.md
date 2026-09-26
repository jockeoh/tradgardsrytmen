# API v1: kontrakt för mobilens första flöde

**Aktuell drift 2026-09-26:** den privata releasen, PostgreSQL 17.11 och
DURABLE_JOBS=1 är nu verifierat aktiva, med schema 0014 och OIDC av.
[Driftbevis, backupgränser och operatörsrutin](p3-activation.md) ersätter
äldre lokalstatus/ej aktiverat i de daterade avsnitten nedan.


Status 2026-09-25: P2 implementerar kärnkontraktet nedan lokalt: `/me/`,
garden-lista/skapa/detalj, plant-lista/skapa/detalj och task-lista/skapa/
detalj/complete. Nuvarande `/api/` är samtidigt sessionsautentiserat och
trädgårdsavgränsat för den privata webben. M1 kan använda exemplen som stabila
fixtures. Auth0 i EU-region är vald men ingen tenant eller klient är ännu
skapad eller aktiverad, och ingen publik drift är godkänd.

## Status efter P3-granskning 2026-09-26

P2-kärnan finns på main. Samlad P3 och rättningar är lokalt verifierade,
ocommittade och inte driftsatta. M1/I1 och verklig Auth0-aktivering är inte
verifierade. Privat SQLite-release med kö/OIDC av bedöms separat i
[releaseunderlaget](private-release-review.md); native AI/push tillkommer inte
av att webbpaketet släpps. Roadmapen listar återstående aktiveringar.

## Gemensamma regler

Bas `/api/v1/`, HTTPS, JSON UTF-8, `Content-Type: application/json`.
Opaka ID:n är strängar (fixtures kan använda `g_01`, `p_01`, `t_01`); den
riktiga P2-servern returnerar UUID-strängar. Klienten får inte anta format,
prefix eller ordning. Serverns interna heltal är inte kontraktet.
Datum är `YYYY-MM-DD`, tidsstämplar RFC3339 UTC med Z. `version` är positivt
heltal. Namn trimmas, krävs och får vara 1–120 tecken; task title 1–180,
notes/instructions/note högst 10 000. Okända skrivfält avvisas med 400;
klienter ska tåla nya läsfält. Frånvarande valfria skrivfält använder angiven
default; null accepteras bara där det uttryckligen anges.

Listor: `{"results": [], "next_cursor": null}`. `?limit=50&cursor=...`,
limit 1–100, opak cursor, stabil ordning created_at+id stigande. Filter ingår
i cursorns kontext; ogiltig cursor ger 400. Ingen sidbaserad implicit komplett
lista. Visa laddning, tomt, fel och nästa sida separat i M1.

## Autentisering: implementerad verifiering och beslutad leverantörsriktning

Beslut 2026-09-25: Auth0 i EU-region med OIDC Authorization Code och PKCE S256
i systemwebbläsaren. En faktisk tenant, issuer, client_id och verifierbara
Universal Links/App Links skapas först i ett separat aktiveringssteg. Leverantören hanterar
registrering, verifiering och återställning; appen samlar inte lösenord.
Mobilen verifierar state och nonce och lagrar roterande refresh-token i
plattformens säkra lagring, aldrig i loggar/vanlig appcache. Begär API-access-token
med rätt audience. Servern verifierar RS256-signatur/JWKS, issuer, audience,
exp, iat och konfigurerat scope och mappar unik `(issuer, subject)` till
Django User. Email används inte för kontolänkning. Bearer-stödet är avstängt
om issuer, audience eller JWKS saknas. Privat webb använder Django-session+CSRF.
P2 accepterar också en giltig Django-session på v1 för lokal/private-webb-
verifiering; mobilklienten använder Bearer och kan inte förlita sig på cookies.

Beslutad policy: access-token 10 minuter, roterande refresh-token med
återanvändningsdetektion, högst 30 dagars absolut livslängd och 14 dagars
inaktivitetsgräns. Under pilot kräver varje nytt subject explicit administrativ
länkning; automatisk provisionering är avstängd. Utloggning återkallar aktuell
refresh-token hos leverantören och tömmer säker lokal lagring. Vid kompromettering
återkallas leverantörens tokenfamilj/session och den lokala spärren sätts. Lokalt finns
`revoked_before` för omedelbar spärr av äldre access-token samt explicita
kommandon för identitetslänkning och spärr. Flödet måste provas mot den verkliga
tenantens logout-/revoke-endpoints före aktivering. Alla
anrop nedan kräver `Authorization: Bearer <access-token>`; servern kontrollerar
aktuellt medlemskap vid varje anrop. Efter 401 gör klienten högst ett
samordnat refresh-försök, sedan ny inloggning. Utloggning återkallar sessionen
och rensar aktiv minnescache. Ett lokalt webbutkast får bara återställas för
exakt samma konto+trädgård; ett annat konto får aldrig se det. Återställd
historik läses alltid från servern.

## Behörighetsmatris

| Åtgärd | Inloggad utan medlemskap | member | owner |
| --- | --- | --- | --- |
| Läsa eget /me, lista egna trädgårdar, skapa trädgård | Ja | Ja | Ja |
| Läsa vald trädgård, växter, uppgifter och historik | Nej | Ja | Ja |
| Skapa växt/manuell uppgift, slutföra uppgift | Nej | Ja | Ja |
| Hantera medlemmar, radera trädgård | Inget stöd i första flödet | Inget stöd | Inget stöd |

Främmande/okänt trädgårds-, växt- eller uppgifts-ID ger samma 404.
Relations-ID från annan trädgård ger också 404, utan objektdetaljer.
Oinloggad får 401. Ägarrollen ger inte global åtkomst. Servern tar garden
från behörig URL-kontext, aldrig från ett extra payloadfält.

## Konkret flöde och exempeldata

1. Skapa konto/logga in hos identitetsleverantören (se förslaget ovan).
   `GET /me/` → 200:
   `{"id":"u_01","display_name":"Kim"}`.
   display_name är sträng, kan vara tom; inga medlemskap eller email krävs i svaret.
2. `POST /gardens/` med `{"name":"Min trädgård"}` → 201:
   `{"id":"g_01","name":"Min trädgård","role":"owner","version":1,"created_at":"2026-09-25T10:00:00Z"}`.
   Garden och skaparens owner-medlemskap skapas atomärt. `GET /gardens/`
   returnerar listformatet med exakt samma objekt för aktuella medlemskap.
   `GET /gardens/g_01/` → 200 med samma objekt. role är alltid anroparens roll.
3. `POST /gardens/g_01/plants/` med
   `{"name":"Äppelträd","notes":"Vid uteplatsen"}` → 201:
   `{"id":"p_01","garden_id":"g_01","name":"Äppelträd","notes":"Vid uteplatsen","has_care_plan":false,"version":1,"created_at":"2026-09-25T10:01:00Z"}`.
   notes är valfri, default `""`. Inget AI-jobb startas. `GET /gardens/g_01/plants/`
   och `GET /gardens/g_01/plants/p_01/` ger listformat respektive samma objekt.
   has_care_plan anger aktiv skötselplan; manuell uppgift sätter inte flaggan.
4. `POST /gardens/g_01/tasks/` med
   `{"plant_id":"p_01","title":"Vattna","instructions":"Kontrollera jorden först","due_date":"2026-09-26"}` → 201:

```json
{"id":"t_01","garden_id":"g_01","plant_id":"p_01","title":"Vattna","instructions":"Kontrollera jorden först","due_date":"2026-09-26","status":"pending","manual":true,"note":"","completed_at":null,"version":1,"created_at":"2026-09-25T10:02:00Z","updated_at":"2026-09-25T10:02:00Z"}
```

plant_id, title och due_date krävs; instructions valfri/default tom.
Tidigare datum är tillåtna. Första flödet skapar en engångsuppgift för datumet,
utan att skapa plan eller skötselregel. manual är serverstyrt.
`GET /gardens/g_01/tasks/?status=pending&plant_id=p_01` ger listformat med
samma objekt; båda filter valfria, frånvaro inkluderar alla. Statusvärden:
pending, completed, skipped, archived (de sista två är läsbara för äldre
historik men har ingen mutation i första flödet). Historiska titlar, datum
och anteckningar ska visas även när växten inte längre är aktiv.
`GET /gardens/g_01/tasks/t_01/` ger samma objekt som detalj.

5. `POST /gardens/g_01/tasks/t_01/complete/` med
   `{"expected_version":1,"note":"Jorden var torr"}` → 200:

```json
{"id":"t_01","garden_id":"g_01","plant_id":"p_01","title":"Vattna","instructions":"Kontrollera jorden först","due_date":"2026-09-26","status":"completed","manual":true,"note":"Jorden var torr","completed_at":"2026-09-26T08:00:00Z","version":2,"created_at":"2026-09-25T10:02:00Z","updated_at":"2026-09-26T08:00:00Z"}
```

expected_version krävs. note valfri; utelämnad bevarar befintlig anteckning.
Servern sätter completed_at; lokal klocka får inte skriva historik.
6. Logga ut/in. `GET /gardens/g_01/tasks/?status=completed` ger listformat
   med exakt den bevarade posten från steg 5. Ingen lokal klarmarkering ska
   behövas för att återskapa historiken.

## Fel, konflikter och återförsök

Alla API-fel använder samma struktur; message är svensk visningstext,
code är stabil för klientlogik, fields är ett objekt med listor av felkoder:

```json
{"error":{"code":"validation_error","message":"Kontrollera uppgifterna.","fields":{"name":["required"]},"request_id":"req_01"}}
```

| HTTP | code | Hantering |
| --- | --- | --- |
| 400 | validation_error / invalid_cursor / invalid_json | Behåll utkast, visa fältfel (required, invalid, too_long, unknown). |
| 401 | unauthenticated | Refresh högst en gång, sedan login. |
| 403 | forbidden | Visas endast när resursen redan är synlig men åtgärden saknar behörighet. |
| 404 | not_found | Ingen information om främmande objekt; uppdatera medlemskap/lista. |
| 409 | version_conflict / invalid_transition | Hämta senaste uppgift; skriv inte över nyare data. |
| 409 | idempotency_conflict | Samma nyckel har använts för annan payload. |
| 429 | rate_limited | Följ Retry-After (sekunder). |
| 503 | temporarily_unavailable | Behåll utkast och erbjud återförsök. |

Alla POST kräver `Idempotency-Key` (slumpad UUID per avsikt). Saknad/ogiltig
nyckel ger 400 validation_error. Servern lagrar atomärt normaliserad request,
status och svar minst 7 dagar per konto+metod+kanonisk URL+nyckel. Samtidiga
identiska anrop får samma resultat, aldrig två trädgårdar eller uppgifter.
Aktuell behörighet kontrolleras **före** replay, även efter återkallat medlemskap.
Samma nyckel med annan body ger 409. Endast lyckade mutationer sparas som
replay; 5xx får inte lämna halvskrivna data eller kvitton.

För de idempotenta manuella v1-mutationerna återanvänder klienten samma
nyckel/body efter timeout, 429 och 503, med
exponentiell väntan och jitter, högst tre automatiska försök. Efter 7 dagar
utan säkert svar krävs avstämning mot servern före ny nyckel. Full offlinekö
är inte implementerad eller beslutad här. expected_version kontrolleras
atomärt med mutation; lyckad replay kontrolleras före versionskonflikt.
Klarmarkering med ny nyckel mot redan completed ger invalid_transition,
inte en andra historikhändelse. Vid 409 visar klienten färsk status och
bevarar lokal anteckning tills användaren väljer nästa handling.

## Kvar före mobilaktivering

Skapa Auth0 EU-tenant och native client, konfigurera verifierbara callback-URL:er
och prova den beslutade token-, logout-, revoke- och komprometteringspolicyn.
Versioner, idempotenslagring, opaka ID:n och behörighetskontroller är
implementerade i P2. Automatisk gallring av äldre kvitton återstår som en
driftuppgift; de tas inte bort före kontraktets sjudagarsgräns. M1 ska även ha
fixtures för tom trädgård, saknad plan, 401/404/409,
avbrutet anrop, paginering och konto med två trädgårdar. Kontraktprov mot P2
krävs före integration; exempeldata är inte bevis på fungerande server.


## P3 local queue addition

P3 does not add native v1 research/push endpoints. The private web's existing
`POST /api/items/{integer}/research/` gains an opt-in queue contract when
`TRADGARDSRYTMEN_DURABLE_JOBS=1`: `Idempotency-Key` is required, 202 returns
`job: {id, state, reason, proposal_id}`, and GET `/api/jobs/{uuid}/` reads the
requesting member's job in the selected garden. Invalid/missing keys or active
job conflicts return 409. A replay returns the original job. Membership must
still match the original membership row; deleting/recreating it does not grant
access to old jobs. No read triggers an analysis. With the flag disabled the
existing synchronous web contract is preserved. Native v1 AI/push is a later
integration and must not infer that these session routes accept Bearer tokens.
See [P3](p3-durable-jobs.md) for the state and external uncertainty contract.


## Privat webb: sidans konto- och trädgårdskontext

Äldre `/api/` (inte `/api/v1/`) kräver `X-Garden-Context` på både läsningar
och skrivningar. HTML-sidan utfärdar ett signerat token för det visade kontots
publika ID, trädgårdens publika ID och den exakta medlemskapsraden. Klienten
fryser detta token vid sidladdning; det hämtas aldrig om från aktuell session
för att skicka ett befintligt utkast. Sessionsautentisering och CSRF krävs
fortfarande. Token är en kontextbindning, inte en ersättning för behörighet.

Saknat/ändrat token, bytt konto/trädgårdsval eller återkallat/återskapat
medlemskap ger HTTP 409 med `code: "context_changed"` och ett svenskt `error`.
Ingen äldre API-vy körs då. Endast en ny sidladdning får välja den enda
kvarvarande trädgården automatiskt; gamla API-anrop får aldrig fallback.
Utloggat/inaktivt konto ger 401. API-svaren lagras inte i HTTP-cache.

Klienten behåller formuläret, dess utkast och sidans ursprungliga kontext vid
401/409 utan automatisk navigering eller omsändning. Användaren kan öppna
rätt konto/trädgård i en annan flik och försöka igen. Återskapat medlemskap
kräver en ny sida. Befintlig lokal utkastlagring förblir avgränsad per konto
och trädgård; ett annat konto eller en annan trädgård tar inte över utkastet.

Dessa regler för automatiska återförsök av manuella v1-mutationer gäller inte
synkron webb-AI eller push. Synkron AI gör ett transportanrop per avsikt och
kräver manuell avstämning vid oklart utfall; samma klientnyckel ger inte någon
beständig deduplicering där. I köläge återger samma nyckel jobbet och ett
uncertain-jobb blockerar nya AI-avsikter för växten tills operatörsavstämning.
Ingen leverantörsidempotens är verifierad.
