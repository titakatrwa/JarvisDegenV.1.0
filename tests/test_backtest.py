from backtest import (
    analyze_parameter_sensitivity,
    analyze_market_regimes,
    compare_strategies,
    compare_signal_confirmations,
    compare_signal_strength_filters,
    compare_volume_filters,
    run_backtest,
    run_buy_and_hold,
    stress_execution_costs,
    summarize_validation_readiness,
    validate_out_of_sample,
    validate_confirmation_out_of_sample,
    validate_strength_filter_out_of_sample,
    validate_volume_filter_out_of_sample,
    validate_volume_filter_walk_forward,
    validate_strength_filter_walk_forward,
    validate_confirmation_walk_forward,
    validate_walk_forward,
)


def candles(prices):
    return [
        {
            "timestamp": 1_700_000_000 + index * 14_400,
            "open": price,
            "high": price,
            "low": price,
            "close": price,
            "volume": 1_000,
        }
        for index, price in enumerate(prices)
    ]


def test_backtest_returns_auditable_metrics():
    prices = [100] * 12 + [102, 104, 106, 108, 110, 109, 107, 105, 103, 101, 99, 98]
    result = run_backtest(candles(prices), short_window=3, long_window=5)
    assert result["round_trips"] >= 1
    assert len(result["equity"]) == len(prices)
    assert result["max_drawdown_percent"] <= 0
    assert result["final_capital"] > 0
    assert {"open", "high", "low", "close", "volume"}.issubset(result["candles"][0])
    assert 0 <= result["exposure_percent"] <= 100
    assert "sharpe_ratio" in result
    assert "sortino_ratio" in result
    assert "profit_factor" in result
    assert result["expectancy_per_trade"] is not None


def test_risk_adjusted_metrics_are_unavailable_without_variation_or_trades():
    result = run_backtest(candles([100] * 30), short_window=3, long_window=8)
    assert result["sharpe_ratio"] is None
    assert result["sortino_ratio"] is None
    assert result["profit_factor"] is None
    assert result["expectancy_per_trade"] is None
    assert result["exposure_percent"] == 0


def test_backtest_rejects_invalid_windows():
    try:
        run_backtest(candles([100] * 20), short_window=12, long_window=5)
    except ValueError as exc:
        assert "moyenne courte" in str(exc)
    else:
        raise AssertionError("Une configuration invalide aurait dû être refusée")


def test_buy_and_hold_uses_same_risk_budget():
    result = run_buy_and_hold(candles([100, 110]))
    assert 10_000 < result["final_capital"] < 10_100
    assert result["round_trips"] == 1


def test_comparison_contains_four_variants_and_aligned_curves():
    prices = [100 + (index % 8) for index in range(50)]
    result = compare_strategies(candles(prices), custom_short=5, custom_long=12)
    assert len(result["summary"]) == 4
    assert len(result["curves"]) == len(prices) * 4
    assert {row["Stratégie"] for row in result["summary"]} == {
        "Personnalisée 5/12",
        "Réactive 3/8",
        "Prudente 12/30",
        "Buy & hold",
    }


def test_parameter_sensitivity_includes_selected_configuration():
    prices = [100 + index * 0.1 + (index % 8) for index in range(100)]
    result = analyze_parameter_sensitivity(candles(prices), 5, 12)
    selected = [row for row in result["results"] if row["sélectionnée"]]
    assert len(selected) == 1
    assert selected[0]["moyenne_courte"] == 5
    assert selected[0]["moyenne_longue"] == 12
    assert result["combination_count"] == 25
    assert 0 <= result["profitable_percent"] <= 100
    assert result["spread"] == round(result["best_return"] - result["worst_return"], 3)


def test_parameter_sensitivity_skips_invalid_combinations():
    result = analyze_parameter_sensitivity(candles([100] * 50), 3, 4)
    assert all(
        row["moyenne_courte"] < row["moyenne_longue"]
        for row in result["results"]
    )


def test_execution_stress_uses_increasing_costs():
    prices = [100] * 15 + [101 + index * 0.5 for index in range(25)]
    result = stress_execution_costs(candles(prices), 3, 8)
    assert result["scenario_count"] == 3
    costs = [row["coût_total_par_exécution"] for row in result["scenarios"]]
    returns = [row["rendement"] for row in result["scenarios"]]
    assert costs == sorted(costs)
    assert returns == sorted(returns, reverse=True)
    assert result["cost_erosion"] == round(returns[0] - returns[-1], 3)


