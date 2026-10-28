#!/usr/bin/env python3
"""Persistent, synthetic phone-test installation; never imports production data.

Run with the project virtualenv. --prepare-only migrates/seeds without listening.
The fixed, ignored .tmp-data/phone-test directory is this installation's boundary.
"""
import argparse
from contextlib import contextmanager
from datetime import timedelta
import fcntl
import ipaddress
import json
import os
from pathlib import Path
import secrets
import sqlite3
import sys
from uuid import uuid4


ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / ".tmp-data" / "phone-test"
DATABASE_PATH = DATA_DIR / "phone-test.sqlite3"
CREDENTIALS_PATH = DATA_DIR / "credentials.json"


def private_host(value):
    """Only local literals or an explicit Tailscale DNS name, never wildcards."""
    if value == "localhost":
        return value
    try:
        address = ipaddress.ip_address(value)
    except ValueError:
        import re
        if re.fullmatch(r"[a-z0-9-]+(?:\.[a-z0-9-]+)*\.ts\.net", value):
            return value
    else:
        private_networks = ("10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16", "100.64.0.0/10")
        if address.is_loopback or any(address in ipaddress.ip_network(net) for net in private_networks):
            return value
    raise argparse.ArgumentTypeError("Ange localhost, en privat IPv4-adress eller ett exakt .ts.net-namn.")


def local_origin(value):
    from urllib.parse import urlsplit
    parsed = urlsplit(value)
    if (parsed.scheme not in {"http", "https"} or not parsed.hostname
            or parsed.username or parsed.password or parsed.path or parsed.query or parsed.fragment):
        raise argparse.ArgumentTypeError("Ange ett exakt lokalt ursprung, t.ex. http://localhost:8083.")
    private_host(parsed.hostname)
    try:
        parsed.port
    except ValueError as exc:
        raise argparse.ArgumentTypeError(str(exc)) from exc
    return value


def _check_path(path):
    # Refuse symlinks even when they point inside the checkout: this script must
    # never migrate a redirected database, key, or inherited data directory.
    for candidate in (ROOT / ".tmp-data", DATA_DIR, path):
        if candidate.is_symlink():
            raise RuntimeError(f"Testinstallationen får inte använda symboliska länkar: {candidate}")


def _read_credentials():
    _check_path(CREDENTIALS_PATH)
    credentials = json.loads(CREDENTIALS_PATH.read_text())
    if (credentials.get("format") != "phone-test-1"
            or not isinstance(credentials.get("installation_id"), str)
            or len(credentials.get("secret_key", "")) < 48
            or len(credentials.get("password", "")) < 8):
        raise RuntimeError("Testinstallationens credentials.json är ogiltig; inga data har ändrats.")
    CREDENTIALS_PATH.chmod(0o600)
    return credentials


def verify_database(credentials):
    _check_path(DATABASE_PATH)
    try:
        with sqlite3.connect(DATABASE_PATH.as_uri() + "?mode=ro", uri=True) as connection:
            marker = connection.execute("SELECT installation_id FROM phone_test_installation").fetchall()
    except sqlite3.Error as exc:
        raise RuntimeError("Databasen saknar testinstallationens markör; vägrar öppna den.") from exc
    if marker != [(credentials["installation_id"],)]:
        raise RuntimeError("Databasen tillhör inte denna testinstallation; vägrar öppna den.")


@contextmanager
def installation_lock():
    _check_path(DATA_DIR)
    DATA_DIR.mkdir(parents=True, exist_ok=True, mode=0o700)
    DATA_DIR.chmod(0o700)
    path = DATA_DIR / ".installation.lock"
    _check_path(path)
    with path.open("a") as lock:
        os.fchmod(lock.fileno(), 0o600)
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise RuntimeError("Testinstallationen används redan av en annan server eller förberedelse.") from exc
        yield


