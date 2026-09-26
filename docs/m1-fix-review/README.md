# M1: lokal granskningsfix 2026-09-26

De tre verifierade fynden är rättade i `/Users/joakimohman/Code/tradgardsrytmen-m1-review-fixes`,
gren `task/m1-review-fixes`, bas `0b3eab4fa200ae09fc2c4cedff2b95ab4114525e`.
Resultatet är redo för ny lokal granskning. Ingen commit, push, merge,
deployment, produktionsdata, riktig AI/push eller extern kontokonfiguration.
Ingen rättning finns i originalet innan separat överföring godkänns.

## Rotorsaker och rättningar

1. **P1, dubblett efter navigation:** skärmen ägde sin egen kopia av utkast och
   busy medan sessionen raderade avslutade avsikter utan publicering. En
   återöppnad vy kunde därför fortsätta med gammal text och en ny nyckel.
   Sessionen äger nu utkast, pending och slutresultat och publicerar en separat
   revision; konto-/trädgårdsgenerationen ändras inte när ett formulär uppdateras.
   Alla tre skapandeflöden visar ”Sparat” efter sen framgång. Gamla submit-anrop
   återger samma bekräftade resultat. Endast ”Börja ett nytt formulär” börjar
   om, och den åtgärden är spärrad för pågående/osäkra avsikter. Fryst kropp,
   nyckel, dubbla-trycksskydd, utkast och kontextisolering består.
2. **P2, förlorad anteckning:** lokal tom sträng skickades även när fältet aldrig
   ändrats. Förekomst av draft.note anger nu uttrycklig ändring. Orört utelämnar
   note, ändrad text skickas som sträng och uttrycklig tömning som `""`.
   UI förklarar effekten och erbjuder bevara/töm. Ingen null skickas.
   Konflikt och läsbekräftelse finns i sessionen, färsk status hämtas även när
   en konflikt anländer efter ommontering. Bekräftelse är spärrad vid pågående
   eller misslyckad färsk läsning. Anteckningsvalet överlever navigation och
   behåller sin exakta form i idempotent återförsök. Ett färdigt kvitto döljer
   inte en senare serverversion vid ny läsning.
3. **P2, sju dagar:** ålder kontrollerades endast före retry-loopen. Kontroll
   görs nu före varje transportanrop, efter eventuell väntan. Vid ålder
   `>= 604800000 ms` behålls avsikt, kropp, nyckel och utkast; avstämning krävs.
   Ingen omnyckling eller automatisk omsändning efter gränsen.

Serverkontraktet lästes i `garden/api_v1.py`, `api_v1_urls.py` och
`api_support.py`. `complete_task` bevarar utelämnad note och skriver tom
sträng uttryckligen. Idempotens/versionsordning och retention har inte
ändrats. V1 saknar redigering och undo/reopen. Ingen backendfil är ändrad.
Syntetisk kontobunden transport, två konton och tre startträdgårdar, inklusive
den tomma, är bevarade.

## Färska kontroller

Körda från fixkopians `mobile/`, Node 26.4.0/npm 11.17.0:

| Kontroll | Resultat / bevis |
| --- | --- |
| `npm test` | **38/38**, inga skips. [Logg](tests.txt). |
| `npm run typecheck` | Godkänd. [Logg](typecheck.txt). |
| `npm run lint` | Godkänd utan varningar. [Logg](lint.txt). |
| `EXPO_NO_TELEMETRY=1 npx expo-doctor` | **21/21**. [Logg](expo-doctor.txt). |
| `EXPO_NO_TELEMETRY=1 npm run export` | Webb-JavaScript samt iOS/Android-Hermes godkända. [Logg](export.txt). |
| Ursprunglig åldersprob | Endast absoluta importvägar ändrade i en kopia; fångat förväntat avstämningsfel före sen retry. [Logg](age-original-probe.txt). |
| Negativa kontrollkörningar | Äldre new.tsx faller på återöppnat pending-läge, äldre task.tsx raderar befintlig text, äldre session.ts skickar efter åldersgränsen. [Skapande](negative-new.txt), [anteckningsförlust](negative-note-loss.txt), [konflikt efter remount](negative-task.txt), [ålder](negative-session.txt). |
| `git diff --check` | Godkänd. |

