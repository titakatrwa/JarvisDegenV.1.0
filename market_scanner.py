"""Classement déterministe d'une liste de marchés en lecture seule."""

from __future__ import annotations

from strategy import analyse_market


def rank_markets(snapshots: list[dict]) -> list[dict]:
    results = []
    for snapshot in snapshots:
        analysis = analyse_market(snapshot)
        liquidity = float(snapshot.get("liquidity_usd", 0))
        liquidity_factor = min(liquidity / 1_000_000, 1.0)
        priority = abs(float(analysis["score"])) * float(analysis["confidence"]) * liquidity_factor
        results.append(
            {
                "marché": snapshot["market"],
                "action": analysis["action"],
                "score": float(analysis["score"]),
                "confiance": float(analysis["confidence"]),
                "priorité": round(priority, 2),
                "prix_usd": float(snapshot["price_usd"]),
                "variation_24h": float(snapshot["change_24h"]),
                "volume_24h": float(snapshot["volume_24h"]),
                "liquidité_usd": liquidity,
                "raison": analysis["rationale"],
                "source": snapshot.get("source", "Source inconnue"),
            }
        )
    action_order = {"BUY": 0, "SELL": 1, "WAIT": 2}
    return sorted(
        results,
        key=lambda row: (action_order.get(row["action"], 3), -row["priorité"], row["marché"]),
    )
