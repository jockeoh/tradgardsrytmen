# M2-PWA – lokal granskningsleverans 2026-09-29

**Uppföljande rättning 2026-09-29:** granskningen av `1883cec` fann två
ytterligare gränsfall: versionsbyte vid sessionStorage-fel och ofullständig
tidsspärr i flerpostskö. De är nu rättade med regressionstester; se
[nya rättningsunderlaget](m2-review/followup-fixes.md). Aktuell kod använder
SW `tradgardsrytmen-v17-m2` / assets `m2-7`. Tidigare versioner, manifest
och testantal nedan beskriver den föregående leveransen. Ingen serverrelease.

**Senare beslut 2026-09-29:** användaren har beställt commit/push av paketet
och en ny uppgift för granskning av rättningarna. Tidigare formuleringar om
ingen commit/push beskriver implementations- och rättningsstegen. Serverrelease
är fortsatt separat och inte utförd här.

**Rättad efter granskning:** de tre fynden om formulär/flikar, väntande
logout/CSRF och beständig tidsgräns är åtgärdade lokalt. Aktuella testresultat,
ändringslista och begränsningar finns i [rättningsunderlaget](m2-review/fixes.md).
Browserbevisen längre ned gäller ursprungsleveransen, inte dessa rättningar.

Arbetskopia `/Users/joakimohman/Code/tradgardsrytmen-m2-pwa`, gren
`task/m2-pwa-offline`, från nyhämtad `origin/main`
`59d4c4c0bcae86778a8b6c54e21371d011679cd9`.
Ingen commit/push, deployment, produktionsdatamutation eller extern AI/push.
Ingen extra agent användes. Telefon-/Expo-prov är fortsatt pausade.

## Funktion

Öppna **Arbetslista · offline** från befintlig PWA. Vyn hämtar samtliga
befintliga uppgifter i vald trädgård och visar senaste hämtningstid.
Klarmarkering med valfri anteckning kan köas utan serverkontakt. Köade
handlingar ligger i en separat sektion; endast svar/kvitto eller läst
serverstatus visas som bekräftad historik. Orörd anteckning utelämnas,
uttryckligen tömd anteckning skickas som tom sträng.

Synkning görs vid öppning, återgång till synlig app, `online`-händelse och
knappen **Synka nu**. Varje tillfälle gör högst ett skrivförsök per köpost;
429/503 respekterar Retry-After (minst en sekund). Ingen bakgrundssynkning,
periodisk omsändning, offline-AI, nya växter, bred offline-redigering eller
native push har lagts till. En återkommen server utan browserns online-event
kan behöva **Synka nu** eller återgång till appen.

Vid 409 visas senast hämtade serverstatus/anteckning. Användaren kan behålla
serverstatus eller uttryckligen klarmarkera senaste planerade versionen.
Båda valen läser på nytt. Nyckel byts bara för ett sådant explicit val efter
en definitivt avvisad konflikt; ursprunglig begäran arkiveras lokalt.
Oklart utfall, felaktig body eller saknat gammalt kvitto har ingen blind
”försök som ny”-väg.

## Lagring, identitet och livscykel

- Webbläsarens origin avgränsar servern. `garden.m2.v1` i localStorage
  innehåller schemaversion 1 och separata poster för konto-UUID,
  trädgårds-UUID och medlemskaps-PK. Aktiv vy är separat från bevarade köer.
- Alla journaländringar och transporter går genom ett gemensamt originlås
  med Web Locks. En andra flik återläser under låset.
  Formulärutkast hålls separat i flikens sessionStorage (`garden.m2.forms.v1`),
  bundna till konto/trädgård/exakt medlemskap och sessionsgräns. Utkastet
  innehåller den faktiskt visade uppgiftsversionen och egen anteckning;
  motorn kopierar dessa vid bekräftelse före väntan på fliklåset. Delade
  snapshots får aldrig uppgradera ett redigerat utkast. Orörd anteckning
  utelämnas; uttrycklig tömning skickas som tom sträng. Samma uppgift kan
  inte få två parallella aktiva avsikter. Saknat låsstöd, trasig JSON eller
  lagringsfel stoppar mutation; ingen tom ersättningsjournal skapas tyst.
- Fryst body/UUID/tid/kontext skrivs först. `sent` skrivs före nätanropet.
  En skickad/oklar post läser kvittot innan omsändning. Inget kvitto före
  sju dagar innebär samma nyckel/body; efter sju dagar eller bakåtställd
  lokal klocka tillåts endast läsande avstämning. Åldern kontrolleras igen
  efter avstämningen och även när anrop misslyckas. `readOnlyReason` och
  `lastObserved` sparas före transport: en konstaterad sjudagarsgräns eller
  klockbackning kan aldrig öppna automatisk mutation igen vid omstart eller
  ny klockjustering. Bekräftat kvitto kan fortfarande avsluta posten.
  Tiden för första försök/avsikt nollställs aldrig.
