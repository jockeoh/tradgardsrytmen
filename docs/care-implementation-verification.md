# Relevant skötsel: lokal leverans och verifiering

Verifierad 2026-09-12. Genomförande av `PLAN (17).md` i Trädgårdsrytmen.
Ändringarna är lokala och har inte publicerats eller driftsatts.

## Levererat beteende

- Beständig arbetsidentitet per växt, moment och undergrupp. Rådrubriken kan ändras mellan planer utan att skapa ett nytt tillfälle. Mellanslag och versaler i undergrupper normaliseras; osäkra semantiska likheter kräver granskning. Val av befintligt arbete använder exakt dess identitet och scope. Förtydligad undergrupp och sammanslagning är separata uttryckliga val med käll-/målidentitet i granskningskvittot.
- Planerat arbete, Vid behov och allmänna råd hanteras separat. Planerat arbete kräver relevansmotivering och källstöd. Villkorad bevattning kan inte döljas som en månatlig kalenderuppgift. Engångsarbete kräver absoluta start- och slutdatum.
- Behövs nu återanvänder det öppna tillfället. Ett nytt behov kan skapas när det förra avslutats. Beständigt bortval bevaras även vid planbyte; Hoppa över gäller bara tillfället.
- AI-underlaget innehåller datum, daterad växtinformation, befintliga arbeten, historik, anteckningar och bortval. AI-import, förslagsredigering och godkännande använder samma lokala validering.
- Granskningskön visar nytt, ändrat, oförändrat och tas bort. Möjliga instruktionella överlapp visas även mot äldre historik. Godkännande kräver en aktuell jämförelse och vid behov en dokumenterad överlappsbedömning. Endast relevanta konfliktfria planerade arbeten är förvalda.
- Planbyte återanvänder öppna tillfällen och respekterar utförda/överhoppade tillfällen. Ersatta automatiska tillfällen arkiveras med orsak. Planens giltighetsgräns sparas och används även av nattkörningen.
- Sidans läsanrop är skrivfria. Uppgifter skapas vid godkännande, uttryckligt behov och materialisering. Bortval kan återställas utan att dubblera befintliga tillfällen. Aktuella arbeten och notiser bygger på samma urval.
- Nu visar diskreta antal, aktuellt och kommande arbete samt en hopfällbar behovsdel. Året läser vald månad och år med planering och historik åtskilda. Trädgården grupperar växter efter område och samlar områdeshanteringen. Växtdetaljen visar skötsel, behovsråd, historik och bortval. Inställningar innehåller profil och notiser.
- Filter, sidposition, profilutkast och granskningsval bevaras vid uppdateringar. Ångra-knappens tidigare genomsläpp av klick är rättat. PWA-cachen är uppdaterad till v4.

## Städrapport för den befintliga lokala databasen

| Inventering | Antal |
| --- | ---: |
| Växter | 6 |
| Skötselregler | 0 |
| Uppgiftstillfällen | 0 |
| Automatiska dubbletter | 0 |
| Passerade automatiska tillfällen | 0 |
| Osäkra överlapp att granska | 0 |

Backup togs före migrering: `backups/tradgardsrytmen-20260912-085817.sqlite3`.
Städkommandot tog dessutom en separat backup med integritetskontroll innan körningen.
Både backup och aktuell databas klarade SQLite-integritetskontrollen. Samtliga ursprungliga
växtfält jämfördes med backupen och var oförändrade.

Städningen är implementerad i `clean_care_content`. Inventering utan `--apply` är skrivfri.
Med `--apply` säkerhetskopieras databasen före arkivering. Bara entydiga samtidiga, öppna automatiska dubbletter
och passerade öppna automatiska tillfällen arkiveras. Historik, manuella uppgifter och samtliga
anteckningar bevaras. Ett nytt uttryckligt behov efter att det förra avslutats behålls som ett
separat tillfälle. Äldre oklassificerade råd och osäkra överlapp får granskningsförslag.
Redan dokumenterat godkända överlapp behöver inte granskas igen.

Denna rapport gäller **den lokala databasen**. Produktionsdatabasen har inte inventerats eller
städats i denna leverans. Dess faktiska antal, hallonråd och eventuella dubbletter ska inventeras
med samma kommando i det separata produktionssteget.

## Kontroller

70 automatiska tester passerar med projektets låsta beroenden, inklusive Django 5.2.17,
i en separat verifieringsmiljö. Kontrollerna omfattar:

- Samma arbete med ändrad rubrik, instruktionella överlapp, olika och osäkra undergrupper.
- Planbyte mitt i säsongen, befintlig historik, årsskifte, månatliga återkomster, absoluta engångsfönster och upprepade godkännanden.
- Fyra samtidiga godkännanden och fyra samtidiga behovsanrop mot en riktig temporär SQLite-fil. Inga extra tillfällen skapas.
- Bortval, återställning efter planbyte, behovsråd utan automatiska kalenderuppgifter eller uppgiftspåminnelser.
- Skrivfria läsanrop, inaktuell jämförelsetoken, gemensam validering och otillåtna arbetsidentiteter från en annan växt.
- Migrering från 0007 med bevarad historik samt upprepningssäker städning med bevarade manuella uppgifter och anteckningar.
- De fyra granskningsreproduktionerna: nytt avslutat/nytt öppet behov, scope-förtydligande med utförd historik och bortval, faktisk autodeploy-övergång till granskningskö utan AI-anrop samt exakt återanvändning av vald identitet.
- Uttrycklig sammanslagning till befintlig identitet, inklusive bevarad historik/anteckning och skydd mot att samma säsongsarbete skapas igen.

Djangos systemkontroll, migrationskontroll, JavaScript-syntaxkontroll, `git diff --check` och
insamling av statiska filer passerar.

Webbläsargranskningen kördes mot en separat fiktiv exempelträdgård, utan externa AI-anrop:

- Nu, Året, Trädgården och Inställningar kontrollerades på dator och mobil.
- Uppgiftsdetalj och formulär mättes vid 320 px; ingen horisontell överrinning.
- Granskningsredigering och godkännande, bevarade granskningsval, platsfilter, månadsval,
  upprepade Behövs nu, markera klart/ångra, bortval/återställning och manuellt formulärsparande provades.
- Profilutkastet var kvar efter en uppgiftsuppdatering. Tangentbordsfokus från formulärfält till
  åtgärdsknapp fungerade. Ångra återöppnade rätt uppgift efter korrigeringen av klickytan.
- Efter granskningsrättningarna kontrollerades identitetsformulärets fyra tydliga val separat.
  Befintligt arbete och sammanslagning låser scope till vald identitet; förtydligande och nytt
  moment gör scope redigerbart och visar konsekvensen. Vid 320 px var formuläret 320 px brett
  utan horisontell överrinning.

Ingen verklig AI-analys eller pushleverans har beställts. Källornas faktiska trädgårdsråd har
inte nygranskats här; testerna verifierar applikationens kontrakt och livscykel.

## Separat produktionssteg

Följ `docs/deployment.md`: backup, migrering 0008–0010, automatisk inventering och städrapport,
aktivering av granskade råd, statiska filer/PWA-cache, tjänstestart och kontroll av driftsatt
revision, hälsa och huvudvyer. Normal autodeploy beställer inte längre
`replace_pending_research`, eftersom det kommandot kan starta verkliga AI-analyser.
Produktionssteget har inte utförts.
