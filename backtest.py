"""Moteur de backtesting long-only pour le MVP JarvisDegen."""

from __future__ import annotations

from typing import Any
from math import sqrt

import pandas as pd


def run_backtest(
    candles: list[dict[str, Any]],
    initial_capital: float = 10_000,
    position_percent: float = 2,
    short_window: int = 5,
    long_window: int = 12,
    fee_percent: float = 0.30,
    slippage_percent: float = 0.20,
    confirmation_bars: int = 1,
    min_ma_separation_percent: float = 0.0,
    min_volume_ratio: float = 0.0,
) -> dict[str, Any]:
    if short_window >= long_window:
        raise ValueError("La moyenne courte doit être inférieure à la moyenne longue")
    if not 0 < position_percent <= 5:
        raise ValueError("La taille de position doit être comprise entre 0 et 5 %")
    if len(candles) < long_window + 2:
        raise ValueError("Historique insuffisant")
    if confirmation_bars not in {1, 2, 3}:
        raise ValueError("La confirmation doit être de 1, 2 ou 3 bougies")
    if not 0 <= min_ma_separation_percent <= 2:
        raise ValueError("Le seuil d’écart des moyennes doit être compris entre 0 et 2 %")
    if min_volume_ratio not in {0.0, 1.0, 1.25}:
        raise ValueError("Le ratio de volume doit être 0, 1 ou 1,25")

    frame = pd.DataFrame(candles).sort_values("timestamp").reset_index(drop=True)
    frame["date"] = pd.to_datetime(frame["timestamp"], unit="s", utc=True)
    frame["moyenne_courte"] = frame["close"].rolling(short_window).mean()
    frame["moyenne_longue"] = frame["close"].rolling(long_window).mean()
    frame["volume_médian_20"] = frame["volume"].rolling(20).median()

    cash = float(initial_capital)
    units = 0.0
    entry_cost = 0.0
    exposure_bars = 0
    trades: list[dict[str, Any]] = []
    equity_rows: list[dict[str, Any]] = []
    friction = (fee_percent + slippage_percent) / 100
    bullish_streak = 0
    bearish_streak = 0

    for index, row in frame.iterrows():
        price = float(row["close"])
        if pd.isna(row["moyenne_longue"]):
            equity_rows.append({"date": row["date"], "capital": cash})
            continue
        separation = (
            (row["moyenne_courte"] - row["moyenne_longue"])
            / row["moyenne_longue"]
            * 100
        )
        bullish = separation > 0 if min_ma_separation_percent == 0 else separation >= min_ma_separation_percent
        bearish = separation <= 0 if min_ma_separation_percent == 0 else separation <= -min_ma_separation_percent
        bullish_streak = bullish_streak + 1 if bullish else 0
        bearish_streak = bearish_streak + 1 if bearish else 0
        volume_confirmed = min_volume_ratio == 0 or (
            not pd.isna(row["volume_médian_20"])
            and float(row["volume"]) >= float(row["volume_médian_20"]) * min_volume_ratio
        )
        if bullish_streak >= confirmation_bars and volume_confirmed and units == 0:
            budget = min(cash, cash * position_percent / 100)
            execution_price = price * (1 + friction)
            units = budget / execution_price
            cash -= budget
            entry_cost = budget
            trades.append({"date": row["date"], "action": "BUY", "prix": execution_price, "pnl": None})
        elif bearish_streak >= confirmation_bars and units > 0:
            execution_price = price * (1 - friction)
            proceeds = units * execution_price
            pnl = proceeds - entry_cost
            cash += proceeds
            trades.append({"date": row["date"], "action": "SELL", "prix": execution_price, "pnl": pnl})
            units = 0.0
            entry_cost = 0.0
        if units > 0:
            exposure_bars += 1
        equity_rows.append({"date": row["date"], "capital": cash + units * price})

    if units > 0:
        final_price = float(frame.iloc[-1]["close"]) * (1 - friction)
        proceeds = units * final_price
        pnl = proceeds - entry_cost
        cash += proceeds
        trades.append({"date": frame.iloc[-1]["date"], "action": "SELL", "prix": final_price, "pnl": pnl})
        equity_rows[-1]["capital"] = cash

    equity = pd.DataFrame(equity_rows)
    running_max = equity["capital"].cummax()
    drawdown = (equity["capital"] / running_max - 1) * 100
    closed = [trade for trade in trades if trade["action"] == "SELL"]
    winners = [trade for trade in closed if float(trade["pnl"] or 0) > 0]
    losses = [trade for trade in closed if float(trade["pnl"] or 0) < 0]
    gross_profit = sum(float(trade["pnl"] or 0) for trade in winners)
    gross_loss = abs(sum(float(trade["pnl"] or 0) for trade in losses))
    profit_factor = gross_profit / gross_loss if gross_loss > 0 else None
    expectancy = (
        sum(float(trade["pnl"] or 0) for trade in closed) / len(closed)
        if closed
        else None
    )
    period_returns = equity["capital"].pct_change().dropna()
    volatility = float(period_returns.std(ddof=0)) if not period_returns.empty else 0
    sharpe = (
        float(period_returns.mean()) / volatility * sqrt(6 * 365)
        if volatility > 0
        else None
    )
    downside = period_returns[period_returns < 0]
    downside_deviation = float(downside.std(ddof=0)) if len(downside) > 1 else 0
    sortino = (
        float(period_returns.mean()) / downside_deviation * sqrt(6 * 365)
        if downside_deviation > 0
        else None
    )
    return {
        "final_capital": round(cash, 2),
        "return_percent": round((cash / initial_capital - 1) * 100, 3),
        "max_drawdown_percent": round(float(drawdown.min()), 3),
        "round_trips": len(closed),
        "win_rate_percent": round(len(winners) / len(closed) * 100, 1) if closed else 0.0,
        "sharpe_ratio": round(sharpe, 3) if sharpe is not None else None,
        "sortino_ratio": round(sortino, 3) if sortino is not None else None,
        "profit_factor": round(profit_factor, 3) if profit_factor is not None else None,
        "expectancy_per_trade": round(expectancy, 2) if expectancy is not None else None,
        "exposure_percent": round(exposure_bars / len(frame) * 100, 1),
        "confirmation_bars": confirmation_bars,
        "min_ma_separation_percent": min_ma_separation_percent,
        "min_volume_ratio": min_volume_ratio,
        "equity": equity.to_dict("records"),
        "trades": trades,
        "candles": frame[
            [
                "date",
                "open",
                "high",
                "low",
                "close",
                "volume",
                "moyenne_courte",
                "moyenne_longue",
            ]
        ].to_dict("records"),
    }


