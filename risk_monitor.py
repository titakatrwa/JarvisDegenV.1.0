"""Indicateurs de risque calculés depuis le portefeuille paper persistant."""

from __future__ import annotations

from datetime import UTC, datetime


DAILY_LOSS_LIMIT = 0.03
WARNING_LEVEL = 0.02


def calculate_risk(portfolio: dict, now: datetime | None = None) -> dict:
    current_time = now or datetime.now(UTC)
    current_equity = float(portfolio["equity"])
    history = portfolio.get("history", [])
    today_points = [
        point
        for point in history
        if datetime.fromisoformat(point["timestamp"]).astimezone(UTC).date()
        == current_time.astimezone(UTC).date()
    ]
    daily_open = float(today_points[0]["equity"]) if today_points else current_equity
    daily_change = current_equity - daily_open
    daily_loss_percent = max(0.0, -daily_change / daily_open) if daily_open > 0 else 0.0

    historical_equities = [float(point["equity"]) for point in history]
    peak_equity = max([current_equity, *historical_equities])
    drawdown_percent = max(0.0, (peak_equity - current_equity) / peak_equity)
    exposure_percent = (
        float(portfolio["exposure"]) / current_equity if current_equity > 0 else 0.0
    )
    halted = daily_loss_percent >= DAILY_LOSS_LIMIT
    warning = daily_loss_percent >= WARNING_LEVEL or drawdown_percent >= 0.05
    return {
        "daily_open": daily_open,
        "daily_change": daily_change,
        "daily_loss_percent": daily_loss_percent,
        "peak_equity": peak_equity,
        "drawdown_percent": drawdown_percent,
        "exposure_percent": exposure_percent,
        "halted": halted,
        "status": "ARRÊTÉ" if halted else "VIGILANCE" if warning else "NORMAL",
        "limit_percent": DAILY_LOSS_LIMIT,
    }
