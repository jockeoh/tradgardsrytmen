# Trädgårdsrytmen: genomförandeplan

Status 2026-09-26: **privat release, PostgreSQL-cutover och köaktivering är
slutförda**. Kodrelease `1ee8e9e`, schema 0014, PostgreSQL 17.11 och
DURABLE_JOBS=1; OIDC är fortsatt av. Grön CI, terminal deploystatus,
verklig backup/återläsning och autentiserad HTTP är verifierade.
Se [driftresultat och operatörsrutin](p3-activation.md).

M1 har en separat lokal rättningskopia med tre granskningsfynd åtgärdade, redo för ny granskning
(se [M1-överlämning](m1-handoff.md)). Användaren har därefter beställt commit/push till main. M1 är inte integrerad eller driftsatt.
Närmaste steg är M1-granskning och L1, därefter I1. Privat aktivering
betyder inte att native, fysisk telefon, riktig AI/push eller publik drift
har verifierats. Historiska leverans-/granskningsavsnitt längre ned bevaras.

## Prioriterad restlista och verifierad status

Ordningen är rekommenderad, inte ett nytt beslut att aktivera externa tjänster.
M1 och L1 kan göras parallellt med driftförberedelser; I1:s manuella flöde
behöver inte vänta på köaktivering eller betalningar.

| Prioritet/del | Nuvarande status | Kvar, nytta och beroenden |
| --- | --- | --- |
| Klart: privat release | Kodrelease 1ee8e9e driftsatt först på SQLite, schema 0014; CI och autentiserad HTTP gröna. | Verklig backup/återläsning, oförändrade domänrader, kontrollerat underhållsfönster och klientmarkörer verifierade. Fysisk telefon och verkliga externa prov återstår separat. |
| Klart: P3 PostgreSQL-cutover | PostgreSQL 17.11 aktivt på lokal socket med peer-auth. | 1 541 fältidentiska exporterade rader och återläst backup, sekvenser och oförändrad SQLite-källa verifierade. Dagliga lokala backuper aktiva; PITR/off-host och publik kapacitet återstår före bredare drift. |
| Klart: P3 köaktivering | DURABLE_JOBS=1, worker och kökontroll aktiva. | Operatörskvitto för bekräftade oklara utfall implementerat och testat; oförändrad försökshistorik och inga automatiska omsändningar. Systemd/journal ger felsignal; aktiv extern larmkanal och publika belastningsprov återstår. |
| 4. M1 | Lokal Expo SDK 57/TypeScript-klient med separat granskningsfix på `task/m1-review-fixes`; originalet bevarat; Git-publicering till main beställd. | Färska 38 tester, typkontroll, lint, doctor 21/21 och export för webb/iOS/Android godkända; mobil webbpreview och tre regressioner verifierade. [Rättningsrapport](m1-fix-review/README.md). Syntetiska konton, trädgårdar, manuellt flöde, utkast, paginering, sena svar och fel. Simulator/fysisk telefon samt riktig transport återstår. Redigering/ångring saknar v1-endpoints. [Underlag och körning](m1-handoff.md). |
| 4. L1 | Produktförslag finns; ingen färdig separat L1-leverans eller fastställd betal-/offlineomfattning verifierad. | Besluta målgrupp/marknad, betalande part, priser, AI-kvoter, delning, offlineomfattning och webbens framtid. Ger avgränsning för M2/B1/R1; leverantörsavtal och köp är separata externa beslut. |
| 5. I1 och identitetsaktivering | Manuellt v1-serverflöde lokalt testat. Native och riktig Auth0-integration inte verifierade. | Efter M1: Auth0 EU-tenant/native client, verifierbara länkar, PKCE, säker tokenlagring, refresh/logout/revoke och administrativ subject-länkning. Två konton genomför hela manuella flödet på iOS/Android med bestående historik efter omstart/inloggning. Redovisa simulator och fysisk enhet separat. Extern konfiguration kräver godkännande. |
| 6. Native AI | P3 ger bara privat webbkö, inga native v1 AI-endpoints. | Specificera/implementera v1 start/status/granskning/godkännande, uttryckligt datamedgivande och utfall/återförsök; koppla till driftklar P3 efter I1. Krävs om AI ingår i mobil v1; inga riktiga prov utan godkännande. |
| 6. M2 | Offline och native push inte verifierade som implementerade. | Efter I1 + L1: lokal arbetslista och beslutad synkkö, versionskonflikter, idempotens, kontoavskild lagring/rensning. Implementera native push med mottagare/tidszon/deduplicering och fysisk enhetsprovning. Full offline-redigering är inte beslutad v1. |
| 7. B1 | Köp/tillgång inte verifierade som implementerade. | Efter I1 + L1: välj köptransport, serververifierad tillgång, köp/återställning/förnyelse/uppsägning/återbetalning och deduplicerade händelser. Butikskonton, avtal, betalningar och publicering kräver separata beslut. Villkorligt: bara nödvändigt för betald lansering. |
| 8. R1 och publik drift | Inte lanseringsklar; lokala testresultat är inte produktionsbevis. | Verifiera kontoåterställning, support, integritetsinformation, export/radering, tillgänglighet och äldre klienter. Inför publik AI-budget/frekvensgränser/kostnadslarm. Verifiera backup/återläsning, driftlarm, belastning, butiksunderlag och båda plattformarna för beslutad v1. Extern pilot och butikslansering godkänns separat. |

