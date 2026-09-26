# P3: lokal leverans och gräns för release

Senare aktiveringsarbete: [privat P3-release och driftaktivering](p3-activation.md).
Den daterade granskningen nedan är underlaget före aktiveringsbeställningen.

## Aktuell releaseuppdelning 2026-09-26

Hela integrationen är lokalt verifierad men inte driftsatt. **JA MED VILLKOR**
för fortsatt privat SQLite med kö/OIDC av; se [releasegrindarna](private-release-review.md).
Migration 0013, synkrona transporträttningar och webbens kontextbindning ingår
även när kön är av. PostgreSQL-cutover och köaktivering är separata steg.
Operatörsflödet för verkligt uncertain blockerar köaktivering, medan Auth0,
publik budget och native inte blockerar den avgränsade privata releasen.
Senaste verifiering är 254/254 per databas och 15/15 JS, inte de äldre
122/152-resultaten. Nytt riktat SQLite-prov av 0012 → 0013 och återläsning
beskrivs i releaseunderlaget. Ingen produktionsverifiering följer av detta.


Datum: 2026-09-26. Bas `6606e76c8f30d42ff364c0ebfecfd10c13c5d31d`.
Arbetskopia `/Users/joakimohman/Code/tradgardsrytmen-p3`, gren
`task/p3-durable-jobs`. Ingen commit, push, produktionsmigrering eller deployment
är godkänd i denna uppgift. Ingen riktig AI eller push används i verifieringen.

## Avgränsning och acceptanskriterier

P3 levererar ett backendval för PostgreSQL, additiva jobbrader/försök, worker,
privat webbens uttryckliga AI-köning, beständiga Web Push-påminnelser och
lokala överförings-/återställningsprov. SQLite fortsätter vara standard.
`TRADGARDSRYTMEN_DURABLE_JOBS=0` är standard; köläget är opt-in.
Mobilpush, publik AI-budget, Auth0-aktivering och produktionsbyte ingår inte.

| Kriterium | Bevis som krävs |
| --- | --- |
| Explicit databasval, aldrig tyst fallback | Konfigurationstest; hela sviten på SQLite och PostgreSQL |
| Inga äldre rader/historik tappas | Migrationsprov samt fältjämförelse SQLite → PostgreSQL → återläst backup |
| En logisk begäran ger ett jobb | Samma nyckel i samtidiga anrop; konflikt vid annat objekt |
| En växt får högst ett aktivt/oklart AI-jobb | Villkorad databasunikhet; samtidiga olika nycklar |
| Arbetare konkurrerar säkert | Fyra separata anslutningar; en claim och en försöksrad |
| Omstart före sändning kan återhämtas | Lease, backoff, maximalt tre försök; äldre försök bevaras |
| Okänd extern effekt sänds aldrig automatiskt igen | Timeout, processförlust och sent svar; fenced commit |
| Konton och trädgårdar avgränsas även vid körning | Främmande objekt, återkallat/återskapat medlemskap, ändrat underlag |
| Endast godkänt underlag skickas | Fryst indata till transport; ingen omläsning av privata ändringar |
| Påminnelser skapas atomärt och dedupliceras | Samtidiga timers, rollback, återkallad mottagare, äldre leveranshistorik |
| Backup använder rätt databas | Läsande SQLite-backup; pg_dump/pg_restore; fel publicerar ingen färdig backup |

## Jobbkontrakt

Jobb och försök finns i samma databas som domändata. Ingen Redis/Celery-tjänst
behövs för detta paket. `BackgroundJob` binder trädgård, beställare och exakt
medlemskaps-ID; borttaget och återskapat medlemskap återupplivar inte ett jobb.

Webbens befintliga POST för AI kräver i köläge `Idempotency-Key` (1–240 tecken)
och svarar 202 med `job.id`, `state`, `reason`, `proposal_id`. Samma nyckel och
objekt återger ursprungsjobbet även om underlaget senare ändrats. Ny analys
kräver en ny uttrycklig begäran. Ett annat objekt med samma nyckel avvisas.
GET `/api/jobs/{uuid}/` och växtdetalj visar endast beställarens aktuella
medlemskaps jobb i vald trädgård. GET startar aldrig arbete. Webb visar köad,
pågående, avbruten, misslyckad eller oklar analys; användaren öppnar växten
igen för aktuell status. Automatisk polling införs inte i detta paket.

`queued → running → sending → succeeded` är normalvägen. En atomär villkorad
UPDATE väljer en vinnare; claim och försöksrad committas tillsammans. En UUID
ger försöket körbehörighet. Alla senare skrivningar kräver rätt token och
status, och resultat kräver en fortfarande giltig femminuterslease.

