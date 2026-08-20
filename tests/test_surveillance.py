from datetime import UTC, datetime

import pytest

from surveillance import scan_is_due


NOW = datetime(2026, 8, 20, 12, 10, tzinfo=UTC)


def test_first_scan_is_immediately_due():
    assert scan_is_due(None, 5, NOW) is True


def test_scan_waits_for_selected_interval():
    assert scan_is_due("2026-08-20T12:06:00+00:00", 5, NOW) is False
    assert scan_is_due("2026-08-20T12:05:00+00:00", 5, NOW) is True


def test_unknown_interval_is_rejected():
    with pytest.raises(ValueError):
        scan_is_due(None, 2, NOW)