Ytterligare kvarvarande server-/produktpunkter från kontrakten:

- Besluta och implementera transaktionell överföring av sista ägare samt
  konto-/trädgårdsradering med historik- och databevarande. Ingen sådan
  administrationsväg är exponerad nu; privat ägardrift behöver inte invänta den.
- Inventera alla äldre nullable garden-relationer och korsande relationer.
  Obligatorisk tillhörighet kräver separat migration efter verifierad backfill;
  dagens behörighetsfilter gör inte detta schemastöd färdigt.
- Besluta driftgallring av idempotenskvitton, aldrig före kontraktets sju dagar.
- Bevara den gamla enhetsgemensamma inköpslistan; eventuell import kräver
  uttryckligt ägarbeslut. Inbjudningar/familjedelning kan skjutas efter I1.
- Synkron AI saknar beständig spärr mot en senare ny uttrycklig analys efter
  oklart utfall. Privat drift kräver manuell avstämning före ny begäran;
  denna begränsning får inte ärvas obemärkt av publik/native AI.
- Följ upp beroendeuppdateringar via separata kompatibilitetskontroller.
  Byte till DRF är ett öppet teknikval, inte ett releasekrav.

Den tidigare M1/L1-kontrollen (före M1-implementationen nedan) omfattade projektets filer, lokala grenar/worktrees och den
relevanta uppgiften **Utvärdera apparkitektur**
(`01a0d93e-072e-75a1-b72c-edf8aff60a3c`), där P1 startades men M1/L1 beskrevs
som framtida spår. Ingen Expo-klient eller separat färdig L1-rapport hittades
här. Det bevisar inte att arbete saknas på annan plats; ingen av dem markeras klar.

## Arbetsordning och beroenden

| Del | Leverans | Beroende |
| --- | --- | --- |
| P1 | Konto-/trädgårdsgrund och konkret API-kontrakt | Dokumenten ovan |
| P2 | Dataägarskap, autentisering, behörigheter och kärn-API | P1 |
| M1 | Expo-app med första flödet mot exempeldata | P1:s stabila kontrakt |
| L1 | Förslag för betalmodell, offline och lansering | Kan utredas parallellt med P1 |
| I1 | Hela kärnflödet mot riktig server på iOS och Android | P2 + M1 |
| P3 | PostgreSQL och beständiga AI-/påminnelsejobb | P2, före publik belastning |
| M2 | Beslutad offlinefunktion och mobilpush | I1 + relevanta beslut från L1 |
| B1 | Köp och serververifierad tillgång | I1 + beslutad betalmodell |
| R1 | Lanseringsprov, datahantering, drift och butiksunderlag | Beslutad v1-omfattning färdig |

P2 och M1 kan utvecklas parallellt. API-ändringar måste först uppdatera det
gemensamma kontraktet. Varje spår använder en egen Git-arbetskopia och gren.
Ingen parallell agent ska ändra samma migrationskedja utan samordning.

## P1: första uppgiften att starta

Syfte: lägga en liten, testbar grund som låser upp parallellt server- och
mobilarbete. Detta är lokal implementation och underlag för granskning,
inte en aktivering av publik flerkundstjänst.

