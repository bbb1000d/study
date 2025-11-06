import os
import sqlite3
import sys
import tempfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

TEST_DATA_DIR = Path(tempfile.mkdtemp(prefix="studymate-test-"))
TEST_DB_PATH = TEST_DATA_DIR / "studymate.db"
os.environ.setdefault("STUDYMATE_DATA_DIR", str(TEST_DATA_DIR))
os.environ.setdefault("STUDYMATE_DB_PATH", str(TEST_DB_PATH))

from study_app.database import initialise
from study_app.repository import StorageRepository


@pytest.fixture
def repo():
    if TEST_DB_PATH.exists():
        TEST_DB_PATH.unlink()
    initialise()
    connection = sqlite3.connect(TEST_DB_PATH)
    connection.row_factory = sqlite3.Row
    repository = StorageRepository(connection)
    try:
        yield repository
    finally:
        connection.close()
