"""Historique SQLite des observations du scanner multi-marchés."""

from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import UTC, datetime
from pathlib import Path


DEFAULT_DB = Path(__file__).parent / "data" / "scanner.db"


def _connect(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(db_path)
    connection.row_factory = sqlite3.Row
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS observations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            cycle_id TEXT NOT NULL,
            timestamp TEXT NOT NULL,
            market TEXT NOT NULL,
            action TEXT NOT NULL,
            score REAL NOT NULL,
            confidence REAL NOT NULL,
            priority REAL NOT NULL,
            price_usd REAL NOT NULL,
            change_24h REAL NOT NULL,
            liquidity_usd REAL NOT NULL
        )
        """
    )
    return connection


def append_scan(results: list[dict], db_path: Path = DEFAULT_DB) -> dict:
    if not results:
        raise ValueError("Un scan vide ne peut pas être enregistré")
    cycle_id = uuid.uuid4().hex
    timestamp = datetime.now(UTC).isoformat()
    with _connect(db_path) as connection:
        connection.executemany(
            "INSERT INTO observations (cycle_id, timestamp, market, action, score, confidence, "
            "priority, price_usd, change_24h, liquidity_usd) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [
                (
                    cycle_id, timestamp, row["marché"], row["action"], row["score"],
                    row["confiance"], row["priorité"], row["prix_usd"],
                    row["variation_24h"], row["liquidité_usd"],
                )
                for row in results
            ],
        )
    return {"cycle_id": cycle_id, "timestamp": timestamp, "count": len(results)}


def list_observations(limit: int = 300, db_path: Path = DEFAULT_DB) -> list[dict]:
    if limit < 1:
        raise ValueError("La limite doit être positive")
    with _connect(db_path) as connection:
        rows = connection.execute(
            "SELECT * FROM observations ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()
    return [dict(row) for row in rows]


def scan_count(db_path: Path = DEFAULT_DB) -> int:
    with _connect(db_path) as connection:
        return int(connection.execute(
            "SELECT COUNT(DISTINCT cycle_id) FROM observations"
        ).fetchone()[0])


def signal_confirmations(observations: list[dict]) -> dict[str, dict]:
    grouped: dict[str, list[dict]] = {}
    for row in observations:
        grouped.setdefault(row["market"], []).append(row)
    confirmations = {}
    for market, rows in grouped.items():
        latest_action = rows[0]["action"]
        streak = 0
        for row in rows:
            if row["action"] != latest_action:
                break
            streak += 1
        confirmations[market] = {"action": latest_action, "cycles": streak}
    return confirmations


def export_history(db_path: Path = DEFAULT_DB) -> str:
    return json.dumps(list_observations(10_000, db_path), ensure_ascii=False, indent=2)