def run_buy_and_hold(
    candles: list[dict[str, Any]],
    initial_capital: float = 10_000,
    position_percent: float = 2,
    fee_percent: float = 0.30,
    slippage_percent: float = 0.20,
) -> dict[str, Any]:
    """Benchmark passif utilisant la même taille et les mêmes frictions."""
    frame = pd.DataFrame(candles).sort_values("timestamp").reset_index(drop=True)
    if len(frame) < 2:
        raise ValueError("Historique insuffisant")
    friction = (fee_percent + slippage_percent) / 100
    budget = initial_capital * position_percent / 100
    entry_price = float(frame.iloc[0]["close"]) * (1 + friction)
    units = budget / entry_price
    idle_cash = initial_capital - budget
    equity_rows = []
    for _, row in frame.iterrows():
        equity_rows.append(
            {
                "date": pd.to_datetime(row["timestamp"], unit="s", utc=True),
                "capital": idle_cash + units * float(row["close"]),
            }
        )
    final_price = float(frame.iloc[-1]["close"]) * (1 - friction)
    final_capital = idle_cash + units * final_price
    equity_rows[-1]["capital"] = final_capital
    equity = pd.DataFrame(equity_rows)
    drawdown = (equity["capital"] / equity["capital"].cummax() - 1) * 100
    pnl = final_capital - initial_capital
    return {
        "final_capital": round(final_capital, 2),
        "return_percent": round((final_capital / initial_capital - 1) * 100, 3),
        "max_drawdown_percent": round(float(drawdown.min()), 3),
        "round_trips": 1,
        "win_rate_percent": 100.0 if pnl > 0 else 0.0,
        "equity": equity.to_dict("records"),
        "trades": [],
        "candles": [],
    }


def compare_strategies(
    candles: list[dict[str, Any]], custom_short: int, custom_long: int
) -> dict[str, Any]:
    """Compare des variantes prédéfinies sans choisir automatiquement un gagnant."""
    variants = {
        f"Personnalisée {custom_short}/{custom_long}": run_backtest(
            candles, short_window=custom_short, long_window=custom_long
        ),
        "Réactive 3/8": run_backtest(candles, short_window=3, long_window=8),
        "Prudente 12/30": run_backtest(candles, short_window=12, long_window=30),
        "Buy & hold": run_buy_and_hold(candles),
    }
    summary = []
    curves = []
    for name, result in variants.items():
        summary.append(
            {
                "Stratégie": name,
                "Capital final": result["final_capital"],
                "Rendement": result["return_percent"] / 100,
                "Drawdown": result["max_drawdown_percent"] / 100,
                "Trades": result["round_trips"],
                "Réussite": result["win_rate_percent"] / 100,
            }
        )
        curves.extend(
            {"date": row["date"], "capital": row["capital"], "stratégie": name}
            for row in result["equity"]
        )
    return {"variants": variants, "summary": summary, "curves": curves}


def analyze_parameter_sensitivity(
    candles: list[dict[str, Any]], selected_short: int, selected_long: int
) -> dict[str, Any]:
    """Mesure la stabilité du rendement autour d'un couple de moyennes mobiles."""
    short_windows = sorted({max(2, selected_short + offset) for offset in (-2, -1, 0, 1, 2)})
    long_windows = sorted({max(4, selected_long + offset) for offset in (-4, -2, 0, 2, 4)})
    results = []
    for short_window in short_windows:
        for long_window in long_windows:
            if short_window >= long_window:
                continue
            result = run_backtest(
                candles,
                short_window=short_window,
                long_window=long_window,
            )
            results.append(
                {
                    "moyenne_courte": short_window,
                    "moyenne_longue": long_window,
                    "rendement": result["return_percent"],
                    "drawdown": result["max_drawdown_percent"],
                    "trades": result["round_trips"],
                    "sélectionnée": short_window == selected_short
                    and long_window == selected_long,
                }
            )
    if not results:
        raise ValueError("Aucune combinaison de paramètres valide")
    returns = pd.Series([row["rendement"] for row in results], dtype="float64")
    profitable_count = int((returns > 0).sum())
    baseline = next((row for row in results if row["sélectionnée"]), None)
    return {
        "results": results,
        "combination_count": len(results),
        "profitable_count": profitable_count,
        "profitable_percent": round(profitable_count / len(results) * 100, 1),
        "median_return": round(float(returns.median()), 3),
        "best_return": round(float(returns.max()), 3),
        "worst_return": round(float(returns.min()), 3),
        "spread": round(float(returns.max() - returns.min()), 3),
        "baseline_return": baseline["rendement"] if baseline else None,
        "passes": baseline is not None
        and baseline["rendement"] > 0
        and profitable_count / len(results) >= 0.60
        and float(returns.median()) > 0,
    }


def stress_execution_costs(
    candles: list[dict[str, Any]], short_window: int, long_window: int
) -> dict[str, Any]:
    """Évalue la stratégie sous plusieurs hypothèses de frais et de slippage."""
    scenarios = (
        ("Conditions normales", 0.30, 0.20),
        ("Marché dégradé", 0.60, 0.50),
        ("Marché extrême", 1.00, 1.00),
    )
    results = []
    for name, fee_percent, slippage_percent in scenarios:
        result = run_backtest(
            candles,
            short_window=short_window,
            long_window=long_window,
            fee_percent=fee_percent,
            slippage_percent=slippage_percent,
        )
        results.append(
            {
                "scénario": name,
                "frais": fee_percent,
                "slippage": slippage_percent,
                "coût_total_par_exécution": round(fee_percent + slippage_percent, 2),
                "rendement": result["return_percent"],
                "capital_final": result["final_capital"],
                "drawdown": result["max_drawdown_percent"],
                "trades": result["round_trips"],
                "rentable": result["return_percent"] > 0,
            }
        )
    baseline_return = results[0]["rendement"]
    extreme_return = results[-1]["rendement"]
    profitable_scenarios = sum(row["rentable"] for row in results)
    return {
        "scenarios": results,
        "scenario_count": len(results),
        "profitable_scenarios": profitable_scenarios,
        "baseline_return": baseline_return,
        "extreme_return": extreme_return,
        "cost_erosion": round(baseline_return - extreme_return, 3),
        "passes": profitable_scenarios == len(results),
    }