### Leverera

1. Läs nuläget och inventera hur alla befintliga modeller, endpoints och
   kommandon behöver avgränsas till en trädgård. Dokumentera inventeringen
   och övergångsordningen i `docs/multiuser-transition.md`.
2. Lägg till en egen användarmodell baserad på Djangos etablerade auth,
   `Garden` och `GardenMembership`. Ge medlemskapet unikhet per konto och
   trädgård samt explicit roll. Håll migreringarna additiva: ingen flytt,
   borttagning eller automatisk tilldelning av befintlig trädgårdsdata.
3. Aktivera endast den Django-konfiguration dessa modeller behöver.
   Inför inte publik registrering, nya användarsessioner eller nya
   trädgårdsendpoints i denna del. Befintlig privat webb ska fungera som förut.
4. Skriv `docs/api-v1.md` med konkreta exempel för kärnflödet, stabila fält,
   fel, behörighetsmatris, återförsök och ett uttryckligt förslag för mobil
   autentisering. Skilj kontraktets förslag från implementerade endpoints.
5. Testa modeller, begränsningar och migrering från tidigare schema med
   representativa äldre växter, uppgifter och historik i isolerad databas.
   Kontrollera att inga befintliga rader har tappats eller tilldelats ett konto.
6. Uppdatera denna plan med faktiskt resultat, tester och kvarvarande frågor.

### Klart när

- Ett konto kan ha medlemskap i flera trädgårdar och en trädgård flera medlemmar.
- Dubbla medlemskap och ogiltiga roller avvisas på dokumenterad nivå.
- Nyinstallation och uppgradering från tidigare schema är testade.
- Befintliga regressionstester passerar och privat webbflöde är bevarat.
- API-kontraktet räcker för att bygga M1 med exempeldata.
- Det framgår tydligt att globalt äldre API fortfarande saknar kundisolering.

### Gränser för denna uppgift

Arbeta i separat arbetskopia från dokumentationscommitten. Använd isolerade
lokala testdatabaser. Ingen produktionsdata, deployment, commit/push av
implementationen, externa AI-anrop, betalningar eller meddelandeutskick ingår.
Rapportera diff, verifiering och återstående risker för granskning.

## P1: faktiskt resultat 2026-09-25

Arbetskopia `/Users/joakimohman/Code/tradgardsrytmen-p1`, gren
`task/p1-account-foundation`, bas `cfa9bfc`. Kanoniska checkouten har inga
filändringar. Commit/push av P1 på uppgiftsgrenen godkändes därefter av
användaren. Ingen deployment eller produktionsdatamutation ingår.

- Egen `accounts.User` baserad på AbstractUser; endast auth/accounts har
  aktiverats. Ingen sessionsapp, admin, publik registrering eller ny route.
- Additiva `accounts/0001` och `garden/0011`: Garden och medlemskap med
  databasunikhet samt check constraint för owner/member. PROTECT skyddar
  föräldrar mot oavsiktlig kaskadradering.
- [Inventering och övergångsordning](multiuser-transition.md) omfattar alla
  befintliga modeller, routes, kommandon och bakgrundsvägar.
- [API-kontrakt](api-v1.md) ger konkret kärnflöde för M1:s exempeldata,
  behörighetsmatris, fel, återförsök och förslag om mobil autentisering.
  Alla v1-endpoints är uttryckligen framtida stöd.

Verifierat med Python 3.12.14 och requirements.txt (Django 5.2.17) i separat
miljö `/tmp/tradgardsrytmen-p1-runtime`:

- `manage.py test`: **78 godkända**, inklusive fem nya modell-/migreringstester.
  Ny testdatabas byggs från tomt schema. Uppgraderingsprovet går från garden
  0010 utan accounts/auth-tabeller till senaste schema; samtliga fält/rader i
  alla äldre modeller jämförs. Fixtures omfattar plan, källa, arbetsidentitet,
  regel, granskningskvitto, fyra uppgiftsstatusar och påminnelsehistorik.
  Inga konton, trädgårdar eller medlemskap skapas av uppgraderingen.
