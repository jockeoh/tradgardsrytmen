# Privat hemmaapp: releaseförberedelse 2026-09-27

Status efter användarens sudo-åtkomst: **serverrelease och privat mobilauth
genomförda**, 2026-09-27 cirka 21:05 CEST. Browser/native/telefonproven nedan
är fortsatt öppna. Tidigare hinder och operatörsplan bevaras som historik.

## Slutresultat efter aktivering

- Terminal deploy 21:04:57: Result=success, ExecMainStatus=0,
  ActiveState=inactive/SubState=dead (avslutad oneshot).
- deployed_commit är `59d4c4c0bcae86778a8b6c54e21371d011679cd9`.
  Runtime matchar godkänt Git-arkiv byteidentiskt för 264 filer.
- Effektiv Django-backend PostgreSQL, DEBUG=False, PRIVATE_MOBILE_AUTH=True.
  accounts/0004 är tillämpad. Endast mobilflaggan ändrades i miljöfilen;
  tidigare konfiguration finns root-only på servern. Inga konton/lösenord ändrades.
- Verklig backup återlästes isolerat före migration. Migration, seed och cleanup
  bevarade alla 1 544 rader. Samma fältidentiska 1 544 rader verifierades i
  skarp databas efter release (contenttypes/auth.permission undantagna).
- Privat HTTPS /health/ ger status ok. POST /api/v1/auth/login/ med tom JSON
  ger förväntat 400 validation_error över HTTPS: mobilvägen är aktiv och
  inget loginförsök/token eller domänobjekt skapades av proben.
- Webb/privat ingress active; worker och kökontroll success/0; sex timers
  återstartade. Inga nya AI-/pushprov begärdes.
- Efterbackup: `/var/lib/tradgardsrytmen/backups/tradgardsrytmen-20260927-190550-363076.dump`.
  Återläst i separat databas och jämförd fältidentiskt. De två isolerade
  repetitionsdatabaserna togs bort. Underlag med privata data stannar på servern.
- Förebackup: `/var/lib/tradgardsrytmen/backups/tradgardsrytmen-20260927-190128-845431.dump`.
- Ingen riktig personlig mobilinloggning eller native-körning är verifierad.
  Serveradressen öppnar befintlig privat webb; Expo-klienten behöver fortfarande
  köras på en tillgänglig telefon/native-miljö för fullständigt appbevis.

## Färska kontroller, cirka 19:38–19:41 CEST

