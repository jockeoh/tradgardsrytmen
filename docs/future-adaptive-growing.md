# Framtidsidé för platsanpassad odlingsrådgivning

**Status:** Potentiell framtida implementering, dokumenterad 2026-10-27.
Idén är inte en beställd milstolpe och ändrar inte prioriteringarna i
[roadmapen](roadmap.md).

Trädgårdsrytmen skulle kunna utvecklas till en odlingsrådgivare som lär sig
vad som fungerar på en viss plats över flera säsonger och hjälper odlaren
att anpassa planen när väder och växternas utveckling avviker från det väntade.
Utgångspunkten är användarens intresse för odling och egen praktisk nytta.
En kommersiell tjänst är en möjlighet att undersöka efter att nyttan har visats.

## Problem och produktidé

Odlingsråd behöver ta hänsyn till sort, plats, säsong och den tid odlaren har
tillgänglig. Ett planerat datum kan behöva ändras när utvecklingen blir sen,
en växt misslyckas eller vädret förändras. Erfarenheter från tidigare år är
värdefulla men behöver vara enkla att fånga och återanvända.

Klimatförändringen gör anpassningen mer relevant. SMHI beskriver både en
längre växtsäsong och risk för minskad vattentillgång. Att fler människor
kommer att vilja odla själva är en separat marknadshypotes; produktens nytta
ska även kunna visas för dagens hobbyodlare.

Den tänkta tjänsten hjälper odlaren att planera, ompröva och lära:

| Situation | Exempel på hjälp |
| --- | --- |
| Inför säsongen | Föreslå ett upplägg utifrån odlingsyta, önskade grödor, platsens förutsättningar och tillgänglig tid. |
| Under säsongen | Uppmärksamma att utvecklingen avviker och föreslå omplanering av sådd, utplantering eller efterföljande gröda. |
| Efter säsongen | Sammanfatta vilka sorter och placeringar som fungerade, vilka försök som misslyckades och vad som är värt att prova nästa år. |

## Växternas utveckling som lokal information

Tidpunkter för groning, bladutveckling, blomning och mognad kan ge information
om hur säsongen fortskrider på en viss plats. Sådana observationer kallas
fenologi och används exempelvis inom SLU:s Naturens kalender.

En möjlig AI-funktion är att föreslå utvecklingsstadium från foton och koppla
observationen till rätt växt, plats och säsong. Flera observationer över tid
skulle tillsammans med odlingskunskap och väderdata kunna ge bättre underlag
för omplanering. Nyttan behöver prövas mot vanliga odlingsråd.

AI:s roll är att tolka bilder och korta anteckningar, sammanföra relevant
kunskap, jämföra förlopp och förklara förslag. Datumregler, väderberäkningar
och verifierad odlingskunskap ska fortfarande vara en del av underlaget.
En bild visar inte säkert markfukt vid rötterna, jordens näringsinnehåll eller
orsaken till en skada. Ett utvecklingsstadium ersätter inte en frostprognos.

## Data med låg registreringsbörda

Den centrala erfarenheten är **sort, plats, förhållanden, åtgärder och utfall**.
Insamlingen ska följa vanlig användning av planeraren och odlingsintresset.
Ingen specialhårdvara eller omfattande daglig journal förutsätts.

| Information | Möjligt sätt att samla den |
| --- | --- |
| Växt, sort och odlingsplats | Återanvänd registreringen i planeraren. Komplettera platsens förutsättningar vid behov. |
| Väderhistorik och prognos | Hämta automatiskt för vald plats; behåll källa, tidpunkt och skillnaden mellan prognos och observation. |
| Sådd, utplantering och andra åtgärder | Återanvänd klarmarkeringar. Skilj när något faktiskt utfördes från när det registrerades. |
| Växternas utveckling | Foton som odlaren väljer att dela samt korta text- eller röstanteckningar. AI föreslår struktur och markerar osäkerhet. |
| Resultat | En enkel återkoppling om exempelvis första skörd, lyckat försök, utebliven skörd eller övervintring. Mängd och arbetsinsats är valfria. |

Väder och bearbetning kan automatiseras. Foton, vissa åtgärder och resultat
kräver fortfarande en liten insats från odlaren. Saknade observationer får
inte tolkas som misslyckanden; en utförd uppgift är inte bevis för ett lyckat
odlingsresultat.

Behåll skillnaden mellan användarens observation, AI:s tolkning och senare
bekräftelse eller rättelse. En rekommendation ska kunna följas tillbaka till
det underlag som fanns när den gavs. Annars riskerar efterhandskunskap att
förväxlas med vad systemet faktiskt kunde förutse.

