# Trädgårdsrytmen: genomförandeplan

## Aktuell inriktning 2026-09-29

**M2-PWA:s tre ursprungliga rättningar har granskats. Två ytterligare
fynd om lagringsfel och flerpostskö har rättats och publicerats till main i
`93e5aface3cee2d8ae9317f3647d93c346f5f3dd`. Nästa steg är kompletterande
isolerade integrationsprov enligt steg 2 nedan.** Källkoden finns i
`tradgardsrytmen-m2-pwa`, gren `task/m2-pwa-offline`. Ingen M2-serverrelease
eller produktionsaktivering har utförts i detta arbete.

Privat PWA prioriteras. iPhone-/Expo-installation och I1:s native-prov är
fortsatt pausade och blockerar inte det lokala M2-arbetet. Se
[leveransen](m2-pwa.md) och [rättningsunderlaget](m2-review/fixes.md).

Ansluten hemmaapp har levererats med riktig HTTP-transport, privat personlig
Django-inloggning, beständiga sparavsikter och avstämning. Serverrelease
`59d4c4c0bcae86778a8b6c54e21371d011679cd9` verifierades 2026-09-27:
terminal deploy success/0, runtime matchade 264 filer, PostgreSQL,
accounts/0004 och PRIVATE_MOBILE_AUTH=1. Alla 1 544 befintliga rader bevarades;
backup återlästes. HTTPS, tjänster och sex timers verifierades. Detta är
historiskt releasebevis, inte en ny driftkontroll 2026-09-29.

Detaljerat lokalt driftunderlag finns i
[releaseunderlaget](home-app-private-release-status.md).
För den tidigare anslutna Expo-klienten blockerades fullt browserflöde/två
riktiga flikar av browsermiljön; fysisk
telefon och simulator har inte verifierats. Export är inte native körning.

## M2-PWA: genomfört lokalt

Arbetslista kan läsas offline. Klarmarkering med valfri anteckning sparas i
en beständig kö och synkas när appen är öppen. Bekräftad historik skiljs från
väntande handlingar; samma key/body återanvänds efter tappat svar. Konto,
trädgård, exakt medlemskap, offlineutloggning och explicita konfliktval ingår.

De tre ursprungliga rättningarna finns i `1883cec`: formulärets visade
version/anteckning, återhämtning av aktuell CSRF vid logout och beständig
tidsspärr. Granskningen fann två ytterligare gränsfall som rättats i `93e5afa`:

- Ett sessionStorage-fel får inte höja formulärets interna version medan
  det gamla formuläret ligger kvar. Formulärunderlaget byts först efter
  lyckad lagring; lagringsfel stoppar ny köläggning.
- Tidsobservationer spärrar hela den aktiva kön före transport och vid
  svar/fel. Första postens kvittofel kan inte lämna senare gamla poster
  öppna för mutation efter klockbackning och omstart.

Aktuell SW är `tradgardsrytmen-v17-m2`, assets `m2-7`. Se
[rättningsunderlaget](m2-review/followup-fixes.md).

Ny lokal verifiering: **60/60 JavaScript, 11/11 Django-PWA-tester och 4/4
fristående Python-prov**, samt syntax/diffkontroll. Fyra nya regressionstestfall
fallerar mot `1883cec` och passerar med rättningarna. Django använde egen
filbaserad SQLite; UI-testerna använder DOM-adapter, inte riktig browser.
Ingen ny full lokal Django-/HTTP-/PostgreSQL-körning gjordes i rättningssteget.

