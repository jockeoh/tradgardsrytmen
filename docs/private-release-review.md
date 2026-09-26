# Privat releasebedömning av samlad P3

Senare aktiveringsarbete: [privat P3-release och driftaktivering](p3-activation.md).
Den daterade granskningen nedan är underlaget före aktiveringsbeställningen.

2026-09-26. **JA MED VILLKOR** för befintlig privat drift med en ägare,
SQLite, `TRADGARDSRYTMEN_DURABLE_JOBS=0` och OIDC okonfigurerat/fail-closed.
Detta är ett tekniskt releaseunderlag, inte ett godkännande att deploya.
Ingen ny konkret kodblockerare identifierades för detta alternativ.
De ännu öppna driftgrindarna nedan måste passera innan release kan slutföras.

## Granskat innehåll och evidens

Enda ändrade arbetskopia är `tradgardsrytmen-p123-review-fixes/jobs-integration`,
detached på `6606e76c8f30d42ff364c0ebfecfd10c13c5d31d`. Startinventeringen:
142 filer, 38 modifierade spårade och 20 ospårade. Hela ursprungliga P3 samt
alla integrerade rättningar ingår; inget nytt worktree från main ersätter dem.

- Startmanifestet matchade exakt `/tmp/p3-integration-end.json`. Lästa loggar
  `/tmp/p3-fixes-sqlite.log` och `/tmp/p3-fixes-postgres.log` visar vardera
  254 godkända tester utan skips; JS-loggen visar 15/15. Det är tidigare
  körningar av exakt samma kod, inte nykörda sviter eller GitHub CI-bevis.
- `/tmp/p3-fixes-transition.log` bekräftar 32 syntetiska rader med identiska
  exporterade fält över SQLite, PostgreSQL och återläst PostgreSQL-backup,
  oförändrad källfil och fungerande sekvenser.
- Koden har granskats för databasval, migration 0013, backup/autodeploy,
  sessions-/CSRF-/sidkontext, synkron AI och påminnelser samt klientversionering.
- Nytt separat prov: `/tmp/p3-private-migration-probe.py` och motsvarande
  `.log`. Uppgradering av P2-schema 0012 → 0013 med kö/OIDC av bevarade
  **18 syntetiska konto-/domänrader fältidentiskt**, inklusive fyra
  uppgiftsstatusar, anteckningar, källor, granskningskvitto, idempotenskvitto
  och skickad påminnelse. Nya jobb-/försökstabeller förblev tomma. Äldre
  auth/contenttype-rader bevarades; Django tillför behörigheter för nya modeller.
  Backup före/efter gick att läsa med identiska data, integrity_check=ok,
  filrättighet 0600 och oförändrad hash för backupen före migrationen.
  Provet använde temporära filer och inga transporter. Första versionerna av
  provskriptet behövde korrigeras för fullständigt P2-schema, egna fixtures
  före jobbschemats existens och Djangos nya permissions; inga produktkodfel.

Lokala godkända prov bevisar inte produktionens schema, databas, webbläsare,
fysisk telefon, verklig AI/push, native eller faktisk produktionsåterläsning.
Ingen produktionsåtkomst har försökts här; tidigare nekad databasbehörighet
ska hanteras av behörig operatör, inte kringgås.

## Bedömning per risk

| Område | Slutsats för privat SQLite med kön av |
| --- | --- |
| Migration | 0013 skapar jobb/försök, index och constraints; ingen RunPython/backfill eller ändring av äldre domänfält. Den körs oberoende av köflaggan. Syntetisk uppgradering är godkänd; verklig kopia återstår. |
| Backup | `garden/database_backup.py` läser SQLite med mode=ro, verifierar integrity, skriver 0600 och publicerar först färdig fil. Separat återläsning krävs fortfarande. |
| Autodeploy | `scripts/auto_deploy_linux.sh:46–48` tar första backupen från den fasta sökvägen `/var/lib/tradgardsrytmen/db.sqlite3` och kan hoppa över den om fil/runtime saknas. Matchning mot tjänstens faktiska DB måste bevisas. Skriptet tar inte ner skrivare före kopiering/migrate och har ingen automatisk återställning vid fel. Detta kräver kontrollerat releasefönster, inte blind timerrelease. |
| Datamutation vid release | Samma skript kör migrate, seed_garden och clean_care_content --apply (63–69). Seed kan lägga tillbaka saknade startväxter; cleanup kan arkivera automatiskt arbete/skapa granskningsförslag. Förhandsgranska resultat på återläst kopia och godkänn exakt påverkan, även när kön är av. |
| Webbsäkerhet | Session, CSRF och signerat konto/garden/exakt medlemskap skyddar äldre API. V1 Bearer förblir fail-closed. Lokal negativ testning stöder kontraktet; verklig proxy/HTTPS/cookies/inloggning återstår. Privat betyder fortfarande autentiserad drift. |
| Webbkompatibilitet | Äldre öppna sidor utan X-Garden-Context får säkert 409. Ny klient använder markör 20260926context1 och SW v9. Planera omladdning med skyddade utkast; inga löften om automatisk återställning av gamla klienters osparade formulär. |
| Synkron AI | En transport per avsikt, färsk behörighets-/underlagskontroll före sändning och atomärt vid lagring. Ingen dold omsändning. Vid oklart utfall saknas beständig spärr mot en senare ny uttrycklig begäran; ägaren måste stämma av före nytt försök. Manuella funktioner fungerar utan AI-nyckel. |
| Påminnelser | Färsk mottagar-/uppgiftskontroll efter förberedelse, befintliga leveransnycklar och bevarat sent/sent_at. Verklig transport/telefon inte provad. Processavbrott mellan extern effekt och DB-lagring kan fortfarande lämna oklar/pending historik; ingen automatisk omsändning av samma leveransnyckel. |

