from strategy import analyse_market


def snapshot(change, volume=2_000_000, liquidity=1_000_000):
    return {
        "change_24h": change,
        "volume_24h": volume,
        "liquidity_usd": liquidity,
    }


def test_positive_momentum_produces_buy():
    decision = analyse_market(snapshot(8))
    assert decision["action"] == "BUY"
    assert decision["confidence"] >= 0.70


def test_negative_momentum_produces_sell():
    decision = analyse_market(snapshot(-8))
    assert decision["action"] == "SELL"


def test_flat_market_waits():
    assert analyse_market(snapshot(0))["action"] == "WAIT"


def test_low_liquidity_always_waits():
    decision = analyse_market(snapshot(15, liquidity=50_000))
    assert decision["action"] == "WAIT"
    assert decision["confidence"] == 0.40


def test_anti_chase_reduces_extreme_momentum():
    normal = analyse_market(snapshot(10))["score"]
    extreme = analyse_market(snapshot(25))["score"]
    assert extreme < normal