[CI för exakt rättningsrevision `93e5afa`](https://github.com/jockeoh/tradgardsrytmen/actions/runs/36536747105)
är **completed/success**: Linux/Python 3.12, macOS/Python 3.13, PostgreSQL
samt mobile är gröna. Detta omfattar full Django-svit och de automatiska
HTTP-/processåterstartsproven, men inga riktiga browser-/telefonprov.
Det tidigare lokala HTTP-provet blockerades av sandboxens loopback-behörighet.
Ursprungliga browserbevis gäller m2-5.

## Plan framåt, i ordning

1. **Genomförd granskning och uppföljande rättning.** De två ytterligare
   fynden är rättade med negativa regressionstester och publicerade i
   `93e5afa`. Bevara äldre patchar/manifest som historiskt bevis; det nya
   rättningssteget har ett separat manifest.
2. **Nästa steg: komplettera isolerade integrationsprov.** Prova m2-7 i två
   riktiga browserflikar: skilda utkast/versioner, sessionStorage-fel,
   orörd/tömd anteckning, offlineutloggning, ny login och byte från äldre
   service worker. Följ exakt revisions CI för HTTP/processåterstart och
   PostgreSQL, och komplettera där automatproven inte täcker verklig browser.
   En full browserprocessdöd är fortfarande ett separat prov. Lokala prov
   ska använda syntetisk filbaserad SQLite eller isolerad PostgreSQL;
   behåll miljöhinder synliga och kringgå inga spärrar.
3. **Separat beslut om serverrelease.** Commit/push är genomfört för
   rättningarna; detta är inte en serverrelease. Jämför med då aktuell main
   och bevara dokumentpubliceringen. Vid beställd release verifieras CI,
   terminal deployment, driftsatt revision, hälsa och SW-/assetversioner.
   Lokala testresultat och publicerad källkod är inte driftbevis.
4. **Följ upp privat PWA efter godkänd release.** Verifiera vardagsflödet på
   en faktisk telefon/installerad PWA när användaren vill återuppta sådana
   prov. Ta därefter ställning till nästa avgränsade förbättring, exempelvis
   export/manuell avstämning av gamla osäkra avsikter. Automatisk gallring
   eller nya nycklar för oklara utfall ingår inte som standard.

Commit/push av rättningarna är genomfört. Serverrelease och nya funktioner
kräver fortfarande separata beslut.
Native I1/Expo förblir pausat. Bred offline-redigering, nya växter offline,
offline-AI, native push, L1/betalningar, Auth0 och publik lansering är senare
spår som kräver egna beslut. Inga verkliga AI-/pushanrop ingår.

## Prioriterad restlista och verifierad status

Tabellen skiljer genomförd serverleverans från pausade native-prov.
Äldre daterade resultat längre ned är historik.

| Prioritet/del | Nuvarande status | Kvar, nytta och beroenden |
| --- | --- | --- |
| Klart: privat release | Kodrelease 1ee8e9e driftsatt först på SQLite, schema 0014; CI och autentiserad HTTP gröna. | Verklig backup/återläsning, oförändrade domänrader, kontrollerat underhållsfönster och klientmarkörer verifierade. Fysisk telefon och verkliga externa prov återstår separat. |
| Klart: P3 PostgreSQL-cutover | PostgreSQL 17.11 aktivt på lokal socket med peer-auth. | 1 541 fältidentiska exporterade rader och återläst backup, sekvenser och oförändrad SQLite-källa verifierade. Dagliga lokala backuper aktiva; PITR/off-host och publik kapacitet återstår före bredare drift. |
| Klart: P3 köaktivering | DURABLE_JOBS=1, worker och kökontroll aktiva. | Operatörskvitto för bekräftade oklara utfall implementerat och testat; oförändrad försökshistorik och inga automatiska omsändningar. Systemd/journal ger felsignal; aktiv extern larmkanal och publika belastningsprov återstår. |
| Klart: M1 och ansluten klientkod | Expo-klient med riktig transport, personlig privat login och beständig journal levererad i 59d4c4c. | CI: 54 mobiltester, typkontroll/lint, HTTP/processdödsprov och export gröna vid release. Två riktiga browserflikar och native/telefonprov återstår. |
| Senare: L1 | Produktförslag finns; ingen färdig separat L1-leverans eller fastställd betal-/offlineomfattning verifierad. | Besluta målgrupp/marknad, betalande part, priser, AI-kvoter, delning, offlineomfattning och webbens framtid. Ger avgränsning för M2/B1/R1; leverantörsavtal och köp är separata externa beslut. |
| Pausat: I1 telefonverifiering | Privat serverintegration och mobilinloggning driftsatta; fysisk iOS/Android inte verifierad. | iPhone-/Expo-installation pausad 2026-09-29 på användarens begäran. Återuppta enhetsprov senare; Auth0 är inte förkrav för privat hemmaapp. |
| Senare: Native AI | P3 ger bara privat webbkö, inga native v1 AI-endpoints. | Specificera/implementera v1 start/status/granskning/godkännande, uttryckligt datamedgivande och utfall/återförsök; koppla till driftklar P3 efter I1. Krävs om AI ingår i mobil v1; inga riktiga prov utan godkännande. |
| Nu: M2-PWA, rättningar publicerade | Ursprungliga tre fynd granskade; två ytterligare gränsfall rättade i 93e5afa. 60 JS, 11 riktade Django och 4 Python passerade lokalt. SW v17-m2/assets m2-7. Ingen M2-serverrelease. | Steg 2: riktiga browserprov, lagringsfel, äldre SW och full browserprocessdöd; följ nya revisionens CI för HTTP/PostgreSQL. Native/Expo fortsatt pausat. |
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
| M2-PWA | Offline arbetslista och köade klarmarkeringar i befintlig PWA | Privat P2/P3/serverintegration; avgränsad omfattning beslutad 2026-09-29 |
| M2 native/push | Senare native offline/push | I1 + relevanta produktbeslut |
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

L1 måste få produktbeslut innan B1 och bredare native M2 låser deras beteenden.
Det avgränsade privata M2-PWA-paketet är redan beslutat ovan. R1 omfattar
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