def test_execution_stress_pass_requires_every_scenario_profitable():
    result = stress_execution_costs(candles([100] * 40), 3, 8)
    assert result["profitable_scenarios"] == 0
    assert result["passes"] is False


def test_confirmation_one_preserves_default_backtest():
    data = candles([100 + index % 9 for index in range(70)])
    default = run_backtest(data, short_window=3, long_window=8)
    explicit = run_backtest(data, short_window=3, long_window=8, confirmation_bars=1)
    assert explicit["final_capital"] == default["final_capital"]
    assert explicit["round_trips"] == default["round_trips"]


def test_confirmation_lab_compares_three_variants_and_stress():
    data = candles([100 + index * 0.05 + index % 10 for index in range(90)])
    result = compare_signal_confirmations(data, 3, 8)
    assert [row["confirmation"] for row in result["variants"]] == [1, 2, 3]
    assert result["baseline_trades"] == result["variants"][0]["trades"]
    assert {row["libellé"] for row in result["variants"]} == {
        "Immédiat", "2 bougies", "3 bougies"
    }


def test_backtest_rejects_invalid_confirmation():
    try:
        run_backtest(candles([100] * 30), short_window=3, long_window=8, confirmation_bars=4)
    except ValueError as exc:
        assert "confirmation" in str(exc)
    else:
        raise AssertionError("Une confirmation invalide aurait dû être refusée")


def test_zero_strength_filter_preserves_default_backtest():
    data = candles([100 + index % 9 for index in range(70)])
    default = run_backtest(data, short_window=3, long_window=8)
    explicit = run_backtest(
        data, short_window=3, long_window=8, min_ma_separation_percent=0
    )
    assert explicit["final_capital"] == default["final_capital"]
    assert explicit["round_trips"] == default["round_trips"]


def test_strength_lab_compares_three_thresholds_without_promotion():
    data = candles([100 + index * 0.04 + index % 8 for index in range(100)])
    result = compare_signal_strength_filters(data, 3, 8)
    assert [row["seuil"] for row in result["variants"]] == [0.0, 0.25, 0.5]
    assert result["baseline_trades"] == result["variants"][0]["trades"]
    assert result["promotion_automatique"] is False


def test_zero_volume_filter_preserves_default_backtest():
    data = candles([100 + index % 9 for index in range(70)])
    default = run_backtest(data, short_window=3, long_window=8)
    explicit = run_backtest(data, short_window=3, long_window=8, min_volume_ratio=0)
    assert explicit["final_capital"] == default["final_capital"]
    assert explicit["round_trips"] == default["round_trips"]


def test_volume_lab_compares_independent_entry_filters():
    data = candles([100 + index * 0.04 + index % 8 for index in range(100)])
    for index, row in enumerate(data):
        row["volume"] = 800 + (index % 7) * 100
    result = compare_volume_filters(data, 3, 8)
    assert [row["ratio"] for row in result["variants"]] == [0.0, 1.0, 1.25]
    assert result["baseline_trades"] == result["variants"][0]["trades"]
    assert result["promotion_automatique"] is False


def test_validation_summary_requires_all_eleven_checks_for_paper_candidate():
    result = summarize_validation_readiness(
        {"return_percent": 1.0},
        {"passes": True, "passed": 7, "total": 7},
        {"sufficient_sample": True, "probability_positive_percent": 75.0, "trade_count": 12},
        {"passes": True, "positive_periods": 2, "outperforming_periods": 2},
        {"passes": True, "excess_return_percent": 0.5},
        {"passes": True, "outperforming_folds": 3, "fold_count": 3},
        {"passes": True, "profitable_percent": 80.0},
        {"passes": True, "profitable_scenarios": 3, "scenario_count": 3},
        {"passes": True, "positive_folds": 2, "outperforming_folds": 2, "fold_count": 3},
        {"passes": True, "positive_folds": 2, "outperforming_folds": 2, "fold_count": 3},
        {"passes": True, "positive_folds": 2, "outperforming_folds": 2, "fold_count": 3},
    )
    assert result["score"] == 100
    assert result["paper_candidate"] is True
    assert result["status"] == "Candidat au paper trading"
    assert result["actions"] == []


