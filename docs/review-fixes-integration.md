# Samlad lokal rättning av sju granskningsfynd

Datum: 2026-09-26. Enda integrerade arbetskopian:
`/Users/joakimohman/Code/tradgardsrytmen-p123-review-fixes/jobs-integration`.
Bas: `6606e76c8f30d42ff364c0ebfecfd10c13c5d31d` plus hela granskade ocommittade
P3. Syskonens färdiga ändringar infördes med trevägsjämförelse mot `baseline`;
båda syskonkopiorna är bevarade. Ingen commit/cherry-pick har gjorts.

## Senare oberoende granskning och kompletterande rättning

Den senare granskningen fann tre kvarvarande transportluckor trots nedanstående
152 gröna tester. Dessa är nu rättade lokalt; slutligt underlag, 254/254 tester
på båda databaserna och nytt integritetsbevis finns i
[transportgränsens rättningsrapport](transport-boundary-review-fixes.md).
Resultat och påståenden nedan beskriver den tidigare integrationsomgången.

## Evidens per fynd

| Fynd | Rättning | Negativ regression |
| --- | --- | --- |
| 1 | Gemensamt trädgårdslås före läsning/ändring i äldre PATCH och v1, samt materialisering, godkännande, bortval och historik. Version ökas även vid byte av regel/arbetsidentitet. | `test_legacy_patch_serializes_v1_and_cannot_erase_completion` pausar PATCH efter omläsning på en anslutning; andra anslutningens v1 väntar och får versionskonflikt. Ny avsikt med rätt version bevarar note/completed och når version 3. Omvänd ordning provas separat. |
| 2 | Lås skyddar hela domänunderlaget genom sista kontroll/resultatcommit. Konto, medlemskap och befintlig profil låses också. Kontext sparas från frysta indata; inga nätverksanrop i databastransaktion. | `test_final_check_and_commit_serialize_history_and_profile_writers` låter en annan behörig medlem försöka v1-complete respektive profil-PATCH efter sista kontrollen: båda väntar till commit. Sparat JSON jämförs exakt med skickat JSON. Ändring under nätverket förkastar resultatet. Synkron profiländring provas också. |
| 3 | Högst ett verkligt transportanrop per synkron avsikt, även när gammal anropare anger fler försök. Osäker extern effekt har särskild feltyp och tydlig text. | `LegacyResearchTransportTests`: timeout, URL-fel, HTTP 429/503, avbruten läsning och ogiltig JSON ger aldrig dold omsändning; manuella funktioner fungerar efter fel. |
| 4 | Signerat sidtoken binder äldre API till konto, trädgård och exakt medlemskapsrad. Sessionens nya val eller fallback kan inte flytta gamla formulär. | `test_web_context.py`: giltig CSRF, två flikar, kontobyte, återkallat/återskapat medlemskap, fallback och saknat/manipulerat token. JS visar bevarat avvisat utkast och avskild lagring. |
| 5 | Villkorad `running` → `sending` efter förberedelse, sista lease/token/statuskontroll efter request-/VAPID-förberedelse och ny kontroll efter slutlig authorization. | `IntegrationContractTests`: utgång under förberedelse, ersatt token, utgång under request/VAPID, recovery under request och utgång under slutlig resultatkontroll. Ingen transport efter misslyckad sändkontroll, ingen sen resultatcommit. |
| 6 | Gemensam mottagarregel för köat/synkront läge; aktivt konto, prenumeration, trädgård, medlemskapsidentitet, adress/nycklar och preferens kontrolleras före transport. | `LegacyPushTransportTests`: inaktivt konto i båda lägen, återkallning under förberedelse och ändrad mottagare/prenumeration stoppar webpush; leveranshistorik och deduplicering består. |
| 7 | Transportkonfiguration valideras före `sending`; säkert osända fel skiljs från osäkra leverantörseffekter. | Saknad API-nyckel ger noll nätverksanrop, `failed` och tillåter en ny uttrycklig avsikt. Timeout och redan återhämtat `uncertain` fortsätter blockera nya avsikter och omsändning. |

## Slutverifiering

- Hela Django-sviten: **152/152 på filbaserad SQLite och 152/152 på PostgreSQL 17.11**. Inga överhoppade konkurrensprov.
- JavaScript: **15/15**.
- `check`, `makemigrations --check --dry-run`, Python-kompilering, JS- och shellsyntax samt `git diff --check`: godkända.
- Syntetisk överföring och återläsning: **32 rader**, identiska exporterade fält i SQLite, PostgreSQL och återläst PostgreSQL-backup; oförändrad källhash och fungerande sekvenser.
- Baseline och ursprunglig P3: **132/132 manifesthashar oförändrade**. Start/slut-inventering av spårade och ej ignorerade ospårade filer visar också oförändrad main och P3. Main är ren på `6606e76`.
- Lokalt PostgreSQL kördes endast via lokal socket. Testklustret stoppades efter proven.

Loggar: `/tmp/jobs-integration-sqlite.log`, `/tmp/jobs-integration-postgres.log`,
`/tmp/jobs-integration-js.log`, `/tmp/jobs-integration-transition.log`.
Integritetsinventering: `/tmp/jobs-integrity-before.json` och
`/tmp/jobs-integrity-after.json`. Testerna varnar för saknad collectstatic-katalog
och avsiktlig backupkonfigurations-override; inga testfel.

## Kvarstående gränser

Detta är lokal verifiering, inte produktionsbevis. Ingen verklig AI/push,
produktionsåtkomst, commit/push, deployment, köaktivering eller OIDC-aktivering
har gjorts. `DURABLE_JOBS` förblir av som standard och OIDC fail-closed.
Auth0-aktivering, publik budget/frekvensgräns, native push, PostgreSQL-cutover,
produktionens återställningsövning och operatörsflöde för verkligt oklara
utfall återstår. Browser/telefon och GitHub CI är inte körda här.

Trädgårdslåset serialiserar korta domänskrivningar inom samma trädgård;
prestanda vid publik belastning är inte verifierad. Nätverksanrop håller inga
databaslås. Databas/leverantör saknar gemensam atomär commit; ett avbrott vid
transportgränsen förblir konservativt `uncertain`. Synkront kompatibilitetsläge
har ingen beständig spärr mot en senare ny uttrycklig analys efter osäkert
utfall; det skickar inte om automatiskt och informerar om avstämning.

## Exakta ändrade filer relativt baseline

- `docs/api-v1.md`
- `docs/legacy-transport-review-fixes.md`
- `docs/multiuser-transition.md`
- `docs/p3-durable-jobs.md`
- `docs/review-fixes-integration.md`
- `docs/web-context-review-fix.md`
- `garden/api_support.py`
- `garden/api_v1.py`
- `garden/cleanup.py`
- `garden/jobs.py`
- `garden/locking.py`
- `garden/push.py`
- `garden/research.py`
- `garden/static/garden/app.js`
- `garden/static/garden/sw.js`
- `garden/tasks.py`
- `garden/templates/garden/index.html`
- `garden/test_accounts.py`
- `garden/test_demo.py`
- `garden/test_jobs.py`
- `garden/test_legacy_transports.py`
- `garden/test_p2_api.py`
- `garden/test_review_integration.py`
- `garden/test_web_context.py`
- `garden/testing.py`
- `garden/tests.py`
- `garden/views.py`
- `tests/design-review.test.cjs`
