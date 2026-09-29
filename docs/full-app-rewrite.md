# Hela Trädgårdsrytmen i den nya appen

## Mål korrigerat 2026-09-29

Användaren har förtydligat att målet är hela appen omskriven. Ett manuellt
kärnflöde eller en offlinearbetslista är delresultat, inte slutleveransen.
Den nya appen ska kunna ersätta den befintliga för privat vardagsanvändning.
Behåll befintliga data, historik och fungerande serverlogik.

Målklienten är bekräftad av användaren: **Expo/React Native** enligt
ursprungsriktningen. Hela funktionsomfattningen ska byggas i Expo-klienten.
Befintlig webb/PWA behålls under övergången. Fysisk installation och externa
tjänsteaktiveringar är separata slutsteg, inte skäl att utelämna funktioner.

## Aktuell lokal implementation, 2026-09-29

Arbetet finns på `task/full-app-rewrite` i `tradgardsrytmen-full-app`.
Paketet och reviewrättningarna är avsedda för publicering på denna arbetsgren.
Ingen installation eller produktionsaktivering ingår i publiceringen.

Den anslutna Expo-klienten har nu ett samlat gränssnitt för:

- Överblick, gruppering efter arbete/plats, sökning, kalender och historik.
- Fulla växtfält, områden, placering och egna uppgifter med datumintervall.
- Redigering, klarmarkering, hoppa över/återöppna, arbeten vid behov och bortval.
- Skötselplaner/källor, uttrycklig analysstart, jobbstatus, redigering av råd,
  jämförelse och godkännande/avvisning av förslag.
- Enhetslagrad inköpslista med ångra och jordberäkning för rabatt/kruka.
- Trädgårdsprofil, påminnelsetider och uttrycklig native-notisregistrering.

[Workspace-API](workspace-api.md) återanvänder befintlig domänlogik och
beständiga kvitton. Inga befintliga växter eller historikrader migreras till
nya kopior. Native-notiser har en separat, avstängd Expo-transport; gamla
Web Push-prenumerationer behåller sitt beteende.

Efter reviewrättningarna verifierat lokalt: 67 mobiltester inklusive monterad navigation/redigering
och konfliktgranskning; typkontroll och lint; export för iOS/Android/webb.
213 riktade serverregressioner passerade efter rättningarna för workspace,
skötsellivscykel, API, jobb, transporter och konto.
De 13 workspace-testerna passerade efter reviewrättningarna.
En tidigare full körning genomförde 291 tester men kunde inte starta det
återstående HTTP-testets loopbackserver på grund av sandboxens portspärr.
Ingen fysisk enhet, simulator, visuell browsergranskning eller PostgreSQL-
körning av denna nya gren är verifierad. Monterade komponenttester använder
mockade native-primitiver; de är inte telefonbevis.

## Rättningar efter oberoende review, 2026-09-29

- Aktuell skötsel använder `current_rules`: endast aktiva, inte bortvalda råd,
  inklusive återställda definitioner från äldre planer. Ursprungliga förslagsråd
  och historik behålls; ovalda råd visas inte som gällande eller i rådssökningen.
- Godkännandevyn visar rådstyp, återkomst, månader/engångsdatum och behovsvillkor
  innan användaren väljer och godkänner råden.
- Konfliktgranskning vid klarmarkering, hoppa över och återöppning visar senaste
  titel, instruktion, datum, kategori och anteckning före ett nytt explicit försök.
  Statushandlingen skriver fortfarande bara vald status.

Fem nya monterade klientprov och ett nytt serverprov täcker rättningarna.
De tre verifierade reviewfynden är åtgärdade. Nästa steg är ett samlat
installationsprov med nedanstående kvarvarande verifierings- och produktluckor.

## Kvar till en verifierad ersättare

1. Kör hela vardagsflödet mot isolerad riktig server i Expo på måltelefonen,
   inklusive omstart under sparning och granskning av en full skötselplan.
   Kontrollera layout/tillgänglighet på liten skärm. Kör återstående HTTP-
   och PostgreSQL-kontroller i en miljö som tillåter dem.
2. Konfigurera den privata installationens verkliga app-/EAS-identitet och
   notisbehörigheter. Prova analys och påminnelser först när extern körning
   är beställd. Expo-ticket är inte leveransbevis; telefonleverans och
   beteendet vid notistryck återstår att prova.
3. Förbered övergång av den gamla webbläsarens lokala inköpslista. Den lämnas
   orörd och importeras inte automatiskt till ett nytt konto. Den nya listan
   avgränsas per server, konto och trädgård.
4. Genomför godkänd release med backup, additiva migrationer, verifierad
   serverversion och återgångsmöjlighet. Behåll den gamla klienten tills
   den nya har verifierats i vardagsanvändning.

Expo bevarar inskickade skrivavsikter i journalen och erbjuder återförsök/
avstämning. Den hämtar fortfarande arbetsunderlaget online; M2-PWA:s fulla
läsbara offlinearbetslista har inte flyttats till Expo i detta paket.
Detta ska inte beskrivas som full offlineparitet eller färdig övergång.

## Inventerad funktionsomfattning