def test_validation_summary_marks_missing_walk_forward_as_failed():
    result = summarize_validation_readiness(
        {"return_percent": 1.0},
        {"passes": True, "passed": 7, "total": 7},
        {"sufficient_sample": False, "probability_positive_percent": 55.0, "trade_count": 5},
        {"passes": False, "positive_periods": 1, "outperforming_periods": 1},
        {"passes": True, "excess_return_percent": 0.5},
        None,
        {"passes": True, "profitable_percent": 80.0},
        {"passes": False, "profitable_scenarios": 1, "scenario_count": 3},
        {"passes": True, "positive_folds": 2, "outperforming_folds": 2, "fold_count": 3},
        {"passes": True, "positive_folds": 2, "outperforming_folds": 2, "fold_count": 3},
        {"passes": True, "positive_folds": 2, "outperforming_folds": 2, "fold_count": 3},
    )
    assert result["passed_count"] == 7
    assert result["paper_candidate"] is False
    assert result["status"] == "Surveillance requise"
    assert len(result["actions"]) == 4
    assert result["actions"][0]["priorité"] == "Critique"


def test_validation_summary_blocks_failed_anti_noise_walk_forward():
    result = summarize_validation_readiness(
        {"return_percent": 1.0},
        {"passes": True, "passed": 7, "total": 7},
        {"sufficient_sample": True, "probability_positive_percent": 75.0, "trade_count": 12},
        {"passes": True, "positive_periods": 2, "outperforming_periods": 2},
        {"passes": True, "excess_return_percent": 0.5},
        {"passes": True, "outperforming_folds": 3, "fold_count": 3},
        {"passes": True, "profitable_percent": 80.0},
        {"passes": True, "profitable_scenarios": 3, "scenario_count": 3},
        {"passes": False, "positive_folds": 1, "outperforming_folds": 1, "fold_count": 3},
        {"passes": True, "positive_folds": 2, "outperforming_folds": 2, "fold_count": 3},
        {"passes": True, "positive_folds": 2, "outperforming_folds": 2, "fold_count": 3},
    )
    assert result["passed_count"] == 10
    assert result["check_count"] == 11
    assert result["paper_candidate"] is False
    assert result["actions"][0]["barrière"] == "Walk-forward anti-bruit"


def test_validation_summary_blocks_failed_strength_walk_forward():
    passing_walk = {"passes": True, "positive_folds": 2, "outperforming_folds": 2, "fold_count": 3}
    result = summarize_validation_readiness(
        {"return_percent": 1.0},
        {"passes": True, "passed": 7, "total": 7},
        {"sufficient_sample": True, "probability_positive_percent": 75.0, "trade_count": 12},
        {"passes": True, "positive_periods": 2, "outperforming_periods": 2},
        {"passes": True, "excess_return_percent": 0.5},
        {"passes": True, "outperforming_folds": 3, "fold_count": 3},
        {"passes": True, "profitable_percent": 80.0},
        {"passes": True, "profitable_scenarios": 3, "scenario_count": 3},
        passing_walk,
        {"passes": False, "positive_folds": 1, "outperforming_folds": 1, "fold_count": 3},
        passing_walk,
    )
    assert result["passed_count"] == 10
    assert result["paper_candidate"] is False
    assert result["actions"][0]["barrière"] == "Walk-forward force du signal"


def test_out_of_sample_keeps_test_data_separate():
    prices = [100 + index * 0.2 + (index % 5) for index in range(100)]
    data = candles(prices)
    result = validate_out_of_sample(data)
    assert result["train_count"] == 70
    assert result["test_count"] == 30
    assert result["selected_short"] in {3, 5, 8}
    assert result["selected_long"] in {8, 12, 16}
    assert result["split_date"].timestamp() == data[70]["timestamp"]


def test_confirmation_validation_selects_only_on_training_data():
    data = candles([100 + index * 0.08 + index % 9 for index in range(120)])
    result = validate_confirmation_out_of_sample(data, 3, 8)
    assert result["train_count"] == 84
    assert result["test_count"] == 36
    assert result["selected_confirmation"] in {1, 2, 3}
    assert len(result["training_results"]) == 3
    assert result["split_date"].timestamp() == data[84]["timestamp"]
    assert result["excess_return_percent"] == round(
        result["test_stressed_return"] - result["baseline_test_stressed_return"], 3
    )


