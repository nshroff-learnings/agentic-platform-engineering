import hashlib
import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from uuid import uuid4

from .contracts import Fault, Principal

SCHEMA = """
CREATE TABLE runs (
 id TEXT PRIMARY KEY, tenant TEXT NOT NULL, project TEXT NOT NULL, request TEXT NOT NULL,
 state TEXT NOT NULL, revision INTEGER NOT NULL DEFAULT 0, design_id TEXT, plan_id TEXT
);
CREATE TABLE artifacts (
 id TEXT PRIMARY KEY, run_id TEXT NOT NULL REFERENCES runs(id), revision INTEGER NOT NULL,
 kind TEXT NOT NULL, author TEXT NOT NULL, content TEXT NOT NULL, sha256 TEXT NOT NULL
);
CREATE TABLE events (
 seq INTEGER PRIMARY KEY AUTOINCREMENT, run_id TEXT NOT NULL REFERENCES runs(id),
 at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
 actor TEXT NOT NULL, kind TEXT NOT NULL, data TEXT NOT NULL
);
CREATE TABLE tasks (
 id TEXT PRIMARY KEY, run_id TEXT NOT NULL REFERENCES runs(id), design_id TEXT UNIQUE NOT NULL REFERENCES artifacts(id),
 status TEXT NOT NULL, result_id TEXT REFERENCES artifacts(id)
);
"""


def uid():
    return uuid4().hex


def encode(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


class Store:
    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.path = path
        with self.transaction() as db:
            version = db.execute("PRAGMA user_version").fetchone()[0]
            if version > 1:
                raise RuntimeError("Database requires a newer APE version")
            if version == 0:
                for statement in SCHEMA.split(";"):
                    if statement.strip():
                        db.execute(statement)
                for table in ("events", "artifacts"):
                    for action in ("UPDATE", "DELETE"):
                        db.execute(f"""CREATE TRIGGER {table}_{action} BEFORE {action} ON {table}
                                       BEGIN SELECT RAISE(ABORT, 'immutable record'); END""")
                db.execute("PRAGMA user_version=1")

    @contextmanager
    def transaction(self):
        db = sqlite3.connect(self.path, timeout=10, isolation_level=None)
        db.row_factory = sqlite3.Row
        try:
            db.execute("PRAGMA foreign_keys=ON")
            db.execute("BEGIN IMMEDIATE")
            yield db
            db.commit()
        finally:
            db.close()


def require(actor: Principal, right: str):
    if right not in actor.rights:
        raise Fault("Insufficient permission", 403)


def run_for(db, actor, run_id):
    row = db.execute(
        "SELECT * FROM runs WHERE id=? AND tenant=? AND project=?",
        (run_id, actor.tenant, actor.project),
    ).fetchone()
    if row is None:
        raise Fault("Unknown request", 404)
    return row


def event(db, run_id, actor, kind, **data):
    return db.execute(
        "INSERT INTO events(run_id,actor,kind,data) VALUES(?,?,?,?)",
        (run_id, actor, kind, encode(data)),
    ).lastrowid


def artifact(db, run, kind, author, content):
    key = uid()
    db.execute(
        "INSERT INTO artifacts VALUES(?,?,?,?,?,?,?)",
        (
            key,
            run["id"],
            run["revision"],
            kind,
            author,
            content,
            hashlib.sha256(content.encode()).hexdigest(),
        ),
    )
    return key


def get_artifact(db, run_id, key):
    row = db.execute(
        "SELECT * FROM artifacts WHERE id=? AND run_id=?", (key, run_id)
    ).fetchone()
    if row is None:
        raise Fault("Unknown artifact", 404)
    return row
