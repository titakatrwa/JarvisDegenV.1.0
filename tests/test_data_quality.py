from datetime import UTC, datetime

from data_quality import assess_ohlcv_quality
from tests.test_backtest import candles


def test_quality_accepts_complete_fresh_series():
    now = datetime(2023, 11, 25, tzinfo=UTC)
    data = candles([100 + index for index in range(70)])
    now = datetime.fromtimestamp(data[-1]["timestamp"] + 3600, UTC)
    result = assess_ohlcv_quality(data, now=now)
    assert result["passes"] is True
    assert result["expected_interval_hours"] == 4
    assert result["coverage_days"] == round((len(data) - 1) * 4 / 24, 1)


def test_quality_detects_duplicates_gaps_and_invalid_ohlc():
    data = candles([100 + index for index in range(70)])
    data[1]["timestamp"] = data[0]["timestamp"]
    data[5]["timestamp"] += 100_000
    data[10]["low"] = data[10]["high"] + 1
    now = datetime.fromtimestamp(data[-1]["timestamp"] + 20 * 3600, UTC)
    result = assess_ohlcv_quality(data, now=now)
    failed = {row["contrôle"] for row in result["checks"] if not row["réussi"]}
    assert "Unicité temporelle" in failed
    assert "Cohérence OHLC" in failed
    assert "Fraîcheur" in failed
