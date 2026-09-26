# Slutlig rättning av tre transportfynd

2026-09-26. Lokal leverans i `tradgardsrytmen-p123-review-fixes/jobs-integration`,
fortfarande detached på `6606e76c8f30d42ff364c0ebfecfd10c13c5d31d`.
Startinventeringen var 139 filer: 36 modifierade spårade och 17 ospårade.
Hela ursprungliga P3 och de tidigare integrerade rättningarna bevaras.
Den här rapporten ersätter tidigare påståenden om transportgränsens fullständighet.

## Fynd 1: behörighet och fryst AI-underlag

- Den synkrona webbvägen skickar konto och sidans exakta medlemskaps-ID till
  analysfunktionen. Ett anrop utan identitet avvisas före transport.
- Gemensam kontroll verifierar aktivt konto, exakt medlemskap, trädgård,
  aktiv växt och samma fingeravtryck av växt, profil och skötselkontext.
  Kontrollen sker efter lokal request-förberedelse och atomärt med resultatcommit.
  Återskapat medlemskap återupplivar inte den ursprungliga avsikten.
- Kövägens sista kontroll läser om hela jobbet under trädgårdslåset, kontrollerar
  behörighet/underlag och kontrollerar token/status/lease igen efter låsväntan.
- Låsordningen är trädgård → jobb (köväg) → konto → profil → medlemskap → växt.
  Domänskrivningar använder det tidigare gemensamma trädgårdslåset.
  Konto-/medlemskapslåsen hålls genom commit. Inga av dessa transaktioner
  omfattar nätverksanropet. Sparad `research_context` är exakt den frysta kontexten.
- `research_starters` och `replace_pending_research` anger uttryckligen sin
  valda operatörsträdgård. Webbvägen har ingen klientstyrd operatörsparameter.
  Köflaggan kan fortfarande inte kringgås av ett synkront operatörsanrop.

Negativa prov ändrar medlemskap, återskapar det, inaktiverar konto/växt,
byter växtens trädgård eller ändrar växt, profil och historik efter `Request`-
förberedelsen respektive under mockad transport. Profil och klarmarkering
ändras via verkliga endpoints. Före transport blir antalet `urlopen` noll;
under transport kastas resultatet och inget förslag sparas. Positiva prov
bekräftar ett enda anrop och exakt kontext. Separata anslutningar visar att
konto-/medlemskapsändringar väntar på synkron resultatcommit.

## Fynd 2: aktuell påminnelse och sann leveranshistorik

`reminder_is_authorized` används av direkt och köad påminnelse. Efter VAPID-
och payloadförberedelse kontrolleras färsk uppgift (pending), aktiv växt,
trädgård, 24 timmars giltighet, leveransens identitet, exakt medlemskap,
aktivt konto, prenumeration, mottagare, adress, båda nycklarna och preferens.
En klarmarkering under förberedelsen ger noll `webpush`.

Efter framgångsrik transport sparas `sent` och `sent_at`, även om uppgiften
slutfördes eller behörigheten ändrades under nätverket. Avslutningen skriver
endast historikens utfallsfält och återställer inte nyare domänfält. Redan
bekräftad sändning kan inte skrivas om som osänd av `_finish` eller recovery.

En sen bekräftelse efter recovery är ett särskilt fall: jobbet och det
avslutade försöket förblir `uncertain`, medan leveransraden får `sent`/`sent_at`
som tillkommande transportbevis. Detta låser inte upp jobbet eller orsakar
omsändning; operatörsavstämning krävs fortfarande. Ett bekräftat Web Push-
anrop betyder leverantörens acceptans, inte verifierad visning på telefonen.

Regressioner täcker ovanstående fält i båda flödena, före och under nätverk,
samt deduplicering, oförändrat antal försök och sena bekräftelser. Data som
redan överlämnats till transporten kan inte återtas; AI-resultat publiceras
inte när resultatkontrollen upptäcker återkallad behörighet eller ändrat underlag.

## Fynd 3: tydliga transportutfall

Gemensamma felkategorier i `garden/transport_outcomes.py` skiljer:

| Fas/utfall | Köavslut | Automatisk ny transport |
| --- | --- | --- |
| Saknad nyckel, lokalt request-/VAPID-/payloadbygge eller fel i lokal slutkontroll | failed, säkert osänt | Nej |
| Återkallad behörighet eller ändrat underlag före transport | cancelled | Nej |
| Fullständigt mottagen ogiltig JSON, svarsenvelop, schema/domänresultat | failed | Nej |
| Bekräftad Web Push-avvisning (4xx) | failed | Nej |
| Timeout, avbrott eller ofullständig läsning efter transportstart | uncertain | Nej |
| Förlorad worker i sending | uncertain | Nej |

