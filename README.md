# Trädgårdsrytmen

Privat svensk trädgårds-PWA för en gemensam trädgård i Karlskrona, odlingszon 1, skyddat kustnära läge.

## Funktioner

- Månadsöversikt med öppna, försenade och kommande uppgifter samt slutför, hoppa över och ångra.
- Årshjul, flexibla växtposter, lokalt sök och manuella uppgifter.
- Källbelagda AI-förslag via OpenAI Responses och webbsökning. Allt måste granskas; inga AI-uppgifter aktiveras automatiskt.
- Installerbar PWA och enhetsunika Web Push-val, avstängda som standard.
- SQLite-historik, nattlig materialisering och verifierade 14-dagarsbackuper.

## Lokal körning

Kräver Python 3.12.

```sh
python3.12 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python manage.py migrate
.venv/bin/python manage.py seed_garden
.venv/bin/python manage.py runserver
```

## Miljövariabler

Se `.env.example`. OpenAI-nyckeln är valfri; alla manuella funktioner fungerar utan den. Web Push-nyckeln genereras på servern och lagras beständigt i datakatalogen.

## Produktion

Systemd-filer och driftsskript ligger i `systemd/` och `scripts/`. Produktionen använder en privat Tailscale Serve-adress på HTTPS-port 10443. Autodeploy följer `main`, vägrar vid smutsig checkout, säkerhetskopierar databasen, migrerar, samlar statik och kräver godkänd hälsokontroll.

Privat PWA-adress: `https://garden.example.com:10443/`
