"""Certification finale du MVP, sans aucune capacité de trading réel."""

from __future__ import annotations

from collections import Counter
from typing import Any

from backtest import run_backtest


CONFIGURATIONS = (
    {"nom": "Base 5/12", "short": 5, "long": 12},
    {"nom": "Confirmation 2", "short": 5, "long": 12, "confirmation_bars": 2},
    {"nom": "Force 0,25 %", "short": 5, "long": 12, "min_ma_separation_percent": 0.25},
    {"nom": "Volume médian", "short": 5, "long": 12, "min_volume_ratio": 1.0},
)


def evaluate_market_dataset(market: str, candles: list[dict[str, Any]]) -> dict[str, Any]:
    """Compare des règles figées sous coûts extrêmes, sans optimisation continue."""
    variants = []
    for config in CONFIGURATIONS:
        kwargs = {key: value for key, value in config.items() if key not in {"nom", "short", "long"}}
        result = run_backtest(
            candles, short_window=config["short"], long_window=config["long"],
            fee_percent=1.0, slippage_percent=1.0, **kwargs,
        )
        variants.append({"configuration": config["nom"],
                         "rendement_stressé": result["return_percent"],
                         "drawdown": result["max_drawdown_percent"],
                         "trades": result["round_trips"]})
    best = max(variants, key=lambda row: (row["rendement_stressé"], row["drawdown"]))
    return {"marché": market, "bougies": len(candles), "variantes": variants,
            "configuration": best["configuration"], "rendement_stressé": best["rendement_stressé"],
            "drawdown": best["drawdown"], "trades": best["trades"],
            "réussi": best["rendement_stressé"] > 0 and best["trades"] >= 3}


def summarize_cross_market(results: list[dict[str, Any]], failures: list[dict[str, str]] | None = None) -> dict[str, Any]:
    failures = failures or []
    positive = sum(bool(row["réussi"]) for row in results)
    required = max(2, len(results) // 2 + 1) if results else 2
    choices = Counter(row["configuration"] for row in results if row["réussi"])
    consensus = choices.most_common(1)[0][0] if choices else None
    passes = len(results) >= 2 and positive >= required and consensus is not None
    return {"marchés": results, "échecs_source": failures, "marchés_disponibles": len(results),
            "marchés_positifs": positive, "marchés_requis": required,
            "configuration_consensus": consensus, "passes": passes}


def select_candidate(cross_market: dict[str, Any], readiness: dict[str, Any]) -> dict[str, Any]:
    reasons = []
    if not cross_market["passes"]:
        reasons.append("Robustesse multi-marchés insuffisante")
    if not readiness["paper_candidate"]:
        reasons.append(f"Seulement {readiness['passed_count']} / {readiness['check_count']} barrières validées")
    eligible = not reasons
    return {"eligible": eligible,
            "configuration": cross_market.get("configuration_consensus") if eligible else None,
            "statut": "CANDIDAT PAPER" if eligible else "AUCUN CANDIDAT",
            "raisons": reasons, "trading_réel": False}


def build_supervised_paper_policy(candidate: dict[str, Any]) -> dict[str, Any]:
    armed = bool(candidate["eligible"])
    return {"paper_automatique_armé": armed, "mode": "PAPER SUPERVISÉ" if armed else "OBSERVATION",
            "approbation_humaine_par_ordre": True, "taille_max_position_pourcent": 2,
            "positions_max": 3, "perte_journalière_max_pourcent": 3,
            "trading_réel": False, "wallet_connecté": False}


def assess_paper_drift(*, paper_return: float, backtest_return: float,
                       paper_drawdown: float, backtest_drawdown: float,
                       closed_trades: int) -> dict[str, Any]:
    return_gap = round(paper_return - backtest_return, 3)
    drawdown_gap = round(abs(paper_drawdown) - abs(backtest_drawdown), 3)
    if closed_trades < 10:
        status, drift = "ÉCHANTILLON INSUFFISANT", False
    else:
        drift = return_gap < -1 or drawdown_gap > 1
        status = "DÉRIVE DÉTECTÉE" if drift else "DANS LES LIMITES"
    return {"statut": status, "dérive": drift, "trades_clôturés": closed_trades,
            "écart_rendement": return_gap, "écart_drawdown": drawdown_gap,
            "paper_à_suspendre": drift, "trading_réel": False}


def build_completion_certificate(*, test_count: int, launch_audit: dict[str, Any],
                                 cross_market: dict[str, Any], candidate: dict[str, Any],
                                 drift: dict[str, Any]) -> dict[str, Any]:
    technical = test_count > 0 and launch_audit["blockers"] == 0
    return {"point_6_terminé": technical, "tests": test_count,
            "audit_sans_bloquant": launch_audit["blockers"] == 0,
            "multi_marchés_validé": cross_market["passes"],
            "candidat_paper": candidate["eligible"], "surveillance": drift["statut"],
            "trading_réel": False,
            "conclusion": "MVP certifié techniquement ; stratégie non promue" if technical and not candidate["eligible"]
            else "MVP et candidat paper prêts pour revue humaine" if technical else "Audit technique incomplet"}
