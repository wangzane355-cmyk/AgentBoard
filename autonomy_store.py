"""Transactional checkpoints and an append-only event journal for autonomous work."""
from __future__ import annotations

import json
import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path


def utc_now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class MissionStore:
    def __init__(self, directory):
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)
        self.path = self.directory / "autonomy.sqlite3"
        self.lock = threading.RLock()
        with self.connect() as db:
            db.executescript("""
                PRAGMA journal_mode=WAL;
                CREATE TABLE IF NOT EXISTS missions (
                    id TEXT PRIMARY KEY, payload TEXT NOT NULL, revision INTEGER NOT NULL DEFAULT 0);
                CREATE TABLE IF NOT EXISTS mission_events (
                    seq INTEGER PRIMARY KEY AUTOINCREMENT, mission_id TEXT NOT NULL,
                    at TEXT NOT NULL, kind TEXT NOT NULL, message TEXT NOT NULL, detail TEXT NOT NULL);
                CREATE INDEX IF NOT EXISTS mission_events_lookup ON mission_events(mission_id, seq);
                CREATE TABLE IF NOT EXISTS runtime_owner (
                    name TEXT PRIMARY KEY, payload TEXT NOT NULL);
            """)

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=15)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA busy_timeout=15000")
        try:
            with db:
                yield db
        finally:
            db.close()

    def create(self, mission):
        payload = {**mission, "created_at": utc_now(), "updated_at": utc_now(), "revision": 0}
        with self.lock, self.connect() as db:
            db.execute("INSERT INTO missions(id,payload) VALUES(?,?)",
                       (payload["id"], json.dumps(payload, ensure_ascii=False)))
            self._event(db, payload["id"], "created", "目标已保存，等待开始", {})
        return payload

    def get(self, mission_id):
        with self.connect() as db:
            row = db.execute("SELECT payload FROM missions WHERE id=?", (mission_id,)).fetchone()
        if row is None:
            raise ValueError("自主任务不存在")
        return json.loads(row["payload"])

    def all(self):
        with self.connect() as db:
            rows = db.execute("SELECT payload FROM missions ORDER BY rowid DESC").fetchall()
        return [json.loads(row["payload"]) for row in rows]

    def update(self, mission_id, patch, kind=None, message="", detail=None, revision=None):
        with self.lock, self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT payload,revision FROM missions WHERE id=?", (mission_id,)).fetchone()
            if row is None:
                raise ValueError("自主任务不存在")
            if revision is not None and row["revision"] != revision:
                raise ValueError("任务状态已变化，请刷新后重试")
            data = json.loads(row["payload"])
            data.update(patch)
            data.update(updated_at=utc_now(), revision=row["revision"] + 1)
            db.execute("UPDATE missions SET payload=?,revision=? WHERE id=?",
                       (json.dumps(data, ensure_ascii=False), data["revision"], mission_id))
            if kind:
                self._event(db, mission_id, kind, message, detail or {})
        return data

    def event(self, mission_id, kind, message, detail=None):
        with self.lock, self.connect() as db:
            self._event(db, mission_id, kind, message, detail or {})

    @staticmethod
    def _event(db, mission_id, kind, message, detail):
        db.execute("INSERT INTO mission_events(mission_id,at,kind,message,detail) VALUES(?,?,?,?,?)",
                   (mission_id, utc_now(), kind, message[:2000], json.dumps(detail, ensure_ascii=False)))

    def events(self, mission_id, after=0, limit=200):
        self.get(mission_id)
        with self.connect() as db:
            rows = db.execute("SELECT * FROM mission_events WHERE mission_id=? AND seq>? ORDER BY seq LIMIT ?",
                              (mission_id, max(0, int(after)), min(500, max(1, int(limit))))).fetchall()
        return [{**dict(row), "detail": json.loads(row["detail"])} for row in rows]

    def claim_owner(self, owner, alive):
        """One live scheduler owns this database; a stale PID alone proves nothing."""
        with self.lock, self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT payload FROM runtime_owner WHERE name='supervisor'").fetchone()
            previous = json.loads(row["payload"]) if row else None
            if previous and previous["token"] != owner["token"] and alive(previous):
                raise RuntimeError("另一个任务监督器仍在运行")
            db.execute("INSERT OR REPLACE INTO runtime_owner(name,payload) VALUES('supervisor',?)",
                       (json.dumps(owner),))

    def release_owner(self, token):
        with self.lock, self.connect() as db:
            row = db.execute("SELECT payload FROM runtime_owner WHERE name='supervisor'").fetchone()
            if row and json.loads(row["payload"])["token"] == token:
                db.execute("DELETE FROM runtime_owner WHERE name='supervisor'")