def prepare_files():
    for path in (DATABASE_PATH, CREDENTIALS_PATH):
        _check_path(path)
    if DATABASE_PATH.exists() and not CREDENTIALS_PATH.exists():
        raise RuntimeError("Befintlig databas saknar testuppgifter; vägrar återanvända den.")
    if not CREDENTIALS_PATH.exists():
        credentials = {"format": "phone-test-1", "installation_id": str(uuid4()),
                       "secret_key": secrets.token_urlsafe(48), "password": secrets.token_urlsafe(18),
                       "usernames": ["kim", "alex"]}
        descriptor = os.open(CREDENTIALS_PATH, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "w") as target:
            json.dump(credentials, target, indent=2)
            target.write("\n")
    credentials = _read_credentials()
    if not DATABASE_PATH.exists():
        # Reserve the file exclusively before SQLite opens it.
        descriptor = os.open(DATABASE_PATH, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        os.close(descriptor)
        with sqlite3.connect(DATABASE_PATH) as connection:
            connection.execute("CREATE TABLE phone_test_installation (installation_id TEXT NOT NULL, seeded INTEGER NOT NULL DEFAULT 0)")
            connection.execute("INSERT INTO phone_test_installation (installation_id) VALUES (?)", [credentials["installation_id"]])
    verify_database(credentials)
    DATABASE_PATH.chmod(0o600)
    return credentials


def seed_fixture(credentials):
    """Seed once transactionally; relaunch preserves edits, approvals and tokens."""
    from django.contrib.auth import get_user_model
    from django.db import connection, transaction
    from django.utils import timezone
    from garden.care_contract import validate_rule
    from garden.models import (CarePlanVersion, CareRule, Garden, GardenArea, GardenItem,
                               GardenMembership, GardenSettings, ResearchProposal,
                               SourceReference, TaskOccurrence, WorkIdentity)
    from garden.tasks import materialize_rule

    with transaction.atomic():
        with connection.cursor() as cursor:
            cursor.execute("SELECT seeded FROM phone_test_installation")
            if cursor.fetchone()[0]:
                return False
        if get_user_model().objects.exists() or Garden.objects.exists():
            raise RuntimeError("Oväntade befintliga konton: inga testdata har lagts till.")
        today, now = timezone.localdate(), timezone.now()
        users = {name: get_user_model().objects.create_user(username=name, password=credentials["password"],
                    first_name=f"{name.title()} (test)") for name in ("kim", "alex")}
        garden = Garden.objects.create(name="Telefonprovet · testträdgård")
        extra = Garden.objects.create(name="Balkongen · testträdgård")
        for user in users.values():
            GardenMembership.objects.create(garden=garden, user=user, role="owner")
        GardenMembership.objects.create(garden=extra, user=users["kim"], role="owner")
        for target in (garden, extra):
            GardenSettings.objects.create(garden=target, garden_name=target.name, city="Karlskrona",
                cultivation_zone="1", exposure="Syntetiskt testläge; inga riktiga odlingsråd")
        bed = GardenArea.objects.create(garden=garden, name="Rabatten", sort_order=1)
        patio = GardenArea.objects.create(garden=garden, name="Uteplatsen", sort_order=2)
        rose = GardenItem.objects.create(garden=garden, name="Ros · test", canonical_name="Ros", area=bed,
            category="Buske", cultivar="Testsort", location="Vid staketet", notes="Påhittad växt för telefonprovet.")
        berry = GardenItem.objects.create(garden=garden, name="Hallon · test", area=bed, kind="group", quantity=3,
            notes="Här finns ett syntetiskt planförslag att granska och godkänna.")
        herb = GardenItem.objects.create(garden=garden, name="Rosmarin · test", area=patio,
            notes="Prova behovsuppgift och bortval på denna växt.")
        GardenItem.objects.create(garden=extra, name="Pelargon · test", notes="Visas bara i den andra testträdgården.")
        warning = "Syntetiskt testunderlag, manuellt skapat för telefonprovet. Ingen AI eller extern källkontroll har körts. Använd inte detta som odlingsråd."
        source_url = "https://phone-test.invalid/syntetiskt-underlag"

        def plan(item, status):
            result = CarePlanVersion.objects.create(item=item, version=1, status=status, source_type="phone-test",
                summary=warning, warnings=[warning], reviewed_at=now if status == "active" else None,
                effective_from=today if status == "active" else None)
            SourceReference.objects.create(plan=result, title="Syntetisk testkälla – ingen extern verifiering",
                url=source_url, domain="phone-test.invalid", summary=warning)
            return result

        def rule(item, care_plan, key, title, instructions, **kwargs):
            work = WorkIdentity.objects.create(item=item, action_key=key, scope="hela-växten")
            result = CareRule.objects.create(item=item, plan=care_plan, work=work, title=title,
                instructions=instructions, relevance_reason="Syntetisk regel för att prova appens skötselflöde.",
                category="Övrigt", source_urls=[source_url], source_validated=True,
                active=care_plan.status == "active", start_month=1, end_month=12, **kwargs)
            validate_rule(result, activation=True)
            return result

        rose_plan = plan(rose, "active")
        planned = rule(rose, rose_plan, "test-anteckna", "Anteckna rosens läge",
            "Skriv en kort testanteckning om platsen och markera sedan uppgiften som klar.",
            advice_kind="planned", cadence="one_off", one_off_date=today, one_off_end=today + timedelta(days=7))
        materialize_rule(planned)
        herb_plan = plan(herb, "active")
        rule(herb, herb_plan, "test-behov", "Anteckna ett nytt behov",
            "Skapa en behovsuppgift och skriv en testanteckning innan du markerar den som klar.",
            advice_kind="on_demand", conditional=True, need_condition="När du vill prova behovsflödet")
        pending = plan(berry, "pending")
        rule(berry, pending, "test-granska", "Anteckna hallongruppens placering",
            "Skriv en testanteckning om gruppens placering efter att planen har godkänts.",
            advice_kind="planned", cadence="one_off", one_off_date=today, one_off_end=today + timedelta(days=14))
        ResearchProposal.objects.create(item=berry, plan=pending)
        for offset, title, status in [(-2, "Lägg till en testanteckning", "pending"),
                                       (4, "Prova en kommande uppgift", "pending"),
                                       (-1, "Redan genomfört telefonprov", "completed")]:
            day = today + timedelta(days=offset)
            TaskOccurrence.objects.create(item=rose, title=title, category="Övrigt", manual=True,
                instructions="Syntetisk manuell uppgift för att prova status och anteckningar.",
                occurrence_key=f"phone-test:{uuid4()}", season_year=day.year, occurrence_month=day.month,
                window_start=day, window_end=day, status=status,
                completed_at=now - timedelta(days=1) if status == "completed" else None,
                note="Sparad testhistorik" if status == "completed" else "")
        with connection.cursor() as cursor:
            cursor.execute("UPDATE phone_test_installation SET seeded = 1")
        return True


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prepare-only", action="store_true")
    parser.add_argument("--bind", default="127.0.0.1", help="Lokal lyssningsadress (standard 127.0.0.1).")
    parser.add_argument("--port", type=int, default=8133)
    parser.add_argument("--allow-network", action="store_true", help="Tillåt uttryckligen bindning på privat nätverk.")
    parser.add_argument("--host", type=private_host, action="append", default=[])
    parser.add_argument("--web-origin", type=local_origin, action="append", default=[])
    args = parser.parse_args(argv)
    try:
        address = ipaddress.IPv4Address(args.bind)
    except ipaddress.AddressValueError:
        parser.error("--bind ska vara en IPv4-adress.")
    if not 1 <= args.port <= 65535:
        parser.error("--port ska vara 1–65535.")
    if not address.is_loopback:
        if not args.allow_network or (args.bind == "0.0.0.0" and not args.host):
            parser.error("Privat nätverk kräver --allow-network och vid 0.0.0.0 även exakt --host.")
        if args.bind != "0.0.0.0":
            private_host(args.bind)
    hosts = ["localhost", "127.0.0.1", *args.host]
    if args.bind != "0.0.0.0":
        hosts.append(args.bind)
    os.environ["DJANGO_SETTINGS_MODULE"] = "config.phone_test_settings"
    os.environ["PHONE_TEST_ALLOWED_HOSTS"] = ",".join(dict.fromkeys(hosts))
    os.environ["PHONE_TEST_WEB_ORIGINS"] = ",".join(args.web_origin or ["http://localhost:8083"])
    sys.path.insert(0, str(ROOT))
    with installation_lock():
        credentials = prepare_files()
        import django
        django.setup()
        from django.core.management import call_command
        call_command("migrate", interactive=False, verbosity=0)
        seeded = seed_fixture(credentials)
        print(f"Isolerad testdatabas: {DATABASE_PATH}\nTestdata: {'skapade' if seeded else 'bevarade'}\n"
              f"Testkonton: kim / alex\nLösenord: {credentials['password']}\n"
              f"Sparade testuppgifter: {CREDENTIALS_PATH}\nAI och alla utgående servertransporter: avstängda", flush=True)
        if not args.prepare_only:
            call_command("runserver", f"{args.bind}:{args.port}", use_reloader=False)


if __name__ == "__main__":
    try:
        main()
    except (RuntimeError, OSError, ValueError) as error:
        raise SystemExit(f"Telefonprovet kunde inte starta: {error}") from error
