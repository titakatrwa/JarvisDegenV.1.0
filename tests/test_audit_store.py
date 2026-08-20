import json
import sqlite3

from audit_store import append_record, export_json, list_records, verify_chain


def test_persistent_chain_and_exports(tmp_path):
    database = tmp_path / "audit.db"
    first = append_record({"action": "BUY", "prix": 100}, database)
    second = append_record({"action": "WAIT", "prix": 101}, database)
    records = list_records(db_path=database)
    assert records[0]["audit_id"] == second["audit_id"]
    assert records[1]["audit_id"] == first["audit_id"]
    assert verify_chain(database) == {"valid": True, "count": 2, "broken_at": None}
    assert len(json.loads(export_json(database))) == 2


def test_chain_detects_tampering(tmp_path):
    database = tmp_path / "audit.db"
    append_record({"action": "BUY"}, database)
    append_record({"action": "SELL"}, database)
    with sqlite3.connect(database) as connection:
        connection.execute("UPDATE decisions SET payload = ? WHERE id = 1", ('{"action":"WAIT"}',))
    verification = verify_chain(database)
    assert verification["valid"] is False
    assert verification["broken_at"] == 1
