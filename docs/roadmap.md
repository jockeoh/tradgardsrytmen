# Trädgårdsrytmen: genomförandeplan

Status: 2026-09-25. P1 är committad/pushad på sin uppgiftsgren. P2 är lokalt
implementerad i separat arbetskopia för granskning; ingen commit, push eller
drift ingår. [Produktmål](product-v1.md) och [arkitektur](architecture.md)
styr omfattningen.

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

## P2 och M1: nästa parallella arbetspaket

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
