# Privat P3-release och driftaktivering, 2026-09-26

Användaren har nu uttryckligen beställt privat release samt PostgreSQL- och
köaktivering. Äldre granskningsrapporter beskriver tillståndet före denna order.
OIDC, publik drift, mobil och verkliga AI-testanrop ingår fortfarande inte.

## Verifierat driftresultat

Båda beställda stegen är genomförda. Kodrelease `1ee8e9e` nådde först privat
SQLite med kö/OIDC av och schema 0014. Därefter aktiverades PostgreSQL 17.11
och DURABLE_JOBS=1 efter separat slutbackup/import/återläsning. OIDC är av.

- GitHub CI för kodreleasen: [releasegren](https://github.com/jockeoh/tradgardsrytmen/actions/runs/36232099933)
  och [main](https://github.com/jockeoh/tradgardsrytmen/actions/runs/36232280485),
  samtliga jobb success på Linux 3.12, macOS 3.13 och PostgreSQL.
- Privat SQLite-release: terminal Result=success, ExecMainStatus=0, rätt SHA,
  schema 0014 och fyra autentiserade HTTP-läsningar godkända med kö/OIDC av.
- Verklig cutover: **1 541 exporterade rader fältidentiska** mellan fryst SQLite,
  PostgreSQL och separat återläst PostgreSQL-backup. Sekvenser verifierade.
  Canonical SHA-256 `63e7232eb855a5936746be700aee79d88e4704cee2cbbc67a2ee85228adfbdc5`.
- Ursprunglig SQLite har oförändrad SHA-256
  `6394bdbabd3fdbeb23e78df71f78d53cab4735a530349ba99f5a17277ce960a7`.
  Källfil och konfiguration före bytet bevaras på servern; inga privata data
  har hämtats till utvecklingsdatorn eller skickats till AI.
- Efter bytet godkändes fyra autentiserade riktiga HTTP-läsningar både före
  och efter köaktivering. Fortsatt 17 växter, 168 uppgifter, 43 förslag och
  noll jobb. Temporär verifieringssession togs bort; ingen riktig analys begärdes.
- Webb, PostgreSQL och samtliga sex app-timers är aktiva. Worker har kört
  flera gånger med `Recovered 0; processed 0`. Kökontroll och första
  PostgreSQL-backupen avslutades med Result=success/ExecMainStatus=0.
- Privat HTTPS-hälsa och inloggningssida svarade 200 med normal
  certifikatkontroll. Assetmarkör 20260926jobs1 och SW v10 är verifierade.
  Browserprov gjordes med syntetiska data, inklusive 390 px utan overflow.

Serverbevis: `/var/lib/tradgardsrytmen/p3-release/cutover-proof.json`.
Slutbackup före bytet:
`/var/lib/tradgardsrytmen/backups/tradgardsrytmen-20260926-092142-705937.sqlite3`.
Återläst PostgreSQL-backup:
`/var/lib/tradgardsrytmen/backups/tradgardsrytmen-20260926-092154-427436.dump`.
Första backupservicekörning:
`/var/lib/tradgardsrytmen/backups/tradgardsrytmen-20260926-092211-040751.dump`.

Fysisk telefon, faktiskt visad push och ett riktigt AI-anrop är inte testade.
Aktiveringen är verifierad utan att skapa sådana externa prov. Den ordinarie
påminnelsetimern är återstartad och framtida uttryckliga AI-begäranden behandlas
av worker med de befintliga behörighets- och osäkerhetsgränserna.

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
när lokal backup finns tillgänglig. Lokala backuper skyddar inte mot förlust
av hela serverdisken. PITR och off-host-backup ingår inte i denna privata
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
  är genomförda enligt driftresultatet ovan.

Källa för paketinstallation: [PostgreSQLs officiella Ubuntu-anvisning](https://www.postgresql.org/download/linux/ubuntu/).

## Integritet

Original-P3, baseline, web-context, legacy-transports, HANDOFF och
oberoende granskningsreferenser är hashidentiska med startmanifestet.
Main uppdaterades genom uttryckligt auktoriserad fast-forward-release.
Lokala provdatabaser rensades och det lokala PostgreSQL-klustret stoppades.
Integrationskopian bevarar hela den granskade leveransen plus den avgränsade
operatörs-/releasekompletteringen; ingen gammal rättning har kastats bort.
