from datetime import UTC, datetime

import pytest

from risk_monitor import calculate_risk


NOW = datetime(2026, 8, 20, 12, tzinfo=UTC)


def portfolio(equity, history, exposure=0):
    return {"equity": equity, "history": history, "exposure": exposure}


def point(timestamp, equity):
    return {"timestamp": timestamp, "equity": equity}


def test_normal_risk_metrics():
    risk = calculate_risk(
        portfolio(9900, [point("2026-08-20T08:00:00+00:00", 10000)], 500), NOW
    )
    assert risk["daily_loss_percent"] == pytest.approx(0.01)
    assert risk["exposure_percent"] == pytest.approx(500 / 9900)
    assert risk["halted"] is False
    assert risk["status"] == "NORMAL"


def test_daily_loss_triggers_circuit_breaker():
    risk = calculate_risk(
        portfolio(9699, [point("2026-08-20T08:00:00+00:00", 10000)]), NOW
    )
    assert risk["halted"] is True
    assert risk["status"] == "ARRÊTÉ"


def test_yesterday_does_not_define_today_open():
    risk = calculate_risk(
        portfolio(9700, [point("2026-08-19T08:00:00+00:00", 10000)]), NOW
    )
    assert risk["daily_change"] == 0
    assert risk["drawdown_percent"] == pytest.approx(0.03)