- Sessions-CSRF och signerad konto/garden/exakt medlemskapskontext följer
  varje privat anrop. Servern validerar aktuell session och levande grant;
  medlemskapsraden hålls låst över klarmarkeringen och kvittoreplay.
- `garden_session_boundary` är en icke-hemlig, ettårig cookie. Den roterar
  vid lyckad login/logout/trädgårdsval, också från en äldre onlineflik.
  Mismatch döljer aktiv lokal vy och kräver nytt online-kontextval. Den är
  **inte** en autentiseringscookie och ersätter aldrig Django-sessionen.
- Offlineutloggning sätter först `garden.m2.stop` synkront, före väntan på
  Web Lock. Nästa köpost får inte sändas. Redan pågående anrop kan ha
  committat; utfallet/journalen bevaras. Därefter rensas aktiva snapshots
  och formulärutkast, aktiv vy låses, och serverlogout sparas som väntande.
  Login/kontextaktivering slutför först denna logout. Aktuell CSRF-cookie
  används vid varje försök; saknad token hämtas via login-sidans vanliga GET.
  403 ger högst en tokenuppdatering och ett nytt logoutförsök per aktivering.
  Login kan försöka på nytt efter ett misslyckat startförsök. Journalens
  signerade konto/trädgård/medlemskap ändras inte för att förnya CSRF.
  Kön raderas inte.
- Samma konto och samma medlemskap kan återuppta kön efter ny online-login.
  Annat konto får varken dess lista, kö eller nycklar i gränssnittet.
  Återskapat medlemskap får en annan scope. Samma konto ser en kort
  upplysning med begäransnycklar för sina spärrade äldre avsikter, utan
  gamla uppgiftstitlar/anteckningar; administratörsavstämning kan behövas.
- Kvittoarkiv och osäkra avsikter har ingen automatisk lokal gallring i
  denna leverans. Kvotfel blockerar nya skrivningar. Rensa inte browserdata
  innan osäkra utfall stämts av. Export/gallrings-UI är inte implementerat.

LocalStorage är inte krypterat för andra användare med tillgång till samma
OS-/browserprofil eller mot kod som redan kör i samma origin. UI-isolering
är verifierad; denna leverans gör inte browserprofilen till ett hemligt valv.
Cache och journal kan förloras om användaren rensar webbplatsdata eller
webbläsaren gallrar dem. Serveråterkallning kan inte upptäckas utan nät;
senast behörigt hämtad lista är läsbar offline tills lokal utloggning eller
ny online-kontroll. Dessa är uttryckliga lokala lagringsgränser.

## Service worker och äldre klienter

Aktuell SW `tradgardsrytmen-v16-m2`, assets `m2-6`. Ingen privat HTML eller API-cache.
Endast ett identitetsfritt skal och statiska resurser lagras. Navigation till
`/` eller `/worklist/` använder nätet och faller tillbaka till detta skal vid
nätfel. Login, trädgårdsval och API-anrop får aldrig skal som SW-fallback.
Gamla cacheversioner inom appens namespace rensas vid aktivering; journalen
berörs inte. Uppdateringen använder ingen tvingad `skipWaiting`/omladdning
som skulle tappa formulär. Alla gamla flikar kan behöva stängas för att den
nya workern ska aktiveras. En gammal worker saknar nya offlinefunktioner men
kan inte skriva om eller skicka den nya kön. Inget bakgrundsjobb registreras.

## Ursprunglig verifiering före rättningarna

Isolerad Python **3.12.14**, Django **5.2.17**, låsta requirements. Namnet på
testmiljön `/tmp/m2-pwa-py313` är historiskt missvisande; exekverad version är
3.12.14. Alla databaser är temporära SQLite-filer. Ingen produktionsdata
eller riktiga AI-/pushanrop användes.

- **280/280 Django**, filbaserad SQLite, inga skips. Inkluderar nio nya
  sessions-/CSRF-/idempotens-/konflikt-/konto-/grant-/cacheprov och ett nytt
  riktigt HTTP-prov. Befintliga 270 tester bevarade.
- **32/32 JavaScript**, därav 16 journalprov. De använder levererad motor
  med kontrollerad transport/lagring/lås och är inte browserbevis.
  Omfattar två klientinstanser, kvotfel, korrupt journal, processåterläsning,
  tappat svar, sjudagarsgräns efter lång avstämning, konflikt, anteckningar,
  återkallning, kontobyte, återskapat medlemskap och logout under pågående
  batch i annan klient.