- Separat temporär checkout från `git archive cfa9bfc`: gamla konfigurationens
  `migrate` + `seed_demo`, därefter P1:s `migrate` mot samma isolerade fil.
  Alla äldre tabellrader oförändrade, inklusive 6 växter, 3 områden och
  11 uppgifter; nya ägarskapstabeller tomma. Separat tom fil migrerades också.
- `node --test tests/*.test.cjs`: **6 godkända**.
- `scripts/verify_care_concurrency.py`: fyra samtidiga godkännanden och fyra
  behovsanrop ger unika uppgifter i temporär SQLite-databas.
- `manage.py check`, `makemigrations --check --dry-run`, `git diff --check`:
  godkända. Testmiljön varnar för saknad collectstatic-katalog; inget testfel.

Återkör Django-kontroller med `TRADGARDSRYTMEN_DB_PATH` satt till en separat
lokal testfil. Testsviten skapar själv en isolerad testdatabas. Ingen riktig
AI eller push har körts. Browser-/telefonprov och PostgreSQL ingår inte i P1;
befintligt webbflöde har verifierats med server- och JavaScript-regressioner.

Kvar för P2: välj identitetsleverantör och fastställ token-/återkallningspolicy,
implementera identitetsmappning, API-version/idempotenslagring, dataägarskap
och samtliga behörigheter. Besluta transaktionell regel för sista ägare och
radering. Det gamla globala API:et är fortfarande olämpligt för flera kunder.
Inga blockerare för lokal P1-granskning; dessa beslut blockerar publik drift.

## P2 och M1: paketens beroenden

P2 implementerar beslutad autentisering och serverflödet. Äldre data får en
explicit trädgård utan att historik skrivs om. Alla tillgängliga datavägar,
även äldre endpoints, måste säkras innan flera kunders data tillåts.
Testa främmande objekt-ID:n, relations-ID:n, listor, sökning, bootstrap och
återkallat medlemskap. Samordna privat webbens övergång till inloggning.

M1 bygger navigation och kärnflödet i React Native/Expo från kontraktet.
Återanvänd visuella beslut och texter. Testa laddning, tomma listor, fel och
utkast. Integrera med P2 vid I1; mobilens exempeldata är inte serververifiering.

## P2: lokalt resultat 2026-09-25

- Nullable ägarskap bevarar äldre rader; `assign_legacy_garden` kräver namngivet
  konto och trädgård, förhandsgranskar som standard och är atomärt/idempotent.
- Privat webb har Django-login/logout och trädgårdsväljare. Alla äldre endpoints,
  bootstrap, sökning, relationer, push och operatörskommandon är avgränsade.
- `/api/v1/` genomför första manuella flödet med UUID-baserade opaka ID:n,
  versioner, signerad/filterbunden cursor och beständiga idempotenskvitton.
- OIDC RS256/JWKS-verifiering och `(issuer, subject)`-mappning finns men är
  fail-closed utan konfiguration. Auth0 EU och administrativ länkning under
  pilot är beslutade; ingen tenant, klient eller extern tjänst har skapats.
- Negativa prov omfattar två konton, främmande objekt/relationer, listor,
  sökning, återkallat medlemskap, jobb, versionskonflikt och samtidiga
  idempotenta återförsök.

Beslutad tokenpolicy är 10 minuters access-token, roterande refresh-token med
30 dagars absolut och 14 dagars inaktiv livslängd samt leverantörs- och lokal
återkallning. Kvarvarande produktbeslut är transaktionell regel för sista
ägaren/radering. En fortsatt privat installation med en uttryckligt skapad
lokal ägare får driftsättas med OIDC avstängt efter att äldre tilldelning och
backup/återläsning har övats och `TRADGARDSRYTMEN_GARDEN_ID` satts uttryckligen.
Auth0-integrationen måste vara konfigurerad och provad före publik eller extern
fleranvändardrift.

## I1: första gemensamma milstolpen

Två konton med olika trädgårdar genomför produktens kärnflöde på iOS och
Android. Data och historik består efter omstart och ny inloggning. Tester
visar att kontona inte kan nå varandras data. Rapportera separat fysisk
enhet, simulator och sådant som ännu inte verifierats.

## Inför lansering

