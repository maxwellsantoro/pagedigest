"""Durable crawl state. pagedigest only helps *stateful* consumers (spec 1), so
state persistence is not optional -- it's the substrate the whole protocol runs
on. SQLite keeps it dependency-free and survivable across runs.
"""
from __future__ import annotations

import sqlite3
import time
from typing import Optional

TRUSTED = "trusted"
SITE_DISTRUSTED = "site_distrusted"


class Store:
    def __init__(self, path: str = "pagedigest_state.db"):
        self.db = sqlite3.connect(path)
        self.db.executescript("""
        CREATE TABLE IF NOT EXISTS rev(
            origin TEXT, url TEXT, rev INTEGER, size INTEGER DEFAULT 0,
            PRIMARY KEY(origin, url));
        CREATE TABLE IF NOT EXISTS site(
            origin TEXT PRIMARY KEY, site_rev INTEGER, first_seen REAL);
        CREATE TABLE IF NOT EXISTS trust(
            origin TEXT PRIMARY KEY, state TEXT, clean_windows INTEGER DEFAULT 0);
        CREATE TABLE IF NOT EXISTS url_suspect(
            origin TEXT, url TEXT, PRIMARY KEY(origin, url));
        """)
        self.db.commit()

    # -- per-URL rev + size --
    def get_rev(self, origin: str, url: str):
        row = self.db.execute("SELECT rev, size FROM rev WHERE origin=? AND url=?",
                              (origin, url)).fetchone()
        return row if row else (None, 0)

    def set_rev(self, origin: str, url: str, rev: int, size: int = 0):
        self.db.execute(
            "INSERT INTO rev(origin,url,rev,size) VALUES(?,?,?,?) "
            "ON CONFLICT(origin,url) DO UPDATE SET rev=excluded.rev, size=excluded.size",
            (origin, url, rev, size))
        self.db.commit()

    # -- site rev + first-contact timestamp (for bootstrap auditing) --
    def get_site(self, origin: str):
        row = self.db.execute("SELECT site_rev, first_seen FROM site WHERE origin=?",
                              (origin,)).fetchone()
        return row if row else (None, None)

    def set_site(self, origin: str, site_rev: int):
        seen = self.get_site(origin)[1] or time.time()
        self.db.execute(
            "INSERT INTO site(origin,site_rev,first_seen) VALUES(?,?,?) "
            "ON CONFLICT(origin) DO UPDATE SET site_rev=excluded.site_rev",
            (origin, site_rev, seen))
        self.db.commit()

    # -- trust --
    def trust_state(self, origin: str) -> str:
        row = self.db.execute("SELECT state FROM trust WHERE origin=?", (origin,)).fetchone()
        return row[0] if row else TRUSTED

    def set_trust(self, origin: str, state: str):
        self.db.execute(
            "INSERT INTO trust(origin,state,clean_windows) VALUES(?,?,0) "
            "ON CONFLICT(origin) DO UPDATE SET state=excluded.state",
            (origin, state))
        self.db.commit()

    def mark_url_suspect(self, origin: str, url: str):
        self.db.execute("INSERT OR IGNORE INTO url_suspect(origin,url) VALUES(?,?)",
                        (origin, url))
        self.db.commit()

    def is_url_suspect(self, origin: str, url: str) -> bool:
        return self.db.execute("SELECT 1 FROM url_suspect WHERE origin=? AND url=?",
                              (origin, url)).fetchone() is not None

    def clear_url_suspect(self, origin: str, url: str):
        self.db.execute("DELETE FROM url_suspect WHERE origin=? AND url=?", (origin, url))
        self.db.commit()

    def count_url_suspects(self, origin: str) -> int:
        return self.db.execute("SELECT COUNT(*) FROM url_suspect WHERE origin=?",
                              (origin,)).fetchone()[0]

    def close(self):
        self.db.close()
