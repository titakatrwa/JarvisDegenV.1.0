import pytest

from paper_portfolio import apply_decision, get_portfolio, update_prices


def decision(side, price=100, size=200):
    return {
        "marché": "SOL/USDC",
        "action": side,
        "statut": "APPROUVÉ",
        "prix_usd": price,
        "position_usd": size,
        "raison": "Test",
    }


def test_buy_creates_persistent_position(tmp_path):
    database = tmp_path / "portfolio.db"
    result = apply_decision(decision("BUY"), database)
    portfolio = get_portfolio(database)
    assert result["mouvement_portefeuille"] == "BUY"
    assert portfolio["cash"] == pytest.approx(9799.4)
    assert portfolio["equity"] < 10000
    assert len(portfolio["positions"]) == 1
    position = portfolio["positions"][0]
    assert position["stop_loss_price"] < position["average_price"]
    assert position["take_profit_price"] > position["average_price"]
    assert result["frais_usd"] == pytest.approx(0.6)
    assert result["slippage_usd"] > 0


def test_sell_closes_position_and_realizes_pnl(tmp_path):
    database = tmp_path / "portfolio.db"
    apply_decision(decision("BUY"), database)
    result = apply_decision(decision("SELL", price=110), database)
    portfolio = get_portfolio(database)
    assert 17 < result["pnl_réalisé_usd"] < 18
    assert 10017 < portfolio["cash"] < 10018
    assert portfolio["positions"] == []


def test_sell_without_position_is_refused(tmp_path):
    result = apply_decision(decision("SELL"), tmp_path / "portfolio.db")
    assert result["statut"] == "REFUSÉ"
    assert result["mouvement_portefeuille"] == "REFUSÉ"


def test_price_refresh_updates_unrealized_pnl(tmp_path):
    database = tmp_path / "portfolio.db"
    apply_decision(decision("BUY"), database)
    update_prices({"SOL/USDC": 105}, database)
    portfolio = get_portfolio(database)
    assert 8 < portfolio["unrealized_pnl"] < 9
    assert portfolio["history"][-1]["event"] == "VALORISATION"


def test_protective_levels_raise_status(tmp_path):
    database = tmp_path / "portfolio.db"
    apply_decision(decision("BUY"), database)
    update_prices({"SOL/USDC": 90}, database)
    assert get_portfolio(database)["positions"][0]["protection"] == "STOP À EXAMINER"