Kontrollerat i koden på `b21cd26`: befintlig webbmall, app.js, garden/views.py,
garden/urls.py, garden/api_v1_urls.py samt mobile/src/app och api/contract.ts.
Tabellen nedan visar inventeringen **före** det samlade omskrivningsarbetet.
Aktuell implementationsstatus står ovanför tabellen.

| Funktion som ska följa med | Expo före detta arbete | Identifierat arbete |
| --- | --- | --- |
| Personlig login, logout, välja/skapa trädgård | Implementerat kärnflöde | Integrera i sammanhängande slutgränssnitt och prova på vald målplattform. |
| Överblick och aktuellt arbete | Enkel lista över väntande uppgifter | Månadsöverblick, relevant nästa handling, gruppering efter jobb/plats, aktuella råd och tydlig status för saknad plan. |
| Årshjul | Saknas | Månad/år-navigation, årsöverblick och månadsdetaljer med befintliga skötselregler. |
| Växter och odlingar | Skapa/läsa namn och anteckningar | Visa och redigera sort, typ, antal, stadium, plats och övriga befintliga växtfält samt full växtdetalj. |
| Områden och placering | Saknas | Skapa, byta namn, ta bort område och placera växter. |
| Uppgifter och historik | Skapa enkel uppgift, klarmarkera, läsa historik | Datumintervall, kategori, redigering, hoppa över/återöppna där tillåtet samt befintliga historikregler. |
| Arbeten vid behov och bortval | Saknas | Starta behov, välja bort/återta arbete och behålla koppling till historiken. |
| Skötselplaner och AI | Visar endast om plan finns | Läsa råd/källor, uttryckligen starta analys, följa jobb, granska/redigera förslag och godkänna plan. Återanvänd befintlig serverlogik och beständig kö. |
| Sökning | Saknas | Gemensam sökning i växter, råd och uppgifter med navigation till träff. |
| Inköpslista och jordberäkning | Saknas | Lägga till/bocka av/ta bort/ångra, jordvolym och säckantal för rabatt/kruka, lägga beräkning i listan. Bevara gammal enhetslista; ingen tyst import eller ny ägare. |
| Trädgårdsprofil | Saknas som komplett inställningsvy | Namn, plats, odlingszon och läge samt befintliga påminnelseinställningar. |
| Påminnelser | Ingen native-lösning | Inställningar, aktivering/avaktivering och transport för vald plattform. Befintlig Web Push är inte native push. |
| Svagt nät och återstart | Expo har beständig journal; separat PWA har offlinearbetslista | Ett samlat beteende i målklienten: tydlig väntande status, återhämtning och bevarade avsikter. Bred offline-redigering av alla funktioner är inte ett krav på funktionslikvärdighet. |

## Samlat genomförande

1. **Bygg full funktionell ersättare.** Bygg vidare i Expo/React Native.
   Genomför navigation, vyer och nödvändiga API-tillägg som ett sammanhängande
   paket utifrån tabellen. Återanvänd domänlogik, databas, identitet och kö;
   bygg inte om redan fungerande serverdelar utan konkret behov. För Expo
   krävs utökat konto-/trädgårdsavgränsat API för de funktioner som nu enbart
   finns i sessionswebben. Ett UI som skickar vidare till gamla webben räknas
   inte som en färdig omskrivning av funktionen.
2. **Verifiera hela vardagsflödet.** Gå igenom samtliga funktioner med isolerade
   data i den riktiga målklienten. Jämför med befintlig app, bevara historik
   och använd riktade tester för skrivningar, behörighet och återhämtning.
   Granskning är en del av leveransen; nya specialfall får inte ersätta
   arbetet med saknade funktioner. Faktiska fel rättas, verifieringsluckor
   beskrivs utan att presenteras som färdiga funktioner.
3. **Ta ersättaren i bruk.** Förbered körning/installation och övergång med
   bevarade data och återgångsmöjlighet. Produktionsrelease och externa
   tjänsteaktiveringar sker efter separat beställning. Den gamla klienten
   tas inte bort innan ersättaren är verifierad och övergången godkänd.

## Klart innebär

- Alla befintliga vardagsfunktioner ovan finns i ett sammanhängande nytt
  gränssnitt; eventuella avvikelser är uttryckligen beslutade av användaren.
- Befintliga växter, områden, planer, arbeten och historik används och bevaras.
- Skötselplan/AI, påminnelser och inköpsverktyg är inte bortdefinierade som
  senare produktutveckling när målet är att ersätta den gamla appen.
- Hela flödet fungerar mot riktig server och är provat i målklienten;
  tester/export räknas inte som faktisk telefoninstallation.
- Driftsatt eller installerad version verifieras separat från publicerad kod.

Betalningar, publik registrering, Auth0, butikslansering och nya funktioner
utöver dagens app ingår inte automatiskt. Implementering av AI-/notisflöden
kan göras med simulerade transporter; verkliga externa anrop, molnbyggen och
produktionsändringar kräver fortsatt uttrycklig beställning.

## Befintliga delresultat

M2-PWA är publicerad i `93e5afa` med roadmap i `b21cd26` och grön CI.
M2-specialproven är en del av verifieringslistan, inte projektets huvudmål.
De ursprungliga delplanerna och granskningsbevisen behålls som historik.
