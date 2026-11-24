import os
import sqlite3
from pathlib import Path


def data_dir() -> Path:
    # %APPDATA%\Scheduler. SCHEDULER_DATA_DIR overrides it (tests, portable use).
    base = os.environ.get("SCHEDULER_DATA_DIR") or Path(os.environ.get("APPDATA", Path.home())) / "Scheduler"
    path = Path(base)
    path.mkdir(parents=True, exist_ok=True)
    return path


def connect() -> sqlite3.Connection:
    conn = sqlite3.connect(data_dir() / "scheduler.db")
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")  # UI, mail watcher and agents write at the same time
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init() -> None:
    # Tables are added here as each feature is built.
    with connect() as conn:
        conn.execute("CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
        conn.execute("INSERT OR IGNORE INTO meta (key, value) VALUES ('schema_version', '1')")
