from trade_bootstrap import bootstrap_trade_outcomes


def trades(values):
    return [{"action": "SELL", "pnl": value} for value in values]


def test_bootstrap_is_reproducible_and_orders_quantiles():
    first = bootstrap_trade_outcomes(trades([5, -2, 4, -1, 3] * 3), simulations=500)
    second = bootstrap_trade_outcomes(trades([5, -2, 4, -1, 3] * 3), simulations=500)
    assert first == second
    assert first["sufficient_sample"] is True
    assert first["pessimistic_pnl"] <= first["median_pnl"] <= first["optimistic_pnl"]
    assert 0 <= first["probability_positive_percent"] <= 100


def test_bootstrap_marks_small_or_empty_samples():
    small = bootstrap_trade_outcomes(trades([2, -1, 3]))
    empty = bootstrap_trade_outcomes([])
    assert small["sufficient_sample"] is False
    assert small["probability_positive_percent"] is not None
    assert empty["probability_positive_percent"] is None
