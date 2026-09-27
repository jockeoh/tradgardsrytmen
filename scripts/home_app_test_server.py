#!/usr/bin/env python3
"""Disposable local manual-flow server. Never reads the configured production DB."""
import os
from pathlib import Path
import secrets
import subprocess
import sys
import tempfile

root = Path(__file__).resolve().parents[1]
folder = Path(tempfile.mkdtemp(prefix="garden-home-preview-"))
password = secrets.token_urlsafe(15)
env = {**os.environ, "DJANGO_SETTINGS_MODULE": "config.settings", "TRADGARDSRYTMEN_DB_ENGINE": "sqlite",
       "TRADGARDSRYTMEN_DB_PATH": str(folder / "preview.sqlite3"), "TRADGARDSRYTMEN_DEBUG": "1",
       "TRADGARDSRYTMEN_PRIVATE_MOBILE_AUTH": "1", "TRADGARDSRYTMEN_SECRET_KEY": secrets.token_urlsafe(48),
       "TRADGARDSRYTMEN_ALLOWED_HOSTS": "localhost,127.0.0.1", "TRADGARDSRYTMEN_MOBILE_WEB_ORIGINS": "http://localhost:8083",
       "TRADGARDSRYTMEN_DURABLE_JOBS": "0", "OPENAI_API_KEY": "", "HOME_TEST_PASSWORD": password}
subprocess.run([sys.executable, "manage.py", "migrate", "--noinput"], cwd=root, env=env, check=True, stdout=subprocess.DEVNULL)
subprocess.run([sys.executable, "-c", "import os,django; django.setup(); from accounts.models import User; [User.objects.create_user(username=u,password=os.environ['HOME_TEST_PASSWORD']) for u in ('kim','alex')]"], cwd=root, env=env, check=True)
print(f"Isolerad testdatabas: {folder}\nServer: http://127.0.0.1:8133\nTestkonton: kim / alex\nTillfälligt testlösenord: {password}", flush=True)
subprocess.run([sys.executable, "manage.py", "runserver", "127.0.0.1:8133", "--noreload"], cwd=root, env=env, check=True)
