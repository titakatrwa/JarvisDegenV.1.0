"""Bootstrap reproductible des P&L de trades clôturés."""

from __future__ import annotations

import random
from typing import Any

import pandas as pd


def bootstrap_trade_outcomes(
    trades: list[dict[str, Any]], simulations: int = 1_000, seed: int = 42
) -> dict[str, Any]:
    if not 100 <= simulations <= 10_000:
        raise ValueError("Le nombre de simulations doit être compris entre 100 et 10 000")
    pnls = [
        float(trade["pnl"])
        for trade in trades
        if trade.get("action") == "SELL" and trade.get("pnl") is not None
    ]
    trade_count = len(pnls)
    if not pnls:
        return {
            "trade_count": 0,
            "simulations": simulations,
            "sufficient_sample": False,
            "probability_positive_percent": None,
            "pessimistic_pnl": None,
            "median_pnl": None,
            "optimistic_pnl": None,
            "simulated_totals": [],
        }
    generator = random.Random(seed)
    totals = [
        sum(generator.choice(pnls) for _ in range(trade_count))
        for _ in range(simulations)
    ]
    series = pd.Series(totals, dtype="float64")
    return {
        "trade_count": trade_count,
        "simulations": simulations,
        "sufficient_sample": trade_count >= 10,
        "probability_positive_percent": round(float((series > 0).mean() * 100), 1),
        "pessimistic_pnl": round(float(series.quantile(0.05)), 2),
        "median_pnl": round(float(series.quantile(0.50)), 2),
        "optimistic_pnl": round(float(series.quantile(0.95)), 2),
        "simulated_totals": [round(value, 2) for value in totals],
    }
