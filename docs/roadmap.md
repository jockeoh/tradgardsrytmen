# Trädgårdsrytmen: genomförandeplan

Status: första arbetsplan, 2026-09-25. Ingen implementation nedan är ännu
verifierad som klar. [Produktmål](product-v1.md) och [arkitektur](architecture.md)
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

## P2 och M1: nästa parallella arbetspaket

P2 implementerar beslutad autentisering och serverflödet. Äldre data får en
explicit trädgård utan att historik skrivs om. Alla tillgängliga datavägar,
även äldre endpoints, måste säkras innan flera kunders data tillåts.
Testa främmande objekt-ID:n, relations-ID:n, listor, sökning, bootstrap och
återkallat medlemskap. Samordna privat webbens övergång till inloggning.

M1 bygger navigation och kärnflödet i React Native/Expo från kontraktet.
Återanvänd visuella beslut och texter. Testa laddning, tomma listor, fel och
utkast. Integrera med P2 vid I1; mobilens exempeldata är inte serververifiering.

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
