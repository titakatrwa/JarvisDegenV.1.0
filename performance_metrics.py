"""Métriques réconciliées du portefeuille paper JarvisDegen."""

from __future__ import annotations


INITIAL_CAPITAL = 10_000.0


def calculate_performance(portfolio: dict) -> dict:
    trades = portfolio.get("trades", [])
    exits = [trade for trade in trades if trade["side"] == "SELL"]
    wins = [trade for trade in exits if float(trade["realized_pnl"]) > 0]
    losses = [trade for trade in exits if float(trade["realized_pnl"]) < 0]
    gross_profit = sum(float(trade["realized_pnl"]) for trade in wins)
    gross_loss = abs(sum(float(trade["realized_pnl"]) for trade in losses))
    total_fees = sum(float(trade.get("fees") or 0) for trade in trades)
    total_slippage = sum(float(trade.get("slippage") or 0) for trade in trades)
    equity = float(portfolio["equity"])

    peak = 0.0
    max_drawdown = 0.0
    for point in portfolio.get("history", []):
        value = float(point["equity"])
        peak = max(peak, value)
        if peak > 0:
            max_drawdown = max(max_drawdown, (peak - value) / peak)

    by_market: dict[str, dict] = {}
    for trade in trades:
        market = trade["market"]
        row = by_market.setdefault(
            market,
            {"marché": market, "ordres": 0, "achats": 0, "ventes": 0,
             "volume_usd": 0.0, "frais_usd": 0.0, "slippage_usd": 0.0,
             "pnl_réalisé_usd": 0.0},
        )
        row["ordres"] += 1
        row["achats"] += trade["side"] == "BUY"
        row["ventes"] += trade["side"] == "SELL"
        row["volume_usd"] += float(trade["notional"])
        row["frais_usd"] += float(trade.get("fees") or 0)
        row["slippage_usd"] += float(trade.get("slippage") or 0)
        row["pnl_réalisé_usd"] += float(trade["realized_pnl"])

    closed_count = len(exits)
    return {
        "equity": equity,
        "net_return_percent": (equity / INITIAL_CAPITAL) - 1,
        "orders": len(trades),
        "closed_trades": closed_count,
        "wins": len(wins),
        "losses": len(losses),
        "win_rate": len(wins) / closed_count if closed_count else None,
        "profit_factor": gross_profit / gross_loss if gross_loss > 0 else None,
        "expectancy_usd": sum(float(trade["realized_pnl"]) for trade in exits) / closed_count
        if closed_count else None,
        "gross_profit_usd": gross_profit,
        "gross_loss_usd": gross_loss,
        "total_fees_usd": total_fees,
        "total_slippage_usd": total_slippage,
        "max_drawdown_percent": max_drawdown,
        "by_market": sorted(by_market.values(), key=lambda row: -row["volume_usd"]),
        "sample_status": "EXPLOITABLE" if closed_count >= 30 else "LIMITÉ" if closed_count >= 10 else "INSUFFISANT",
    }
