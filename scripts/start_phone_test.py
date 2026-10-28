#!/usr/bin/env python3
"""Run the isolated phone preview on this Mac's private Tailscale network."""
import json
import os
from pathlib import Path
import shutil
import signal
import socket
import subprocess
import sys
import time
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
PYTHON = ROOT / ".venv/bin/python"
TAILSCALE = shutil.which("tailscale") or "/Applications/Tailscale.app/Contents/MacOS/Tailscale"
API_PORT, METRO_PORT, HTTPS_PORT = 8133, 8083, 18443


def main():
    if not PYTHON.exists() or not (ROOT / "mobile/node_modules/expo/bin/cli").exists():
        raise SystemExit("Installera .venv/requirements.txt och mobile/npm ci först. Se docs/phone-test.md.")
    status = json.loads(subprocess.check_output([TAILSCALE, "status", "--json"]))
    if status.get("BackendState") != "Running":
        raise SystemExit("Starta Tailscale på Macen först.")
    hostname = status["Self"]["DNSName"].rstrip(".")
    address = next(ip for ip in status["TailscaleIPs"] if ":" not in ip)
    origin = f"https://{hostname}:{HTTPS_PORT}"
    for port in (API_PORT, METRO_PORT):
        with socket.socket() as check:
            if check.connect_ex(("127.0.0.1", port)) == 0:
                raise SystemExit(f"Port {port} används redan. Stoppa den tidigare testsessionen först.")
    serve = json.loads(subprocess.check_output([TAILSCALE, "serve", "status", "--json"]))
    # Never overwrite another private service using our dedicated port.
    existing = serve.get("Web", {}).get(f"{hostname}:{HTTPS_PORT}")
    expected = {"Handlers": {"/": {"Proxy": f"http://127.0.0.1:{API_PORT}"}}}
    if existing and existing != expected:
        raise SystemExit(f"Tailscale-port {HTTPS_PORT} har en annan tjänst. Lämnar den orörd.")
    if str(HTTPS_PORT) in serve.get("TCP", {}) and not existing:
        raise SystemExit(f"Tailscale-port {HTTPS_PORT} används redan för annan trafik.")
    server = [str(PYTHON), "scripts/phone_test_server.py", "--port", str(API_PORT),
              "--host", hostname, "--web-origin", f"http://localhost:{METRO_PORT}"]
    subprocess.run(server + ["--prepare-only"], cwd=ROOT, check=True)
    subprocess.run([TAILSCALE, "serve", "--bg", f"--https={HTTPS_PORT}",
                    f"http://127.0.0.1:{API_PORT}"], check=True)
    children = []
    def stop(_signum=None, _frame=None):
        raise KeyboardInterrupt
    signal.signal(signal.SIGTERM, stop)
    try:
        children.append(subprocess.Popen(server, cwd=ROOT, start_new_session=True))
        for _ in range(80):
            if children[0].poll() is not None:
                raise RuntimeError("Testservern avslutades före start.")
            try:
                with urllib.request.urlopen(f"http://127.0.0.1:{API_PORT}/health/", timeout=1) as response:
                    if response.status == 200:
                        break
            except OSError:
                time.sleep(0.25)
        else:
            raise RuntimeError("Testservern svarade inte inom 20 sekunder.")
        env = {k: v for k, v in os.environ.items()
               if not k.startswith("EXPO_PUBLIC_") and k not in ("EXPO_OFFLINE", "CI")}
        env.update(EXPO_NO_TELEMETRY="1", EXPO_PUBLIC_API_ORIGIN=origin,
                   REACT_NATIVE_PACKAGER_HOSTNAME=address, EXPO_NO_DOTENV="1")
        print(f"\nAPI: {origin}\nExpo Go: exp://{address}:{METRO_PORT}\n"
              "Tailscale ska vara på på iPhone. Samma Expo-konto krävs på Mac och iPhone.\n"
              "Ctrl-C stoppar båda testprocesserna; testdata finns kvar.\n", flush=True)
        children.append(subprocess.Popen(["node", "node_modules/expo/bin/cli", "start", "--go",
                                          "--lan", "--port", str(METRO_PORT)],
                                         cwd=ROOT / "mobile", env=env, start_new_session=True))
        while all(child.poll() is None for child in children):
            time.sleep(0.5)
    except KeyboardInterrupt:
        pass
    finally:
        for child in children:
            if child.poll() is None:
                os.killpg(child.pid, signal.SIGTERM)
        for child in children:
            try:
                child.wait(timeout=8)
            except subprocess.TimeoutExpired:
                os.killpg(child.pid, signal.SIGKILL)
                child.wait()
        print("Testprocesserna är stoppade. Testdata och den privata HTTPS-adressen finns kvar.")


if __name__ == "__main__":
    main()
