# M1: separat lokal granskningsfix, 2026-09-26

**Git-publicering 2026-09-26:** användaren har efter verifieringen beställt
commit/push av hela M1-leveransen till main. Granskningsunderlaget nedan
beskriver tillståndet före publiceringen. Serverrelease, riktig transport
och mobilintegration aktiveras inte av denna Git-leverans.

De tre verifierade fynden är rättade **endast i fixkopian**:
`/Users/joakimohman/Code/tradgardsrytmen-m1-review-fixes`, gren
`task/m1-review-fixes`, bas `0b3eab4fa200ae09fc2c4cedff2b95ab4114525e`.
Ingen commit, push, merge eller deployment. Originalets M1-kopia och index,
kanoniskt repo samt övriga arbetskopior är bevarade och hashkontrollerade.

- Gemensamt prenumererbart formulärtillstånd och bekräftat slutresultat
  förhindrar att ett återöppnat skapande blir en ny avsikt efter sen framgång.
- Orörd note utelämnas; ändrad/tömd note skickas som sträng. Utkast,
  konfliktbekräftelse och fryst återförsökskropp bevarar avsikten vid navigation.
- Sjudagarsspärr före varje transportförsök, även efter väntan.

Färskt: **38/38 tester**, typkontroll och lint, Expo doctor **21/21** samt
webb/iOS/Android-export godkända. Monterade skärmregressioner, negativa
kontroller mot äldre kod och upprepade webb-reproduktioner ingår.
Se [full rättningsrapport, loggar, UI-bevis och gränser](m1-fix-review/README.md).
Export är inte native körning. Simulator/emulator och fysisk telefon är
fortsatt ej verifierade; riktig HTTP/Auth0 och beständig avstämning hör till I1.
L1/M2 och externa tjänster ingår inte.

---

Följande är **ursprunglig M1-överlämning och historiska kontrollresultat**.
Dess kopieadresser och testantal avser originalet, inte rättningskopian.
Rättningsrapporten ovan ersätter beskrivningarna av formulärlivscykel,
anteckningsfält och återförsök där de skiljer sig.

# M1: lokal Expo-klient, 2026-09-26

Redo för lokal granskning. Ingen commit, push, merge eller deployment.

- Arbetskopia: `/Users/joakimohman/Code/tradgardsrytmen-m1`
- Gren: `task/m1-expo-manual`
- Bas: `0b3eab4fa200ae09fc2c4cedff2b95ab4114525e`
- Lokal main, origin/main och läsande `ls-remote` bekräftade samma SHA.
- Kanonisk checkout var ren. Sju tidigare arbetskopior inventerades;
  ingen Expo-klient hittades i projektfiler, grenar eller arbetskopior.
  Inga tillämpliga AGENTS.md fanns i föräldrarna/projektet. Expos nya
  `mobile/AGENTS.md` följdes för SDK 57, Router, typkontroll och lint.
- Filer i de sju tidigare arbetskopiorna hashades före implementation;
  slutjämförelsen är dokumenterad i `m1-review/isolation.txt`.

## Leverans

`mobile/` innehåller Expo SDK 57, TypeScript och Expo Router. Svenskt flöde:
provkonto → trädgård → växt → manuell uppgift → utförd → historik.
Trädgård/växt/uppgift kan skapas; detaljer och historiska anteckningar visas.
Historik skiljer utförd, överhoppad och arkiverad. Saknad skötselplan visas
uttryckligen. Listor har cursor och två poster/sida i provmiljön.

Två konton och tre startträdgårdar (en tom) finns i en helt separat
syntetisk transport. Ingen riktig data, token, API-basadress, fetch,
Auth0, AI, push, beständig lokal lagring eller kö ingår.

Utkast binds till konto+trädgård+formulär/objekt. Konto-/trädgårdsbyten
avbryter anrop och byter generation; även transporter som ignorerar avbrott
får inte publicera sena svar. Fokusbyte spärrar sen formulärnavigation.
Kontobyte/utloggning/401 rensar utkast; trädgårdsbyte inom kontot bevarar dem.
Minnesserverns historik finns kvar över login i samma körning, inte appomstart.

Skrivningar fryser slumpad UUID, kropp och ursprungskontext. Dubbla tryck
delar samma pågående avsikt. Nätverksfel, 429 och 503 ger högst tre
automatiska återförsök efter första anropet, exponentiell väntan/jitter och
Retry-After. Efter osäkert svar låses utkastet och explicit återförsök
behåller samma nyckel/kropp. Sjudagarsgräns kräver avstämning, inte ny nyckel.
409 hämtar aktuell uppgift och bevarar lokal anteckning; användaren behöver
bekräfta att den nya statusen är läst före ny klarmarkering i samma vy.
404 återför användaren till uppdaterat trädgårdsval; 401 till provkontoval.

## Kontrakt och avvikelser

`docs/api-v1.md`, `architecture.md`, `product-v1.md`, `roadmap.md` och
`p3-activation.md` lästes. Stödet verifierades mot `garden/api_v1.py`,
`api_v1_urls.py` och `api_support.py`.

- V1 har **ingen redigering eller ångring/återöppning**. Bara skapande och
  klarmarkering exponeras. Sparade objekt har inga falska redigeringsknappar.
  Utökat stöd kräver separat kontraktsbeslut; ingen backendfil är ändrad.
