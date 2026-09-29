# Privat app: workspace-1

`GET /api/v1/gardens/<garden UUID>/workspace/` ger hela den privata trädgårdens
underlag: växter, områden, arbetslista, kalender/historik, råd, förslag med
jämförelsetoken, profil och den inloggades analysjobb. Samma autentisering och
CSRF-regler som övrigt API v1 gäller. Det befintliga kärn-API:t finns kvar.

Svaret innehåller `protocol`, `garden_id`, exakt `membership`, signerad
`context` och `revision`. Resurs-ID:n inom detta underlag är opaka strängar
av befintliga domän-ID:n, **inte** kärn-API:ts publika UUID:n. Klienten får
inte blanda dem. Alla mål kontrolleras inom den valda trädgården.

Varje växt innehåller `current_rules`, aktiva råd vars arbete inte är bortvalt,
även när rådet kommer från en äldre plan. `plan.rules` bevarar hela förslaget
för historik/granskning och får inte användas som lista över aktuell skötsel.
Klient och server i detta paket ska installeras tillsammans.

POST till samma adress kräver `Idempotency-Key` och exakt följande form:

```json
{
  "command": "plant.update",
  "target": "123",
  "values": {"name": "Ros"},
  "context": "signerad-kontext-fran-det-visade-underlaget",
  "revision": "sha256-fran-det-visade-underlaget"
}
```

Tillåtna handlingar: `plant.create/update`, `task.create/update`,
`area.create/update/delete`, `work.need/update`, `rule.update`,
`proposal.approve/reject`, `profile.update`, `research.start`,
`notifications.save`. Endast uttryckligen tillåtna fält skickas vidare till
befintliga domänoperationer; ingen godtycklig URL-vidarebefordran.

Servern låser trädgården och kontrollerar ursprungligt medlemskap. Revisionen
omfattar trädgårdens växter, områden, inställningar, planer, råd, arbeten,
tillfällen och förslag. Ändrat underlag ger 409 före ny mutation. Detta är en
avsiktligt konservativ kontroll: även en annan ändring i trädgården kan
kräva ny granskning. Snapshot och revisionsberäkning är avsedda för små
privata trädgårdar, inte paginerade stora organisationer.

En lyckad mutation ger beständigt kvitto. Återförsök använder samma
nyckel/body; kvitto kan läsas via befintliga `/api/v1/reconcile/`.
Återskapat medlemskap ger inte åtkomst till ett tidigare medlemskaps kvitto.
Klienten bevarar skrivavsikten i befintlig journal före transport.

`research.start` kräver `consent: true` och aktiverad beständig jobbkö.
HTTP-anropet köar endast arbetet. Befintlig worker utför analys och dess
ordinarie kontroller gäller; läsning/pollning startar ingen analys.

Native-notiser kräver `TRADGARDSRYTMEN_NATIVE_PUSH=1`, aktuell privat
mobilinloggning, Expo-token och uttrycklig registrering. Prenumerationen
binds till konto, trädgård, exakt medlemskap och mobilinloggning. Utloggning,
utgången inloggning eller lösenordsbyte stoppar nya utskick. En annan
trädgård/konto måste först avregistrera en aktiv token. Gamla jobbmål flyttas
inte till en ny ägare. Expo är en fast transportadress; notisen innehåller
bara en allmän påminnelse. Mottaget push-ticket betyder att leverantören
accepterat begäran, inte bevis på leverans till telefonen. Fysisk leverans
måste verifieras separat. Web Push fortsätter använda sin befintliga transport.

Migrationerna 0015/0016 är additiva och påverkar inte befintliga
trädgårdsdata. Native push är avstängt som standard. Inga migrations- eller
aktiveringsåtgärder i produktion ingår i det lokala arbetet.
