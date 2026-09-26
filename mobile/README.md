# Trädgårdsrytmen M1

Lokal Expo/TypeScript-klient med syntetiska data, inte en ansluten tjänst.
Expo SDK 57 / React Native 0.86.3 / React 19.2.3, Expo Router.

## Körning

```sh
cd mobile
npm ci
npm run typecheck
npm run lint
npm test
EXPO_NO_TELEMETRY=1 npm run web -- --localhost --port 8081
npm run export
```

Node >=22.13 enligt SDK 57 (verifierad med Node 26.4.0/npm 11.17.0).
`npm run ios` / `npm run android` kräver tillgänglig simulator/emulator
eller rätt Expo-miljö på telefon. Molnbyggen, butik och extern identitet
är inte konfigurerade. Export kompilerar JavaScript/Hermes för tre plattformar,
men ersätter inte körning eller native bygge.

## Prova

Kim har Lilla lunden samt tomma Sommarstugan. Alex har en separat balkong.
Välj konto → trädgård → Växter → lägg till/öppna växt → lägg till uppgift →
markera utförd → läs historik. Skapa också en egen provträdgård.
Listorna visar två poster per sida för att göra cursorflödet synligt.
Historik har separata val för utförd, överhoppad och arkiverad.
Saknad uppgift betyder inte att en skötselplan finns.

Formulär sparas bara i minnet för konto+trädgård+formulär/objekt. Navigation
och trädgårdsbyte inom kontot bevarar utkast; explicit utloggning, sessionens
401, kontobyte och appomstart rensar. Syntetiska sparade objekt lever vidare
vid kontobyte i samma körning men återställs vid omstart. Ingen offlinekö,
lagring på disk eller anslutning till produktionsdata finns.

Provverktyg på kontosidan ger nätverksfel, 401, 403 och långsamma svar.
Uppgiftsdetalj ger versionskonflikt, tappat svar efter skrivning, fyra
nätverksfel och återkallat medlemskap. Starta om previewn för att återställa
medlemskap. Felinjektionen gäller nästa anrop, även en läsning. Tester
injekterar även 429/503, främmande objekt/relationer och sena svar.

## Struktur och kontraktsgräns

- `src/app/`: Expo Router-vyer. `src/ui/`: gemensam svensk mobil-UI och
  fokusbundna läsningar/paginering.
- `src/core/session.ts`: konto-/trädgårdsgeneration, avbrutna anrop,
  avskilda utkast och frysta idempotenta avsikter.
- `src/api/contract.ts`: wire-fält och utbytbart `Transport`-interface.
- `src/api/synthetic.ts`: separat minnesbaserad testdubbel; en transport
  binds till ett konto, aldrig till ett globalt förändrat konto/token.
- `tests/client.test.ts`: klientprov plus läsande jämförelse av fixturefält
  med de aktuella Python-serialiserarna. Inte serverbehörighetsbevis.

Alla stödda skrivningar använder en slumpad UUID per avsikt. Timeout,
429 och 503 återanvänder samma kropp/nyckel: initialt försök + högst tre
automatiska försök med exponentiell väntan/jitter och Retry-After.
Efter uttömda försök fryses formuläret; uttryckligt återförsök använder
samma avsikt. Byte av kontext stoppar vidare återförsök och publicering.
Äldre än sju dagar kräver avstämning. Inget nytt osäkert försök skapas
under en befintlig avsikt. Versionskonflikt hämtar färsk status och kräver
uttrycklig läsbekräftelse; anteckningen finns kvar.

Riktig HTTP-transport, samordnad tokenrefresh (högst en gång), Auth0/PKCE,
säker tokenlagring och verifierad logout/revoke hör till I1. M1 har inga
tokens och låtsas därför inte implementera refresh: 401 avslutar provsessionen.
I1 måste dessutom besluta beständig hantering av oklara skrivutfall över
processdöd/utloggning och prova retention/reconciliation innan riktig trafik.

V1 saknar PATCH/PUT och undo/reopen. Appen erbjuder inte dessa åtgärder.
Ingen ändring av backend eller API-kontrakt ingår. `note: null` är en känd
skillnad mellan dokument och serverkod (server bevarar anteckningen);
klienten utelämnar note när fältet är orört och skickar sträng (även uttryckligt tom) när det ändrats. Ingen null skickas; testdubbeln följer dokumentet där.
Provservern är avsiktligt ingen full serveremulator: cursor är kontrollerat
opak i minnet, inte Djangos signerade cursor; UUID/nycklar och wire-fält följer
kontraktet. Riktiga HTTP-statusar, headers, 30-dagars cursorutgång, databas-
konkurrens och rättigheter måste provas mot P2 i I1.

Se [M1-överlämningen](../docs/m1-handoff.md) för verifieringsmatris och luckor.

## Lokal granskningsfix 2026-09-26

Aktuell fixkopia: `/Users/joakimohman/Code/tradgardsrytmen-m1-review-fixes`,
gren `task/m1-review-fixes`. Originalet `tradgardsrytmen-m1` är oförändrad
referens. Använd port 8082 för denna kopia; originalets 8081 tillhör originalet.

Formulärets utkast, pågående begäran, konflikt och bekräftade resultat ägs av
sessionen och publiceras till prenumererande skärmar utan att byta
konto-/trädgårdsgeneration. Efter sen framgång visar återöppnat skapande
”Sparat”. ”Börja ett nytt formulär” är en uttrycklig ny avsikt; en gammal
sparknapp kan bara få tillbaka det bekräftade resultatet. En osäker avsikt
kan inte nollställas med denna åtgärd.

Orört anteckningsfält utelämnas från klarmarkeringen. Ändrad text ersätter
befintlig text; uttrycklig tömning skickar tom sträng. Valet och
konfliktbekräftelsen överlever navigation. Den frysta återförsökskroppen
bevarar också skillnaden. Sjudagarsspärren kontrolleras före varje faktiskt
transportförsök, inklusive efter väntan och explicit återförsök.

`npm test` omfattar nu 38 prov, varav 13 monterar riktiga skärmar/listkomponenter
med React, deras hooks, session och syntetisk transport. Native-värdar,
Expo-crypto och Router/fokus är små testdubblar i `tests/support/`; verklig
Expo-navigation provas separat i webbpreview. React-test-renderer 19.2.3
matchar React-versionen men ger sin kända deprecation-varning. Detta är
inte native layout-/simulatorprov. Se [färska resultat](../docs/m1-fix-review/README.md).
