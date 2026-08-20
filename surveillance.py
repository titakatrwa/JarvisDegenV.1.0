"""Planification déterministe des cycles de surveillance du scanner."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta


INTERVALS = {"1 min": 1, "5 min": 5, "15 min": 15}


def scan_is_due(
    last_scan_iso: str | None,
    interval_minutes: int,
    now: datetime | None = None,
) -> bool:
    if interval_minutes not in INTERVALS.values():
        raise ValueError("Intervalle de surveillance non autorisé")
    if not last_scan_iso:
        return True
    current = now or datetime.now(UTC)
    last_scan = datetime.fromisoformat(last_scan_iso).astimezone(UTC)
    return current.astimezone(UTC) - last_scan >= timedelta(minutes=interval_minutes)
