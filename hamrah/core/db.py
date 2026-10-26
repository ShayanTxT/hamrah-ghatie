"""پایگاه داده SQLite — تکفایل ``data/app.db``.

* WAL برای مقاومت در برابر قطع برق/کشیدن فلش.
* هر تراکنش یک اتصال تازه میگیرد (ایمن برای چند نخ).
* FTS5 برای جستجوی تماممتن فارسی (هم متن و هم پرسوجو نرمال میشوند).
"""
from __future__ import annotations

import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

SCHEMA_VERSION = 1

SCHEMA = """
CREATE TABLE IF NOT EXISTS meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

-- ۱) وضعیت اتصال
CREATE TABLE IF NOT EXISTS state_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts REAL NOT NULL,
    state TEXT NOT NULL,
    detail TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_state_ts ON state_events(ts);

CREATE TABLE IF NOT EXISTS outages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    state TEXT NOT NULL,
    worst_state TEXT NOT NULL,
    started_at REAL NOT NULL,
    ended_at REAL
);
CREATE INDEX IF NOT EXISTS idx_outages_start ON outages(started_at);

CREATE TABLE IF NOT EXISTS probe_samples (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts REAL NOT NULL,
    state TEXT NOT NULL,
    external_ok INTEGER NOT NULL DEFAULT 0,
    internal_ok INTEGER NOT NULL DEFAULT 0,
    dns_ok INTEGER NOT NULL DEFAULT 0,
    gateway_ok INTEGER NOT NULL DEFAULT 0,
    detail TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_samples_ts ON probe_samples(ts);

-- ۲) کیف آمادگی
CREATE TABLE IF NOT EXISTS downloads (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    url TEXT NOT NULL,
    kind TEXT NOT NULL DEFAULT 'file',
    dest TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    bytes_done INTEGER NOT NULL DEFAULT 0,
    bytes_total INTEGER NOT NULL DEFAULT 0,
    etag TEXT,
    last_modified TEXT,
    error TEXT,
    attempts INTEGER NOT NULL DEFAULT 0,
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL,
    UNIQUE(url, dest)
);

CREATE TABLE IF NOT EXISTS checklist (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    note TEXT NOT NULL DEFAULT '',
    category TEXT NOT NULL DEFAULT 'سایر',
    link TEXT NOT NULL DEFAULT '',
    done INTEGER NOT NULL DEFAULT 0,
    sort INTEGER NOT NULL DEFAULT 0,
    builtin INTEGER NOT NULL DEFAULT 0
);

-- ۳) کتابخانهٔ آفلاین
CREATE TABLE IF NOT EXISTS documents (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    path TEXT NOT NULL UNIQUE,
    title TEXT NOT NULL DEFAULT '',
    kind TEXT NOT NULL DEFAULT 'text',
    source TEXT NOT NULL DEFAULT 'file',
    size INTEGER NOT NULL DEFAULT 0,
    mtime REAL NOT NULL DEFAULT 0,
    content TEXT NOT NULL DEFAULT '',
    indexed_at REAL NOT NULL
);

CREATE VIRTUAL TABLE IF NOT EXISTS documents_fts USING fts5(
    title_norm,
    body_norm,
    path UNINDEXED,
    tokenize = 'unicode61 remove_diacritics 2'
);

CREATE TABLE IF NOT EXISTS zim_archives (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    path TEXT NOT NULL UNIQUE,
    title TEXT NOT NULL DEFAULT '',
    entry_count INTEGER NOT NULL DEFAULT 0,
    indexed_count INTEGER NOT NULL DEFAULT 0,
    added_at REAL NOT NULL
);

-- ۴) دستیار آفلاین
CREATE TABLE IF NOT EXISTS chats (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL DEFAULT 'گفتگوی جدید',
    model TEXT NOT NULL DEFAULT '',
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS chat_messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    chat_id INTEGER NOT NULL,
    role TEXT NOT NULL,
    content TEXT NOT NULL,
    sources TEXT NOT NULL DEFAULT '',
    ts REAL NOT NULL,
    FOREIGN KEY (chat_id) REFERENCES chats(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_chat_messages ON chat_messages(chat_id, id);

-- ۵) شبکهٔ محلی
CREATE TABLE IF NOT EXISTS lan_messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    peer_id TEXT NOT NULL,
    direction TEXT NOT NULL,
    content TEXT NOT NULL,
    ts REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_lan_ts ON lan_messages(ts);
"""


class Database:
    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.initialize()

    def connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.path), timeout=15, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute("PRAGMA busy_timeout=10000")
        return conn

    def initialize(self) -> None:
        with self.transaction() as conn:
            conn.executescript(SCHEMA)
            conn.execute(
                "INSERT OR REPLACE INTO meta(key, value) VALUES('schema_version', ?)",
                (str(SCHEMA_VERSION),),
            )

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        conn = self.connect()
        try:
            conn.execute("BEGIN IMMEDIATE")
            yield conn
            conn.commit()
        except BaseException:
            conn.rollback()
            raise
        finally:
            conn.close()

    def execute(self, sql: str, params: tuple[Any, ...] = ()) -> int:
        with self.transaction() as conn:
            cur = conn.execute(sql, params)
            return int(cur.lastrowid or 0)

    def query(self, sql: str, params: tuple[Any, ...] = ()) -> list[sqlite3.Row]:
        conn = self.connect()
        try:
            return list(conn.execute(sql, params).fetchall())
        finally:
            conn.close()

    def scalar(self, sql: str, params: tuple[Any, ...] = ()) -> Any:
        rows = self.query(sql, params)
        return rows[0][0] if rows else None

    @staticmethod
    def now() -> float:
        return time.time()

    def vacuum(self) -> None:
        """فشردهسازی (مثلاً بعد از حذف ایندکس یک ZIM بزرگ)."""
        conn = self.connect()
        try:
            conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
            conn.execute("VACUUM")
        finally:
            conn.close()
