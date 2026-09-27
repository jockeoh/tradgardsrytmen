# Ansluten hemmaapp — lokal granskningsleverans 2026-09-27

## Uppföljning efter oberoende review

Användaren har därefter beställt rättning och commit/push på leveransgrenen.
Ingen produktionsaktivering ingår. De ursprungliga granskningsgränserna och
proven nedan redovisar den första leveransen.

- P1: webbens journal använder Web Locks för atomär kontroll och skrivning
  mellan flikar. En annan begäransnyckel får varken ersätta eller radera en
  befintlig rad. Förlorande flik skickar inget nätanrop och hänvisas till
  omladdning/inloggning för avstämning. Bekräftat kvitto nedgraderas aldrig av
  en annan fliks retry. Webb utan Web Locks stoppar mutation före nätet.
- P2: version 2 av säker sessionslagring skiljer aktiv inloggning från en
  beständig kö med återkallningar. Ny login kräver inte kontakt med tidigare
  server. Omstart/återanslutning och logout försöker återkalla väntande token
  utan att radera en annan aktiv identitet. Det äldre lagringsformatet läses.
- Riktade regressioner täcker samtidiga journalförfattare, gammalt fönsters
  radering, bevarat kvitto, Web Locks-adaptern och avsaknad av låsstöd samt
  serverbyte, omstart, 401 och fel vid säker lagring. Dessa är inte browser-
  eller fysisk telefonprov.