En förlorad `running` återköas med 30/60 sekunders väntan, högst tre försök.
En förlorad `sending`, oklart transportavbrott eller obekräftat utskick blir
`uncertain`. Säkert osända lokala fel och fullständigt mottagna ogiltiga svar
ger i stället `failed`; se transportklassificeringen i slutrapporten. Det kan betyda att leverantören tog emot anropet. Inga automatiska
externa återförsök görs i detta läge, inte ens med en ny AI-nyckel för samma
växt. Leverantören erbjuder inget här verifierat exactly-once-kontrakt.
Det finns därför avsiktligt inget generellt retry-kommando för oklara jobb.
Operatörens avstämnings-/upplåsningsflöde måste beslutas och implementeras
före aktivering i drift; historik får inte raderas för att kringgå spärren.

Extern I/O ligger utanför databastransaktioner. AI-indata fryses och jämförs
med den ursprungliga begärans fingeravtryck före sändning. Datumbyte, ändrad
växt/platsprofil/skötselhistorik eller återkallad behörighet avbryter jobbet.
Efter anropet kontrolleras behörighet och underlag igen. Förslaget och jobbets
slutstatus sparas atomärt; gammal worker får inte publicera ett sent svar.
Återkallning efter att nätverksanropet börjat kan inte ta tillbaka skickad data.
Ett sent eller osäkert svar sparas inte automatiskt som ett nytt förslag.

Ett externt svar som inte kan valideras ger `failed`, utan ny modellkörning.
Försökshistorik innehåller stabila felkoder, inte råa transportfel, nycklar,
pushadresser eller privata anteckningar. Befintliga synkrona AI-kommandon
stoppar före nätverksanrop när köläget är aktiverat.

Påminnelsetimern lägger leverans och jobb i samma transaktion, efter trädgårdens
tidszon. Nycklarna för månad/vecka behålls så att äldre leveranser inte upprepas.
Gammal pending/failed/sent-historik återköas inte. Medlemskap, mottagare,
prenumerationsnycklar, inställning och uppgiftens status kontrolleras före
sändning. Påminnelser äldre än 24 timmar avbryts. Ett återförsök skapar inte
en ny leveransrad. Testnotiser är fortsatt användarinitierade direkttester.

Worker kör en begränsad batch för ett uttryckligt garden-UUID:

```sh
python manage.py run_jobs --garden UUID --recover-only
# Aktiverar externa effekter och kräver separat godkänd driftkonfiguration:
python manage.py run_jobs --garden UUID --limit 10 --allow-external
```

Båda kräver att köläget redan aktiverats i miljön. Ingen ny worker eller timer
installeras/startas av denna lokala leverans. En driftworker ska regelbundet
köra både recovery och claim och larma för gamla queued-jobb samt failed/uncertain.

## PostgreSQL, backup och övergång

`TRADGARDSRYTMEN_DB_ENGINE=postgresql` kräver PGDATABASE, PGUSER och PGHOST.
PGPASSWORD och PGPORT kan anges. TLS-standard är `verify-full`; lokal testmiljö
använder uttryckligen `disable` och separat socket. Felaktig backend eller
ofullständig konfiguration stoppar appen. Psycopg är versionslåst.

`backup_database` och cleanup använder en gemensam backendmedveten funktion.
SQLite öppnas med mode=ro. PostgreSQL använder custom-format pg_dump, och
pg_restore läser katalogen innan filen publiceras. Återläsningsprovet krävs
separat: katalogläsning ensam bevisar inte återställbarhet. Filer skapas 0600
som `.partial` och får slutnamn först vid lyckat resultat. Matchande PostgreSQL-
klientverktyg måste finnas i tjänstens PATH. Backupretention är 14 dagar.

Den befintliga automatiska deployen stoppas uttryckligen för PostgreSQL före
kodkopiering/migrering. Dess ursprungliga SQLite-flöde är inte ett validerat
PostgreSQL-releaseflöde. Det behöver anpassas och provas separat efter beslut
om driftplats, autentisering, backup och underhållsfönster.

Övergångsordning inför en separat godkänd release:

1. Verifiera faktisk produktionsrevision, konfiguration, schema, ägare,
   antal/fältfingeravtryck och kvarvarande otilldelade rader läsande.
2. Repetera övergång på en skyddad återläst kopia, inklusive alla konton,
   relationer, källor, uppgiftshistorik, idempotenskvitton och jobb/försök.
3. Besluta PostgreSQL-tjänst/version, TLS, minst privilegier, backup/PITR,
   larm, workerintervall och hantering av osäkra externa effekter.
4. Stoppa skrivare, timers och workers under det godkända fönstret. Ta och
   återläs slutbackup. Behåll ursprunglig SQLite orörd. Migrera endast en kopia
   till aktuellt schema inför export om det behövs.
5. Skapa tomt PostgreSQL-schema med migrate, importera med bevarade PK/UUID
   och naturliga auth-referenser, jämför varje fält och kontrollera sekvenser.
   Återläs även PostgreSQL-backup till separat instans innan växling godkänns.