def compare_signal_confirmations(
    candles: list[dict[str, Any]], short_window: int, long_window: int
) -> dict[str, Any]:
    """Compare un signal immédiat à des confirmations de deux ou trois bougies."""
    variants = []
    for confirmation in (1, 2, 3):
        normal = run_backtest(
            candles,
            short_window=short_window,
            long_window=long_window,
            confirmation_bars=confirmation,
        )
        stressed = run_backtest(
            candles,
            short_window=short_window,
            long_window=long_window,
            fee_percent=1.0,
            slippage_percent=1.0,
            confirmation_bars=confirmation,
        )
        variants.append(
            {
                "confirmation": confirmation,
                "libellé": "Immédiat" if confirmation == 1 else f"{confirmation} bougies",
                "rendement_normal": normal["return_percent"],
                "rendement_stress": stressed["return_percent"],
                "érosion_coûts": round(
                    normal["return_percent"] - stressed["return_percent"], 3
                ),
                "trades": normal["round_trips"],
                "drawdown": normal["max_drawdown_percent"],
                "facteur_profit": normal["profit_factor"],
                "espérance": normal["expectancy_per_trade"],
            }
        )
    lowest_turnover = min(
        variants, key=lambda row: (row["trades"], -row["rendement_normal"])
    )
    best_stressed = max(variants, key=lambda row: row["rendement_stress"])
    return {
        "variants": variants,
        "baseline_trades": variants[0]["trades"],
        "lowest_turnover": lowest_turnover,
        "best_stressed": best_stressed,
    }


def compare_signal_strength_filters(
    candles: list[dict[str, Any]], short_window: int, long_window: int
) -> dict[str, Any]:
    """Compare des seuils minimaux d'écart entre les moyennes mobiles."""
    variants = []
    for threshold in (0.0, 0.25, 0.50):
        normal = run_backtest(
            candles, short_window=short_window, long_window=long_window,
            min_ma_separation_percent=threshold,
        )
        stressed = run_backtest(
            candles, short_window=short_window, long_window=long_window,
            fee_percent=1.0, slippage_percent=1.0,
            min_ma_separation_percent=threshold,
        )
        variants.append({
            "seuil": threshold,
            "libellé": "Sans filtre" if threshold == 0 else f"Écart ≥ {threshold:.2f} %",
            "rendement_normal": normal["return_percent"],
            "rendement_stress": stressed["return_percent"],
            "érosion_coûts": round(normal["return_percent"] - stressed["return_percent"], 3),
            "trades": normal["round_trips"],
            "drawdown": normal["max_drawdown_percent"],
            "facteur_profit": normal["profit_factor"],
            "espérance": normal["expectancy_per_trade"],
        })
    lowest_turnover = min(variants, key=lambda row: (row["trades"], -row["rendement_normal"]))
    best_stressed = max(variants, key=lambda row: row["rendement_stress"])
    return {
        "variants": variants,
        "baseline_trades": variants[0]["trades"],
        "lowest_turnover": lowest_turnover,
        "best_stressed": best_stressed,
        "promotion_automatique": False,
    }


def compare_volume_filters(
    candles: list[dict[str, Any]], short_window: int, long_window: int
) -> dict[str, Any]:
    """Compare des confirmations d'entrée fondées sur le volume médian récent."""
    variants = []
    for ratio in (0.0, 1.0, 1.25):
        normal = run_backtest(
            candles, short_window=short_window, long_window=long_window,
            min_volume_ratio=ratio,
        )
        stressed = run_backtest(
            candles, short_window=short_window, long_window=long_window,
            fee_percent=1.0, slippage_percent=1.0, min_volume_ratio=ratio,
        )
        label = "Sans filtre" if ratio == 0 else (
            "Volume ≥ médiane" if ratio == 1 else "Volume ≥ 1,25 × médiane"
        )
        variants.append({
            "ratio": ratio,
            "libellé": label,
            "rendement_normal": normal["return_percent"],
            "rendement_stress": stressed["return_percent"],
            "érosion_coûts": round(normal["return_percent"] - stressed["return_percent"], 3),
            "trades": normal["round_trips"],
            "drawdown": normal["max_drawdown_percent"],
            "facteur_profit": normal["profit_factor"],
            "espérance": normal["expectancy_per_trade"],
        })
    return {
        "variants": variants,
        "baseline_trades": variants[0]["trades"],
        "lowest_turnover": min(variants, key=lambda row: (row["trades"], -row["rendement_normal"])),
        "best_stressed": max(variants, key=lambda row: row["rendement_stress"]),
        "promotion_automatique": False,
    }


