"""Rapport de validation compact et vérifiable pour les backtests JDEGEN."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from typing import Any


def _json_default(value: Any) -> str:
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)


def _canonical_json(payload: dict[str, Any]) -> str:
    return json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=_json_default,
    )


def build_backtest_report(
    *,
    market: str,
    candles: list[dict[str, Any]],
    short_window: int,
    long_window: int,
    result: dict[str, Any],
    data_quality: dict[str, Any],
    trade_bootstrap: dict[str, Any],
    market_regimes: dict[str, Any] | None,
    out_of_sample: dict[str, Any],
    walk_forward: dict[str, Any] | None,
    sensitivity: dict[str, Any],
    execution_stress: dict[str, Any],
    confirmation_lab: dict[str, Any],
    strength_lab: dict[str, Any],
    volume_lab: dict[str, Any],
    volume_validation: dict[str, Any],
    volume_walk_forward: dict[str, Any] | None,
    strength_validation: dict[str, Any],
    strength_walk_forward: dict[str, Any] | None,
    confirmation_validation: dict[str, Any],
    confirmation_walk_forward: dict[str, Any] | None,
    readiness: dict[str, Any],
    generated_at: datetime | None = None,
) -> dict[str, Any]:
    """Construit un instantané sans les séries volumineuses, puis le signe par hash."""
    ordered = sorted(candles, key=lambda row: row["timestamp"])
    created = generated_at or datetime.now(UTC)
    payload = {
        "format": "jdegen-backtest-report-v1",
        "généré_le": created.isoformat(),
        "mode": "simulation_uniquement",
        "marché": market,
        "données": {
            "bougies": len(ordered),
            "début": datetime.fromtimestamp(ordered[0]["timestamp"], UTC).isoformat(),
            "fin": datetime.fromtimestamp(ordered[-1]["timestamp"], UTC).isoformat(),
            "couverture_jours": data_quality["coverage_days"],
        },
        "paramètres": {
            "moyenne_courte": short_window,
            "moyenne_longue": long_window,
            "capital_initial": 10_000,
            "position_pourcent": 2,
            "frais_pourcent": 0.30,
            "slippage_pourcent": 0.20,
        },
        "résultat": {
            "capital_final": result["final_capital"],
            "rendement_pourcent": result["return_percent"],
            "drawdown_max_pourcent": result["max_drawdown_percent"],
            "trades_clôturés": result["round_trips"],
            "taux_réussite_pourcent": result["win_rate_percent"],
            "ratio_sharpe": result.get("sharpe_ratio"),
            "ratio_sortino": result.get("sortino_ratio"),
            "facteur_profit": result.get("profit_factor"),
            "espérance_par_trade": result.get("expectancy_per_trade"),
            "exposition_pourcent": result.get("exposure_percent"),
        },
        "diagnostics": {
            "régimes_marché": {
                "évalué": market_regimes is not None,
                "périodes_positives": market_regimes["positive_periods"] if market_regimes else 0,
                "périodes_surperformantes": market_regimes["outperforming_periods"] if market_regimes else 0,
                "régimes_observés": market_regimes["regimes_observed"] if market_regimes else [],
                "réussi": bool(market_regimes and market_regimes["passes"]),
            },
            "bootstrap_trades": {
                "trades": trade_bootstrap["trade_count"],
                "simulations": trade_bootstrap["simulations"],
                "échantillon_suffisant": trade_bootstrap["sufficient_sample"],
                "probabilité_positive_pourcent": trade_bootstrap["probability_positive_percent"],
                "pnl_prudent": trade_bootstrap["pessimistic_pnl"],
                "pnl_médian": trade_bootstrap["median_pnl"],
                "pnl_favorable": trade_bootstrap["optimistic_pnl"],
            },
            "qualité_données": {
                "réussi": data_quality["passes"],
                "contrôles_réussis": data_quality["passed"],
                "contrôles": data_quality["total"],
                "trous_temporels": data_quality["gap_count"],
                "fraîcheur_heures": data_quality["freshness_hours"],
            },
            "hors_échantillon": {
                "réussi": out_of_sample["passes"],
                "surperformance_pourcent": out_of_sample["excess_return_percent"],
            },
            "walk_forward": {
                "évalué": walk_forward is not None,
                "réussi": bool(walk_forward and walk_forward["passes"]),
                "plis_positifs": walk_forward["positive_folds"] if walk_forward else 0,
                "plis": walk_forward["fold_count"] if walk_forward else 0,
            },
            "sensibilité": {
                "réussi": sensitivity["passes"],
                "variantes_rentables_pourcent": sensitivity["profitable_percent"],
                "rendement_médian_pourcent": sensitivity["median_return"],
            },
            "stress_coûts": {
                "réussi": execution_stress["passes"],
                "scénarios_rentables": execution_stress["profitable_scenarios"],
                "scénarios": execution_stress["scenario_count"],
                "érosion_pourcent": execution_stress["cost_erosion"],
            },
            "laboratoire_confirmation": {
                "variantes": confirmation_lab["variants"],
                "rotation_minimale": confirmation_lab["lowest_turnover"]["libellé"],
                "meilleur_sous_stress": confirmation_lab["best_stressed"]["libellé"],
                "promotion_automatique": False,
            },
            "laboratoire_force_signal": {
                "variantes": strength_lab["variants"],
                "rotation_minimale": strength_lab["lowest_turnover"]["libellé"],
                "meilleur_sous_stress": strength_lab["best_stressed"]["libellé"],
                "promotion_automatique": False,
            },
            "laboratoire_volume": {
                "variantes": volume_lab["variants"],
                "rotation_minimale": volume_lab["lowest_turnover"]["libellé"],
                "meilleur_sous_stress": volume_lab["best_stressed"]["libellé"],
                "sorties_toujours_autorisées": True,
                "promotion_automatique": False,
            },
            "volume_hors_échantillon": {
                "sélection_entraînement": volume_validation["selected_label"],
                "bougies_entraînement": volume_validation["train_count"],
                "bougies_test": volume_validation["test_count"],
                "rendement_test_stressé": volume_validation["test_stressed_return"],
                "écart_vs_sans_filtre": volume_validation["excess_return_percent"],
                "réussi": volume_validation["passes"],
            },
            "volume_walk_forward": {
                "évalué": volume_walk_forward is not None,
                "plis_positifs": volume_walk_forward["positive_folds"] if volume_walk_forward else 0,
                "plis_surperformants": volume_walk_forward["outperforming_folds"] if volume_walk_forward else 0,
                "plis": volume_walk_forward["fold_count"] if volume_walk_forward else 0,
                "rendement_moyen_stressé": volume_walk_forward["average_test_return"] if volume_walk_forward else None,
                "réussi": bool(volume_walk_forward and volume_walk_forward["passes"]),
            },
            "force_signal_hors_échantillon": {
                "sélection_entraînement": strength_validation["selected_label"],
                "bougies_entraînement": strength_validation["train_count"],
                "bougies_test": strength_validation["test_count"],
                "rendement_test_stressé": strength_validation["test_stressed_return"],
                "écart_vs_sans_filtre": strength_validation["excess_return_percent"],
                "réussi": strength_validation["passes"],
            },
            "force_signal_walk_forward": {
                "évalué": strength_walk_forward is not None,
                "plis_positifs": strength_walk_forward["positive_folds"] if strength_walk_forward else 0,
                "plis_surperformants": strength_walk_forward["outperforming_folds"] if strength_walk_forward else 0,
                "plis": strength_walk_forward["fold_count"] if strength_walk_forward else 0,
                "rendement_moyen_stressé": strength_walk_forward["average_test_return"] if strength_walk_forward else None,
                "avantage_moyen": strength_walk_forward["average_excess_return"] if strength_walk_forward else None,
                "réussi": bool(strength_walk_forward and strength_walk_forward["passes"]),
            },
            "confirmation_hors_échantillon": {
                "sélection_entraînement": confirmation_validation["selected_label"],
                "bougies_entraînement": confirmation_validation["train_count"],
                "bougies_test": confirmation_validation["test_count"],
                "rendement_test_stressé": confirmation_validation["test_stressed_return"],
                "écart_vs_immédiat": confirmation_validation["excess_return_percent"],
                "réussi": confirmation_validation["passes"],
            },
            "confirmation_walk_forward": {
                "évalué": confirmation_walk_forward is not None,
                "plis_positifs": confirmation_walk_forward["positive_folds"] if confirmation_walk_forward else 0,
                "plis_surperformants": confirmation_walk_forward["outperforming_folds"] if confirmation_walk_forward else 0,
                "plis": confirmation_walk_forward["fold_count"] if confirmation_walk_forward else 0,
                "rendement_moyen_stressé": confirmation_walk_forward["average_test_return"] if confirmation_walk_forward else None,
                "réussi": bool(confirmation_walk_forward and confirmation_walk_forward["passes"]),
            },
        },
        "verdict": {
            "score": readiness["score"],
            "statut": readiness["status"],
            "barrières_validées": readiness["passed_count"],
            "barrières": readiness["check_count"],
            "candidat_paper": readiness["paper_candidate"],
            "trading_réel": "verrouillé",
            "plan_amélioration": readiness.get("actions", []),
        },
    }
    payload["empreinte_sha256"] = hashlib.sha256(
        _canonical_json(payload).encode("utf-8")
    ).hexdigest()
    return payload


def verify_backtest_report(report: dict[str, Any]) -> bool:
    """Vérifie que le contenu correspond toujours à son empreinte."""
    payload = dict(report)
    expected = payload.pop("empreinte_sha256", None)
    if not isinstance(expected, str):
        return False
    actual = hashlib.sha256(_canonical_json(payload).encode("utf-8")).hexdigest()
    return actual == expected


def export_backtest_report(report: dict[str, Any]) -> str:
    return json.dumps(report, ensure_ascii=False, indent=2, default=_json_default)


def inspect_backtest_report(raw: bytes | str) -> dict[str, Any]:
    """Analyse un rapport importé sans faire confiance au nom ni à l'extension du fichier."""
    raw_bytes = raw.encode("utf-8") if isinstance(raw, str) else raw
    if len(raw_bytes) > 1_000_000:
        return {"valid": False, "reason": "Fichier trop volumineux", "report": None}
    try:
        text = raw_bytes.decode("utf-8")
    except UnicodeDecodeError:
        return {"valid": False, "reason": "Encodage UTF-8 invalide", "report": None}
    try:
        report = json.loads(text)
    except json.JSONDecodeError:
        return {"valid": False, "reason": "JSON invalide", "report": None}
    if not isinstance(report, dict):
        return {"valid": False, "reason": "Le rapport doit être un objet JSON", "report": None}
    if report.get("format") != "jdegen-backtest-report-v1":
        return {"valid": False, "reason": "Format de rapport JDEGEN inconnu", "report": None}
    required = {"généré_le", "marché", "paramètres", "résultat", "verdict", "empreinte_sha256"}
    missing = sorted(required - report.keys())
    if missing:
        return {
            "valid": False,
            "reason": f"Champs obligatoires absents : {', '.join(missing)}",
            "report": report,
        }
    if not verify_backtest_report(report):
        return {
            "valid": False,
            "reason": "Empreinte SHA-256 incorrecte : contenu modifié",
            "report": report,
        }
    return {"valid": True, "reason": "Rapport authentique et intact", "report": report}
