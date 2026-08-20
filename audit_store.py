"""Journal local persistant avec chaînage cryptographique des décisions."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from pathlib import Path
from typing import Any


DEFAULT_DB = Path(__file__).parent / "data" / "audit.db"


def _connect(db_path: Path = DEFAULT_DB) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(db_path)
    connection.row_factory = sqlite3.Row
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS decisions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            payload TEXT NOT NULL,
            previous_hash TEXT NOT NULL,
            record_hash TEXT NOT NULL UNIQUE,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    return connection


def append_record(record: dict[str, Any], db_path: Path = DEFAULT_DB) -> dict[str, Any]:
    payload = json.dumps(record, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    with _connect(db_path) as connection:
        previous = connection.execute(
            "SELECT record_hash FROM decisions ORDER BY id DESC LIMIT 1"
        ).fetchone()
        previous_hash = previous["record_hash"] if previous else "GENESIS"
        record_hash = hashlib.sha256(f"{previous_hash}:{payload}".encode("utf-8")).hexdigest()
        cursor = connection.execute(
            "INSERT INTO decisions(payload, previous_hash, record_hash) VALUES (?, ?, ?)",
            (payload, previous_hash, record_hash),
        )
    return {**record, "audit_id": cursor.lastrowid, "empreinte": record_hash}


def list_records(limit: int = 500, db_path: Path = DEFAULT_DB) -> list[dict[str, Any]]:
    if not 1 <= limit <= 10_000:
        raise ValueError("Limite de journal invalide")
    with _connect(db_path) as connection:
        rows = connection.execute(
            "SELECT id, payload, record_hash FROM decisions ORDER BY id DESC LIMIT ?",
            (limit,),
        ).fetchall()
    return [
        {
            **json.loads(row["payload"]),
            "audit_id": row["id"],
            "empreinte": row["record_hash"],
        }
        for row in rows
    ]


def verify_chain(db_path: Path = DEFAULT_DB) -> dict[str, Any]:
    with _connect(db_path) as connection:
        rows = connection.execute(
            "SELECT id, payload, previous_hash, record_hash FROM decisions ORDER BY id"
        ).fetchall()
    expected_previous = "GENESIS"
    for row in rows:
        expected_hash = hashlib.sha256(
            f"{expected_previous}:{row['payload']}".encode("utf-8")
        ).hexdigest()
        if row["previous_hash"] != expected_previous or row["record_hash"] != expected_hash:
            return {"valid": False, "count": len(rows), "broken_at": row["id"]}
        expected_previous = row["record_hash"]
    return {"valid": True, "count": len(rows), "broken_at": None}


def export_json(db_path: Path = DEFAULT_DB) -> str:
    records = list(reversed(list_records(10_000, db_path)))
    return json.dumps(records, ensure_ascii=False, indent=2)
