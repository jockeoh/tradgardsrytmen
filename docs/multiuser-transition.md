# Övergång till trädgårdsägarskap

P1, 2026-09-25. Endast modellgrund är implementerad. Privat drift krävs
fortfarande: äldre `/api/` saknar kundisolering. Att skapa ett konto eller
medlemskap begränsar inte dagens API. Ingen äldre data tilldelas automatiskt.

## Modellinventering och nästa steg

| Befintlig modell | Ägarskap i P2 och viktiga kontroller |
| --- | --- |
| GardenSettings | Ersätt global `load()`/pk=1 med en inställningspost per Garden; bevara befintliga värden. |
| GardenArea | Explicit Garden; ändra global namnunikhet till garden + name. |
| GardenItem | Explicit Garden; area måste tillhöra samma trädgård. Även inaktiva växter bevaras. |
| CarePlanVersion | Härled via item; bevara version, status, research_context, reviewed_at och effective_from. |
| SourceReference | Härled via plan/item; källor får inte exponeras via främmande plan. |
| WorkIdentity | Härled via item; merged_into måste ligga inom samma växt/trädgård; bevara action_key och scope. |
| CareRule | Härled via item; plan, work och identity_source måste tillhöra rätt växt, inte bara samma trädgård. |
| ResearchProposal | Härled via item; plan måste avse samma växt; behåll svar, fel och granskningskvitton. |
| TaskOccurrence | Härled via item; rule och work måste avse samma växt. Bevara nycklar, datum, anteckning och alla statusar. |
| PushSubscription | Knyt mottagare till konto och valda trädgårdar; gammal prenumeration kräver explicit övergång. |
| ReminderDelivery | Behåll leveranshistorik/dubbleringsnycklar; kontrollera mottagarens aktuella medlemskap även vid återförsök. |

P1 tillför `accounts.User(AbstractUser)`, `Garden(name, created_at, updated_at)`
och `GardenMembership(garden, user, role, created_at)`. Standard username är
unik; email är valfri och inte unik. Det är **inte** ett beslut att använda
email som inloggningsnyckel. Roller `owner`/`member` och unikhet garden+user
skyddas i databasen, även vid bulk/update. Modellvalidering avvisar också
ogiltiga roller. Medlemskapets föräldrar använder PROTECT för att förhindra
omedveten kaskadradering. Explicit medlemskapsradering är möjlig.
Minst en ägare och överföring av sista ägarskap är framtida transaktionell
servicelogik; P1 tillåter tom trädgård och flera ägare. Ingen behörighetslogik
följer automatiskt av rollen. Garden-namn är inte globalt unika.

Auth och accounts är aktiverade; sessionsapp, sessions-/auth-middleware,
admin och inloggningsroutes är inte aktiverade. Custom User ligger i sin
apps första migrering och refereras via AUTH_USER_MODEL. Garden 0011
skapar endast nya tabeller, med beroende till den utbytbara användarmodellen.
Äldre migreringar ändras inte. Auth skapar grupper/behörigheter men inga
konton, trädgårdar eller medlemskap. Inga gamla domäntabeller får nya fält.

## Alla tillgängliga datavägar

| Befintlig route under /api/ | P2:s avgränsning |
| --- | --- |
| bootstrap/, month/, search/ | Filtrera alla ingående listor, räknare och sökträffar; byt global settings. |
| items/, items/:id/ | Trädgårdsfilter för läsning/skrivning; validera area; skydda även borttagning. |
| areas/, areas/:id/ | Trädgårdsfilter och relationsvalidering vid flytt/radering. |
| items/:id/research/ | Behörighet, uttrycklig AI-start och budget; jobbet binder garden/item/initiator. |
| proposals/, proposals/:id/, proposals/:id/approve/ | Kontrollera item/plan och medlemskap igen vid aktivering. |
| works/:id/, works/:id/need/ | Behörighet till work/item och alla nya uppgifter. |
| tasks/, tasks/:id/, rules/:id/ | Avgränsa listor, relationer och statusändringar. |
| settings/ | Ersätt global singleton med vald trädgård. |
| push/public-key/, push/subscriptions/, push/test/ | Publik nyckel kan vara gemensam; prenumerationer och testutskick får bara avse behörig mottagare. |

`/` och dess JavaScript behöver samordnad inloggning och vald trädgård;
`/health/`, `/sw.js` och statiska resurser får inte innehålla kunddata.
Service worker och lokal inköpslista måste granskas för kontobyte, utloggning
och cacheisolering. Nya v1-routes får inte lämna gamla routes som bakdörr.

| Kommando eller intern väg | Övergång |
| --- | --- |
| seed_garden | Kräver explicit målträdgård; aldrig första registrerade konto. |
| seed_demo | Endast isolerad demodatabas. Dess befintliga tomhetskontroll inkluderar nu även Garden och Membership. |
| materialize_tasks | Iterera explicit per trädgård; bevara stabila arbetsidentiteter och historik. |
| research_starters, replace_pending_research | Explicit garden och auktoriserad start; inga globala kundbatcher. |
| clean_care_content | Explicit garden, förhandsgranskning och avgränsat urval. |
| send_reminders, push.py | Trädgårdsinställningar/tidszon och aktuellt medlemskap per mottagare. |
| backup_database | Fortsatt driftfunktion för hela databasen; aldrig kundendpoint. |
| tasks.py, care_contract.py, research.py, cleanup.py | Alla ORM-ingångar måste ta behörigt avgränsad kontext; relationskontroller gäller även bakgrundsjobb. |
| systemd/scheduled scripts | Uppdatera anrop och privilegier tillsammans med kommandona; loggar/backup är operatörsdata. |

## Övergångsordning

1. Granska P1 lokalt. Nyinstallation och uppgradering verifieras i isolerade
   databaser; inga produktionskommandon ingår i detta arbete.
2. P2 lägger nullable garden-relationer och avgränsad servicelogik bakom
   fortsatt privat drift. Bestäm autentisering och privat webbens övergång.
3. Öva explicit administrativ backfill till namngiven äldre trädgård och
   verifierat ägarkonto på en säker kopia. Transaktion, idempotent körning,
   radräkning, relationskontroller och full historikjämförelse krävs.
4. När samtliga rader är mappade: gör tillhörighet obligatorisk och byt
   unikhetsregler. Aktivera behörigheter på **alla** vägar samtidigt innan
   kunddata kan skapas. Återkallat medlemskap gäller även cachar och jobb.
5. Testa två konton, främmande objekt/relations-ID, listor/sökning och gamla
   routes. Först därefter kan autentiserad fleranvändardrift övervägas.

Backup/återläsning ska provas före faktisk övergång. P1:s schemamigrering
är tekniskt reversibel men bakåtmigrering raderar nya konton/medlemskap;
rollback efter användning kräver separat bevarandeplan, inte blind migrate.
