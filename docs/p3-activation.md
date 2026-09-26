# Privat P3-release och driftaktivering, 2026-09-26

Användaren har nu uttryckligen beställt privat release samt PostgreSQL- och
köaktivering. Äldre granskningsrapporter beskriver tillståndet före denna order.
OIDC, publik drift, mobil och verkliga AI-testanrop ingår fortfarande inte.

## Lokalt kompletterat inför aktivering

Migration 0014 lägger till ett beständigt operatörskvitto och jobbstatus
`reconciled`. `reconcile_job --garden UUID --job UUID` visar en läsande
förhandsgranskning och dess expected-hash. `--apply --operator USERNAME
--decision confirmed_not_sent|confirmed_received --evidence REFERENS
--expected HASH` kräver aktiv ägare och oförändrat underlag. Referensen får
inte innehålla nycklar, råa leverantörssvar eller privata anteckningar.
Fortfarande oklart utfall får inte lösas upp. Mottaget AI-svar importeras inte:
operatören bekräftar extern effekt och avslutar ärendet utan nytt resultat.

Kvittot sparar originalets uncertain-status och försöksunderlag. Jobbet får
reconciled, men avslutade försök och påminnelsehistorik skrivs inte om. Samma
begäransnyckel återger gamla jobbet. Ingen transport, köning eller automatisk
retry sker vid avstämning; senare analys kräver ny uttrycklig användarhandling.
Sena workers kan inte publicera AI-resultat eller starta om jobbet. Sen
pushbekräftelse kan fortfarande tillföra leveransbevis.

Worker: en avsikt per körning, var 30:e sekund, med recovery före claim.
`check_jobs` körs var femte minut och ger systemd failure/journalsignal vid
kö äldre än tio minuter, utgången lease, failed eller uncertain. Failed är
kumulativt och kräver operatörsuppföljning; kontrollen startar inga transporter.
Ingen email/Slack eller annan extern larmkanal har konfigurerats. Privat
operatör följer systemd/journal; aktiv fjärrnotifiering är ett separat val.

Autodeploy kräver en exakt SHA i `/var/lib/tradgardsrytmen/release-approved`
efter grön CI. Den stänger ingressen, pausar timers, dränerar befintliga
anrop, stoppar webben och tar backup från effektiv tjänstekonfiguration före
kodbyte/migrate. Den deployar exakt den godkända, redan hämtade revisionen.
Fel lämnar underhållsläget för avstämning; ingen blind rollback sker.
PostgreSQL kräver dessutom `TRADGARDSRYTMEN_POSTGRES_DEPLOY_READY=1` efter
verifierad cutover. Det är ingen tillåtelse för nya databasbyten.

## Vald privat drift

PostgreSQL 17.11 på samma server, eget kluster `17/tradgardsrytmen`, port
55440 endast Unix-socket `/var/run/postgresql`, tom listen_addresses och
peer-auth för samma OS-/databasroll. Rollen har varken superuser, createdb
eller createrole. Inget databaslösenord behövs. TLS gäller nätverkstransport;
PGSSLMODE=disable används här uttryckligen för den lokala socketen. Extern
PostgreSQL kräver en separat konfiguration med verifierad TLS.

Daglig custom-format-backup, 14 dagars retention och verifierad återläsning.
Privat återställningsmål är senaste backup, högst cirka 24 timmars dataförlust
vid databasförlust. PITR och off-host-backup ingår inte i denna privata
aktivering och ska bedömas före publik drift. Fryst SQLite-källa bevaras vid
cutover; efter nya PostgreSQL-skrivningar krävs avstämning/återföring, aldrig
ett enkelt byte tillbaka till den gamla filen.

## Verifiering före release

- 263/263 Django på filbaserad SQLite och PostgreSQL 17.11; inga skips.
- 16/16 JavaScript samt fyra isolerade deployskriptprov.
- Syntetisk överföring/återläsning: 32 rader fältidentiska, sekvenser godkända.
- Browser med syntetiskt konto: login, växtsparande, klarmarkering och bevarat
  utkast efter 401 följt av lyckat explicit sparande. Ingen AI/push.
- Serverns riktiga backupkopia: 1 539 konto-/domänrader bevarade genom
  0012 → 0014; seed/cleanup gav inga domänändringar; SQLite-återläsning godkänd.
- Verklig PostgreSQL-repetition, GitHub CI och terminal releaseverifiering
  genomförs som efterföljande grindar. Detta avsnitt är inte driftbevis.

Källa för paketinstallation: [PostgreSQLs officiella Ubuntu-anvisning](https://www.postgresql.org/download/linux/ubuntu/).
