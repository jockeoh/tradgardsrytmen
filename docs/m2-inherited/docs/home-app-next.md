# Nästa uppgift: ansluten hemmaapp

Beställd inriktning 2026-09-27: användaren vill ha en större samlad
implementation för privat hemmabruk. Undvik att göra kommersiell lansering
eller en lång serie förstudier till förkrav. Implementera ett sammanhängande,
granskningsbart paket och välj enkla lösningar som bevarar data och behörighet.

## Mål och omfattning

Gör befintlig Expo-app användbar mot riktig Django-server: logga in, välj
trädgård, skapa växt och manuell uppgift, klarmarkera och läs historik även
efter appomstart och ny inloggning. Bevara befintlig privat webb.

- Implementera riktig kontobunden HTTP-transport och begriplig inloggning,
  utloggning, sessionsutgång och återanslutning. Bedöm först om befintlig
  Django-identitet kan återanvändas säkert för hemmaappen. Auth0 är tidigare
  målval, men får inte bli ett onödigt externt hinder för privat användning.
  Dokumentera och testa ett enklare privat alternativ om det väljs; ingen
  anonym åtkomst, hårdkodad delad hemlighet eller kringgång av behörigheter.
  Befintligt kontrakt anger Bearer för mobil: eventuell annan lösning kräver
  uttrycklig kontraktsuppdatering med CSRF-/lagrings-/återkallningshantering.
- Bevara information om osäkra sparningar över processdöd. Samma konto,
  begäransnyckel och innehåll ska kunna återanvändas utan dubbletter. Håll
  lösningen liten; en full offlineplattform ingår inte. Bestäm en konkret
  avstämningsväg när säker retry inte längre är möjlig. Ingen blind ny nyckel.
- Behåll M1:s skydd för navigation, orörd/tömd anteckning, färsk serverstatus,
  kontobyte och återkallad åtkomst. Servern är sanningskälla för historik.
- Lägg mobiltester, typkontroll och lint i CI. Uppdatera körinstruktioner och
  kontrakt tillsammans med implementationen. Bedöm befintliga
  beroendevarningar när riktig trafik och inloggningslänkar införs.
- Prova hela flödet mot isolerad riktig server. Kör native på tillgängliga
  iOS-/Android-miljöer och redovisa fysisk telefon, simulator, webb och export
  separat. Saknad enhet ska bli en konkret återstående provpunkt, inte
  stopp för all lokal implementation.

## Klart för granskning när

Två testkonton har åtskild data genom den riktiga servern. Historik består
efter omstart/inloggning. Tappat svar efter serverns sparning och efterföljande
appomstart skapar exakt ett objekt. Främmande ID:n och återkallad åtkomst
avvisas. Sessionsutgång, konflikt och saknad anslutning har begripliga
återvägar. Befintliga relevanta regressioner och nya riktade prov passerar.
Leveransen innehåller tydliga körinstruktioner och kvarvarande aktiveringssteg.

## Arbetsform och gränser

Arbeta i en ny isolerad worktree från aktuell main. Kanoniskt repo är
`/Users/joakimohman/Code/tradgardsrytmen`; föräldern Code är inget Git-repo.
Denna dokumentuppdatering kan vara ocommittad där: läs och överför exakt de
aktuella dokumenten till den nya kopian utan att ändra andra arbetskopior.
Original-M1, fixkopian och äldre referensworktrees ska lämnas orörda.

Lokal implementation och isolerade testdata ingår. Användaren har beställt
en ny uppgift med GPT-6 Astra, low. Starta inga extra agenter.
Ingen commit/push, produktionsrelease, produktionsdatamutation eller
extern tjänsteaktivering ingår i denna beställning. Förbered hela paketet
för granskning; redovisa därefter konkreta eventuella aktiveringsbeslut.

AI, push, köp, publik registrering, familjeinbjudningar och butikslansering
är senare arbete. Redigering/ångring behöver inte läggas till för detta mål.
L1:s kommersiella beslut blockerar inte hemmaappen. Nya leverantörskonton,
molnbyggen och faktiska externa AI-/pushprov kräver separat beställning.
