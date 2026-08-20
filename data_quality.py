"""Contrôles de qualité des bougies OHLCV utilisées par les backtests."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pandas as pd


def assess_ohlcv_quality(
    candles: list[dict[str, Any]], now: datetime | None = None
) -> dict[str, Any]:
    if not candles:
        raise ValueError("Aucune bougie à contrôler")
    frame = pd.DataFrame(candles).sort_values("timestamp").reset_index(drop=True)
    required = {"timestamp", "open", "high", "low", "close", "volume"}
    missing = sorted(required - set(frame.columns))
    if missing:
        raise ValueError(f"Colonnes OHLCV absentes : {', '.join(missing)}")
    numeric = frame[list(required)].apply(pd.to_numeric, errors="coerce")
    null_or_invalid = int(numeric.isna().any(axis=1).sum())
    duplicate_count = int(frame["timestamp"].duplicated().sum())
    invalid_price_count = int(
        ((numeric[["open", "high", "low", "close"]] <= 0).any(axis=1)).sum()
    )
    invalid_volume_count = int((numeric["volume"] < 0).sum())
    invalid_ohlc_count = int(
        (
            (numeric["low"] > numeric[["open", "close"]].min(axis=1))
            | (numeric["high"] < numeric[["open", "close"]].max(axis=1))
            | (numeric["low"] > numeric["high"])
        ).sum()
    )
    timestamps = numeric["timestamp"].dropna().sort_values()
    differences = timestamps.diff().dropna()
    expected_interval = float(differences.median()) if not differences.empty else 0
    gap_count = int((differences > expected_interval * 1.5).sum()) if expected_interval else 0
    gap_rate = gap_count / max(len(frame) - 1, 1) * 100
    reference = now or datetime.now(UTC)
    if reference.tzinfo is None:
        reference = reference.replace(tzinfo=UTC)
    latest = datetime.fromtimestamp(float(timestamps.iloc[-1]), UTC)
    earliest = datetime.fromtimestamp(float(timestamps.iloc[0]), UTC)
    coverage_days = max((latest - earliest).total_seconds() / 86_400, 0)
    freshness_hours = max((reference - latest).total_seconds() / 3600, 0)
    checks = [
        {"contrôle": "Volume minimal", "réussi": len(frame) >= 60, "preuve": f"{len(frame)} bougies"},
        {"contrôle": "Unicité temporelle", "réussi": duplicate_count == 0, "preuve": f"{duplicate_count} doublon(s)"},
        {"contrôle": "Valeurs complètes", "réussi": null_or_invalid == 0, "preuve": f"{null_or_invalid} ligne(s) invalide(s)"},
        {"contrôle": "Cohérence OHLC", "réussi": invalid_ohlc_count == 0 and invalid_price_count == 0, "preuve": f"{invalid_ohlc_count + invalid_price_count} anomalie(s)"},
        {"contrôle": "Volumes valides", "réussi": invalid_volume_count == 0, "preuve": f"{invalid_volume_count} volume(s) négatif(s)"},
        {"contrôle": "Continuité temporelle", "réussi": gap_rate <= 2, "preuve": f"{gap_count} trou(s), {gap_rate:.2f} %"},
        {"contrôle": "Fraîcheur", "réussi": freshness_hours <= 12, "preuve": f"retard {freshness_hours:.1f} h"},
    ]
    passed = sum(check["réussi"] for check in checks)
    return {
        "checks": checks,
        "passed": passed,
        "total": len(checks),
        "passes": passed == len(checks),
        "row_count": len(frame),
        "gap_count": gap_count,
        "freshness_hours": round(freshness_hours, 1),
        "expected_interval_hours": round(expected_interval / 3600, 1),
        "latest": latest,
        "earliest": earliest,
        "coverage_days": round(coverage_days, 1),
    }