## Möjlig anslutning till Trädgårdsrytmen

Projektet har redan modeller för trädgårdar, områden, växter och sorter,
versionerade skötselplaner samt utförda och överhoppade uppgifter. En framtida
implementation kan bygga vidare på dessa relationer med säsongsanknutna
observationer, väderunderlag, utfall och förslag till ändrad plan.

Förslag ska visa vad som ändras, varför och hur säkert underlaget är.
Granskning och godkännande av skötselråd ska bevaras, liksom befintlig
historik och avgränsningen mellan olika trädgårdar. En rättad tolkning ska
kunna följas utan att originalobservationen skrivs om.

Exakta modeller, bildlagring, väderleverantör, AI-kostnad och gränssnitt är
öppna implementationsfrågor. Denna idéskiss startar inga integrationer,
AI-anrop, datadelningar eller ändringar i drift.

## Första möjliga experimentet

Nästa odlingssäsong, preliminärt 2027, kan användas för ett litet försök i
den egna trädgården med några utvalda grödor eller odlingsplatser.

**Frågan att pröva:** Kan Trädgårdsrytmen upptäcka när planen behöver ändras
och ge ett råd som odlaren faktiskt har nytta av, med låg registreringsbörda?

1. Dokumentera en enkel ursprungsplan och de viktigaste lokala förutsättningarna.
2. Koppla väderdata till odlingen och samla ett fåtal observationer under säsongen.
3. Visa konkreta förslag till omplanering med skäl och osäkerhet. Utgå från
   etablerad kunskap innan det finns tillräckligt med egna erfarenheter.
4. Bevara vilket råd som gavs, om det följdes och det resultat som faktiskt
   observerades. Använd kort återkoppling när den behövs för utvärderingen.
5. Jämför med ursprungsplanen och enkla kalender- eller väderregler. Bedöm vilka
   råd som ändrade ett beslut, hjälpte i tid eller visade sig missvisande.

Fortsatt utveckling är motiverad om hjälpen påverkar verkliga beslut och
upplevs värd insatsen att använda den. Fler råd eller fler klarmarkeringar är
inte i sig ett framgångsmått. En liten pilot kan pröva användbarheten, men
bevisar inte orsakssamband eller generell skördeökning. Minska omfattningen
om insamlingen blir betungande eller råden inte tillför något utöver basreglerna.

## Möjlig kommersiell utveckling

Första möjliga målgruppen är engagerade hobbyodlare som vill lyckas bättre,
prioritera sin tid och återanvända sina erfarenheter. Ett säsongs- eller
årsabonnemang kan prövas när nyttan är tydlig; pris och betalningsvilja är
inte fastställda. Produkten behöver vara användbar redan första säsongen.

Lokala planteringskalendrar och AI-rådgivning finns redan, exempelvis hos
GrowVeg och RHS. Den tänkta fördelen måste därför visas genom bättre stöd
för den faktiska odlingen och mindre arbete för användaren.

På längre sikt kan frivilligt delade erfarenheter från flera trädgårdar ge
bättre jämförelser mellan sorter och liknande odlingsförhållanden. Både
lyckade och misslyckade försök behövs; skillnader i skötsel och rapportering
begränsar slutsatserna. Datadelning ska vara ett separat, tydligt val.

Plantskolor och fröföretag kan senare vara möjliga partner för råd efter köp.
Det finns inget beslut om att sälja personliga odlingsdata eller bygga en
marknadsplats. Egen odlingsnytta och ett litet verifierbart experiment kommer först.

## Bakgrundskällor

- [SMHI om torka, växtsäsong och vattenbehov](https://www.smhi.se/tema/hantera-vatten-och-klimat/hantera-torka)
  ger klimatbakgrunden; den fastställer inte framtida efterfrågan på hobbyodling.
- [SLU om Naturens kalender](https://www.slu.se/miljoanalys/statistik-och-miljodata/miljodatakatalogen/naturens-kalender/)
  beskriver fenologiska observationer; den validerar inte den föreslagna AI-funktionen.
- [GrowVegs lokalt anpassade kalender och odlingshistorik](https://www.growveg.com/garden-planner-calendar.aspx)
  och [RHS om AI i odling](https://www.rhs.org.uk/garden-inspiration/get-gardening/how-will-ai-change-gardening)
  visar befintliga produktområden att förhålla sig till.