- GitHub main: `59d4c4c0bcae86778a8b6c54e21371d011679cd9`.
- [CI 36337375132](https://github.com/jockeoh/tradgardsrytmen/actions/runs/36337375132):
  completed/success för exakt SHA; Linux, macOS, PostgreSQL och mobile success.
- Servercheckout är ren på `0b3eab4fa200ae09fc2c4cedff2b95ab4114525e`.
  Detta är inte ett verifierat runtime-SHA; skyddad deployed_commit och
  effektiv tjänstekonfiguration kan inte läsas med tillgänglig behörighet.
- Webbservice active/running, Result=success. Loopback och privat HTTPS
  `/health/` svarar status ok med certifikatkontroll påslagen.
- Privat adress: `https://clawd-thinkpad-t450s.tail197480.ts.net:10443`.
  Tailscale Serve anger tailnet only för just denna adress/port.
- PostgreSQL-kluster `postgresql@17-tradgardsrytmen.service` och privat
  ingress är active. Effektiv Django-backend och tillämpade migrationer är
  inte nyverifierade. Historiskt P3-underlag anger PostgreSQL; det räcker
  inte som bevis på aktuell effektiv konfiguration.
- Worker, köhälsa och backup: Result=success, ExecMainStatus=0.
  Alla sex app-timers finns med framtida körningar.
- Autodeploy: failed, Result=exit-code, ExecMainStatus=1. Journalen anger
  `Revision requires completed CI and an explicit release-approved marker.`
  Markörens innehåll är inte läsbart. Felet inträffar före underhållssteget.
- Installerat deployskript och runtime-kopia är byteidentiska med granskad
  main: SHA-256 `1a298e4e00953bb7917434d9a0c800e7572948f67a256ff2458ad6c90ebdbd4e`.
- Runtime innehåller accounts-migrationsfiler 0001–0003, inte 0004.
  Privat mobilinloggning är därmed inte levererad av denna runtime.
- `sudo -n true` ger `a password is required`. Befintlig NOPASSWD-lista
  gäller endast vissa Finance-servicekommandon och kan inte användas här.

## Historisk operatörsplan före genomförandet

Följande var planen före den genomförda releasen; kör inte om den som en ny release.

En behörig operatör behövde utföra följande via egen interaktiv SSH/sudo på
`t450`, eller tillhandahålla en avgränsad operatörsfunktion för samma flöde.
Inga lösenord ska skickas i chatten och bred NOPASSWD behövs inte.

1. Läs effektiv servicekonfiguration utan att skriva hemligheter i logg.
   Bekräfta PostgreSQL, POSTGRES_DEPLOY_READY=1, befintlig explicit garden,
   aktuell migrationstatus, runtime/deployed_commit och oförändrade AI-/push-
   och OIDC-inställningar. Stoppa vid avvikelse. Ändra inte ägare eller garden.
2. Verifiera aktuell main och grön CI för exakt SHA ovan igen. Pausa
   autodeploy-timern medan konfiguration och markör förbereds. Säkerhetskopiera
   miljöfilen med root-only rättighet; bevara tidigare markör och drifttillstånd.
3. Repetera migration på en skyddad återläst aktuell PostgreSQL-backup med
   externa transporter avstängda. Enda nya migrationsfil sedan servercheckout
   är accounts/0004: två nya tabeller, ingen datamigrering. Kontrollera ändå
   bevarad domänhistorik samt seed_garden/clean_care_content på kopian eftersom
   deployskriptet kör dem. Kräv noll oönskade domänändringar före skarp release.
4. Sätt endast `TRADGARDSRYTMEN_PRIVATE_MOBILE_AUTH=1` i befintlig miljöfil.
   Native behöver ingen browser-CORS-origin. Lägg endast till exakt origin
   om en faktisk separat privat browserklient ska användas; inget wildcard.
   Befintlig HTTPS/proxy ska bevaras. Skapa inget konto eller lösenord.
5. Skriv exakt `59d4c4c0bcae86778a8b6c54e21371d011679cd9` i
   `/var/lib/tradgardsrytmen/release-approved` och starta
   `tradgardsrytmen-autodeploy.service` med befintligt installerat skript.
   Skriptet kräver att remote main fortfarande matchar markören, dränerar
   writers, tar backup, migrerar och återstartar befintliga tjänster/timers.
   Kör inte separat git-merge, rsync eller migrate utanför detta flöde.
6. Vänta på terminalt success/ExecMainStatus=0. Bekräfta checkout,
   runtime-innehåll och deployed_commit mot mål-SHA, accounts/0004 tillämpad,
   faktisk PostgreSQL-backend, mobilflagga, check --deploy, privat HTTPS,
   webbtjänst, ingress, worker, köhälsa och sex timers. Verifiera att backupen
   kan återläsas och att historik/garden/ägarskap är bevarade.
7. Användaren loggar själv in med befintlig personlig identitet. Autentiserade
   produktionsläsningar kan verifieras; felinjektion och syntetiska mutationer
   ska ske isolerat, aldrig i användarens riktiga trädgård.

## Återgång

Vid deployfel: behåll underhållsläge och utred innan återöppning. Gör ingen
blind bakåtmigrering eller återställning av gammal SQLite. Säkra PostgreSQL-
backup och eventuella nya skrivningar. Mobilfunktionen kan stängas med flaggan
0 och kontrollerad webbomstart utan att radera de nya sessionstabellerna.
Kodåtergång kräver schema-/datakompatibilitetskontroll; databasåterläsning
kräver avstämning av skrivningar efter backupen. Bevara gamla kvitton/historik.

## Browser, native och återstående prov

Den isolerade testservern från exakt main startades med ny temporär SQLite
och två testkonton; hälsokontrollen gav status ok. Inga lösenord skrevs till
logg. Browsern kunde inte nå servern: `ERR_BLOCKED_BY_CLIENT` på
`http://127.0.0.1:8133/health/`. Lokal webbexport gav anslutningsfel i browsern.
Inget fullt browserflöde eller tvåfliksprov är därför godkänt i denna uppgift.
Browserns spärr kringgicks inte. Testservrarna stoppades efter kontrollen.

Endast CommandLineTools finns; `xcrun simctl` saknas. adb/emulator och
Android SDK saknas, och USB-inventeringen visade ingen iPhone/iPad/Android.
Ingen native-körning eller fysisk telefonverifiering genomfördes.

CI:s godkända HTTP/processdödsprov är aktuell automatiserad evidens, men
ersätter inte dessa återstående prov:

- Login → trädgård → växt → manuell uppgift → utförd → historik efter
  omstart och ny login, med två isolerade konton.
- Två riktiga browserflikar: en avsikt vinner, gammal flik får inte radera ny.
- Native SecureStore/SQLite: offline-utloggning, omstart, senare återkallning,
  konto-/serverbyte och bevarad separat återkallningskö.
- Tappat svar efter commit och tvångsavslut: samma key/body, exakt ett objekt.
- Orörd respektive tömd anteckning, färsk konfliktstatus och avstämning utan
  blind ny nyckel.

Efter serversteget: anslut telefonen till befintligt Tailscale-nät, öppna
ovanstående privata HTTPS-adress och kontrollera vanlig webb. Native-provet
kräver dessutom en tillgänglig kompatibel lokal Expo/native-miljö; ett
webbprov eller en export ska inte redovisas som native. Molnbygge, Auth0,
publik registrering och externa AI-/pushprov ingår inte.

## Arbetskopior

Allt nytt underlag ligger i separat worktree
`/Users/joakimohman/Code/tradgardsrytmen-private-release`, gren
`task/home-app-private-release`, från verifierad origin/main. Kanoniska
ocommittade dokument, hemmaappleveransen och äldre kopior har inte ändrats.
Ingen ny commit eller push har gjorts.