def summarize_validation_readiness(
    backtest_result: dict[str, Any],
    data_quality: dict[str, Any],
    trade_bootstrap: dict[str, Any],
    market_regimes: dict[str, Any] | None,
    out_of_sample: dict[str, Any],
    walk_forward: dict[str, Any] | None,
    sensitivity: dict[str, Any],
    execution_stress: dict[str, Any],
    confirmation_walk_forward: dict[str, Any] | None,
    strength_walk_forward: dict[str, Any] | None,
    volume_walk_forward: dict[str, Any] | None,
) -> dict[str, Any]:
    """Synthétise les contrôles sans autoriser d'exécution réelle."""
    checks = [
        {
            "contrôle": "Qualité des données OHLCV",
            "réussi": bool(data_quality["passes"]),
            "résultat": f"{data_quality['passed']} / {data_quality['total']} contrôles réussis",
        },
        {
            "contrôle": "Suffisance statistique",
            "réussi": bool(
                trade_bootstrap["sufficient_sample"]
                and trade_bootstrap["probability_positive_percent"] is not None
                and trade_bootstrap["probability_positive_percent"] >= 60
            ),
            "résultat": (
                f"{trade_bootstrap['trade_count']} trades, "
                f"{trade_bootstrap['probability_positive_percent']:.1f} % de simulations positives"
                if trade_bootstrap["probability_positive_percent"] is not None
                else "Aucun trade clôturé"
            ),
        },
        {
            "contrôle": "Robustesse par régime",
            "réussi": bool(market_regimes and market_regimes["passes"]),
            "résultat": (
                f"{market_regimes['positive_periods']} / 3 périodes positives, "
                f"{market_regimes['outperforming_periods']} / 3 surperformantes"
                if market_regimes
                else "Non évaluée : historique insuffisant"
            ),
        },
        {
            "contrôle": "Rendement historique",
            "réussi": backtest_result["return_percent"] > 0,
            "résultat": f"{backtest_result['return_percent']:+.3f} %",
        },
        {
            "contrôle": "Validation hors échantillon",
            "réussi": bool(out_of_sample["passes"]),
            "résultat": f"{out_of_sample['excess_return_percent']:+.3f} point vs buy & hold",
        },
        {
            "contrôle": "Validation walk-forward",
            "réussi": bool(walk_forward and walk_forward["passes"]),
            "résultat": (
                f"{walk_forward['outperforming_folds']} / {walk_forward['fold_count']} plis surperforment"
                if walk_forward
                else "Non évaluée : historique insuffisant"
            ),
        },
        {
            "contrôle": "Sensibilité des paramètres",
            "réussi": bool(sensitivity["passes"]),
            "résultat": f"{sensitivity['profitable_percent']:.1f} % de variantes rentables",
        },
        {
            "contrôle": "Stress des coûts",
            "réussi": bool(execution_stress["passes"]),
            "résultat": (
                f"{execution_stress['profitable_scenarios']} / "
                f"{execution_stress['scenario_count']} scénarios rentables"
            ),
        },
        {
            "contrôle": "Walk-forward anti-bruit",
            "réussi": bool(
                confirmation_walk_forward and confirmation_walk_forward["passes"]
            ),
            "résultat": (
                f"{confirmation_walk_forward['positive_folds']} / "
                f"{confirmation_walk_forward['fold_count']} plis positifs, "
                f"{confirmation_walk_forward['outperforming_folds']} / "
                f"{confirmation_walk_forward['fold_count']} surperformants"
                if confirmation_walk_forward
                else "Non évalué : fenêtres futures trop courtes"
            ),
        },
        {
            "contrôle": "Walk-forward force du signal",
            "réussi": bool(strength_walk_forward and strength_walk_forward["passes"]),
            "résultat": (
                f"{strength_walk_forward['positive_folds']} / "
                f"{strength_walk_forward['fold_count']} plis positifs, "
                f"{strength_walk_forward['outperforming_folds']} / "
                f"{strength_walk_forward['fold_count']} meilleurs que sans filtre"
                if strength_walk_forward
                else "Non évalué : fenêtres futures trop courtes"
            ),
        },
        {
            "contrôle": "Walk-forward volume",
            "réussi": bool(volume_walk_forward and volume_walk_forward["passes"]),
            "résultat": (
                f"{volume_walk_forward['positive_folds']} / {volume_walk_forward['fold_count']} plis positifs, "
                f"{volume_walk_forward['outperforming_folds']} / {volume_walk_forward['fold_count']} meilleurs que sans filtre"
                if volume_walk_forward else "Non évalué : fenêtres futures trop courtes"
            ),
        },
    ]
    passed_count = sum(check["réussi"] for check in checks)
    score = round(passed_count / len(checks) * 100)
    action_catalog = {
        "Qualité des données OHLCV": ("Critique", "Corriger ou remplacer la source OHLCV avant toute interprétation.", "Tous les contrôles de données au vert"),
        "Suffisance statistique": ("Haute", "Étendre l’historique ou réduire raisonnablement la fréquence des signaux pour obtenir davantage de trades indépendants.", "Au moins 10 trades et ≥ 60 % de simulations positives"),
        "Robustesse par régime": ("Haute", "Tester un filtre de tendance ou une règle de mise en pause, puis revérifier sans modifier les segments historiques.", "Au moins 2/3 périodes positives et surperformantes"),
        "Rendement historique": ("Haute", "Revoir la logique d’entrée et de sortie sans augmenter la taille de position.", "Rendement historique net positif"),
        "Validation hors échantillon": ("Critique", "Éviter d’optimiser sur toute la période et rechercher des paramètres plus simples sur l’entraînement uniquement.", "Test futur positif et supérieur au buy & hold"),
        "Validation walk-forward": ("Critique", "Réduire la dépendance temporelle puis relancer les trois plis futurs disjoints.", "Majorité des plis positifs et surperformants"),
        "Sensibilité des paramètres": ("Haute", "Privilégier une zone stable de paramètres plutôt que le meilleur point isolé.", "Médiane positive et ≥ 60 % de voisins rentables"),
        "Stress des coûts": ("Critique", "Réduire la rotation ou exiger un avantage brut supérieur avant l’entrée.", "Rentabilité positive dans les trois scénarios de coûts"),
        "Walk-forward anti-bruit": ("Critique", "Ne pas retenir une confirmation fixe ; collecter davantage d’historique ou tester une règle anti-bruit plus stable.", "Au moins 2/3 plis futurs positifs et surperformants sous coûts extrêmes"),
        "Walk-forward force du signal": ("Critique", "Ne pas activer le seuil de force ; rechercher un avantage brut plus important ou un filtre indépendant des mêmes moyennes.", "Au moins 2/3 plis futurs positifs et meilleurs que sans filtre sous coûts extrêmes"),
        "Walk-forward volume": ("Critique", "Ne pas activer le filtre de volume tant que sa stabilité temporelle n’est pas démontrée.", "Au moins 2/3 plis futurs positifs et meilleurs que sans filtre sous coûts extrêmes"),
    }
    actions = []
    for check in checks:
        if check["réussi"]:
            continue
        priority, action, objective = action_catalog[check["contrôle"]]
        actions.append(
            {
                "priorité": priority,
                "barrière": check["contrôle"],
                "constat": check["résultat"],
                "action recommandée": action,
                "objectif du prochain test": objective,
            }
        )
    priority_order = {"Critique": 0, "Haute": 1, "Moyenne": 2}
    actions.sort(key=lambda row: priority_order[row["priorité"]])
    if passed_count == len(checks):
        status = "Candidat au paper trading"
        color = "green"
        recommendation = "Poursuivre uniquement en simulation avec surveillance humaine."
    elif passed_count >= len(checks) // 2:
        status = "Surveillance requise"
        color = "orange"
        recommendation = "Conserver en observation et corriger les contrôles échoués."
    else:
        status = "Validation refusée"
        color = "red"
        recommendation = "Ne pas promouvoir cette configuration ; revoir la stratégie."
    return {
        "checks": checks,
        "passed_count": passed_count,
        "check_count": len(checks),
        "score": score,
        "status": status,
        "color": color,
        "recommendation": recommendation,
        "paper_candidate": passed_count == len(checks),
        "actions": actions,
    }


