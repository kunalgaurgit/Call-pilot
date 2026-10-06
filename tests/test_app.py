import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import db
from app import app, SESSIONS, mask


@pytest.fixture
def client(tmp_path):
    test_db = tmp_path / "test_app.db"
    db.init(test_db)
    SESSIONS.clear()
    with TestClient(app) as tc:
        yield tc
    SESSIONS.clear()


def test_status(client):
    res = client.get("/api/status")
    assert res.status_code == 200
    data = res.json()
    assert "mode" in data
    assert "model" in data
    assert data["mode"] in ("fake", "gemini")


def test_configs(client):
    res = client.get("/api/configs")
    assert res.status_code == 200
    configs = res.json()
    assert isinstance(configs, list)
    config_ids = {c["id"] for c in configs}
    assert "salon_booking" in config_ids
    assert "hospital_helpline" in config_ids
    for item in configs:
        assert "id" in item
        assert "business" in item
        assert "purpose" in item


def test_start_call_unknown_config(client):
    res = client.post("/api/call/start", json={"config_id": "nonexistent_config"})
    assert res.status_code == 404
    assert res.json()["detail"] == "Unknown config"


def test_start_call_success(client):
    res = client.post("/api/call/start", json={"config_id": "salon_booking", "use_fake": True})
    assert res.status_code == 200
    data = res.json()
    assert "session_id" in data
    assert "greeting" in data
    assert "consent_notice" in data
    assert data["business"] == "Glow Salon"
    assert data["mode"] == "fake"
    assert isinstance(data["hints"], list)
    assert len(data["hints"]) > 0


def test_turn_unknown_session(client):
    res = client.post("/api/call/unknown-session-12345/turn", json={"text": "hello"})
    assert res.status_code == 404
    assert res.json()["detail"] == "Session not found"


def test_turn_empty_text_400(client):
    start_res = client.post("/api/call/start", json={"config_id": "salon_booking", "use_fake": True})
    sid = start_res.json()["session_id"]

    res_empty = client.post(f"/api/call/{sid}/turn", json={"text": ""})
    assert res_empty.status_code == 400
    assert "Text must be between 1 and 500 characters" in res_empty.json()["detail"]

    res_whitespace = client.post(f"/api/call/{sid}/turn", json={"text": "   \n\t  "})
    assert res_whitespace.status_code == 400
    assert "Text must be between 1 and 500 characters" in res_whitespace.json()["detail"]


def test_turn_too_long_text_400(client):
    start_res = client.post("/api/call/start", json={"config_id": "salon_booking", "use_fake": True})
    sid = start_res.json()["session_id"]

    res_long = client.post(f"/api/call/{sid}/turn", json={"text": "a" * 501})
    assert res_long.status_code == 400
    assert "Text must be between 1 and 500 characters" in res_long.json()["detail"]


def test_full_salon_fake_call_through_http(client):
    start_res = client.post("/api/call/start", json={"config_id": "salon_booking", "use_fake": True})
    assert start_res.status_code == 200
    start_data = start_res.json()
    sid = start_data["session_id"]
    hints = start_data["hints"]
    assert len(hints) > 0

    last_res = None
    for hint in hints:
        turn_res = client.post(f"/api/call/{sid}/turn", json={"text": hint})
        assert turn_res.status_code == 200
        last_res = turn_res.json()

    assert last_res is not None
    assert last_res["state"] == "done"
    assert last_res["record"] is not None

    record_id = last_res["record_id"]
    assert isinstance(record_id, int)
    assert record_id > 0

    # Masked in turn response
    masked_turn_record = last_res["record"]
    assert masked_turn_record["fields"]["phone"] == "******3210"
    assert "9876543210" not in masked_turn_record["fields"]["phone"]

    # Session dropped after completion
    after_res = client.post(f"/api/call/{sid}/turn", json={"text": "Are you still there?"})
    assert after_res.status_code == 404

    # Masked in GET /api/records
    records_res = client.get("/api/records")
    assert records_res.status_code == 200
    records = records_res.json()
    matching = [r for r in records if r["id"] == record_id]
    assert len(matching) == 1
    rec_from_list = matching[0]
    assert rec_from_list["fields"]["phone"] == "******3210"
    assert "******3210" in rec_from_list["summary"]
    assert "9876543210" not in rec_from_list["fields"]["phone"]
    assert "9876543210" not in rec_from_list["summary"]

    # Masked in GET /api/records/{id}
    rec_by_id_res = client.get(f"/api/records/{record_id}")
    assert rec_by_id_res.status_code == 200
    rec_by_id = rec_by_id_res.json()
    assert rec_by_id["fields"]["phone"] == "******3210"
    assert "9876543210" not in rec_by_id["fields"]["phone"]

    # Raw phone in db.get(record_id)
    raw_db_record = db.get(record_id)
    assert raw_db_record is not None
    assert raw_db_record["fields"]["phone"] == "9876543210"


def test_hangup_abandoned(client):
    start_res = client.post("/api/call/start", json={"config_id": "salon_booking", "use_fake": True})
    sid = start_res.json()["session_id"]

    hangup_res = client.post(f"/api/call/{sid}/hangup")
    assert hangup_res.status_code == 200
    assert hangup_res.json() == {"ok": True}

    # Session dropped
    turn_res = client.post(f"/api/call/{sid}/turn", json={"text": "hello"})
    assert turn_res.status_code == 404

    # Abandoned record saved to DB and retrievable via /api/records
    records_res = client.get("/api/records")
    records = records_res.json()
    abandoned = [r for r in records if r["session_id"] == sid]
    assert len(abandoned) == 1
    assert abandoned[0]["status"] == "abandoned"


