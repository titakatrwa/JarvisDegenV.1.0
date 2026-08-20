from launch_audit import run_launch_audit


def make_project(tmp_path, package="{}", source_extra=""):
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "config.ts").write_text(
        'const simulation_mode = true; // doit rester à true', encoding="utf-8"
    )
    (tmp_path / "src" / "engine.ts").write_text(source_extra, encoding="utf-8")
    (tmp_path / "package.json").write_text(package, encoding="utf-8")
    (tmp_path / ".gitignore").write_text(".env\n", encoding="utf-8")
    (tmp_path / "app.py").write_text(
        '# validation humaine obligatoire', encoding="utf-8"
    )
    return tmp_path


def test_safe_project_is_ready_for_human_review(tmp_path):
    result = run_launch_audit(make_project(tmp_path), {"valid": True, "count": 2})
    assert result["review_ready"] is True
    assert result["blockers"] == 0
    assert result["real_trading_enabled"] is False


def test_transaction_sender_is_blocking(tmp_path):
    root = make_project(tmp_path, source_extra="client.sendTransaction(payload)")
    result = run_launch_audit(root, {"valid": True, "count": 1})
    assert result["review_ready"] is False
    assert result["blockers"] == 1


def test_broken_audit_chain_is_blocking(tmp_path):
    result = run_launch_audit(make_project(tmp_path), {"valid": False, "count": 1})
    assert result["review_ready"] is False
    assert result["blockers"] == 1