def validate_out_of_sample(
    candles: list[dict[str, Any]], train_ratio: float = 0.70
) -> dict[str, Any]:
    """Choisit une variante sur l'entraînement puis la teste sur des données séparées."""
    if not 0.50 <= train_ratio <= 0.80:
        raise ValueError("Le ratio d'entraînement doit être compris entre 50 et 80 %")
    split_index = int(len(candles) * train_ratio)
    training = candles[:split_index]
    testing = candles[split_index:]
    candidates = [(3, 8), (5, 12), (8, 16)]
    training_results = []
    for short_window, long_window in candidates:
        result = run_backtest(
            training, short_window=short_window, long_window=long_window
        )
        training_results.append(
            {
                "short": short_window,
                "long": long_window,
                "return_percent": result["return_percent"],
                "drawdown_percent": result["max_drawdown_percent"],
            }
        )
    selected = max(training_results, key=lambda row: row["return_percent"])
    test_result = run_backtest(
        testing,
        short_window=selected["short"],
        long_window=selected["long"],
    )
    benchmark = run_buy_and_hold(testing)
    excess_return = round(
        test_result["return_percent"] - benchmark["return_percent"], 3
    )
    return {
        "train_count": len(training),
        "test_count": len(testing),
        "split_date": pd.to_datetime(testing[0]["timestamp"], unit="s", utc=True),
        "training_results": training_results,
        "selected_short": selected["short"],
        "selected_long": selected["long"],
        "training_return_percent": selected["return_percent"],
        "test_result": test_result,
        "benchmark_result": benchmark,
        "excess_return_percent": excess_return,
        "passes": test_result["return_percent"] > 0 and excess_return > 0,
    }


def validate_confirmation_out_of_sample(
    candles: list[dict[str, Any]],
    short_window: int,
    long_window: int,
    train_ratio: float = 0.70,
) -> dict[str, Any]:
    """Sélectionne la confirmation sur le passé puis l'évalue sur le futur séparé."""
    if not 0.50 <= train_ratio <= 0.80:
        raise ValueError("Le ratio d'entraînement doit être compris entre 50 et 80 %")
    ordered = sorted(candles, key=lambda row: row["timestamp"])
    split_index = int(len(ordered) * train_ratio)
    training = ordered[:split_index]
    testing = ordered[split_index:]
    if len(training) < long_window + 2 or len(testing) < long_window + 2:
        raise ValueError("Historique insuffisant pour valider la confirmation")

    training_results = []
    for confirmation in (1, 2, 3):
        normal = run_backtest(
            training, short_window=short_window, long_window=long_window,
            confirmation_bars=confirmation,
        )
        stressed = run_backtest(
            training, short_window=short_window, long_window=long_window,
            fee_percent=1.0, slippage_percent=1.0,
            confirmation_bars=confirmation,
        )
        training_results.append({
            "confirmation": confirmation,
            "libellé": "Immédiat" if confirmation == 1 else f"{confirmation} bougies",
            "rendement_normal": normal["return_percent"],
            "rendement_stress": stressed["return_percent"],
            "trades": normal["round_trips"],
        })

    selected = max(training_results, key=lambda row: row["rendement_stress"])
    selected_test = run_backtest(
        testing, short_window=short_window, long_window=long_window,
        fee_percent=1.0, slippage_percent=1.0,
        confirmation_bars=selected["confirmation"],
    )
    baseline_test = run_backtest(
        testing, short_window=short_window, long_window=long_window,
        fee_percent=1.0, slippage_percent=1.0, confirmation_bars=1,
    )
    excess = round(
        selected_test["return_percent"] - baseline_test["return_percent"], 3
    )
    return {
        "train_count": len(training),
        "test_count": len(testing),
        "split_date": pd.to_datetime(testing[0]["timestamp"], unit="s", utc=True),
        "training_results": training_results,
        "selected_confirmation": selected["confirmation"],
        "selected_label": selected["libellé"],
        "training_stressed_return": selected["rendement_stress"],
        "test_stressed_return": selected_test["return_percent"],
        "baseline_test_stressed_return": baseline_test["return_percent"],
        "excess_return_percent": excess,
        "test_trades": selected_test["round_trips"],
        "passes": selected_test["return_percent"] > 0 and excess >= 0,
    }


