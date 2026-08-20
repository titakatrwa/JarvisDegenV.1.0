from datetime import UTC, datetime

from backtest_report import (
    build_backtest_report,
    export_backtest_report,
    inspect_backtest_report,
    verify_backtest_report,
)


def sample_report():
    return build_backtest_report(
        market="SOL / USDC",
        candles=[
            {"timestamp": 1_700_000_000},
            {"timestamp": 1_700_014_400},
        ],
        short_window=5,
        long_window=12,
        result={
            "final_capital": 10_010,
            "return_percent": 0.1,
            "max_drawdown_percent": -0.05,
            "round_trips": 2,
            "win_rate_percent": 50,
        },
        data_quality={
            "passes": True,
            "passed": 7,
            "total": 7,
            "gap_count": 0,
            "freshness_hours": 1,
            "coverage_days": 30.0,
        },
        trade_bootstrap={
            "trade_count": 12,
            "simulations": 1_000,
            "sufficient_sample": True,
            "probability_positive_percent": 75.0,
            "pessimistic_pnl": -5.0,
            "median_pnl": 10.0,
            "optimistic_pnl": 25.0,
        },
        market_regimes={
            "positive_periods": 2,
            "outperforming_periods": 2,
            "regimes_observed": ["Baissier", "Haussier"],
            "passes": True,
        },
        out_of_sample={"passes": False, "excess_return_percent": -0.2},
        walk_forward={"passes": False, "positive_folds": 2, "fold_count": 3},
        sensitivity={"passes": True, "profitable_percent": 76, "median_return": 0.04},
        execution_stress={
            "passes": False,
            "profitable_scenarios": 1,
            "scenario_count": 3,
            "cost_erosion": 0.5,
        },
        confirmation_lab={
            "variants": [
                {
                    "confirmation": 1,
                    "libellé": "Immédiat",
                    "rendement_normal": 0.1,
                    "rendement_stress": -0.1,
                    "érosion_coûts": 0.2,
                    "trades": 2,
                    "drawdown": -0.05,
                    "facteur_profit": 1.2,
                    "espérance": 1.0,
                }
            ],
            "lowest_turnover": {"libellé": "Immédiat"},
            "best_stressed": {"libellé": "Immédiat"},
        },
        strength_lab={
            "variants": [{"seuil": 0.0, "libellé": "Sans filtre"}],
            "lowest_turnover": {"libellé": "Sans filtre"},
            "best_stressed": {"libellé": "Sans filtre"},
        },
        volume_lab={
            "variants": [{"ratio": 0.0, "libellé": "Sans filtre"}],
            "lowest_turnover": {"libellé": "Sans filtre"},
            "best_stressed": {"libellé": "Sans filtre"},
        },
        volume_validation={
            "selected_label": "Volume ≥ médiane",
            "train_count": 70,
            "test_count": 30,
            "test_stressed_return": 0.04,
            "excess_return_percent": 0.02,
            "passes": True,
        },
        volume_walk_forward={
            "positive_folds": 2, "outperforming_folds": 2, "fold_count": 3,
            "average_test_return": 0.03, "passes": True,
        },
        strength_validation={
            "selected_label": "Écart ≥ 0.25 %",
            "train_count": 70,
            "test_count": 30,
            "test_stressed_return": 0.04,
            "excess_return_percent": 0.02,
            "passes": True,
        },
        strength_walk_forward={
            "positive_folds": 2,
            "outperforming_folds": 2,
            "fold_count": 3,
            "average_test_return": 0.03,
            "average_excess_return": 0.01,
            "passes": True,
        },
        confirmation_validation={
            "selected_label": "2 bougies",
            "train_count": 70,
            "test_count": 30,
            "test_stressed_return": 0.05,
            "excess_return_percent": 0.02,
            "passes": True,
        },
        confirmation_walk_forward={
            "positive_folds": 2,
            "outperforming_folds": 2,
            "fold_count": 3,
            "average_test_return": 0.03,
            "passes": True,
        },
        readiness={
            "score": 40,
            "status": "Validation refusée",
            "passed_count": 2,
            "check_count": 5,
            "paper_candidate": False,
        },
        generated_at=datetime(2026, 8, 20, 12, 0, tzinfo=UTC),
    )


def test_backtest_report_is_verifiable_and_exportable():
    report = sample_report()
    assert verify_backtest_report(report) is True
    assert len(report["empreinte_sha256"]) == 64
    assert '"format": "jdegen-backtest-report-v1"' in export_backtest_report(report)


def test_backtest_report_detects_tampering():
    report = sample_report()
    report["verdict"]["score"] = 100
    assert verify_backtest_report(report) is False


def test_imported_report_accepts_valid_export():
    result = inspect_backtest_report(export_backtest_report(sample_report()).encode("utf-8"))
    assert result["valid"] is True
    assert result["report"]["marché"] == "SOL / USDC"


def test_imported_report_rejects_tampered_content():
    report = sample_report()
    report["verdict"]["score"] = 100
    result = inspect_backtest_report(export_backtest_report(report))
    assert result["valid"] is False
    assert "Empreinte" in result["reason"]


def test_imported_report_rejects_malformed_or_oversized_files():
    assert inspect_backtest_report(b"not-json")["reason"] == "JSON invalide"
    assert inspect_backtest_report(b"x" * 1_000_001)["reason"] == "Fichier trop volumineux"
