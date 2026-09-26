# Trädgårdsrytmen: produktmål för första mobilversionen

**Aktuell drift 2026-09-26:** den privata releasen, PostgreSQL 17.11 och
DURABLE_JOBS=1 är nu verifierat aktiva, med schema 0014 och OIDC av.
[Driftbevis, backupgränser och operatörsrutin](p3-activation.md) ersätter
äldre lokalstatus/ej aktiverat i de daterade avsnitten nedan.


Status: 2026-09-26. P1/P2 finns på main; P3 och rättningar är lokalt verifierade
men inte driftsatta. Privat SQLite-release är möjlig med de särskilda
[releasevillkoren](private-release-review.md), oberoende av butikslanseringen.
M1:s Expo-klient och separat färdig L1-leverans är inte verifierade i tillgängligt
underlag. Auth0 EU är beslutad riktning men inte verifierat aktiverad.
Läs tillsammans med [arkitekturen](architecture.md) och [arbetsplanen](roadmap.md).

## Överenskommen riktning

Utveckla dagens privata trädgårdsverktyg mot en tjänst som kan lanseras för
både iPhone och Android. Behåll och vidareutveckla Django på servern; bygg
mobilgränssnittet separat med React Native och Expo. Nuvarande webbapp får
fortsätta fungera under övergången. Detta är inte ett beslut om publik drift
eller om att alla föreslagna funktioner ska byggas omedelbart.

## Målgrupp och nytta — förslag

Första målgruppen är svenska privatpersoner som vill veta vad som behöver
göras i den egna trädgården och bevara historiken. Visa en begriplig nästa
handling, med källor och osäkerheter tillgängliga bakom detaljer.
Behåll den botaniska visuella identiteten och skilj saknad skötselplan från
att en trädgård faktiskt är i fas.

## Första verifierbara milstolpen

Skapa konto → skapa trädgård → lägga till växt → skapa en manuell
skötseluppgift → markera den klar → se samma historik efter ny inloggning.

Flödet ska fungera mot samma server från iPhone och Android. Två oberoende
konton ska ha separata trädgårdar. En användare får inte läsa eller ändra
en annan trädgård genom att ändra identifierare i ett anrop.
Manuella uppgifter gör denna milstolpe oberoende av AI och köp.

P2 verifierar nu serverdelen av flödet lokalt via `/api/v1/`: två konton,
separata trädgårdar, växt, manuell uppgift, klarmarkering, versionskonflikt,
återförsök och bevarad historik. Det är inte samma sak som I1: fysisk iPhone,
Android och faktisk konfiguration/prov av vald Auth0 EU-tenant återstår.

## Föreslagen omfattning för en första butikslansering

- Konto, inloggning, återställning och hantering av användardata.
- Egen trädgård, områden, växter, skötseluppgifter och bevarad historik.
- Tydlig lista över aktuellt arbete och möjlighet att slutföra uppgifter.
- AI-råd startas uttryckligen, bearbetas i bakgrunden och granskas före aktivering.
- Påminnelser med användarens val av tid och möjlighet att stänga av dem.
- Begripligt beteende vid dålig täckning; exakt offlineomfattning beslutas separat.
- Om lanseringen är betald: köp, återställning av köp och korrekt tillgång
  även efter förnyelse, uppsägning eller återbetalning.
- Tillgänglighet, supportkontakt, integritetsinformation, export/radering,
  driftövervakning och återställningsbara säkerhetskopior.

Delade trädgårdar ska stödjas av modellen från början. Inbjudningar och
familjedelning i gränssnittet behöver inte ingå i första milstolpen.

## Utanför första milstolpen

Betalningar, riktiga AI-anrop, pushutskick, full offline-redigering,
växtidentifiering via kamera, sociala funktioner, handel med fysiska varor,
flera språk och en omskrivning av hela webbgränssnittet.

## Öppna produktbeslut

| Fråga | Arbetsförslag | Måste avgöras före |
| --- | --- | --- |
| Vem betalar? | Abonnemang knutet till trädgård, personligt köpkonto | Betalningsmodellens implementation |
| Vad ingår? | Manuell planering och en tydligt begränsad AI-kvot | Prissättning och AI-budget |
| Delning vid lansering? | Modellen stödjer flera medlemmar; UI kan komma senare | Fastställande av lanseringsomfattning |
| Offline? | Läsa arbetslistan och köa klarmarkeringar | Implementation av synkning |
| Webbens framtid? | Behåll befintlig webb under övergången | Större investering i webbgränssnittet |
| Marknad? | Sverige först | Butiks- och betalningsupplägg |

Inga priser, leverantörsavtal eller användarkvoter är beslutade.

## Produktkriterier

Användaren ska kunna slutföra kärnflödet utan AI eller köp. Utkast och pågående
arbete ska överleva normal navigation. Fel ska ha en begriplig återväg.
Lansering kräver dokumenterad provning på båda plattformarna; simulatorprov
ska inte beskrivas som verifiering på fysiska telefoner.
