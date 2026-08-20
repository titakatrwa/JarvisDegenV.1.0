import pytest

from performance_metrics import calculate_performance


def trade(side, pnl=0, fees=1, slippage=0.5, market="SOL/USDC"):
    return {"side": side, "realized_pnl": pnl, "fees": fees, "slippage": slippage,
            "market": market, "notional": 200}


def test_performance_reconciles_trades_and_costs():
    portfolio = {
        "equity": 10_030,
        "trades": [trade("BUY"), trade("SELL", 40), trade("SELL", -10)],
        "history": [{"equity": 10_000}, {"equity": 9_900}, {"equity": 10_030}],
    }
    result = calculate_performance(portfolio)
    assert result["net_return_percent"] == pytest.approx(0.003)
    assert result["win_rate"] == 0.5
    assert result["profit_factor"] == 4
    assert result["expectancy_usd"] == 15
    assert result["total_fees_usd"] == 3
    assert result["max_drawdown_percent"] == pytest.approx(0.01)


def test_open_portfolio_does_not_invent_closed_metrics():
    result = calculate_performance(
        {"equity": 9_999, "trades": [trade("BUY")], "history": [{"equity": 9_999}]}
    )
    assert result["closed_trades"] == 0
    assert result["win_rate"] is None
    assert result["profit_factor"] is None
    assert result["sample_status"] == "INSUFFISANT"


def test_market_attribution_is_separate():
    result = calculate_performance(
        {"equity": 10_000, "trades": [trade("BUY"), trade("BUY", market="JUP/USDC")],
         "history": []}
    )
    assert {row["marché"] for row in result["by_market"]} == {"SOL/USDC", "JUP/USDC"}