De 38 proven består av 25 session-/kontraktprov och 13 monterade
skärm-/komponentprov. De ursprungliga 17 finns kvar; konfliktprovet har
anpassats till uttrycklig läsbekräftelse och ny avsikt.

Skärmproven kör de riktiga route-komponenterna, React-hooks, prenumerationerna,
Session och syntetiska transporten. Endast native-värdar, Router/fokus och
Expo-crypto är testdubblar. React-test-renderer 19.2.3 matchar React men
avger sin deprecation-varning; den redovisas i loggen. Verklig Expo-navigation
kontrollerades separat i webbpreview, inte i dessa värdmockar.

Regressionsmatris:

- Trädgård, växt och uppgift: faktisk unmount/remount medan skrivningen väntar,
  ”Sparar…” spärrad, sen framgång → ”Sparat”, gammalt knappanrop → inget nytt
  POST eller nytt objekt, inga sena navigeringar från den gamla skärmen,
  uttryckligt nytt formulär ger tomt utkast.
- Note orörd, ändrad och tömd med befintlig servertext: 409, färsk läsning,
  ommontering, läsbekräftelse och förlorat svar. Retry har exakt samma kropp
  och nyckel; orört saknar note-fält, explicit tomt innehåller `note: ""`.
- Uppgiftsvy ommonteras både före sen framgång och före sen 409. Slutläget
  visas utan andra klarmarkeringar; sen konflikt kräver färsk läsning.
- Verklig PagedList monteras: nästa sida anländer efter ommontering och får
  inte publiceras, därefter nätverksfel och lyckat återförsök med tre unika
  fixtureväxter. Äldre cursor-/filter-/konto-/trädgårdsprov består.
- Återvald identisk trädgård respektive identiskt konto: gamla svar avvisas;
  explicit retry behåller kropp/nyckel och skapar inte en dubblett.
- Förlorad åtkomst ger 404 och lämnar aktiv trädgård; osäker avsikt återanvänds
  före avvisningen. Utkast visas inte i annan trädgård eller annat konto.
- Automatiskt respektive explicit återförsök vid **604799999**, **604800000**
  och **604800001 ms** efter förlorat svar. Före gränsen tillåts replay, på/efter
  blockeras det; exakt ett skapat objekt och ingen blind ny nyckel.

## Interaktiv webbgranskning

Egen Expo-process **35248**, arbetskatalog
`/Users/joakimohman/Code/tradgardsrytmen-m1-review-fixes/mobile`, port **8082**.
Originalets process **19415** på port **8081** har inte ändrats. Processernas
arbetskataloger och kommandon kontrollerades läsande.

- Upprepade den rapporterade Dubbelros-sekvensen: Kim, tre sekunders svar,
  fyra nätverksfel, Lilla lunden → Växter → ny växt, Spara → Tillbaka →
  Växter → ny växt. Återöppnat slutläge visar ”Sparat” och saknar retry-knapp.
  Hela listan lästes via Visa fler: exakt en ”Visa Dubbelros”, ingen ytterligare
  sida. [Slutläge](duplicate-complete.txt), [listan](duplicate-list.txt),
  [390 px](duplicate-complete-390.jpg). Den deterministiska tidpunkten
  *remount medan transporten ännu väntar* styrs dessutom av skärmproven ovan;
  browserklickens exakta timing är inte ett transportloggbevis.
- Kontrollera jorden → Versionskonflikt → klarmarkera, fält orört → färsk
  ”Ändrad i en annan klient.” → läsbekräftelse → klarmarkera. Texten finns kvar
  i utförd uppgift. [Före](note-before.txt), [efter](note-after.txt),
  [320 px](note-preserved-320.jpg).
- Samla fallfrukt: lokalt ändrad anteckning, konflikt, lämna/återöppna,
  bevarat utkast och kvarstående läsbekräftelse, klarmarkera. [Sparat resultat](note-changed.txt).