L1 måste få produktbeslut innan B1 och M2 låser deras beteenden. R1 omfattar
kontoåterställning, export/radering, kostnadsgränser, återställningsprov,
support, integritetsuppgifter, tillgänglighet och relevanta butiksprov.
En grön testsvit innebär inte i sig att appen är godkänd eller lanseringsklar.


## P1/P2: releaseuppdatering 2026-09-26

P1/P2 är släppta enligt överlämningen. Tidigare lokalstatus ovan är historisk.
Den tidigare P3-uppgiften rapporterade läsande verifiering av ren main och servercheckout på
`6606e76`, aktiv webb/påminnelsetimer, HTTP 200 från `/health/` och avslutad
autodeploy med Result=success/ExecMainStatus=0. Tjänstens datakatalog kräver
behörighet som inte finns för aktuell SSH-användare; produktionsdatabasens
schema, innehåll, deployed_commit-markör och `admin`-tilldelning har därför
inte återverifierats här. Det begränsar releaseunderlaget men hindrar inte
isolerad lokal P3-utveckling.

## P3: ursprungligt lokalt resultat 2026-09-26 (historik)

Worktree `/Users/joakimohman/Code/tradgardsrytmen-p3`, gren
`task/p3-durable-jobs`, bas `6606e76`. [Omfattning, acceptans och releasegräns](p3-durable-jobs.md).

- Explicit PostgreSQL-konfiguration med TLS-standard och låst psycopg; SQLite
  kvar som standard. PostgreSQL-fel faller aldrig tillbaka till annan databas.
- Additiv migration 0013 för beständiga jobb och försök. Idempotens,
  databasunikhet för aktiv AI per växt, atomär claim, lease/token,
  begränsad recovery/backoff, bevarad försökshistorik och separata oklara utfall.
- Kontroller av trädgård, beställare, medlemskapets identitet och oförändrat
  underlag före/efter extern effekt; indata fryses före sändning.
- Privat webbens uttryckliga AI-begäran och påminnelsetimern använder kön när
  flaggan aktiveras. Worker är avgränsad per trädgård och kräver explicit
  extern opt-in. Ingen worker installeras eller aktiveras av denna ändring.
- Backendmedveten backup/cleanup och syntetiskt överförings-/återställningsprov.
  Gammal autodeploy stoppar för PostgreSQL tills separat releaseflöde granskats.
- GitHub CI utökad för PostgreSQL 17 och SQLite med filbaserade konkurrensprov.
  CI-konfigurationen är lokalt granskad men har inte körts på GitHub.

Verifierat lokalt med Python 3.12, Django 5.2.17, psycopg 3.2.10 och PostgreSQL
17.11 (isolerad socket, ingen publik lyssnare):

- Hela Django-sviten: **122/122 på filbaserad SQLite och 122/122 på PostgreSQL**,
  utan överhoppade konkurrensprov.
- JavaScript: **11/11**, inklusive bevarad återförsöksnyckel efter nätverksfel,
  korrekt kömeddelande och uttrycklig information om oklart utfall.
- Överföring/återläsning: **32 syntetiska rader**, samtliga exporterade fält
  identiska i SQLite, PostgreSQL och återläst PostgreSQL-backup. Källfilens
  SHA-256 oförändrad; nästa sekvens-ID kunde skapas utan konflikt.
- `check`, `makemigrations --check --dry-run`, JavaScript-/shellsyntax och
  `git diff --check` godkända. Testerna varnar om saknad collectstatic-katalog
  och avsiktligt override av backupkonfiguration; inga testfel.
- Negativa prov omfattar tomt leverantörssvar utan dolt andra AI-anrop,
  timeout, sena svar, medlemskap, ändrat underlag, samtidiga workers/anrop/timers,
  utgången påminnelse och misslyckad backup utan publicerad slutfil.

Lokala granskningsloggar finns i `/tmp/p3-sqlite-tests.log` och
`/tmp/p3-postgres-tests.log`. PostgreSQL installerades lokalt för proven;
ingen inloggnings-/systemtjänst aktiverades. Kanoniska checkouten är fortsatt
ren på basrevisionen. Alla externa transporter i jobbstesterna är mockade.

