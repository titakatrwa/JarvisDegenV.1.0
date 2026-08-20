"""Archive SQLite locale des rapports de validation JDEGEN."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

from backtest_report import verify_backtest_report


DEFAULT_DB = Path(__file__).parent / "data" / "backtest_reports.db"


def _connect(db_path: Path = DEFAULT_DB) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(db_path)
    connection.row_factory = sqlite3.Row
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS backtest_reports (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            fingerprint TEXT NOT NULL UNIQUE,
            payload TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    return connection


def archive_backtest_report(
    report: dict[str, Any], db_path: Path = DEFAULT_DB
) -> dict[str, Any]:
    if not verify_backtest_report(report):
        raise ValueError("Le rapport de backtest est invalide ou altéré")
    payload = json.dumps(report, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    fingerprint = report["empreinte_sha256"]
    with _connect(db_path) as connection:
        cursor = connection.execute(
            "INSERT OR IGNORE INTO backtest_reports(fingerprint, payload) VALUES (?, ?)",
            (fingerprint, payload),
        )
        row = connection.execute(
            "SELECT id FROM backtest_reports WHERE fingerprint = ?", (fingerprint,)
        ).fetchone()
    return {"id": row["id"], "inserted": cursor.rowcount == 1, "fingerprint": fingerprint}


def list_backtest_reports(
    limit: int = 50, db_path: Path = DEFAULT_DB
) -> list[dict[str, Any]]:
    if not 1 <= limit <= 1_000:
        raise ValueError("Limite d'archive invalide")
    with _connect(db_path) as connection:
        rows = connection.execute(
            "SELECT id, payload, created_at FROM backtest_reports ORDER BY id DESC LIMIT ?",
            (limit,),
        ).fetchall()
    reports = []
    for row in rows:
        report = json.loads(row["payload"])
        reports.append(
            {
                "archive_id": row["id"],
                "archivé_le": row["created_at"],
                "intègre": verify_backtest_report(report),
                **report,
            }
        )
    return reports


def verify_backtest_archive(db_path: Path = DEFAULT_DB) -> dict[str, Any]:
    reports = list_backtest_reports(1_000, db_path)
    invalid = [report["archive_id"] for report in reports if not report["intègre"]]
    return {"valid": not invalid, "count": len(reports), "invalid_ids": invalid}


def summarize_backtest_history(reports: list[dict[str, Any]]) -> dict[str, Any]:
    """Prépare les tendances à partir de rapports classés du plus récent au plus ancien."""
    if not reports:
        return {
            "count": 0,
            "score_delta": None,
            "return_delta": None,
            "best_score": None,
            "best_market": None,
            "trend": [],
        }
    latest = reports[0]
    previous = reports[1] if len(reports) > 1 else None
    best = max(reports, key=lambda report: report["verdict"]["score"])
    trend = [
        {
            "date": report["généré_le"],
            "marché": report["marché"],
            "score": report["verdict"]["score"],
            "rendement": report["résultat"]["rendement_pourcent"],
        }
        for report in reversed(reports)
    ]
    return {
        "count": len(reports),
        "latest_score": latest["verdict"]["score"],
        "latest_return": latest["résultat"]["rendement_pourcent"],
        "score_delta": (
            latest["verdict"]["score"] - previous["verdict"]["score"]
            if previous
            else None
        ),
        "return_delta": (
            round(
                latest["résultat"]["rendement_pourcent"]
                - previous["résultat"]["rendement_pourcent"],
                3,
            )
            if previous
            else None
        ),
        "best_score": best["verdict"]["score"],
        "best_market": best["marché"],
        "trend": trend,
    }
