from datetime import UTC, datetime

from review_guard import validate_review


NOW = datetime(2026, 8, 20, 12, tzinfo=UTC)
ALERT = {"statut": "À EXAMINER", "signal": "BUY"}
OBSERVATION = {"timestamp": "2026-08-20T11:50:00+00:00"}
ANALYSIS = {"action": "BUY", "confidence": 0.85}


def test_fresh_reconfirmed_alert_is_eligible():
    assert validate_review(ALERT, OBSERVATION, ANALYSIS, True, NOW)["eligible"] is True


def test_human_acknowledgement_is_required():
    result = validate_review(ALERT, OBSERVATION, ANALYSIS, False, NOW)
    assert result == {"eligible": False, "reason": "Validation humaine manquante"}


def test_expired_alert_is_rejected():
    old = {"timestamp": "2026-08-20T11:30:00+00:00"}
    assert validate_review(ALERT, old, ANALYSIS, True, NOW)["eligible"] is False


def test_changed_signal_is_rejected():
    changed = {"action": "WAIT", "confidence": 0.9}
    result = validate_review(ALERT, OBSERVATION, changed, True, NOW)
    assert result["reason"] == "Le signal du marché a changé"