def validate_strength_filter_out_of_sample(
    candles: list[dict[str, Any]],
    short_window: int,
    long_window: int,
    train_ratio: float = 0.70,
) -> dict[str, Any]:
    """Choisit un seuil de force sur l'entraînement puis le teste sur le futur."""
    if not 0.50 <= train_ratio <= 0.80:
        raise ValueError("Le ratio d’entraînement doit être compris entre 50 et 80 %")
    ordered = sorted(candles, key=lambda row: row["timestamp"])
    split_index = int(len(ordered) * train_ratio)
    training = ordered[:split_index]
    testing = ordered[split_index:]
    if len(training) < long_window + 2 or len(testing) < long_window + 2:
        raise ValueError("Historique insuffisant pour valider le filtre de force")

    training_results = []
    for threshold in (0.0, 0.25, 0.50):
        result = run_backtest(
            training, short_window=short_window, long_window=long_window,
            fee_percent=1.0, slippage_percent=1.0,
            min_ma_separation_percent=threshold,
        )
        training_results.append({
            "seuil": threshold,
            "libellé": "Sans filtre" if threshold == 0 else f"Écart ≥ {threshold:.2f} %",
            "rendement_stress": result["return_percent"],
            "trades": result["round_trips"],
        })
    selected = max(training_results, key=lambda row: row["rendement_stress"])
    selected_test = run_backtest(
        testing, short_window=short_window, long_window=long_window,
        fee_percent=1.0, slippage_percent=1.0,
        min_ma_separation_percent=selected["seuil"],
    )
    baseline_test = run_backtest(
        testing, short_window=short_window, long_window=long_window,
        fee_percent=1.0, slippage_percent=1.0,
        min_ma_separation_percent=0,
    )
    excess = round(selected_test["return_percent"] - baseline_test["return_percent"], 3)
    return {
        "train_count": len(training),
        "test_count": len(testing),
        "split_date": pd.to_datetime(testing[0]["timestamp"], unit="s", utc=True),
        "training_results": training_results,
        "selected_threshold": selected["seuil"],
        "selected_label": selected["libellé"],
        "training_stressed_return": selected["rendement_stress"],
        "test_stressed_return": selected_test["return_percent"],
        "baseline_test_stressed_return": baseline_test["return_percent"],
        "excess_return_percent": excess,
        "test_trades": selected_test["round_trips"],
        "passes": selected_test["return_percent"] > 0 and excess >= 0,
    }


def validate_volume_filter_out_of_sample(
    candles: list[dict[str, Any]],
    short_window: int,
    long_window: int,
    train_ratio: float = 0.70,
) -> dict[str, Any]:
    """Choisit un filtre de volume sur l'entraînement puis le teste sur le futur."""
    if not 0.50 <= train_ratio <= 0.80:
        raise ValueError("Le ratio d’entraînement doit être compris entre 50 et 80 %")
    ordered = sorted(candles, key=lambda row: row["timestamp"])
    split_index = int(len(ordered) * train_ratio)
    training = ordered[:split_index]
    testing = ordered[split_index:]
    if len(training) < max(long_window + 2, 20) or len(testing) < max(long_window + 2, 20):
        raise ValueError("Historique insuffisant pour valider le filtre de volume")
    training_results = []
    for ratio in (0.0, 1.0, 1.25):
        result = run_backtest(
            training, short_window=short_window, long_window=long_window,
            fee_percent=1.0, slippage_percent=1.0, min_volume_ratio=ratio,
        )
        label = "Sans filtre" if ratio == 0 else (
            "Volume ≥ médiane" if ratio == 1 else "Volume ≥ 1,25 × médiane"
        )
        training_results.append({
            "ratio": ratio, "libellé": label,
            "rendement_stress": result["return_percent"],
            "trades": result["round_trips"],
        })
    selected = max(training_results, key=lambda row: row["rendement_stress"])
    selected_test = run_backtest(
        testing, short_window=short_window, long_window=long_window,
        fee_percent=1.0, slippage_percent=1.0, min_volume_ratio=selected["ratio"],
    )
    baseline_test = run_backtest(
        testing, short_window=short_window, long_window=long_window,
        fee_percent=1.0, slippage_percent=1.0, min_volume_ratio=0,
    )
    excess = round(selected_test["return_percent"] - baseline_test["return_percent"], 3)
    return {
        "train_count": len(training),
        "test_count": len(testing),
        "split_date": pd.to_datetime(testing[0]["timestamp"], unit="s", utc=True),
        "training_results": training_results,
        "selected_ratio": selected["ratio"],
        "selected_label": selected["libellé"],
        "training_stressed_return": selected["rendement_stress"],
        "test_stressed_return": selected_test["return_percent"],
        "baseline_test_stressed_return": baseline_test["return_percent"],
        "excess_return_percent": excess,
        "test_trades": selected_test["round_trips"],
        "passes": selected_test["return_percent"] > 0 and excess >= 0,
    }


def validate_confirmation_walk_forward(
    candles: list[dict[str, Any]],
    short_window: int,
    long_window: int,
    folds: int = 3,
) -> dict[str, Any]:
    """Répète la sélection de confirmation sur trois fenêtres futures distinctes."""
    if folds not in {2, 3, 4}:
        raise ValueError("Le nombre de plis doit être compris entre 2 et 4")
    ordered = sorted(candles, key=lambda row: row["timestamp"])
    if len(ordered) < 120:
        raise ValueError("Au moins 120 bougies sont nécessaires au walk-forward")
    initial_train = len(ordered) // 2
    test_size = (len(ordered) - initial_train) // folds
    if test_size < long_window + 2:
        raise ValueError("Les fenêtres futures sont trop courtes pour ces moyennes")

    fold_results = []
    for fold_index in range(folds):
        train_end = initial_train + fold_index * test_size
        test_end = len(ordered) if fold_index == folds - 1 else train_end + test_size
        training = ordered[:train_end]
        testing = ordered[train_end:test_end]
        selections = []
        for confirmation in (1, 2, 3):
            result = run_backtest(
                training, short_window=short_window, long_window=long_window,
                fee_percent=1.0, slippage_percent=1.0,
                confirmation_bars=confirmation,
            )
            selections.append({
                "confirmation": confirmation,
                "rendement_stress": result["return_percent"],
            })
        selected = max(selections, key=lambda row: row["rendement_stress"])
        test_result = run_backtest(
            testing, short_window=short_window, long_window=long_window,
            fee_percent=1.0, slippage_percent=1.0,
            confirmation_bars=selected["confirmation"],
        )
        baseline = run_backtest(
            testing, short_window=short_window, long_window=long_window,
            fee_percent=1.0, slippage_percent=1.0, confirmation_bars=1,
        )
        excess = round(test_result["return_percent"] - baseline["return_percent"], 3)
        fold_results.append({
            "pli": fold_index + 1,
            "bougies_entraînement": len(training),
            "bougies_test": len(testing),
            "début_test": pd.to_datetime(testing[0]["timestamp"], unit="s", utc=True),
            "fin_test": pd.to_datetime(testing[-1]["timestamp"], unit="s", utc=True),
            "confirmation": selected["confirmation"],
            "libellé": "Immédiat" if selected["confirmation"] == 1 else f"{selected['confirmation']} bougies",
            "rendement_test_stressé": test_result["return_percent"],
            "rendement_immédiat_stressé": baseline["return_percent"],
            "écart_vs_immédiat": excess,
            "trades": test_result["round_trips"],
            "positif": test_result["return_percent"] > 0,
            "surperforme": excess >= 0,
        })
    positive_folds = sum(row["positif"] for row in fold_results)
    outperforming_folds = sum(row["surperforme"] for row in fold_results)
    return {
        "folds": fold_results,
        "fold_count": len(fold_results),
        "positive_folds": positive_folds,
        "outperforming_folds": outperforming_folds,
        "average_test_return": round(
            sum(row["rendement_test_stressé"] for row in fold_results) / len(fold_results), 3
        ),
        "average_excess_return": round(
            sum(row["écart_vs_immédiat"] for row in fold_results) / len(fold_results), 3
        ),
        "passes": positive_folds >= 2 and outperforming_folds >= 2,
    }


