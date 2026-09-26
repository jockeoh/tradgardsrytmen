"""File-backed SQLite test database, for real multi-connection concurrency tests."""
import os
from .settings import *  # noqa
DATABASES['default']['TEST'] = {'NAME': os.environ['P3_SQLITE_TEST_PATH']}