- Wire-fält jämförs i tester med Python-serialiserarnas faktiska nycklar.
  ID:n är opaka strängar; fixtures använder UUID. Cursor följer listformen
  och binds till konto, resurs och filter, men är en opak minnesmarkör,
  inte Djangos kryptografiskt signerade cursor med 30 dagars giltighet.
- Testdubbeln är ingen full serveremulator: HTTP-headers/statusleverans,
  tokenverifiering, databastransaktioner, samtidig behörighetsåterkallning och
  verklig idempotensretention är **inte** verifierade av klientproven.
- Dokumentet förbjuder implicit null i `note`; servern accepterar null som
  bevara befintligt. Klienten skickar alltid sträng. Ingen kontraktsändring.
- M1 saknar tokenrefresh. Syntetisk 401 avslutar sessionen; verklig samordnad
  refresh högst en gång tillhör I1. Säker rensning prioriteras över att
  återställa utkast efter utgången session.

## Verifiering

Körning och filstruktur finns i [mobile/README.md](../mobile/README.md).
Node 26.4.0, npm 11.17.0. Låst `package-lock.json` ingår.

| Kontroll | Faktiskt resultat |
| --- | --- |
| `npm test` | 17/17 godkända, inga skips; [logg](m1-review/tests.txt). |
| `npm run typecheck` | Godkänd; [logg](m1-review/typecheck.txt). |
| `npm run lint` | Godkänd utan varningar; [logg](m1-review/lint.txt). |
| `npx expo-doctor` | 21/21; [logg](m1-review/expo-doctor.txt). |
| `npm run export` | Webb-JavaScript samt iOS/Android-Hermes godkända; [logg](m1-review/export.txt). |
| Webbpreview | Kördes lokalt på localhost:8081. Manuell browsergranskning vid 320, 390 och 820 px; se nedan. |
| iOS-simulator | Inte körd. `xcode-select -p` pekar på CommandLineTools; `xcrun simctl` saknas, ingen full Xcode-installation. |
| Android-emulator | Inte körd. `adb`, `emulator` och `~/Library/Android/sdk` saknas. |
| Fysisk iPhone | Inte verifierad; ingen telefon kopplad till proven. |
| Fysisk Android | Inte verifierad; ingen telefon kopplad till proven. |
| Backend/produktion | Inte testad eller ändrad i M1. Klientprov bevisar inte serverbehörigheter. |

De 17 automatiska proven omfattar hela manuella flödet inklusive historik
efter syntetisk återinloggning; två konton; två egna trädgårdar; tomt läge;
främmande objekt/relationer; cursor med ändrat konto/filter/trädgård; sena
läsningar/skrivningar trots ignorerat avbrott; konto- och trädgårdsutkast;
revokerat medlemskap före replay; 401/403; version/transition/idempotency-
konflikt; ogiltiga fält/datum; dubbla tryck; tappat svar efter commit;
429/503/backoff; byte under återförsök; sjudagarsgräns; inaktiv växts historik.

Browserprovet skapade Provträdgården → Päronträd → Vattna päronträdet,
bevarade växtutkast efter navigation, visade versionskonflikt med bevarad
lokal anteckning, återhämtade tappat skrivsvar, visade utförd historik och
skilde Alex konto från Kims trädgårdar. Paginering verifierades i Lilla
lunden. Nätverksfel visade explicit återförsök som återställde listan. Utgången
provsession visade kontoval och rensade den aktiva trädgårdsvyn. 320 px hade ingen horisontell
overflow och synliga knappar var minst 50 px höga. Detta är webbprov,
inte touch-/tangentbords-/skärmläsarprov på native telefon.

Skärmbilder: [konflikt vid 390 px](m1-review/conflict-390.png),
[utförd uppgift vid 320 px](m1-review/completed-320.png),
[översikt vid 820 px](m1-review/garden-820.png).

Beroendegranskning: `npm audit` rapporterade 13 **moderate**, noll high/critical.
Rotvarningar är `decode-uri-component <=0.4.2` (malformerad URI/DoS via
Expo Router/query-string) och äldre transitiv `uuid` (buffergränser i vissa
UUID-funktioner via Xcode/Expo-byggverktyg). Audit föreslog inkompatibla
nedgraderingar av Expo/Router; inga sådana genomfördes. Expo-kompatibla
Worklets/Reanimated låstes explicit efter initial peer-varning. Innan
externa länkar/riktig I1-trafik aktiveras måste beroendevarningarna bedömas
på nytt. [Auditrapport](m1-review/npm-audit.json).

## Kvar före I1

1. Implementera riktig kontobunden HTTP-transport och kontraktprov mot P2,
   inklusive headers, fel, cursor, medlemskap och idempotens över processer.
2. Separat godkänd Auth0 EU/native client, PKCE och verifierbara länkar;
   säker tokenlagring, samordnad refresh, återkallning och logout.
3. Beständig, kontoavskild avstämning av oklara skrivutfall över processdöd
   och ny inloggning. M1:s minnesavsikter är inte en produktionslösning för det.
4. Kör hela flödet mot riktig testserver på iOS och Android; verifiera
   bestående historik efter appomstart/inloggning, native navigation,
   tangentbord, tillgänglighet och fysisk telefon separat från simulator.
5. Besluta separat om redigering/ångring ska tillföras v1. L1, M2,
   native AI, push och betalning är fortsatt utanför M1.

SDK-val/installationsväg verifierades mot [Expo SDK 57](https://docs.expo.dev/versions/v57.0.0/)
och [officiell Router-installation](https://docs.expo.dev/router/installation/).