Databasen och leverantören kan inte göra gemensam atomär commit. Redan skickad
data kan inte återtas vid senare återkallning. Dessa dokumenterade gränser är
acceptabla för fortsatt uttryckligt styrd privat användning, med avstämning vid
oklart utfall. De är inte ett löfte om exactly-once eller offentlig AI-beredskap.

## Grindar vid separat godkänd privat release

1. **Inventera läsande med behörig operatör.** Bekräfta aktuell tjänsterevision,
   effektiv SQLite-sökväg, schema 0012, rätt ägare/exakt garden-UUID,
   otilldelade/korsande rader och historikräkning/fingeravtryck. Bekräfta kö=0,
   inga workers, OIDC av, DEBUG=0, skyddad secret och HTTPS/host/CSRF/cookies.
   Saknad åtkomst eller avvikande databas är ett stopp före release.
2. **Återläs verklig backup i skyddad isolerad miljö.** Stäng av externa
   transporter där. Verifiera integritet, relationer och alla historikfält,
   migrera kopian till 0013, prova seed/cleanup och jämför avsedda förändringar.
   Ta/återläs även backup efter migration. Dokumentera återgång med bevarade
   nya skrivningar; kör inte blind bakåtmigrering som raderar jobbhistorik.
3. **Granska exakt releaseinnehåll och klientbyte.** Ta med alla ospårade
   leveransfiler och migration 0013. Kontrollera CI för den slutliga revisionen
   före aktivering (håll autodeploy från att hinna före CI vid push till main).
   Browser/PWA-prov av login, listor, formulär/utkast, 401/409 och gammal→ny
   klient krävs; säkra osparade formulär innan omladdning. Inga riktiga AI-/pushprov
   ingår automatiskt i ett sådant manuellt webbprov.
4. **Genomför ett kontrollerat underhållsfönster.** Stoppa nya webbskrivningar,
   låt pågående AI/push avslutas och pausa/samordna timers och operatörskommandon
   innan slutbackup, kodkopiering och migrate. Verifiera att backupvägen är
   exakt tjänstens databas; vid avvikelse behövs separat korrekt backup och
   granskat deployupplägg. Observera att skriptet återaktiverar timers i steg 77:
   deras återstart och eventuella externa effekter måste omfattas av beslutet.
5. **Avsluta först med driftbevis.** Terminal Result=success/ExecMainStatus=0,
   rätt SHA i checkout/runtime/deployed_commit, schema 0013, webb/timers friska,
   health 200 samt autentiserad bootstrap/månad/historik, rätt ägare och
   förväntad granskningskö. Verifiera v9/20260926context1 och att inga jobb
   skapats genom normal navigation eller manuell användning med flaggan av.
   Health och markerad SHA ensamma bevisar inte dataintegritet. Kontrollera
   första riktiga backupkörningen. Redovisa separat det som inte provats på telefon.

Ingen av dessa produktionsgrindar har passerats genom denna lokala granskning.
Privat release behöver inte invänta Auth0, native, betalningar eller publik
budget. **PostgreSQL-cutover** kräver däremot eget granskat deployflöde,
TLS/backup/PITR och verklig övergångsövning; **köaktivering** kräver
worker/larm/recovery och ett implementerat operatörsflöde för uncertain.
Publik/native drift följer [roadmapens restlista](roadmap.md).

## Dokumentationsändring och integritet

Denna uppgift ändrar endast `docs/roadmap.md`, `docs/deployment.md`,
`docs/architecture.md`, `docs/product-v1.md`, `docs/multiuser-transition.md`,
`docs/api-v1.md`, `docs/p3-durable-jobs.md` och denna nya rapport.
Tidigare rättningsrapporter lämnas som daterad evidens.

Start/slutmanifest för skyddade kopior:
`/tmp/p3-private-review-protected-start.json` och `...-end.json`.
Integrationskopian: `/tmp/p3-private-review-integration-start.json`,
`...-end.json` och `/tmp/p3-private-review-delta.json`.
Dessa skiljer dokumentationsarbetet från den redan ocommittade leveransen.
Slutkontrollen gav exakt åtta dokumentfiler i deltat (sju ändrade, en ny),
142 → 143 inventerade filer. Samtliga kod-/testhashar är oförändrade.
Skyddade manifest är byteidentiska, SHA-256
`e48420267ed7f73c02a5e1293a9715f30620adbed33b800cf2b2a3571f1a1ef5`:
main 122, ursprunglig P3 132, baseline 132, web-context 134 och
legacy-transports 134 filer. HANDOFF och granskningsreferenser är orörda.
Dokumentlänkar, blanksteg och git diff --check är kontrollerade.
Ingen commit/push, deployment, produktionsmigrering, extern dataöverföring,
verklig AI/push eller kö-/OIDC-aktivering ingår.
