"""Stratégie expérimentale et explicable pour le paper trading JarvisDegen."""

from __future__ import annotations

from dataclasses import asdict, dataclass


def _clamp(value: float, minimum: float, maximum: float) -> float:
    return max(minimum, min(maximum, value))


@dataclass(frozen=True)
class StrategyDecision:
    action: str
    score: float
    confidence: float
    rationale: str
    contributions: dict[str, float]


def analyse_market(snapshot: dict) -> dict:
    """Produit BUY, SELL ou WAIT à partir d'indicateurs publics et auditables."""
    change = float(snapshot.get("change_24h", 0))
    volume = float(snapshot.get("volume_24h", 0))
    liquidity = float(snapshot.get("liquidity_usd", 0))

    if liquidity < 100_000:
        return asdict(
            StrategyDecision(
                action="WAIT",
                score=0,
                confidence=0.40,
                rationale="Liquidité inférieure au seuil minimal de 100 000 $.",
                contributions={"Momentum 24 h": 0, "Activité": 0, "Anti-poursuite": 0},
            )
        )

    momentum = _clamp(change / 10, -1, 1) * 45
    direction = 1 if change > 0 else -1 if change < 0 else 0
    activity_ratio = volume / liquidity if liquidity else 0
    activity = direction * _clamp(activity_ratio / 2, 0, 1) * 20
    anti_chase = -direction * 25 if abs(change) >= 20 else 0
    score = round(_clamp(momentum + activity + anti_chase, -100, 100), 1)

    if score >= 25:
        action = "BUY"
    elif score <= -25:
        action = "SELL"
    else:
        action = "WAIT"

    confidence = round(_clamp(0.50 + abs(score) / 100, 0.50, 0.95), 2)
    rationale = (
        f"Momentum {change:+.2f} % sur 24 h, ratio volume/liquidité "
        f"{activity_ratio:.2f}, score final {score:+.1f}."
    )
    return asdict(
        StrategyDecision(
            action=action,
            score=score,
            confidence=confidence,
            rationale=rationale,
            contributions={
                "Momentum 24 h": round(momentum, 1),
                "Activité": round(activity, 1),
                "Anti-poursuite": round(anti_chase, 1),
            },
        )
    )