- **4/4 fristående Python-prov**, Django check, makemigrations --check
  (ingen migration), JavaScript-syntax och diff-kontroll passerade.
- **Riktig HTTP + processdöd:** `garden.test_pwa_http` startar Django på
  loopback med isolerad databas och tre separata Node-processer. Första
  sparar journalen i fil, andra POST:ar och avslutas med kod 23 efter att
  servern svarat 200 men innan motorn fått svar. Tredje återläser originalets
  key/body och läser serverkvittot. En kvittorad, version 2, tom anteckning,
  ingen dubblerad klarmarkering. Detta är verklig HTTP, inte en telefon
  eller browser och inte en test av OS-krasch mitt i en disksektor.

### Faktiska browserprov

Codex in-app Browser, riktig Django-server `127.0.0.1:8766`, separat databas
`/tmp/m2-pwa-browser.sqlite3`. Två vanliga testkonton, två trädgårdar, tio
syntetiska uppgifter. Inga mockade browser-API-svar eller säkerhetsspärrar
kringgicks. Tidigare ERR_BLOCKED_BY_CLIENT uppstod inte i denna körning.

1. Login och befintlig överblick laddade; länken öppnade arbetslistan.
2. Två **riktiga** browserflikar visade samma konto/lista.
3. Servern stoppades. Omladdning visade cachat skal, lista och hämtningstid.
   Klarmarkeringar från båda flikarna syntes i gemensam väntande sektion
   och bestod vid omladdning. Detta är verkligt serveravbrott, inte ett
   prov med avstängd iPhone-radio eller browserns offline-emulering.
4. Servern återstartades. **Synka nu** bekräftade posterna utan dubbletter.
   Databasen verifierades med två kvitton och version 2 per uppgift.
5. Uttrycklig tömning med tangentbordet gav `(tömd)` i offlinekön och tom
   anteckning i både bekräftad browserhistorik och databas efter återanslutning.
   Orörd anteckning bevarades. Browserverktygets `fill('')` tömde inte fältet;
   det försöket räknas inte som tömningsprov. Faktiskt DOM-värde kontrollerades.
6. En testuppgift ändrades i isolerade serverdata medan klienten var offline.
   Synkning visade konflikt med ny serveranteckning. Uttryckligt val av
   senaste version klarmarkerade och bevarade denna anteckning (version 3).
7. Offlineutloggning med en kvarvarande avsikt dolde både flikarnas data.
   Vid återanslutning avslutades serversessionen. Bobs login visade bara
   Bobs lista; Alices femte uppgift var fortfarande pending/version 1 på
   servern, med totalt fyra bekräftade kvitton. Äldre fliken var tom/låst.

8. Ny login som Alice med ursprungligt medlemskap återupptog femte
   handlingen. Servern hade därefter exakt fem kvitton och alla fem uppgifter
   klara; orörda, tömda och konfliktreviderade anteckningar var korrekta.

9. Slutversionen `m2-5` öppnades i en ny flik efter att alla äldre flikar
   stängts och servern stoppats. Listan var läsbar, ny anteckning köades och
   offlineutloggning visade **Slutför utloggning** utan privat lista.
   Mobilkontroll: viewport 390 px, dokumentbredd 390 px, ingen horisontell
   överströmning. Skärmbilder finns för online- och offlinevy.

Browserbevis och slutliga kontrollartefakter finns i [m2-review](m2-review/).
Separat iPhone-/Android-/installerad PWA-/full browserprocessdöd och
PostgreSQL har inte provats i detta paket. Den automatiska `online`-lyssnaren
finns men fysisk nätväxling på telefon har inte verifierats.

## Bevarande och nästa steg

Ursprunglig roadmap bevarades byteidentiskt under kodrättningen. Efter
användarens separata dokumentuppdrag uppdaterades den aktiva roadmapen med
status och nästa steg; originalet finns i
[m2-review/roadmap-before-update.md](m2-review/roadmap-before-update.md). `m2-source-manifest.json` dokumenterar alla åtta ursprungliga
filhashar. Äldre ocommittat dokumentarbete bevaras även i `m2-inherited/`;
nyare dokument i basens main har återställts som arbetsunderlag så att den
äldre kopian inte skriver över hemmaappleveransens tillägg. API-/arkitektur-
ändringarna ovan är additiva. Den separata dokumentpubliceringen hanteras
utanför detta paket; vid integration ska dess senaste roadmap behållas.

Nästa steg: granska denna lokala diff, särskilt journalens tillståndsbyten,
utloggningsspärren och sessionsadaptern. Därefter separat beslut om eventuell
commit/push och release. Telefonprov kan återupptas när användaren önskar;
de blockerar inte denna lokala granskningsleverans.