6. Växla en datakälla åt gången. Bekräfta webbsessioner/API, ägarskap, historik
   och manuell funktion innan workers aktiveras. Kör ingen riktig AI som smoke-test.
7. Återgång till gammal SQLite är bara möjlig utan dataförlust före nya
   skrivningar. Efter nya PostgreSQL-skrivningar krävs avstämning/återföring,
   inte bara byte av miljövariabel. Ingen dual-write införs.

## Verifiering och kvarvarande releasegräns

Kommandon körs i P3-arbetskopian med separat runtime i
`/tmp/tradgardsrytmen-p3-runtime`. Verifieringsresultat finns i roadmapens
P3-avsnitt. `scripts/verify_postgres_transition.py` vägrar externa PGHOST,
använder syntetiska data och skapar två unikt namngivna lokala databaser som
rensas efteråt. Den använder aldrig PGDATABASE som importmål.

```sh
P3_SQLITE_TEST_PATH=/tmp/p3-test.sqlite3 python manage.py test --settings=config.p3_sqlite_test_settings --noinput
# Med explicit lokal PostgreSQL-miljö:
python manage.py test --noinput
python scripts/verify_postgres_transition.py
node --test tests/*.test.cjs
```

Inte verifierat: produktionens skyddade databas i denna task, återläsning av
verklig produktionskopia, verklig OpenAI/Web Push, mobil/native integration,
fysisk telefon eller browserinteraktion. Ingen sådan kontroll får beskrivas
som godkänd bara för att lokala tester passerar. Köflaggan förblir avstängd
fram till separat granskning och releasebeslut. Budget/frekvensbegränsning
krävs dessutom före publik AI; detta paket aktiverar inte publik drift.

Teknisk referens: [Django transaktionella radlås](https://docs.djangoproject.com/en/5.2/ref/models/querysets/#select-for-update).

## Integrerad granskningsrättning 2026-09-26

Alla sju fynd från den oberoende P1/P2/P3-granskningen är rättade lokalt i
`tradgardsrytmen-p123-review-fixes/jobs-integration`. Samlad evidens, exakta
filer relativt granskad P3 och kvarvarande releasegränser finns i
[integrationsrapporten](review-fixes-integration.md).

Domänskrivningar tar trädgårdens transaktionella skrivlås före underordnade
rader. Det omfattar äldre webb, v1, profiler, materialisering, godkännande,
bortval och historikstädning. Jobbets ordning är trädgård → jobb → konto/profil/
medlemskap → växt → arbetsidentitet → tillfälle. Claim/recovery och ren
felavslutning låser bara jobbraden och går inte vidare till trädgårdslås.
Framtida skrivvägar och administrativa verktyg måste följa samma kontrakt;
godtycklig direkt SQL är inte en stödd samtidig domänskrivväg.

Sista kontextkontroll och resultatlagring sker under samma lås. Sparad
`research_context` är exakt den frysta kontext som skickats, inte en omläsning
vid lagring. Även den synkrona kompatibilitetsvägen släpper transaktionen före
nätverk och kontrollerar underlaget igen före lagring.

Övergång till `sending` kräver fortfarande rätt token/status och giltig lease
efter förberedelsen. Transporten kontrollerar samma villkor direkt före
`urlopen`/`webpush`, efter eventuell egen request-/nyckelförberedelse. Saknad
AI-nyckel avslutas som `failed` före `sending`; explicit säkert osända fel
avslutas utan att tolka timeout som säkert osänd. Recovery till `uncertain`
får aldrig hävas av en sen worker. Databas och leverantör kan inte göra en
atomär gemensam commit: processen kan fortfarande dö mellan sista lokala
kontroll och extern effekt. Därför kvarstår `uncertain` och operatörsgränsen.


## Kompletterande transporträttning efter oberoende omgranskning

Den tidigare integrationskontrollen missade återkallning under request-/VAPID-
förberedelse, ändrad uppgift före push och felaktig uncertain-klassificering.
Dessa tre fynd är rättade i samma integrationskopia. Synkron webb-AI binder nu
exakt beställaridentitet; båda AI-vägarna verifierar behörighet och fryst underlag
efter förberedelsen och atomärt med resultatcommit. Direkt/köad push kontrollerar
hela aktuella påminnelsen efter förberedelsen. Bekräftad transport består som
sent/sent_at även om domänstatus ändras under nätverket. Vid sen bekräftelse
består ett redan återhämtat uncertain-jobb och dess försök, medan leveransraden
bevarar det nya transportbeviset utan omsändning.

Gemensamma transportfel skiljer säkert osänt, mottaget ogiltigt resultat och
oklar extern effekt. Ingen kategori orsakar automatiskt nytt modellanrop;
endast failed/cancelled tillåter en senare ny uttrycklig AI-avsikt. Detaljer,
254/254 tester på SQLite/PostgreSQL, integritet och oförändrade releasegränser:
[slutlig rättningsrapport](transport-boundary-review-fixes.md).
