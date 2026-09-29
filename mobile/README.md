# Trädgårdsrytmen — ansluten hemmaapp

Lokal fullappsimplementation på grenen `task/full-app-rewrite`.
Expo SDK 57 / React Native 0.86.3 / React 19.2.3 / Expo Router.
Se [fullappsstatus och kvarvarande prov](../docs/full-app-rewrite.md) och
[workspace-kontraktet](../docs/workspace-api.md).
Paketet publiceras på arbetsgrenen; installation och produktionsaktivering är separata steg.

## Isolerat prov med riktig server

Installera projektets requirements i en separat Python 3.12-miljö. Från roten:

```sh
python scripts/home_app_test_server.py
```

Skriptet skapar en ny temporär SQLite-databas och skriver två provkonton
(`kim`, `alex`) med ett nytt tillfälligt lösenord. Servern lyssnar endast på
127.0.0.1:8133. Ingen produktionsdata eller AI används.

I en annan terminal:

```sh
cd mobile
npm ci
EXPO_NO_TELEMETRY=1 EXPO_PUBLIC_API_ORIGIN=http://127.0.0.1:8133 npm run web -- --localhost --port 8083
```

Öppna `http://localhost:8083`. Ange testkontots lösenord, skapa trädgård,
växt och manuell uppgift, markera utförd och läs historik. Logga ut/in med
båda kontona och ladda om. Servern bevarar historik; webbpreview kräver ny
login efter omladdning. Startar du om testserverskriptet skapas en **ny**
serverdatabas och nya konton; låt servern vara igång när appomstart provas.
Stoppa båda processerna med Ctrl-C efter provet.

För syntetisk M1 utan server: `EXPO_PUBLIC_DEMO=1 npm run web`. Endast det
läget visar provkonton och felinjektion. Standardläget använder riktig HTTP.

## Kontroller

Node 22.15+ (CI använder senaste 22.x) eller Node 24+, Python 3.12 med projektets requirements:

```sh
npm run typecheck
npm run lint
npm test
PYTHON=/absolut/sokvag/till/python npm run test:integration
EXPO_NO_TELEMETRY=1 npm run export
npx expo-doctor
```

HTTP-provet skapar och avslutar egen server på ledig loopbackport. Det använder
verkliga subprocesser och diskjournal för processdöd efter servercommit.
CI kör samma mobilkontroller och export, tillsammans med serverregressionerna.
Kör Django med filbaserad testinställning för samtidighetsproven:

```sh
P3_SQLITE_TEST_PATH=/tmp/garden-home-tests.sqlite3 python manage.py test --settings=config.p3_sqlite_test_settings --noinput
```

## Privat telefon

Servern behöver separat godkänd deployment av detta paket och
`TRADGARDSRYTMEN_PRIVATE_MOBILE_AUTH=1`, HTTPS och en adress telefonen når.
Ange adressen i loginvyn eller EXPO_PUBLIC_API_ORIGIN. Lösenord/token ska
aldrig ligga i EXPO_PUBLIC-variabler. Publik registrering erbjuds inte.
Befintligt Django-konto återanvänds. Vid behov finns det befintliga kommandot
`create_private_owner` och dess engångslänk för privat lösenordsval.

`npm run ios` / `npm run android` kräver tillgänglig Expo-/native-miljö.
SecureStore och SQLite är SDK-moduler; nytt native-bygge behöver inkludera
dem. iOS-/Android-export verifierar inte att modulerna kör på telefon.
Denna dator saknar simulator/emulator; fysisk telefon är ännu inte provad.
Ingen molnbyggtjänst eller butik är aktiverad.

Operatören kan återkalla ett kontos samtliga mobilinloggningar:

```sh
python manage.py revoke_mobile_sessions --username PERSONLIGT_KONTO
```

Lösenordsbyte och kontoavaktivering spärrar också privata mobil-token.
Privat webb fortsätter använda session och CSRF.

## Sparningar och datagräns

Servern är källa för historik. Journalen innehåller enbart redan inskickade
avsikter och bekräftade kvitton, konto-/serveravskilt. Den skrivs före nätet.
Native: SQLite-journal och SecureStore-token. Webb: localStorage-journal och
token i minnet. Vanliga osparade utkast är inte en fullständig offlinefunktion.

Osäkra sparningar visas på kontots startsida även efter omstart/login.
”Hämta sparat kvitto” är läsande. Explicit retry använder samma kropp/UUID
högst sju dagar; därefter krävs avstämning. Inget nytt försök med ny nyckel
skapas blint. Saknat kvitto efter gränsen låser avsikten och kräver operatörens
kontroll enligt [avstämningsvägen](../docs/home-app-delivery.md).

Formulär bevarar navigation, orörd/tömd anteckning och konflikter. Konto-/
trädgårdsbyten spärrar sena svar. Den nya workspace-vyn omfattar även
redigering, återöppning, skötselplansgranskning och köad analys. Historiska M1-prov finns i
[m1-handoff](../docs/m1-handoff.md) och [rättningsrapporten](../docs/m1-fix-review/README.md).


## Reviewrättningar: flikar och serverbyte

Webbpreview kräver Web Locks (HTTPS eller localhost) för journalskrivning.
Två flikar får inte skriva över varandras avsikter: den andra fliken stoppas
före nätanrop och behöver ladda om/logga in för att läsa befintlig sparning.
Äldre kvitton kan inte radera en annan begärans journalrad.

Aktiv inloggning och väntande tokenåterkallningar sparas separat i samma
säkra lagringspost på native. En otillgänglig gammal server blockerar inte
ny login. Kön återförsöks vid appstart/återanslutning och utloggning; 401 på
aktivt konto raderar inte andra servrars väntande återkallningar. Webbpreview
har fortsatt enbart token/återkallningskö i flikens minne.


## Fullappsgränssnitt och native-notiser

Efter val/skapa trädgård öppnas `/workspace`: Överblick, Min trädgård,
Årshjulet, Inköp och Inställningar. Det syntetiska M1-läget behåller sitt
historiska kärnflöde; använd isolerad Django-server för den nya helheten.

Servern behöver migrationerna 0015/0016. Native push är avstängt som standard.
För verklig aktivering krävs en privat development/installation build med
`expo-notifications`, rätt iOS/Android-identitet och notiscredentials, samt
projektets verkliga EAS project ID i `extra.eas.projectId`. Inget sådant ID
eller externa credentials har hittats på eller lagts in i detta arbete.
På servern krävs `TRADGARDSRYTMEN_NATIVE_PUSH=1` och privat mobilinloggning.
Registreringen sker först när användaren väljer att aktivera påminnelser.

En Expo-export bevisar inte installation eller mottagen notis. Kör inga EAS-
byggen, verklig AI eller notisleveranser som del av automatiska testkommandon.
Inköpslistan är lokal per server/konto/trädgård. Gamla webbens lista finns kvar
på sin ursprungliga enhet; ingen tyst import eller kontoflytt görs.