Säkert misslyckad eller ogiltig AI tillåter en **ny uttrycklig avsikt** med ny
nyckel; det gamla försöket består. Samma nyckel återger det gamla jobbet.
Ett verkligt `uncertain` blockerar fortsatt ny analys för växten. Sena fel,
ogiltiga svar och säkert osända lokala fel kan inte ändra ett redan återhämtat
`uncertain`. HTTP-fel från AI klassificeras fortsatt konservativt utan antagen
leverantörsidempotens. Direkt påminnelse lagrar också `uncertain` vid oklar
transport och återanvänder inte leveransnyckeln.

## Utförd verifiering

Alla externa transporter är mockade och data syntetiska. Miljön har tom
`OPENAI_API_KEY`; endast mockade konfigurationstester anger syntetisk nyckel.

- Hela Django-sviten: **254/254 på filbaserad SQLite och 254/254 på PostgreSQL
  17.11**, utan skips. Av dessa är 102 nya transportgränsregressioner.
- Tidigare regressionssviter ingår, inklusive trädgårdslås, exakt fryst
  kontext, sidtoken/utkast, token/lease/recovery och saknad AI-nyckel.
- JavaScript: **15/15**. Django check, migrationskontroll, Python-kompilering,
  JavaScript-/shellsyntax och diffkontroll godkända. Inga nya schemaändringar.
- Syntetisk SQLite → PostgreSQL → återläst backup: **32 rader** fältidentiska,
  källhash oförändrad och sekvenser provade.
- Befintliga testvarningar gäller saknad collectstatic-katalog och uttrycklig
  databasoverride i backup-proven; inga fel eller överhoppade prov.

Loggar: `/tmp/p3-fixes-sqlite.log`, `/tmp/p3-fixes-postgres.log`,
`/tmp/p3-fixes-js.log`, `/tmp/p3-fixes-transition.log`,
`/tmp/p3-fixes-final-targeted.log`, `/tmp/p3-fixes-checks.log`.
PostgreSQL kördes endast via lokal socket. Endast egna namngivna syntetiska
testdatabaser skapades/rensades; testklustret stoppades efter verifieringen.

## Exakt ändrade filer i denna rättningsomgång

Jämför med startinventeringen, inte med HEAD som saknar hela P3:

- `garden/jobs.py`
- `garden/research.py`
- `garden/push.py`
- `garden/transport_outcomes.py` (ny)
- `garden/views.py`
- `garden/management/commands/research_starters.py`
- `garden/management/commands/replace_pending_research.py`
- `garden/test_transport_boundaries.py` (ny)
- `garden/test_legacy_transports.py` (explicit testklocka för giltighetstid)
- `garden/test_review_integration.py` (exakt beställaridentitet i synkront prov)
- `docs/p3-durable-jobs.md`
- `docs/review-fixes-integration.md`
- `docs/transport-boundary-review-fixes.md` (denna rapport)

## Integritet och releasegränser

Start-/slutmanifest: `/tmp/p3-fixes-before.json` och `/tmp/p3-fixes-after.json`.
Skyddade kopior har samma filinventering och SHA-256 före/efter: main 122,
ursprunglig P3 132, baseline 132, web-context 134 och legacy-transports 134 filer.
Förälderns HANDOFF, baseline-manifest och granskningsreproduktion samt samtliga
referensfiler i `/tmp/independent-p3-review` är också hashidentiska.
Integrationskopians startmanifest är `/tmp/p3-integration-start.json` och
slutmanifest `/tmp/p3-integration-end.json`; en separat deltafil visar endast
ovanstående ändringar. Ingen skyddad kopia har använts som testarbetskatalog.

Detta är lokal kvalitetssäkring. Ingen commit/push, release, produktion,
verklig AI/push, extern trädgårdsdataöverföring eller kö-/OIDC-aktivering ingår.
SQLite är standard, DURABLE_JOBS av och OIDC fail-closed.

En eventuell privat SQLite-release med flaggan av kräver ett separat
releasebeslut och driftverifiering. Produktionsdatabasen är inte läst och
verklig produktionsåterläsning är inte verifierad. PostgreSQL-cutover och
köaktivering kräver egna drift-/backup-/larm-/operatörsbeslut; det avsiktliga
PostgreSQL-stoppet i autodeploy kvarstår. Publik drift kräver dessutom Auth0,
budget/frekvensgräns och ett operatörsflöde för verkligt uncertain. Native v1
AI/push, browser/telefon och GitHub CI är inte verifierade här.

Databas och leverantör har ingen gemensam atomär commit. Den korta luckan
mellan avslutad slutkontroll och transport kan inte elimineras utan att hålla
nätverk under databaslås; ett processavbrott där förblir konservativt uncertain.
Synkron AI gör ingen dold omsändning men har fortfarande ingen beständig spärr
mot en senare ny uttrycklig avsikt efter ett oklart utfall. Belastningsprestanda
för trädgårdslåset och verklig leverantörsidempotens är inte verifierade.