Kvar före PostgreSQL-cutover/köaktivering: skyddad produktionsinventering och återställningsövning på
verklig kopia; beslutad PostgreSQL-drift/TLS/backup/PITR; granskat deployflöde,
workerdrift/larm och operatörsflöde för osäkra externa effekter. Köflaggan är
avstängd som standard. Auth0, publik AI-budget/frekvensbegränsning och mobilpush
är fortsatt egna aktiveringskrav. Ingen riktig AI, push, commit, push till Git
eller deployment har gjorts i P3-tasken.

## P3: samlad aktuell verifiering 2026-09-26

Integrationskopians 142 filer vid denna granskningsstart matchade exakt
slutmanifestet från transporträttningen, inklusive samtliga kod- och testfiler.
De faktiska loggarna bekräftar 254/254 Django på filbaserad SQLite respektive
PostgreSQL 17.11 utan skips, 15/15 JS och 32 fältidentiska syntetiska rader
SQLite → PostgreSQL → återläst backup. Sviterna har inte rutinmässigt körts om.
Ett nytt riktat prov av 0012 → 0013 med flaggorna av bevarade 18 syntetiska
konto-/domänrader fältidentiskt och verifierade SQLite-backup/återläsning före
och efter migrationen. Detaljer och begränsningar finns i
[privat releasebedömning](private-release-review.md) och
[transportgränsens rättningsrapport](transport-boundary-review-fixes.md).


## M1: ursprungligt lokalt resultat 2026-09-26 (historik)

Expo/TypeScript-klienten finns i `mobile/`, separat arbetskopia
`/Users/joakimohman/Code/tradgardsrytmen-m1`, gren `task/m1-expo-manual`,
bas `0b3eab4fa200ae09fc2c4cedff2b95ab4114525e`. Ingen commit/push eller
deployment. Kanonisk checkout och tidigare arbetskopior är bevarade.

- Expo Router: konto/trädgårdsval, skapa trädgård/växt/uppgift, detaljer,
  klarmarkering och läsbar utförd/överhoppad/arkiverad historik.
- Svenska mobilvyer, laddning/tomt/fel/fältfel, explicita återförsök,
  cursorpaginering och kontextbundna minnesutkast.
- Syntetisk utbytbar transport med två konton och tre trädgårdar.
  Konto-/trädgårdsgeneration samt avbrott skyddar mot sena svar; idempotenta
  skrivningar fryser kropp/nyckel vid oklart utfall. Konflikt visar färsk
  status och bevarad anteckning innan ny uttrycklig åtgärd.
- 17 klienttester godkända; inklusive läsande fältjämförelse mot aktuella
  Python-serialiserare. Typkontroll/lint godkända, Expo doctor 21/21,
  JavaScript/Hermes-export för webb, iOS och Android godkänd.
- Webbpreview provad vid 320/390/820 px, med kärnflöde, utkast, historik,
  konflikt, tappat svar och kontoseparering. Skärmbilder i `docs/m1-review/`.
- Ingen iOS-simulator (full Xcode/simctl saknas), Android-emulator/SDK
  eller fysisk telefon verifierad. Export är inte native körning.

V1 saknar redigering och återöppning/ångring; inga sådana endpoints har
uppfunnits och ingen backend ändrats. I1 behöver riktig transport, Auth0/PKCE,
säker tokenlagring/refresh/revoke, beständig avstämning av oklara skrivutfall
samt kontraktprov mot P2 och hela flödet på båda plattformarna. Klientens
syntetiska behörighetsprov verifierar inte serverns skydd. L1/M2/AI/push/köp
ligger kvar utanför leveransen. Se [M1-överlämning](m1-handoff.md).


## M1: separat granskningsfix 2026-09-26

Arbetskopia `tradgardsrytmen-m1-review-fixes`, gren `task/m1-review-fixes`,
samma bas `0b3eab4`. Hela aktuella M1-diffen överfördes byteidentiskt innan
ändringar; åtta tidigare arbetskopior inklusive index är bevarade.
Gemensam formulärlivscykel, orörd/ändrad/tömd anteckning och spärr före varje
återförsök är rättade. Färska 38/38 tester inkluderar monterade skärmar;
webb-reproduktionerna och negativa kontroller mot originalkod är dokumenterade.
Nästa steg är ny granskning av fixkopian. Ingen överföring till originalet,
commit/push, release eller utökning till L1/I1/M2 ingår.
[Resultat och verifieringsgränser](m1-fix-review/README.md).
