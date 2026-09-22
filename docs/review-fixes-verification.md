# Verifiering av reviewrättningar

22 september 2026. Bygger vidare på det befintliga, ocommittade designomtaget. Ingen commit, push, publicering eller produktionsåtgärd.

## Automatiska kontroller

- `manage.py test --noinput`: 73 godkända tester, varav tre nya i `garden/test_design_review.py`.
- `node --test tests/design-review.test.cjs`: sex godkända regressioner. Produktens JavaScript-funktioner körs med en begränsad DOM-modell: neutral tomlista efter slutförd egen uppgift, fokus via radidentitet och reservfält, omhämtning av växt-/uppgiftsdialog vid klart och ångra, samt återkoppling i rätt dialog utan kort tidsgräns.
- `node --check garden/static/garden/app.js`, Django-systemkontroll, `makemigrations --check --dry-run` och `git diff --check`: godkända.
- PWA-resurserna i mallen och service worker har samma CSS/JS-version (`20260922b`); cacheversionen är `tradgardsrytmen-v6`.

## Egna webbläsarprov

Testat med Browser-skillen mot lokal förhandsvisning. Mobilbredderna var 320 × 568, 390 × 844 och 430 × 932. Surfplatta och dator kontrollerades vid 820 × 1000 och 1280 × 1000. Ingen horisontell sidrullning i de provade huvudvyerna. Interaktionsproven nedan fördelades mellan bredderna; detta är inte en fullständig kombination av varje flöde på varje bredd.

| Område | Verifierat resultat |
| --- | --- |
| Första skärmen | Konkret uppgift med växt och datum samt öppningsknapp synlig. Knappens underkant cirka y=376 vid 320 px, y=348 vid 390 px och y=326 vid 430 px. |
| Neutral tomstatus | Sex växter utan planer och en slutförd egen uppgift gav ”Inga planerade uppgifter just nu”, inte ”Du är i fas”. Plantäckningen var fortfarande 0 av 6. |
| Klart och ångra | Provade överblick, separat uppgiftsdialog och ”Nästa uppgifter” i växtdialog. Raden och historiken uppdaterades; fokus gick till Ångra. Ångra återställde raden och historiken, även efter att dialogen stängts. |
| Dialog med långt namn | Vid 320 px rymdes dialogen; återkopplingen låg i dialogens översta lager och Ångra var nåbar. |
| Vid behov | Aktivering skapade uppgiften. Upprepat tryck gav ”Arbetet är redan öppet”. Växtdialogen uppdaterades och fokus återgick till Behövs nu. |
| Uppgiftstyper | Aktuell, försenad, kommande i oktober och nästa års marsuppgift. Gruppering efter jobb och plats. |
| Formulär | Omvänt datum gav inlinefel med kvarvarande titel/datum. Tomt växtnamn blockerades med fokus på namnfältet. Ny växt sparades och öppnades utan researchförslag. |
| Sökning/filter | Kategorifilter med Enter behöll fokus. Kombinerat filter och sökning, noll träffar och återställning fungerade. Global sökning öppnade växten med långt namn. |
| År och månad | Månadslista på mobil, årsknappar och år skrivet med tangentbord. Mars 2027 visade rätt testuppgift. Månadsdetaljen började cirka y=367 vid 320 px. |
| Jord | 120 × 80 × 20 cm: 192 liter, 5 säckar à 40 liter. Cylinder Ø40 × 20 cm: 25,1 liter, 2 säckar à 20 liter. Diameter 0 blockerade tillägg. Jordtillägg flyttade fokus till inköpsfältet. |
| Inköp | Listpanelen började cirka y=202–206 på mobil, före den stängda kalkylatorn. Avbockning med mellanslag behöll fokus på kryssrutan och sparades över omladdning. Borttagning gav fokus till inmatningsfältet. Tillägg, borttagning och ångra fungerade. |
| Tom trädgård | Relevant första-växt-text, tom växtlista och tom kalender. Egen uppgift öppnade växtformuläret. Escape stängde och återförde fokus. |
| Större skärmar | Navigation genom alla fyra huvudvyer vid 820 och 1280 px; ingen sidbreddsöverskridning. Den större botaniska heron och månadskorten finns kvar. |

Årsfältets programmässiga `fill` i Browser-verktyget utlöste inte alltid webbläsarens ändringshändelse. Årsväxlingen verifierades därför även med riktig tangentsekvens och årsknappar. Inmatning som har fokus skyddas mot sena omhämtningssvar.

Förhandsvisningens tidigare server stannade under arbetet. Den startades om med angiven testdatabas och explicit tom `OPENAI_API_KEY`, varefter kontrollerna fortsatte.

## Skärmbilder

Bilder med uppgifter och extra växter visar tillfälliga testdata, som sedan togs bort.

- [Överblick, 320 px](images/review-fixes/overview-320.jpg)
- [Överblick, 390 px](images/review-fixes/overview-390.jpg)
- [Växtlista med långt namn, 390 px](images/review-fixes/plants-390.jpg)
- [Dialog och Ångra, 320 px](images/review-fixes/dialog-320.jpg)
- [Inköpslista, 390 px](images/review-fixes/shopping-390.jpg)
- [Årshjul, 320 px](images/review-fixes/year-320.jpg)
- [Surfplatta, 820 px](images/review-fixes/overview-820.jpg)
- [Dator, 1280 px](images/review-fixes/overview-1280.jpg)

## Återställning och avgränsning

Den ursprungliga testdatabasen säkerhetskopierades före första mutation. Efter proven jämfördes SQL-dumpar: exakt samma innehåll, sex växter, noll uppgifter och noll regler. Inköpslistans testvaror togs bort via gränssnittet. Ordinarie `db.sqlite3` hade samma SHA-1 före och efter: `8bf753756e3c9aacaea50b54c891bab4919cabf4`.

Kvar att verifiera på fysisk telefon: mjukvarutangentbord, safe areas, utomhusläsbarhet, VoiceOver/TalkBack och installerad PWA. En faktisk uppgradering av en äldre PWA, offlineflöden och pushleverans provades inte. Ingen verklig extern AI-research kördes. ”Hoppa över” med webbläsarens inbyggda bekräftelseruta kunde inte slutföras i Browser-verktyget och räknas inte som ett godkänt interaktionsprov.
