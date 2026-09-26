# Fynd 3 och 6: lokal transporträttning 2026-09-26

Arbetskopia: `tradgardsrytmen-p123-review-fixes/legacy-transports`.
Ingen aktivering, verklig AI/push, commit, push eller deployment ingår.

## AI utan kö

`call_openai` gör högst ett `urlopen`, även om en äldre anropare anger
`max_attempts > 1`. Timeout, URLError, HTTP-fel, avbruten anslutning och
ofullständig HTTP-läsning får inte starta en dold andra modellkörning.
`ResearchOutcomeUnknown`, en `ResearchError`, ger svensk information om
oklart utfall, utebliven automatisk omsändning och fortsatt manuell funktion.
HTTP 429/5xx klassificeras konservativt som oklara externa effekter; ingen
leverantörsidempotens antas. Ogiltig mottagen JSON ger `ResearchError` utan retry.

`validate_research_transport()` kontrollerar lokal nyckelkonfiguration och
kastar `ResearchNotSent(ResearchError)` före extern transport. Integrationen
kan använda samma kontroll före `sending`. Funktionen är inte en verifiering
av nyckelns giltighet hos leverantören. Det synkrona flödet har fortfarande
inte kölägets beständiga spärr för en senare, ny explicit begäran efter ett
oklart utfall. Feltexten uppmanar därför till avstämning före ny analys.

## Mottagare och påminnelser

`eligible_subscriptions(garden)` används av direkt påminnelse, köning och
testpush. Urvalet kräver aktiv användare, aktiv prenumeration och medlemskap;
medlemskapets identitet följer med urvalet.

`recipient_is_authorized(subscription, membership_pk=None, kind=None)`
kontrollerar färska databasvärden för användare, medlemskap, trädgård,
prenumeration, endpoint och nycklar. `kind` kontrollerar dessutom aktuell
månad-/uppgiftspreferens. Kontrollen görs igen av `_send` efter lokal
nyckelförberedelse, omedelbart före `webpush`. Ett avslag kastar `PushNotSent`
utan extern transport. Direktleveransen behåller raden/nyckeln med
`cancelled` och `recipient_changed`; återaktivering återköar inte historiken.
Testpush returnerar noll skickade efter återkallning. HTTP 404/410 avaktiverar
endast samma transportadress/nycklar och kräver inte att ett redan återkallat
medlemskap återställs för att felhanteringen ska kunna sparas.

Integrationsägaren kopplar jobs.py till samma behörighetsfunktion och
`_send(..., membership_pk=job.membership_pk, kind=job.delivery.kind)` samt
klassificerar `PushNotSent` som säkert avbrutet. jobs.py ändras inte här.
Återkallning efter att transporten har börjat kan inte återta skickad data;
ingen databastransaktion hålls över Web Push-anropet.

## Verifiering

134 Django-tester godkända på egen filbaserad SQLite, inklusive 12 nya
transporttester och uppdaterad äldre timeoutregression. Alla externa
transporter i de nya proven är mockade. Proven omfattar timeout under
anslutning/läsning, HTTP-fel, ofullständigt svar, saknad nyckel, ogiltig JSON,
bevarad växt/manuellt skapande, inaktiv användare i båda kölägena, återkallning
under nyckelförberedelse, återskapat medlemskap, ändrad adress/nyckel/preferens,
testpush och bevarad leveransdeduplicering. Logg:
`/tmp/legacy-transports-tests.log`.

Django check, makemigrations --check --dry-run och diffkontroll godkända.
Sviten har befintliga varningar för saknad collectstatic-katalog och
avsiktligt databasoverride i backup-proven. PostgreSQL, slutlig integration,
överföringsprov, browser/telefon och verkliga externa tjänster lämnas till
respektive verifieringssteg; inga produktionsbevis påstås.
