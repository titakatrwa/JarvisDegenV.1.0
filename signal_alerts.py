"""Qualification prudente des signaux confirmés du scanner."""

from __future__ import annotations

import json


MIN_CONFIRMATIONS = 2
MIN_CONFIDENCE = 0.70


def build_alerts(
    observations: list[dict],
    confirmations: dict[str, dict],
    portfolio: dict,
    risk: dict,
) -> list[dict]:
    latest_by_market = {}
    for row in observations:
        latest_by_market.setdefault(row["market"], row)
    open_markets = {position["market"] for position in portfolio.get("positions", [])}
    alerts = []
    for market, row in latest_by_market.items():
        action = row["action"]
        if action == "WAIT":
            continue
        cycles = confirmations.get(market, {}).get("cycles", 1)
        confidence = float(row["confidence"])
        blockers = []
        if cycles < MIN_CONFIRMATIONS:
            blockers.append(f"Signal confirmé seulement {cycles} fois")
        if confidence < MIN_CONFIDENCE:
            blockers.append("Confiance inférieure à 70 %")
        if action == "BUY":
            if risk.get("halted"):
                blockers.append("Coupe-circuit journalier actif")
            if market in open_markets:
                blockers.append("Une position paper est déjà ouverte sur ce marché")
            if len(open_markets) >= 3 and market not in open_markets:
                blockers.append("Trois positions sont déjà ouvertes")
        elif action == "SELL" and market not in open_markets:
            blockers.append("Aucune position paper à fermer")

        ready = not blockers
        alerts.append(
            {
                "marché": market,
                "signal": action,
                "score": float(row["score"]),
                "confiance": confidence,
                "confirmations": cycles,
                "prix_usd": float(row["price_usd"]),
                "statut": "À EXAMINER" if ready else "SURVEILLANCE",
                "motif": "Tous les critères préalables sont réunis" if ready else " • ".join(blockers),
                "exécution_automatique": False,
            }
        )
    return sorted(alerts, key=lambda item: (item["statut"] != "À EXAMINER", -abs(item["score"])))


def export_alerts(alerts: list[dict]) -> str:
    return json.dumps(alerts, ensure_ascii=False, indent=2)