def test_hangup_unknown_session(client):
    res = client.post("/api/call/nonexistent-session/hangup")
    assert res.status_code == 200
    assert res.json() == {"ok": True}


def test_escalation_phrase_via_api(client):
    start_res = client.post("/api/call/start", json={"config_id": "salon_booking", "use_fake": True})
    sid = start_res.json()["session_id"]

    turn_res = client.post(f"/api/call/{sid}/turn", json={"text": "I want to talk to a human"})
    assert turn_res.status_code == 200
    data = turn_res.json()
    assert data["state"] == "escalated"
    assert data["record"] is not None
    assert data["record"]["status"] == "escalated"
    assert data["record_id"] is not None

    # Session dropped
    next_res = client.post(f"/api/call/{sid}/turn", json={"text": "hello"})
    assert next_res.status_code == 404

    # Escalated record in db
    db_rec = db.get(data["record_id"])
    assert db_rec is not None
    assert db_rec["status"] == "escalated"
    assert db_rec["escalation_reason"] == "customer asked for a human"


def test_get_record_not_found(client):
    res = client.get("/api/records/999999")
    assert res.status_code == 404
    assert res.json()["detail"] == "Record not found"


def test_records_business_filter(client):
    rec1 = {
        "session_id": "s-salon",
        "business_id": "salon_booking",
        "status": "completed",
        "fields": {},
        "summary": "Salon summary",
    }
    rec2 = {
        "session_id": "s-hospital",
        "business_id": "hospital_helpline",
        "status": "completed",
        "fields": {},
        "summary": "Hospital summary",
    }
    db.save(rec1)
    db.save(rec2)

    salon_res = client.get("/api/records", params={"business_id": "salon_booking"})
    assert salon_res.status_code == 200
    salon_records = salon_res.json()
    assert len(salon_records) == 1
    assert salon_records[0]["business_id"] == "salon_booking"

    hospital_res = client.get("/api/records", params={"business_id": "hospital_helpline"})
    assert hospital_res.status_code == 200
    hospital_records = hospital_res.json()
    assert len(hospital_records) == 1
    assert hospital_records[0]["business_id"] == "hospital_helpline"


def test_hospital_fake_call_through_http(client):
    start_res = client.post("/api/call/start", json={"config_id": "hospital_helpline", "use_fake": True})
    assert start_res.status_code == 200
    data = start_res.json()
    sid = data["session_id"]
    hints = data["hints"]
    assert len(hints) > 0

    last_res = None
    for hint in hints:
        turn_res = client.post(f"/api/call/{sid}/turn", json={"text": hint})
        assert turn_res.status_code == 200
        last_res = turn_res.json()

    assert last_res is not None
    assert last_res["state"] == "done"
    assert last_res["record"] is not None
    assert last_res["record"]["status"] == "completed"
    assert last_res["record"]["business_id"] == "hospital_helpline"


def test_mask_helper():
    assert mask(None) is None
    assert mask("string") == "string"

    record = {
        "fields": {"phone": "9876543210", "name": "Priya"},
        "summary": "Call from 9876543210 confirmed",
        "escalation_reason": "customer 9876543210 requested staff",
        "transcript": [{"role": "customer", "text": "My phone is 9876543210."}],
    }
    masked = mask(record)
    assert masked["fields"]["phone"] == "******3210"
    assert masked["fields"]["name"] == "Priya"
    assert masked["summary"] == "Call from ******3210 confirmed"
    assert masked["escalation_reason"] == "customer ******3210 requested staff"
    assert masked["transcript"][0]["text"] == "My phone is ******3210."

    # Original record remains untouched
    assert record["fields"]["phone"] == "9876543210"


def test_mask_escalation_reason():
    """mask() masks phone numbers in escalation_reason and preserves None."""
    rec = {"escalation_reason": "Customer called from 9876543210"}
    masked = mask(rec)
    assert masked["escalation_reason"] == "Customer called from ******3210"

    rec_dash = {"escalation_reason": "Escalate to 9876-543-210"}
    masked_dash = mask(rec_dash)
    assert masked_dash["escalation_reason"] == "Escalate to ******3210"

    rec_none = {"escalation_reason": None}
    assert mask(rec_none)["escalation_reason"] is None


def test_records_masked_escalation_reason(client):
    """GET /api/records/{id} returns masked escalation_reason."""
    rec = {
        "session_id": "s-esc",
        "business_id": "salon_booking",
        "status": "escalated",
        "fields": {"phone": "9876543210"},
        "summary": "Escalated for 9876543210",
        "escalation_reason": "customer 9876543210 asked for human",
        "transcript": [],
    }
    rec_id = db.save(rec)
    res = client.get(f"/api/records/{rec_id}")
    assert res.status_code == 200
    data = res.json()
    assert data["fields"]["phone"] == "******3210"
    assert data["summary"] == "Escalated for ******3210"
    assert data["escalation_reason"] == "customer ******3210 asked for human"