def validate_strength_filter_walk_forward(
    candles: list[dict[str, Any]],
    short_window: int,
    long_window: int,
    folds: int = 3,
) -> dict[str, Any]:
    """Répète la sélection du seuil de force sur des fenêtres futures distinctes."""
    if folds not in {2, 3, 4}:
        raise ValueError("Le nombre de plis doit être compris entre 2 et 4")
    ordered = sorted(candles, key=lambda row: row["timestamp"])
    if len(ordered) < 120:
        raise ValueError("Au moins 120 bougies sont nécessaires au walk-forward")
    initial_train = len(ordered) // 2
    test_size = (len(ordered) - initial_train) // folds
    if test_size < long_window + 2:
        raise ValueError("Les fenêtres futures sont trop courtes pour ces moyennes")

    fold_results = []
    for fold_index in range(folds):
        train_end = initial_train + fold_index * test_size
        test_end = len(ordered) if fold_index == folds - 1 else train_end + test_size
        training = ordered[:train_end]
        testing = ordered[train_end:test_end]
        selections = []
        for threshold in (0.0, 0.25, 0.50):
            result = run_backtest(
                training, short_window=short_window, long_window=long_window,
                fee_percent=1.0, slippage_percent=1.0,
                min_ma_separation_percent=threshold,
            )
            selections.append({"seuil": threshold, "rendement_stress": result["return_percent"]})
        selected = max(selections, key=lambda row: row["rendement_stress"])
        test_result = run_backtest(
            testing, short_window=short_window, long_window=long_window,
            fee_percent=1.0, slippage_percent=1.0,
            min_ma_separation_percent=selected["seuil"],
        )
        baseline = run_backtest(
            testing, short_window=short_window, long_window=long_window,
            fee_percent=1.0, slippage_percent=1.0,
            min_ma_separation_percent=0,
        )
        excess = round(test_result["return_percent"] - baseline["return_percent"], 3)
        fold_results.append({
            "pli": fold_index + 1,
            "bougies_entraînement": len(training),
            "bougies_test": len(testing),
            "début_test": pd.to_datetime(testing[0]["timestamp"], unit="s", utc=True),
            "fin_test": pd.to_datetime(testing[-1]["timestamp"], unit="s", utc=True),
            "seuil": selected["seuil"],
            "libellé": "Sans filtre" if selected["seuil"] == 0 else f"Écart ≥ {selected['seuil']:.2f} %",
            "rendement_test_stressé": test_result["return_percent"],
            "rendement_sans_filtre_stressé": baseline["return_percent"],
            "écart_vs_sans_filtre": excess,
            "trades": test_result["round_trips"],
            "positif": test_result["return_percent"] > 0,
            "surperforme": excess >= 0,
        })
    positive_folds = sum(row["positif"] for row in fold_results)
    outperforming_folds = sum(row["surperforme"] for row in fold_results)
    return {
        "folds": fold_results,
        "fold_count": len(fold_results),
        "positive_folds": positive_folds,
        "outperforming_folds": outperforming_folds,
        "average_test_return": round(sum(row["rendement_test_stressé"] for row in fold_results) / len(fold_results), 3),
        "average_excess_return": round(sum(row["écart_vs_sans_filtre"] for row in fold_results) / len(fold_results), 3),
        "passes": positive_folds >= 2 and outperforming_folds >= 2,
    }


def validate_volume_filter_walk_forward(
    candles: list[dict[str, Any]], short_window: int, long_window: int, folds: int = 3
) -> dict[str, Any]:
    """Sélectionne le filtre de volume avant chaque fenêtre future distincte."""
    if folds not in {2, 3, 4}:
        raise ValueError("Le nombre de plis doit être compris entre 2 et 4")
    ordered = sorted(candles, key=lambda row: row["timestamp"])
    if len(ordered) < 120:
        raise ValueError("Au moins 120 bougies sont nécessaires au walk-forward")
    initial_train = len(ordered) // 2
    test_size = (len(ordered) - initial_train) // folds
    if test_size < max(long_window + 2, 20):
        raise ValueError("Les fenêtres futures sont trop courtes pour le filtre de volume")
    rows = []
    for fold_index in range(folds):
        train_end = initial_train + fold_index * test_size
        test_end = len(ordered) if fold_index == folds - 1 else train_end + test_size
        training, testing = ordered[:train_end], ordered[train_end:test_end]
        choices = []
        for ratio in (0.0, 1.0, 1.25):
            result = run_backtest(training, short_window=short_window, long_window=long_window,
                                  fee_percent=1.0, slippage_percent=1.0, min_volume_ratio=ratio)
            choices.append({"ratio": ratio, "rendement": result["return_percent"]})
        selected = max(choices, key=lambda row: row["rendement"])
        test = run_backtest(testing, short_window=short_window, long_window=long_window,
                            fee_percent=1.0, slippage_percent=1.0,
                            min_volume_ratio=selected["ratio"])
        baseline = run_backtest(testing, short_window=short_window, long_window=long_window,
                                fee_percent=1.0, slippage_percent=1.0, min_volume_ratio=0)
        excess = round(test["return_percent"] - baseline["return_percent"], 3)
        label = "Sans filtre" if selected["ratio"] == 0 else (
            "Volume ≥ médiane" if selected["ratio"] == 1 else "Volume ≥ 1,25 × médiane"
        )
        rows.append({"pli": fold_index + 1, "bougies_entraînement": len(training),
                     "bougies_test": len(testing),
                     "début_test": pd.to_datetime(testing[0]["timestamp"], unit="s", utc=True),
                     "fin_test": pd.to_datetime(testing[-1]["timestamp"], unit="s", utc=True),
                     "ratio": selected["ratio"], "libellé": label,
                     "rendement_test_stressé": test["return_percent"],
                     "rendement_sans_filtre_stressé": baseline["return_percent"],
                     "écart_vs_sans_filtre": excess, "trades": test["round_trips"],
                     "positif": test["return_percent"] > 0, "surperforme": excess >= 0})
    positive = sum(row["positif"] for row in rows)
    outperforming = sum(row["surperforme"] for row in rows)
    return {"folds": rows, "fold_count": len(rows), "positive_folds": positive,
            "outperforming_folds": outperforming,
            "average_test_return": round(sum(r["rendement_test_stressé"] for r in rows) / len(rows), 3),
            "average_excess_return": round(sum(r["écart_vs_sans_filtre"] for r in rows) / len(rows), 3),
            "passes": positive >= 2 and outperforming >= 2}