Webbens låsmekanism följer [Web Locks](https://developer.mozilla.org/en-US/docs/Web/API/Web_Locks_API).
Slutkontroller efter rättningen finns i `home-app-review/fix-validation.txt`.


Implementation i `/Users/joakimohman/Code/tradgardsrytmen-home-app`, gren
`task/connected-home-app`, bas `77d81f56f9994d73874ddbf28f7decf97fbfc10d`.
Ingen commit, push, produktionsrelease, produktionsdataändring eller extern
aktivering ingår. Kanoniska dokumentändringar och äldre arbetskopior bevaras.
De åtta beställningsdokumenten kopierades byteidentiskt före implementation;
SHA-256 finns i [överföringsmanifestet](home-app-transfer.json).

## Leverans och identitetsval

Appens standardläge ansluter via riktig HTTP. Syntetiska konton och felverktyg
visas endast med `EXPO_PUBLIC_DEMO=1`. Serveradress kan anges i loginvyn eller
med `EXPO_PUBLIC_API_ORIGIN`. HTTPS krävs utom för explicit lokal utveckling
på localhost, 127.0.0.1 och Android-emulatorns 10.0.2.2. Inga hemligheter
byggs in i appen. Transporten fryser server och token för varje session,
utesluter cookies och använder timeout, JSON-fel, Idempotency-Key och Retry-After.

Befintligt privat Django-konto återanvänds. Auth0 behövs inte för denna
hemmaapp. `TRADGARDSRYTMEN_PRIVATE_MOBILE_AUTH=1` aktiverar ett separat privat
lösenordsflöde som ger ett slumpat personligt Bearer-token. Flaggan är av
som standard. Bearer-kontraktet behålls, men utfärdare/livscykel ändras:
14 dagars absolut livslängd, ingen refresh, därefter ny lösenordsinloggning.
Servern sparar endast tokenhash. Lösenordsbyte, inaktiverat konto, explicit
utloggning och operatörsåterkallning spärrar token. OIDC och privat webb
behåller sina befintliga vägar. Inga anonyma genvägar eller publik registrering.

Login kräver JSON, särskild klientheader, tillåten browser-Origin och HTTPS
när DEBUG är av. Vanliga HTML-formulär kan inte starta mobilinloggning.
CORS är en explicit lista av exakta webb-origin utan cookies eller wildcard.
Alla v1-svar har no-store. Befintliga cookieanrop kräver fortfarande CSRF.
Misslyckade och lyckade loginförsök räknas i databasen: högst tio försök från samma
IP-adress eller för samma konto under 15 minuter. Bakom en proxy delas
IP-gränsen av hushållet; forwarded IP används inte som betrodd uppgift.
Detta är privat drift, inte en komplett publik identitetsplattform.

Native lagrar token i Expo SecureStore med WHEN_UNLOCKED_THIS_DEVICE_ONLY.
Webbpreviewn behåller token endast i minnet: omladdning kräver ny login.
Lösenord sparas inte. Native sparar väntande utloggning innan lokal identitet
rensats; saknas nät återförsöks återkallningen vid återanslutning/appstart.
Webbens väntande återkallning försvinner om fliken stängs, liksom token;
serverns 14-dagarsgräns och operatörsåterkallning gäller fortfarande.

## Beständig sparning och avstämning

En journalrad skrivs atomärt **innan** något muterande nätanrop skickas.
Den innehåller server, konto, trädgård, formulär, slumpad nyckel, fryst kropp,
starttid och formulärets anteckningar. Native använder SQLite; webbpreview
använder localStorage. Token finns aldrig i journalen. Journalen ligger i
appens privata lagring men anteckningar är inte separat krypterade där.

Osäkra begäranden bevaras vid utloggning, 401 och processdöd och blir synliga
endast efter autentisering av samma konto på samma server. Ett annat konto
eller en annan server får inte överta dem. Ett bekräftat svar sparas också
före formuläret öppnas för en ny avsikt, så omstart inte skapar dubbletter.
Vanliga osparade utkast lever fortfarande bara under session/navigation.
Ingen full offlinekö, bakgrundssynk eller automatisk omsändning vid login.
Avinstallation, rensad webbläsarlagring och enhetsförlust kan ta bort journalen;
serverhistoriken är fortsatt sanningskälla.

Startsidan visar kvarvarande osäkra sparningar. ”Kontrollera sparningen”
ger två explicita vägar:

1. Hämta det sparade serverkvittot via läsande `POST /api/v1/reconcile/`.
   Servern kontrollerar konto, requesthash och aktuellt medlemskap. Finns
   kvittot blir utfallet bekräftat även efter sju dagar, utan ny mutation.
2. Inom sju dagar: skicka exakt samma nyckel/kropp. Gränsen kontrolleras
   före varje transportförsök, även efter backoff. Ingen ny nyckel skapas
   under osäkerhet. Timeout och 5xx behåller avsikten.

Saknas kvitto efter sju dagar förblir formuläret låst. Administratören får
begäransnyckel, kropp och konto från användaren, kontrollerar IdempotencyRecord
för konto+POST+path+key samt objekt/historik och eventuell backup. Återställ
ett verifierat ursprungligt kvitto från backup om det finns och hämta det
igen i appen. Saknas säkert underlag görs ingen ny mobilmutation. Ingen
”försök med ny nyckel”-knapp eller automatisk slutsats att saknat kvitto
betyder att inget sparades. Manuell kassering/import av ett definitivt
saknat kvitto är inte implementerad. Kvitton gallras inte av detta paket.

Navigation, orörd/tömd anteckning, versionskonflikt med färsk status och
bekräftelse, paginering och aktuell behörighet från M1/P2 bevaras.
Manuellt flöde: login → trädgård → växt → uppgift → utförd → historik.

## Lokal körning och verifiering

Se [mobile/README](../mobile/README.md) för körkommandon. Isolerad testserver
skapas av `scripts/home_app_test_server.py`; den väljer alltid en ny SQLite-fil,
två tillfälliga konton och nytt lösenord, utan att använda produktionsdatabasen.

| Prov | Resultat |
| --- | --- |
| Mobiltester | 46 riktade och befintliga tester; se slutlogg i home-app-review. |
| Typkontroll/lint | Godkända. |
| Riktig HTTP | Båda kontonas hela manuella flöde, främmande ID/relation, versionskonflikt, medlemskapsåterkallning före replay/avstämning, logout och utgång. |
| Faktisk JS-processdöd | Separat barnprocess avslutas direkt efter servercommit vid växtskapande **och** klarmarkering. Nästa process läser diskjournal och återanvänder ursprunglig nyckel/kropp. Exakt en växt respektive en klarmarkering/version 2. |
| Historik | Bevarad på servern efter ny login; klientens lokala anteckning behövs inte för att återskapa den. |
| Native auth-livscykel | Lagringsinterface testat för offline-logout, återkallning efter omstart, fel konto och lagringsfel. SecureStore/SQLite på faktisk enhet är inte exekverade. |
| Django | 270 tester med filbaserad SQLite-inställning från CI. Standardens in-memory SQLite är inte lämplig för projektets fleranslutningsprov. |
| Övriga regressioner | 4 Python-unittest och 16 webb-JavaScript-prov. |
| Expo doctor | 21/21. |
| Export | Webb, iOS och Android. Export är inte native bygge eller native körning. |
| Webb-UI | Inloggningsvy vid 390 px och begripligt anslutningsfel verifierade. Appens webbläsare blockerade separat localhost-testserver med ERR_BLOCKED_BY_CLIENT, även vid direkt hälsoläsning. Fullt browserflöde därför inte verifierat. Riktig HTTP verifierades separat. |
| iOS-simulator | Ej tillgänglig: endast CommandLineTools, simctl saknas. |
| Android-emulator | Ej tillgänglig: adb/emulator/SDK saknas. |
| Fysisk iPhone/Android | Ej provade; inga enheter tillgängliga i uppgiften. |
| GitHub CI | Mobiljobb tillagt med tester, typkontroll, lint, riktig HTTP och export. Inte fjärrkört eftersom ingen push är beställd. |

Inga verkliga AI-/push-/betalningsanrop. Skärmtester använder simulerade
native-värdar; HTTP-provet använder riktig Django och SQLite. Dessa resultat
ska inte beskrivas som fysisk telefonverifiering eller produktionsbevis.

## Beroendegranskning

`npm audit` efter tillägg av SDK-kompatibel SecureStore/SQLite visar fortsatt
13 moderate, 0 high, 0 critical. Två rotorsaker:

- decode-uri-component 0.2.2 via Router/query-string: DoS vid illformad
  percentkodad länk. Rättad 0.5.0 är ESM medan den installerade query-string
  använder CommonJS-funktionen; ett blint override är inte kompatibelt.
  Inga Auth0-callbacks, universallänkar eller externa inloggningslänkar införs
  här. Privat användning eliminerar inte den kvarvarande länkrisken.
- uuid 7.0.3 via Xcode-byggverktyg: buffergränser i v3/v5/v6. Xcode-koden
  använder v4 utan användarstyrd buffer och ingår inte i HTTP-autentiseringen.
  Appens idempotensnycklar kommer från expo-crypto, inte detta paket.

Audit föreslår inkompatibla Expo/Router-nedgraderingar; de utfördes inte.
Beroendena är därmed bedömda men inte samtliga säkerhetsvarningar åtgärdade.
En kompatibel uppströmsuppdatering och nytt länkregrressionstest behövs innan
externa djuplänkar aktiveras. Rapporterna finns i home-app-review.

## Faktiska återstående aktiveringsbeslut

1. Godkänn separat granskning/commit/push och eventuell serverrelease med
   migration 0004 samt PRIVATE_MOBILE_AUTH=1. Inget av detta är gjort här.
2. Välj den befintliga privata HTTPS-adress som telefonen ska nå och ange
   den i appen. Återanvänd befintligt personligt konto/lösenord, eller beställ
   uttryckligen ett privat nytt konto; ingen automatisk äldre dataflytt.
3. Prova på fysisk telefon eller lokalt installerad simulator: SecureStore,
   SQLite över tvångsavslut, login/logout offline, tangentbord/navigation och
   historik. Fullt browserflöde behöver också provas i en miljö som når servern.

Auth0, L1, AI, push, köp, molnbygge, butik och publik registrering är inte
förkrav. Produktionsläget är inte återverifierat; äldre P3-bevis är historiska.

## Underlag

[Testloggar och skärmbild](home-app-review/) innehåller de avslutande proven.
SDK-valen följer [Expo SecureStore SDK 57](https://docs.expo.dev/versions/v57.0.0/sdk/securestore/)
och [Expo SQLite SDK 57](https://docs.expo.dev/versions/v57.0.0/sdk/sqlite/).