def test_strength_validation_keeps_future_data_out_of_selection():
    data = candles([100 + index * 0.05 + index % 8 for index in range(120)])
    result = validate_strength_filter_out_of_sample(data, 3, 8)
    assert result["train_count"] == 84
    assert result["test_count"] == 36
    assert result["selected_threshold"] in {0.0, 0.25, 0.5}
    assert len(result["training_results"]) == 3
    assert result["split_date"].timestamp() == data[84]["timestamp"]
    assert result["excess_return_percent"] == round(
        result["test_stressed_return"] - result["baseline_test_stressed_return"], 3
    )


def test_volume_validation_keeps_future_data_out_of_selection():
    data = candles([100 + index * 0.05 + index % 8 for index in range(120)])
    for index, row in enumerate(data):
        row["volume"] = 800 + (index % 7) * 100
    result = validate_volume_filter_out_of_sample(data, 3, 8)
    assert result["train_count"] == 84
    assert result["test_count"] == 36
    assert result["selected_ratio"] in {0.0, 1.0, 1.25}
    assert len(result["training_results"]) == 3
    assert result["split_date"].timestamp() == data[84]["timestamp"]
    assert result["excess_return_percent"] == round(
        result["test_stressed_return"] - result["baseline_test_stressed_return"], 3
    )


def test_strength_walk_forward_uses_three_disjoint_future_windows():
    data = candles([100 + index * 0.05 + index % 10 for index in range(180)])
    result = validate_strength_filter_walk_forward(data, 3, 8)
    assert result["fold_count"] == 3
    assert [row["bougies_entraînement"] for row in result["folds"]] == [90, 120, 150]
    assert [row["bougies_test"] for row in result["folds"]] == [30, 30, 30]
    assert result["folds"][0]["fin_test"] < result["folds"][1]["début_test"]
    assert all(row["seuil"] in {0.0, 0.25, 0.5} for row in result["folds"])


def test_volume_walk_forward_uses_three_disjoint_future_windows():
    data = candles([100 + index * 0.05 + index % 10 for index in range(180)])
    for index, row in enumerate(data):
        row["volume"] = 800 + (index % 7) * 100
    result = validate_volume_filter_walk_forward(data, 3, 8)
    assert result["fold_count"] == 3
    assert [row["bougies_test"] for row in result["folds"]] == [30, 30, 30]
    assert result["folds"][0]["fin_test"] < result["folds"][1]["début_test"]


def test_confirmation_walk_forward_uses_disjoint_future_windows():
    data = candles([100 + index * 0.06 + index % 11 for index in range(180)])
    result = validate_confirmation_walk_forward(data, 3, 8)
    assert result["fold_count"] == 3
    assert [row["bougies_entraînement"] for row in result["folds"]] == [90, 120, 150]
    assert [row["bougies_test"] for row in result["folds"]] == [30, 30, 30]
    assert result["folds"][0]["fin_test"] < result["folds"][1]["début_test"]
    assert all(row["confirmation"] in {1, 2, 3} for row in result["folds"])


def test_walk_forward_uses_disjoint_future_test_windows():
    prices = [100 + index * 0.05 + (index % 10) for index in range(180)]
    result = validate_walk_forward(candles(prices), folds=3)
    assert result["fold_count"] == 3
    assert [row["bougies_entraînement"] for row in result["folds"]] == [90, 120, 150]
    assert [row["bougies_test"] for row in result["folds"]] == [30, 30, 30]
    assert result["folds"][0]["fin_test"] < result["folds"][1]["début_test"]


def test_walk_forward_rejects_short_history():
    try:
        validate_walk_forward(candles([100] * 100))
    except ValueError as exc:
        assert "120 bougies" in str(exc)
    else:
        raise AssertionError("Un historique court aurait dû être refusé")


def test_market_regimes_use_three_disjoint_chronological_periods():
    prices = list(range(100, 160)) + list(range(160, 100, -1)) + [100 + index % 3 for index in range(60)]
    result = analyze_market_regimes(candles(prices), 5, 12)
    assert len(result["periods"]) == 3
    assert [period["régime"] for period in result["periods"]] == ["Haussier", "Baissier", "Latéral"]
    assert result["periods"][0]["fin"] < result["periods"][1]["début"]


def test_market_regimes_reject_short_segments():
    try:
        analyze_market_regimes(candles([100] * 60), 5, 30)
    except ValueError as exc:
        assert "trois régimes" in str(exc)
    else:
        raise AssertionError("Des segments trop courts auraient dû être refusés")
