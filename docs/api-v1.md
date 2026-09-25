# API v1: kontrakt för mobilens första flöde

Status 2026-09-25: **hela HTTP-kontraktet nedan är ett förslag för P2 och
exempeldata för M1; inga /api/v1/-endpoints är implementerade i P1.**
Implementerat: User, Garden och GardenMembership i ORM. Nuvarande `/api/`
är privat, globalt och inte kompatibelt med eller säkrat av detta kontrakt.
M1 kan låsa exempeldata mot detta dokument; ändringar ska samordnas med P2.

## Gemensamma regler

Bas `/api/v1/`, HTTPS, JSON UTF-8, `Content-Type: application/json`.
Opaka ID:n är strängar (exempel `g_01`, `p_01`, `t_01`); klienten får inte
anta prefix, ordning eller UUID. Serverns interna heltal är inte kontraktet.
Datum är `YYYY-MM-DD`, tidsstämplar RFC3339 UTC med Z. `version` är positivt
heltal. Namn trimmas, krävs och får vara 1–120 tecken; task title 1–180,
notes/instructions/note högst 10 000. Okända skrivfält avvisas med 400;
klienter ska tåla nya läsfält. Frånvarande valfria skrivfält använder angiven
default; null accepteras bara där det uttryckligen anges.

Listor: `{"results": [], "next_cursor": null}`. `?limit=50&cursor=...`,
limit 1–100, opak cursor, stabil ordning created_at+id stigande. Filter ingår
i cursorns kontext; ogiltig cursor ger 400. Ingen sidbaserad implicit komplett
lista. Visa laddning, tomt, fel och nästa sida separat i M1.

## Föreslagen autentisering (beslut krävs före P2)

OIDC Authorization Code med PKCE S256 i systemwebbläsaren. Leverantör, issuer,
client_id och redirect URI är ännu inte valda. Leverantören hanterar
registrering, verifiering och återställning; appen samlar inte lösenord.
Mobilen verifierar state och nonce och lagrar roterande refresh-token i
plattformens säkra lagring, aldrig i loggar/vanlig appcache. Begär API-access-token
med rätt audience. Servern verifierar signatur/JWKS, issuer, audience, exp
och scope och mappar unik `(issuer, subject)` till Django User i P2. Denna
mappning finns **inte** i P1. Email får inte användas för automatisk kontolänkning.

Arbetsförslag: access-token 10 minuter, refresh-session högst 30 dagar,
återkallning och rotation vid utloggning/kompromettering. Exakta leverantörs-
och återkallningsmekanismer måste verifieras innan implementation. Alla
anrop nedan kräver `Authorization: Bearer <access-token>`; servern kontrollerar
aktuellt medlemskap vid varje anrop. Efter 401 gör klienten högst ett
samordnat refresh-försök, sedan ny inloggning. Utloggning återkallar sessionen
och rensar kontots cache/utkast. Återställd historik läses alltid från servern.

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

Klienten återanvänder samma nyckel/body efter timeout, 429 och 503, med
exponentiell väntan och jitter, högst tre automatiska försök. Efter 7 dagar
utan säkert svar krävs avstämning mot servern före ny nyckel. Full offlinekö
är inte implementerad eller beslutad här. expected_version kontrolleras
atomärt med mutation; lyckad replay kontrolleras före versionskonflikt.
Klarmarkering med ny nyckel mot redan completed ger invalid_transition,
inte en andra historikhändelse. Vid 409 visar klienten färsk status och
bevarar lokal anteckning tills användaren väljer nästa handling.

## Kvar inför serverimplementation

Besluta OIDC-leverantör och kontolänkning/återkallning, implementera versions-
och idempotenslagring samt alla behörighetskontroller. P1-modellerna saknar
ännu API-id, version och domänägarskap. API-modellen är avsiktligt skild från
ORM. M1 ska även ha fixtures för tom trädgård, saknad plan, 401/404/409,
avbrutet anrop, paginering och konto med två trädgårdar. Kontraktprov mot P2
krävs före integration; exempeldata är inte bevis på fungerande server.