- Se över uppbindningen: konflikt med befintlig text, uttrycklig tömning med
  tydlig effekttext, läsbekräftelse och klarmarkering. [Avsikt](note-clear-intent.txt),
  [tomt slutresultat](note-cleared.txt).
- Historiken och den bevarade texten lästes på nytt efter kontobyte/ny inloggning.
  Återkallat syntetiskt medlemskap gav återgång till uppdaterat trädgårdsval.
  [Historik](history-after-login.txt), [förlorad åtkomst](revoked-access.txt).
- Sommarstugans tomma växtlista och Alex separata trädgårdslista kontrollerade.
  [Tomt läge](empty-garden.txt), [Alex](account-isolation.txt).
- 320/390/820 px: ingen horisontell overflow i de mätta vyerna. Synliga
  knappar minst 50 px i 320-provet. [320](layout-320.json), [390](layout-390.json),
  [820](layout-820.json), [820-skärmbild](garden-820.jpg).

## Bevarade arbetskopior och granskningsdiff

Startinventeringen omfattade **åtta** befintliga worktrees. Den aktuella
M1-diffen hade 40 filer och SHA-256
`c3982bdaf32e14665428487bc30b48969a42c22cc651b62491c2fbb0a02193b8`.
Alla **193** versionshanterade/icke-ignorerade källfiler överfördes och
hashjämfördes före första ändringen, inklusive nya filer och binära bilder.
Den nya kopians kompletta binärdiff hade exakt samma hash. Ingen gammal
/tmp-patch användes som källa; source.patch skapades från aktuell M1-kopia.

Efter arbetet är samtliga ursprungliga filmanifest, råa index, HEAD, status
och diffar identiska. Kanoniskt repo är fortsatt rent. Ignorerade
runtime-/cachekataloger ingår inte i filmanifesten.
[Isoleringsbevis](isolation.json), [slutjämförelse](isolation.txt),
[källans filmanifest](source-files.json).

Fullständiga före-manifest och kontrollskript ligger i
`/tmp/tradgardsrytmen-m1-fixes-20260926/`.
Där levereras också `fix-only.patch` (enbart skillnaden mot oförändrat M1-original)
och `complete-m1-fixed.patch` (hela slutleveransen mot basen), med hashlista
`patches.sha256`. Båda inkluderar nya filer och binära underlag. Fixkopians
nya filer är intent-to-add; inga innehållsändringar är staged.

## Verifieringsgränser och nästa steg

| Yta | Status |
| --- | --- |
| Webb | Interaktiv syntetisk Expo-preview och skärmprov enligt ovan. |
| iOS | Färsk Hermes-export godkänd. Ingen native körning eller native byggning. |
| Android | Färsk Hermes-export godkänd. Ingen native körning eller native byggning. |
| iOS-simulator | Inte körd; färsk kontroll visar CommandLineTools och saknat simctl/full Xcode. |
| Android-emulator | Inte körd; adb/emulator och `~/Library/Android/sdk` saknas vid färsk kontroll. |
| Fysisk iPhone | Inte verifierad. |
| Fysisk Android | Inte verifierad. |
| Serverbehörighet | Syntetiska rättighetsprov är inte serverbehörighetsbevis. Ingen backend/produktion testad eller ändrad här. |
| Beständighet | Avsikter/utkast finns endast i processminnet. HTTP/Auth0 och beständig avstämning över processdöd hör till I1. |

[Färsk inventering av nativeverktyg](native-environment.json).

Äldre `docs/m1-review/` är bevarade historiska loggar och bilder, inte nya
körningar. Dess auditrapport visar 13 moderate, noll high/critical.
Installationen av de nya testberoendena rapporterade också 13 moderate;
full auditrapport har inte tagits om. Ingen inkompatibel Expo-nedgradering.

Nästa steg är oberoende granskning av denna fixkopia. L1/M2 och nya API-stöd
ligger utanför. Ingen extern tjänst eller riktig transport ska härledas från
att dessa lokala prov är gröna.
