from pathlib import Path
import sqlite3
from tempfile import TemporaryDirectory
from unittest.mock import patch
from django.core.management.base import CommandError
from django.test import SimpleTestCase, override_settings
from garden.database_backup import backup_database


class BackupTests(SimpleTestCase):
    def test_sqlite_backup_is_read_only_and_private(self):
        with TemporaryDirectory() as directory:
            source = Path(directory) / 'source.sqlite3'
            with sqlite3.connect(source) as db:
                db.execute('create table history (note text)')
                db.execute("insert into history values ('bevara åäö')")
            original = source.read_bytes()
            with override_settings(DATA_DIR=Path(directory), DATABASES={'default': {'ENGINE': 'django.db.backends.sqlite3', 'NAME': source}}):
                backup = backup_database()
            self.assertEqual(source.read_bytes(), original)
            self.assertEqual(backup.stat().st_mode & 0o777, 0o600)
            with sqlite3.connect(backup) as db:
                self.assertEqual(db.execute('select note from history').fetchone()[0], 'bevara åäö')

    def test_missing_sqlite_source_never_creates_empty_database(self):
        with TemporaryDirectory() as directory:
            source = Path(directory) / 'missing.sqlite3'
            with override_settings(DATA_DIR=Path(directory), DATABASES={'default': {'ENGINE': 'django.db.backends.sqlite3', 'NAME': source}}):
                with self.assertRaises(CommandError):
                    backup_database()
            self.assertFalse(source.exists())
            self.assertFalse(list((Path(directory) / 'backups').iterdir()))

    def test_postgres_failure_does_not_publish_partial_backup_or_use_sqlite(self):
        with TemporaryDirectory() as directory:
            config = {'ENGINE':'django.db.backends.postgresql', 'NAME':'p3', 'HOST':'localhost', 'USER':'p3', 'PASSWORD':'secret'}
            with override_settings(DATA_DIR=Path(directory), DATABASES={'default': config}), patch('garden.database_backup.subprocess.run', side_effect=OSError('failed')) as command, patch('garden.database_backup.sqlite3.connect') as sqlite:
                with self.assertRaises(CommandError):
                    backup_database()
                sqlite.assert_not_called()
                self.assertNotIn('secret', str(command.call_args.args))
            self.assertFalse(list((Path(directory) / 'backups').iterdir()))