def validate_walk_forward(
    candles: list[dict[str, Any]], folds: int = 3
) -> dict[str, Any]:
    """Répète sélection puis test sur plusieurs fenêtres chronologiques disjointes."""
    if folds not in {2, 3, 4}:
        raise ValueError("Le nombre de plis doit être compris entre 2 et 4")
    if len(candles) < 120:
        raise ValueError("Au moins 120 bougies sont nécessaires au walk-forward")
    ordered = sorted(candles, key=lambda row: row["timestamp"])
    initial_train = len(ordered) // 2
    test_size = (len(ordered) - initial_train) // folds
    if test_size < 20:
        raise ValueError("Les fenêtres de test sont trop courtes")
    candidates = [(3, 8), (5, 12), (8, 16)]
    fold_results = []
    for fold_index in range(folds):
        train_end = initial_train + fold_index * test_size
        test_end = len(ordered) if fold_index == folds - 1 else train_end + test_size
        training = ordered[:train_end]
        testing = ordered[train_end:test_end]
        selections = []
        for short_window, long_window in candidates:
            result = run_backtest(
                training, short_window=short_window, long_window=long_window
            )
            selections.append(
                {
                    "short": short_window,
                    "long": long_window,
                    "return_percent": result["return_percent"],
                    "drawdown_percent": result["max_drawdown_percent"],
                }
            )
        selected = max(
            selections,
            key=lambda row: (row["return_percent"], row["drawdown_percent"]),
        )
        test_result = run_backtest(
            testing,
            short_window=selected["short"],
            long_window=selected["long"],
        )
        benchmark = run_buy_and_hold(testing)
        excess = round(
            test_result["return_percent"] - benchmark["return_percent"], 3
        )
        fold_results.append(
            {
                "pli": fold_index + 1,
                "début_test": pd.to_datetime(testing[0]["timestamp"], unit="s", utc=True),
                "fin_test": pd.to_datetime(testing[-1]["timestamp"], unit="s", utc=True),
                "bougies_entraînement": len(training),
                "bougies_test": len(testing),
                "paramètres": f"{selected['short']}/{selected['long']}",
                "rendement_entraînement": selected["return_percent"],
                "rendement_test": test_result["return_percent"],
                "rendement_benchmark": benchmark["return_percent"],
                "surperformance": excess,
                "trades": test_result["round_trips"],
                "positif": test_result["return_percent"] > 0,
                "surperforme": excess > 0,
            }
        )
    positive_folds = sum(row["positif"] for row in fold_results)
    outperforming_folds = sum(row["surperforme"] for row in fold_results)
    return {
        "folds": fold_results,
        "fold_count": folds,
        "positive_folds": positive_folds,
        "outperforming_folds": outperforming_folds,
        "average_test_return": round(
            sum(row["rendement_test"] for row in fold_results) / folds, 3
        ),
        "average_benchmark_return": round(
            sum(row["rendement_benchmark"] for row in fold_results) / folds, 3
        ),
        "passes": positive_folds >= (folds // 2 + 1)
        and outperforming_folds >= (folds // 2 + 1),
    }


def analyze_market_regimes(
    candles: list[dict[str, Any]], short_window: int, long_window: int
) -> dict[str, Any]:
    """Évalue les mêmes paramètres sur trois segments chronologiques indépendants."""
    ordered = sorted(candles, key=lambda row: row["timestamp"])
    if len(ordered) < 3 * (long_window + 2):
        raise ValueError("Historique insuffisant pour trois régimes indépendants")
    segment_size = len(ordered) // 3
    periods = []
    for index in range(3):
        start = index * segment_size
        end = len(ordered) if index == 2 else (index + 1) * segment_size
        segment = ordered[start:end]
        market_return = (float(segment[-1]["close"]) / float(segment[0]["close"]) - 1) * 100
        regime = (
            "Haussier"
            if market_return > 2.000001
            else "Baissier"
            if market_return < -2.000001
            else "Latéral"
        )
        strategy = run_backtest(
            segment,
            short_window=short_window,
            long_window=long_window,
        )
        benchmark = run_buy_and_hold(segment)
        excess = round(strategy["return_percent"] - benchmark["return_percent"], 3)
        periods.append(
            {
                "période": index + 1,
                "début": pd.to_datetime(segment[0]["timestamp"], unit="s", utc=True),
                "fin": pd.to_datetime(segment[-1]["timestamp"], unit="s", utc=True),
                "régime": regime,
                "mouvement_marché": round(market_return, 3),
                "rendement_stratégie": strategy["return_percent"],
                "rendement_buy_hold": benchmark["return_percent"],
                "surperformance": excess,
                "drawdown": strategy["max_drawdown_percent"],
                "trades": strategy["round_trips"],
                "positif": strategy["return_percent"] > 0,
                "surperforme": excess > 0,
            }
        )
    return {
        "periods": periods,
        "positive_periods": sum(period["positif"] for period in periods),
        "outperforming_periods": sum(period["surperforme"] for period in periods),
        "regimes_observed": sorted({period["régime"] for period in periods}),
        "passes": sum(period["positif"] for period in periods) >= 2
        and sum(period["surperforme"] for period in periods) >= 2,
    }
