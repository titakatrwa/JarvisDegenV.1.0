"""Validation serveur d'une alerte avant soumission au moteur paper."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta


MAX_ALERT_AGE = timedelta(minutes=20)


def validate_review(
    alert: dict,
    observation: dict,
    fresh_analysis: dict,
    acknowledged: bool,
    now: datetime | None = None,
) -> dict:
    if not acknowledged:
        return {"eligible": False, "reason": "Validation humaine manquante"}
    if alert.get("statut") != "À EXAMINER":
        return {"eligible": False, "reason": "L’alerte n’est pas qualifiée pour examen"}
    current = (now or datetime.now(UTC)).astimezone(UTC)
    observed_at = datetime.fromisoformat(observation["timestamp"]).astimezone(UTC)
    age = current - observed_at
    if age < timedelta(0) or age > MAX_ALERT_AGE:
        return {"eligible": False, "reason": "L’alerte a expiré ; relance un scan"}
    if fresh_analysis.get("action") != alert.get("signal"):
        return {"eligible": False, "reason": "Le signal du marché a changé"}
    if float(fresh_analysis.get("confidence", 0)) < 0.70:
        return {"eligible": False, "reason": "La confiance actuelle est inférieure à 70 %"}
    return {"eligible": True, "reason": "Alerte fraîche et signal reconfirmé"}
