import json

import pytest

from scanner_store import append_scan, export_history, list_observations, scan_count, signal_confirmations


def result(market, action, score):
    return {
        "marché": market, "action": action, "score": score, "confiance": 0.8,
        "priorité": 30, "prix_usd": 10, "variation_24h": 5,
        "liquidité_usd": 1_000_000,
    }


def test_scans_are_persistent_and_exportable(tmp_path):
    database = tmp_path / "scanner.db"
    append_scan([result("SOL", "BUY", 40), result("JUP", "WAIT", 5)], database)
    append_scan([result("SOL", "BUY", 45)], database)
    assert scan_count(database) == 2
    assert len(list_observations(db_path=database)) == 3
    assert len(json.loads(export_history(database))) == 3


def test_signal_confirmation_stops_when_action_changes(tmp_path):
    database = tmp_path / "scanner.db"
    append_scan([result("SOL", "WAIT", 5)], database)
    append_scan([result("SOL", "BUY", 35)], database)
    append_scan([result("SOL", "BUY", 40)], database)
    confirmation = signal_confirmations(list_observations(db_path=database))["SOL"]
    assert confirmation == {"action": "BUY", "cycles": 2}


def test_empty_scan_is_rejected(tmp_path):
    with pytest.raises(ValueError):
        append_scan([], tmp_path / "scanner.db")
