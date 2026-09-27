# Slutligt lokalt provunderlag

Efter reviewrättningar: `fix-validation.txt` sammanfattar 54 mobiltester,
HTTP, export och övriga slutkontroller. Äldre loggar nedan avser första leveransen.

Se [leveransrapporten](../home-app-delivery.md) för omfattning och begränsningar.

- `mobile-tests.txt`: 46 godkända, inklusive M1:s tidigare 38.
- `http-integration.txt`: riktig isolerad Django-server, två konton och faktisk
  JS-processdöd efter växtskapande och klarmarkering.
- `django-tests.txt`: 270 godkända med projektets filbaserade SQLite-CI-inställning.
- `typecheck.txt`, `lint.txt`: godkända.
- `python-unit.txt`, `web-tests.txt`: 4 respektive 16 godkända.
- `export.txt`: webb, iOS och Android. Inte native körning.
- `npm-audit.json`: 13 moderate; se bedömning i leveransen.
- `login-390.png`: faktisk webbvy vid 390 px; hela browserflödet är inte verifierat.
- `isolation.txt`, `../home-app-transfer.json`: arbetskopia, bas och dokumenthashar.

Expo doctor: 21/21 vid avslutande kontroll. iOS-simulator saknas (bara
CommandLineTools, ingen simctl). Android SDK/adb/emulator saknas. Inga
fysiska enheter har provats. Lokala previewservrar har avslutats.
