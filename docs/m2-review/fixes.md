# M2-PWA: rättning av tre granskningsfynd

2026-09-29. Endast arbetskopian `tradgardsrytmen-m2-pwa`, gren
`task/m2-pwa-offline`, bas `59d4c4c0bcae86778a8b6c54e21371d011679cd9`.
Ingen commit/push, deployment, produktionsmutation eller verklig AI/push.
Inga extra agenter.

## Åtgärdat

- **P1, formulär och flikar:** enqueue tar en kopia av det bekräftade
  formulärets uppgift/version och faktiska anteckningsfält. Det sker före
  väntan på Web Lock. Flikens utkast sparas i egen sessionStorage med
  ursprunglig version, scope och sessionsgräns; en annan fliks uppdatering
  kan inte ändra avsikten. Orörd anteckning utelämnas, uttrycklig tömning
  förblir `""`. Gemensam beständig kö och fliklås är kvar.
- **P1, logout/CSRF:** varje logoutförsök läser aktuell cookie. Saknad CSRF
  hämtas via vanlig login-GET; 403 medger ett begränsat omförsök med aktuell
  token. Äldre journaler med fryst CSRF återhämtas också. Loginspärren
  försöker på nytt efter tidigare nätfel, och formulärets CSRF uppdateras
  inför login. Stoppspärren kvarstår tills serverlogout lyckats. Kö, fryst
  key/body och signerad ursprunglig medlemskapskontext bevaras.
- **P2, sjudagarsgräns:** beständig `readOnlyReason` sparas före kvittoläsning
  och kontrolleras igen före mutation och vid fel. `lastObserved` upptäcker
  även klockbackning som inte passerar skapandetiden. Spärren kvarstår efter
  klockjustering/omstart; kvittoläsning och bekräftelse fungerar fortfarande.
  Ingen blind ny nyckel införs. Explicita konfliktval kräver fortsatt en
  definitiv konflikt och ny serverläsning.

SW/assetversioner höjda till `tradgardsrytmen-v16-m2` / `m2-6` på samtliga
fem referensfiler. Ingen tvingad workeraktivering eller kömigrering.

## Verifiering och egen slutgranskning

- **56/56 JavaScript**, inklusive 40 motor-/UI-prov. Båda rapporterade
  flikförloppen, faktiskt levererade formulär-/login-skript, tom/orörd
  anteckning, omladdade utkast, aktuell/roterad/äldre fryst CSRF, bestående
  403, tidsgräns med okänt/senare bekräftat kvitto, klockbackning, läsfel
  över tidsgränsen och lagringsfel täcks. UI-proven använder en liten
  DOM-adapter och kontrollerad transport: **inte riktiga browserprov**.
- **281 Django-tester passerade**, inklusive två nya prov med
  `Client(enforce_csrf_checks=True)` för anonym CSRF-bootstrap och verklig
  tokenrotation vid login. Hela körningen fann 282 tester men avslutades
  med ett miljöfel: `garden.test_pwa_http` kunde inte starta loopbackserver
  (`PermissionError: Operation not permitted`). Därför är hela Django-
  körningen inte grön och HTTP/processdödsprovet inte återverifierat.
- **4/4 fristående Python**, Django check, migrationskontroll, JS-syntax
  och diffkontroll passerade. Python är **3.12.14**, trots miljönamnet
  `/tmp/m2-pwa-py313`. Filbaserad SQLite via `config.p3_sqlite_test_settings`,
  `P3_SQLITE_TEST_PATH=/tmp/m2-fixes-django.sqlite3` och
  `TRADGARDSRYTMEN_DB_PATH=/tmp/m2-fixes-unused.sqlite3`; kontrollkommandona
  hade separata temporära sökvägar. Ingen normal databas användes.

Egen slutgranskning kontrollerade payloadbindningen före asynkron väntan,
konfliktval, stoppspärr vid logout, samma key/body över omstart, negativa
konto-/grant-prov och att lagringsfel inte tillåter transport eller lämnar
privat DOM synlig efter logout. Inga kvarvarande fel i de tre fynden hittades.

## Exakta ändringar och bevarande

Ändrade filer jämfört med den mottagna, ocommittade leveransen:

- `garden/static/garden/offline-core.js`
- `garden/static/garden/offline-session.js`
- `garden/static/garden/worklist.js`
- `garden/static/garden/worklist.html`
- `garden/static/garden/sw.js`
- `garden/templates/garden/index.html`
- `garden/templates/garden/select_garden.html`
- `garden/templates/registration/login.html`
- `garden/test_pwa.py`
- `tests/pwa-offline.test.cjs`
- `tests/pwa-http-driver.cjs` (anpassat till explicit formulärpayload)
- `docs/m2-pwa.md`
- `docs/m2-review/final-manifest.json`

Nya underlag i `docs/m2-review/`: `fixes.md`, `fixes.patch`,
`fixes-changes.json`, `fixes-before-manifest.json`, `fixes-javascript.txt`,
`fixes-django.txt` och `fixes-checks.txt`. Patchen isolerar rättningarna från
ursprunglig implementation; ändringsmanifestet visar före-/efterhashar.
Slutmanifestet omfattar hela leveransen och dessa nya underlag, men inte
sig självt.

Före ändring verifierades alla **41** ursprungliga slutmanifestposter och
alla **åtta** dokumentkopior. **297** tracked/untracked filer inventerades.
`docs/m2-inherited`, källmanifestet, roadmap, API-/arkitekturdokumentens
befintliga ändringar och tidigare browser-/testartefakter har bevarats.
Ingen annan arbetskopia eller main har ändrats.

## Begränsningar

Ingen ny riktig browserkörning, fysisk telefon, installerad PWA, full
browserprocessdöd eller PostgreSQL-verifiering. Ursprungliga browserbevis
avser m2-5. HTTP-provet ovan är blockerat av miljön; ingen spärr kringgicks.

Oköade nya formulärutkast följer flikens sessionStorage-livslängd, inklusive
omladdning; köade avsikter ligger fortsatt i beständig localStorage. Äldre
delade m2-5-utkast saknar säker versions-/flikbindning och återanvänds inte
som nya formulär; de lämnas i journalen tills ordinarie logout-rensning.
Gamla redan öppna klienter kör gammal kod tills de laddas om. Alla äldre
flikar kan behöva stängas för att nya workern ska aktiveras. En lokal klocka
kan bara spärras för förändringar som klienten faktiskt har observerat.


## Efterföljande dokumentuppdatering 2026-09-29

På användarens begäran uppdaterades därefter `docs/roadmap.md` med lokal
M2-status, verifieringsluckor och ordnad plan för granskning, kompletterande
prov, separat publiceringsbeslut och senare PWA-uppföljning. Kod, tester,
källmanifest och `docs/m2-inherited` ändrades inte i detta dokumentsteg.

Roadmapens tidigare innehåll är byteidentiskt bevarat i
`docs/m2-review/roadmap-before-update.md`; dess hash motsvarar roadmap-posten
i ursprungligt källmanifest. Bevarandebeskrivningen i `docs/m2-pwa.md` och
slutmanifestet uppdaterades också. `fixes.patch` och `fixes-changes.json`
beskriver fortfarande kodrättningssteget före denna dokumentuppdatering.
Ingen main-ändring, commit/push eller release gjordes.
