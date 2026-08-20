from market_scanner import rank_markets


def snapshot(market, change, liquidity=2_000_000, volume=1_000_000):
    return {
        "market": market,
        "price_usd": 10,
        "change_24h": change,
        "volume_24h": volume,
        "liquidity_usd": liquidity,
        "source": "Test",
    }


def test_buy_signals_are_ranked_before_wait():
    ranked = rank_markets([snapshot("CALME", 1), snapshot("FORT", 8)])
    assert ranked[0]["marché"] == "FORT"
    assert ranked[0]["action"] == "BUY"
    assert ranked[-1]["action"] == "WAIT"


def test_liquidity_reduces_priority():
    ranked = rank_markets(
        [snapshot("LIQUIDE", 8), snapshot("MINCE", 8, liquidity=200_000)]
    )
    assert ranked[0]["marché"] == "LIQUIDE"
    assert ranked[0]["priorité"] > ranked[1]["priorité"]


def test_scanner_keeps_sell_signals():
    ranked = rank_markets([snapshot("BAISSE", -8)])
    assert ranked[0]["action"] == "SELL"
    assert ranked[0]["score"] < 0
