import sqlite3

from backtest_report_store import (
    archive_backtest_report,
    list_backtest_reports,
    summarize_backtest_history,
    verify_backtest_archive,
)
from tests.test_backtest_report import sample_report


def test_archive_deduplicates_report_fingerprint(tmp_path):
    db_path = tmp_path / "reports.db"
    report = sample_report()
    first = archive_backtest_report(report, db_path)
    second = archive_backtest_report(report, db_path)
    assert first["inserted"] is True
    assert second["inserted"] is False
    assert len(list_backtest_reports(db_path=db_path)) == 1


def test_archive_detects_modified_payload(tmp_path):
    db_path = tmp_path / "reports.db"
    archived = archive_backtest_report(sample_report(), db_path)
    with sqlite3.connect(db_path) as connection:
        connection.execute(
            "UPDATE backtest_reports SET payload = replace(payload, '40', '99') WHERE id = ?",
            (archived["id"],),
        )
    status = verify_backtest_archive(db_path)
    assert status["valid"] is False
    assert status["invalid_ids"] == [archived["id"]]


def test_history_summary_compares_latest_with_previous():
    reports = [
        {
            "généré_le": "2026-08-20T12:10:00+00:00",
            "marché": "SOL / USDC",
            "verdict": {"score": 60},
            "résultat": {"rendement_pourcent": 0.3},
        },
        {
            "généré_le": "2026-08-20T12:00:00+00:00",
            "marché": "SOL / USDC",
            "verdict": {"score": 40},
            "résultat": {"rendement_pourcent": 0.1},
        },
    ]
    summary = summarize_backtest_history(reports)
    assert summary["score_delta"] == 20
    assert summary["return_delta"] == 0.2
    assert summary["best_score"] == 60
    assert summary["trend"][0]["score"] == 40


def test_history_summary_handles_first_report():
    summary = summarize_backtest_history(
        [{
            "généré_le": "2026-08-20T12:00:00+00:00",
            "marché": "SOL / USDC",
            "verdict": {"score": 40},
            "résultat": {"rendement_pourcent": 0.1},
        }]
    )
    assert summary["score_delta"] is None
    assert summary["best_score"] == 40
