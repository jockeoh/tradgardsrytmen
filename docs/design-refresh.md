# Trädgårdsrytmen — designomtag, september 2026

En lugn, personlig trädgårdsprodukt med en tydlig väg från växt till skötsel till inköp.

## Visuell identitet

Kalkvita ytor, djupgrön navigation, salvia och jordnära accenter. Serifrubriker ger karaktär; systemtypsnitt gör att appen laddar utan externa fonttjänster. Ett sammanhållet designsystem ersätter fyra överlappande stilmallar. Botaniska vektorillustrationer representerar växttyper och utger sig inte för att vara foton av användarens egna växter.

## Färdiga flöden

- **Överblick:** konkret nästa uppgift direkt i en kompakt mobilhero, riktiga uppgifts- och växtantal, månadskalender och aktuella/kommande/behovsbaserade uppgifter. En tom lista beskriver endast planen. Antalet växter med granskad skötselplan visas separat.
- **Min trädgård:** illustrerade växtkort på dator och breda listrader på mobil, direkt sökning på namn, sort och plats, kategorifilter, växtdetaljer och områdeshantering.
- **Årshjulet:** valbart år, årstider och separata planerade uppgifter och historik. Mobilen använder en vanlig månadslista med tangentbordsstöd; datorn behåller månadskorten.
- **Inköpslista:** listan visas först, med jordberäkning som öppnas vid behov. Volymberäkning för rektangulära bäddar och cylindriska krukor, avrundning till hela säckar, egna inköp, avbockning och ångra. Listan sparas lokalt i webbläsaren; gränssnittet berättar detta.
- **Inställningar:** namngivning och platsprofil, befintliga notisfunktioner och granskningskö.

Navigationen har länkbart tillstånd och stöd för bakåt/framåt. Mobilens brukstext är huvudsakligen 14–16 px, statistikförklaringar 12 px och centrala kontroller minst 44 px höga. Mobilen har en egen bottennavigation, sökning och formulär som öppnas från skärmens nederkant. Fokusmarkeringar, formuläretiketter, statusmeddelanden, minskad rörelse och tydliga tomlägen finns genomgående.

Växtsparande startar ingen research. Externa råd hämtas separat från växtdialogen, med information om att växtinformation, anteckningar, platsprofil och skötselhistorik skickas till OpenAI. Granskningen sker efter överföringen. Vid ändring av sort/anteckningar är eventuell ny research ett aktivt, från början omarkerat val.

Klarmarkering och ångra uppdaterar den öppna uppgifts- eller växtdialogen, inklusive historik. Ångra ligger i dialogens översta visningslager och följer med när en annan dialog öppnas eller stängs. Ångra försvinner inte på en kort timer; nästa återkoppling ersätter meddelandet. Inköpsrader och växtfilter behåller fokus efter omrendering. Om en fokuserad inköpsrad tas bort återgår fokus till inmatningsfältet.

## En grund för intäkter

Jordberäkningen och inköpslistan ger en konkret plats för framtida produktlänkar: användaren har redan angett ett behov och en mängd. En partnerintegration kan visa tillgängliga säckstorlekar och butiker efter beräkningen, med tydlig märkning som **Annonslänk** och en förklaring att appen kan få ersättning.

Relevans för växt och plantering bör styra urvalet. Provision ska inte ändra skötselråden eller den beräknade mängden. Partnerdata bör hållas separat från granskade råd och visa källa, aktuell förpackningsstorlek och tidpunkt för prisuppdatering.

Den här versionen innehåller inga produktpriser, aktiva partnerlänkar, betalflöden eller påhittade samarbeten. Innan en publik tjänst lanseras behövs fortfarande inloggning, behörighet per trädgård, synkroniserade användardata och en lösning för bakgrundskörning av research. Designarbetet ändrar inte den befintliga driftens modell för ett betrott hushåll.

## Bild och tillgångar

- Hero: `garden/static/garden/images/garden-hero.jpg`, 1536 × 1024, cirka 705 KiB.
- Skapad med det inbyggda imagegen-verktyget; därefter JPEG-komprimerad för webben.
- En redaktionell stämningsbild av en skandinavisk trädgård, inte en bild av användarens faktiska trädgård.
- Ikoner och botaniska SVG-symboler: `garden/templates/garden/symbols.html`.
- Befintlig Lucide-licens för appikonen finns kvar under `garden/static/garden/icons/LICENSE.txt`.

### Slutlig bildprompt

Use case: photorealistic-natural. Asset type: premium Swedish garden planning app hero photograph. Create an editorial natural photograph of a beautiful lived-in Scandinavian cottage garden in early autumn, in the style of a high-end Nordic gardening magazine. An intimate lush green garden, winding pale gravel path, weathered terracotta pots, raised oak vegetable beds with leafy greens, subtle mauve and dusty pink asters and white cosmos, small apple tree with a few ripe apples, layered soft foliage. No buildings dominating, no people. Wide landscape composition 1536x1024; lush focal planting on the right, soft deep green foliage on the left so the app can blend the left edge into a pale sage text panel. Camera at human eye level looking gently along the garden path. Dappled warm late afternoon sunlight, atmospheric but realistic, fine organic texture, slightly analog film grain. Muted forest green, sage, cream and restrained dusty mauve. Sophisticated, tranquil, achievable home garden, never tropical, no saturated orange, no overly manicured mansion garden, no text, no logos, no watermarks, no UI.

## Verifiering efter reviewrättningarna, 22 september

- 73 Django-tester godkända, inklusive tre nya regressioner för separat sparande, planernas täckning och uppgift/historik vid klart och ångra.
- Sex nya JavaScript-regressioner godkända med Node:s inbyggda testverktyg. De kör produktfunktionerna med en begränsad DOM-modell; de ersätter inte webbläsartester.
- JavaScript-syntax, Django-systemkontroll, migrationskontroll och `git diff --check` godkända.
- Faktiska webbläsarinteraktioner och responsiv kontroll vid 320, 390, 430, 820 och 1280 px. Nästa uppgifts öppningsknapp är helt synlig på första skärmen vid 320 × 568. Inköpspanelen börjar omkring y=202–206 på mobil.
- CSS/JS-resursernas version är `20260922b`, med service worker-cache `tradgardsrytmen-v6`.
- Utförlig testredovisning, begränsningar och nya skärmbilder: [review-fixes-verification.md](review-fixes-verification.md).

Endast `.tmp-data/design-preview.sqlite3` användes för tillfälliga trädgårdsdata. Kopian återställdes till exakt ursprungligt SQL-innehåll: sex växter, noll uppgifter, noll regler. Inköpens testvaror togs bort. Ordinarie databas ändrades inte. Ingen verklig AI-research, commit, push eller publicering utfördes.
