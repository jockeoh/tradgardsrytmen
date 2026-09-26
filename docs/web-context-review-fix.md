# Fynd 4: färdig lokal rättning för integration

Arbetskopia: `/Users/joakimohman/Code/tradgardsrytmen-p123-review-fixes/web-context`.
Jämförelse: systerkatalogen `baseline`, inte git HEAD (som saknar ursprunglig P3).
Ingen commit/push/deployment/produktion/aktivering eller verklig extern transport.

## Kontrakt

`web_context_token` signerar konto-UUID, trädgårds-UUID och medlemskaps-PK vid
sidrendering. Samtliga äldre API-rutter kräver tokenet på läsningar och skrivningar.
Aktivt konto, sessionens val och exakt levande medlemskap måste matcha innan
vyn anropas. Inget API-anrop får automatiskt falla tillbaka till en annan
trädgård. Återskapat medlemskap återupplivar inte ett tidigare sidtoken.
CSRF gäller fortfarande. Nekad kontext ger 409/context_changed; utloggad eller
inaktiv användare ger 401. API-svar, även kontextfel, har no-store.

Klienten fryser sidtokenet och tillåter inte anropsspecifika headers att ersätta
det. 401 navigerar inte bort från utkast. Fel lämnar formuläret öppet, bevarar
fält/in-memory-utkast och sparar dynamiska formulärets konto-/trädgårdsskopade
utkast före submit. Ingen automatisk omsändning. Ett giltigt ursprungligt
medlemskap kan återanvända sin sida efter återgång till rätt konto/trädgård.
Nytt medlemskap kräver ny sida. Versionsmarkör 20260926context1 och SW v9.

## Ändrade filer relativt baseline

- docs/api-v1.md
- docs/multiuser-transition.md
- docs/web-context-review-fix.md (ny rapport)
- garden/api_support.py
- garden/static/garden/app.js
- garden/static/garden/sw.js
- garden/templates/garden/index.html
- garden/test_accounts.py
- garden/test_demo.py
- garden/test_p2_api.py
- garden/test_web_context.py (ny)
- garden/testing.py
- garden/views.py (endast import + en rad i index render-kontext)
- tests/design-review.test.cjs

## Verifiering

Runtime `/tmp/tradgardsrytmen-p3-runtime/bin/python`, OPENAI_API_KEY tom,
DATA_DIR=/tmp/web-context-data. Egna temporära SQLite-testdatabaser.

- 97/97 riktade Django-tester: garden.test_web_context, garden.test_p2_api,
  garden.test_accounts, garden.test_demo, garden.tests, garden.test_care_lifecycle,
  garden.test_design_review. Logg `/tmp/web-context-tests.log`.
- 15/15 Node-tester. Logg `/tmp/web-context-js.log`.
- Hela SQLite-sviten: 128 tester, 127 godkända. Enda fel är
  `garden.test_jobs.JobTests.test_job_api_does_not_leak_other_actor_or_garden`:
  den äldre testklienten saknar token och får nu korrekt 409. Filen tillhör
  integrationsägaren och är medvetet orörd här. Importera `bind_web_context`
  från garden.testing och anropa den efter båda force_login i testmetoden.
  Logg `/tmp/web-context-full-tests.log`.
- Django check, makemigrations --check --dry-run, node --check app.js och
  git diff --check passerar.
- Baselines samtliga manifesthashar verifierades oförändrade.

Nya serverprov använder riktig sessions-/CSRF-hantering: initialt ensamt
trädgårdsval, två flikar, byte tillbaka, kontobyte med tillgång till samma
trädgård, återkallning, automatisk fallback på en ny sida, återskapat medlemskap,
saknat/förfalskat token, saknat sessionsval, inaktivt konto, saknad CSRF samt
alla äldre rutter med GET/POST/PATCH/DELETE före dispatch.
Klientprov kör levererade funktioner: fryst header även vid ändrad DOM/cookies,
401/409 med öppet formulär och bevarad anteckning, utkastisolering mellan konton
och trädgårdar samt återläsning för ursprunglig kontext.

## Integrationsgräns

PostgreSQL, gemensam fullsvit, konkurrensprov och backup-/överföringsprov ägs av
jobs-integration och återstår där. Ingen fysisk browser/telefon eller produktion
har verifierats. Tidigare redan öppna klienter utan sidtoken får ett säkert 409;
ny sida krävs. Ingen ändring av OIDC, köflagga eller extern körning.
Arbetskopian hålls stilla efter slutmeddelandet till integrationsägaren.
