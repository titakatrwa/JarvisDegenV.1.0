from signal_alerts import build_alerts


def observation(action="BUY", confidence=0.8, market="SOL/USDC"):
    return {
        "market": market,
        "action": action,
        "score": 40,
        "confidence": confidence,
        "price_usd": 100,
    }


def test_confirmed_buy_is_ready_for_review():
    alerts = build_alerts(
        [observation()],
        {"SOL/USDC": {"action": "BUY", "cycles": 2}},
        {"positions": []},
        {"halted": False},
    )
    assert alerts[0]["statut"] == "À EXAMINER"
    assert alerts[0]["exécution_automatique"] is False


def test_circuit_breaker_blocks_buy_alert():
    alerts = build_alerts(
        [observation()],
        {"SOL/USDC": {"action": "BUY", "cycles": 3}},
        {"positions": []},
        {"halted": True},
    )
    assert alerts[0]["statut"] == "SURVEILLANCE"
    assert "Coupe-circuit" in alerts[0]["motif"]


def test_existing_position_blocks_another_buy():
    alerts = build_alerts(
        [observation()],
        {"SOL/USDC": {"action": "BUY", "cycles": 3}},
        {"positions": [{"market": "SOL/USDC"}]},
        {"halted": False},
    )
    assert alerts[0]["statut"] == "SURVEILLANCE"
    assert "déjà ouverte" in alerts[0]["motif"]


def test_sell_requires_an_open_position():
    alerts = build_alerts(
        [observation(action="SELL")],
        {"SOL/USDC": {"action": "SELL", "cycles": 2}},
        {"positions": []},
        {"halted": False},
    )
    assert alerts[0]["statut"] == "SURVEILLANCE"
    assert "Aucune position" in alerts[0]["motif"]


def test_wait_does_not_create_an_alert():
    assert build_alerts(
        [observation(action="WAIT")],
        {"SOL/USDC": {"action": "WAIT", "cycles": 5}},
        {"positions": []},
        {"halted": False},
    ) == []
