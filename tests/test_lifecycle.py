from lifecycle import (assess_paper_drift, build_completion_certificate,
                       build_supervised_paper_policy, evaluate_market_dataset,
                       select_candidate, summarize_cross_market)
from tests.test_backtest import candles


def test_cross_market_requires_two_profitable_markets():
    rows = [{"marché": "A", "configuration": "Base", "réussi": True},
            {"marché": "B", "configuration": "Base", "réussi": True},
            {"marché": "C", "configuration": "Volume", "réussi": False}]
    result = summarize_cross_market(rows)
    assert result["passes"] is True
    assert result["configuration_consensus"] == "Base"


def test_candidate_and_policy_remain_disarmed_when_barriers_fail():
    candidate = select_candidate(
        {"passes": True, "configuration_consensus": "Base"},
        {"paper_candidate": False, "passed_count": 2, "check_count": 11},
    )
    assert candidate["eligible"] is False
    assert build_supervised_paper_policy(candidate)["paper_automatique_armé"] is False


def test_drift_requires_ten_closed_trades():
    assert assess_paper_drift(paper_return=-5, backtest_return=1, paper_drawdown=-5,
                              backtest_drawdown=-1, closed_trades=2)["dérive"] is False
    assert assess_paper_drift(paper_return=-5, backtest_return=1, paper_drawdown=-5,
                              backtest_drawdown=-1, closed_trades=12)["paper_à_suspendre"] is True


def test_market_evaluation_is_stressed_and_auditable():
    data = candles([100 + index * .1 + index % 8 for index in range(100)])
    result = evaluate_market_dataset("TEST", data)
    assert len(result["variantes"]) == 4
    assert result["configuration"] in {row["configuration"] for row in result["variantes"]}


def test_completion_can_certify_mvp_without_promoting_strategy():
    result = build_completion_certificate(
        test_count=100, launch_audit={"blockers": 0}, cross_market={"passes": False},
        candidate={"eligible": False}, drift={"statut": "ÉCHANTILLON INSUFFISANT"},
    )
    assert result["point_6_terminé"] is True
    assert result["candidat_paper"] is False
