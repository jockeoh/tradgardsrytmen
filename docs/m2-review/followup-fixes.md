# M2-PWA: rättningar efter granskning av 1883cec

2026-09-29. Bas `1883cec05096252be2d78569ca78809cc0c6b970`.
Endast arbetskopian `tradgardsrytmen-m2-pwa`, inga extra agenter.
Användaren har beställt rättning, commit/push och därefter roadmapuppdatering.
Ingen serverrelease, produktionsmutation eller verklig AI/push ingår.

## Rättningar

- P1: omritning bygger ett separat formulärunderlag och byter det aktiva
  underlaget först efter lyckad sessionStorage-skrivning. Ett lagringsfel
  lämnar skärmens gamla version intakt och stoppar ny köläggning. När
  lagringen fungerar igen ger det gamla formuläret korrekt versionskonflikt;
  en nyare serveranteckning skrivs inte över tyst.
- P2: varje tidsobservation i synkningen sparar ålder/klockspärr för hela
  den aktiva kön före transport och vid svar/fel. Första postens läsfel kan
  inte lämna senare gamla poster öppna för mutation efter klockbackning.
  Frysta nycklar/kroppar behålls, och senare bekräftade kvitton kan fortfarande
  avsluta spärrade poster utan nya mutationsanrop.
- SW `tradgardsrytmen-v17-m2`, assets `m2-7`. Ingen tvingad aktivering.

## Lokal verifiering

- 60/60 JavaScript: fyra nya regressionstestfall för lagringsfel samt
  flerpostskö med åldersgräns före/under misslyckad kvittoläsning och
  klockbackning ovanför skapandetiden. Samtliga fyra fall fallerar mot
  föregående revision. UI-testet använder levererad kod och DOM-adapter,
  inte en riktig browser.
- 11/11 Django-PWA-tester med CSRF-kontroll och egen filbaserad SQLite.
- 4/4 fristående Python-tester. JS-syntax och diffkontroll gröna.
- Ingen ny full lokal Django-, HTTP-, PostgreSQL- eller browserkörning.
  Tidigare CI för 1883cec rapporterades grön i Linux/macOS/PostgreSQL/mobile;
  detta är separat från nya revisionens kommande CI.

Befintliga manifest, fixes.patch, fixes-changes.json och äldre bevis ändras
inte: de beskriver tidigare revisioner. `followup-manifest.json` beskriver
rättningsfilerna i detta steg och inkluderar inte sig självt eller den
senare roadmapuppdateringen. Fysisk telefon, installerad PWA och full
browserprocessdöd är fortsatt ej verifierade; iPhone/Expo är pausat.
