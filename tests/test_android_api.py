import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app import app, discovery_reply, SESSIONS
import db


@pytest.fixture
def client(tmp_path):
    test_db_path = tmp_path / "test_android_api.db"
    db.init(test_db_path)
    SESSIONS.clear()
    with TestClient(app) as tc:
        yield tc
    SESSIONS.clear()


def test_discovery_reply_match():
    assert discovery_reply(b"CALLPILOT_DISCOVER", 8001) == b"CALLPILOT 8001"
    assert discovery_reply(b"CALLPILOT_DISCOVER", 9000) == b"CALLPILOT 9000"


def test_discovery_reply_whitespace():
    assert discovery_reply(b"  CALLPILOT_DISCOVER  ", 8001) == b"CALLPILOT 8001"
    assert discovery_reply(b"\r\nCALLPILOT_DISCOVER\n", 8001) == b"CALLPILOT 8001"
    assert discovery_reply(b"\tCALLPILOT_DISCOVER\t", 8001) == b"CALLPILOT 8001"


def test_discovery_reply_wrong_msg():
    assert discovery_reply(b"", 8001) is None
    assert discovery_reply(b"CALLPILOT", 8001) is None
    assert discovery_reply(b"CALLPILOT_DISCOVER_MORE", 8001) is None
    assert discovery_reply(b"DISCOVER", 8001) is None
    assert discovery_reply(b"hello world", 8001) is None


def test_get_booking_404_unknown(client):
    res = client.get("/api/bookings/nonexistent-session")
    assert res.status_code == 404
    assert res.json() == {"detail": "Appointment not found"}


def test_get_booking_full_json_after_fake_demo_booking(client):
    start_res = client.post("/api/call/start", json={"config_id": "hospital_helpline", "use_fake": True})
    assert start_res.status_code == 200
    data = start_res.json()
    sid = data["session_id"]
    hints = data["hints"]

    last_res = None
    for hint in hints:
        turn_res = client.post(f"/api/call/{sid}/turn", json={"text": hint})
        assert turn_res.status_code == 200
        last_res = turn_res.json()

    assert last_res is not None
    assert last_res["state"] == "done"
    assert "booking_id" in last_res
    booking_id = last_res["booking_id"]

    res = client.get(f"/api/bookings/{sid}")
    assert res.status_code == 200
    booking = res.json()

    assert booking["session_id"] == sid
    assert booking["booking_id"] == booking_id
    assert booking["pdf_url"] == f"/api/bookings/{sid}/pdf"
    assert isinstance(booking["id"], int)
    assert booking["doctor"]
    assert booking["department"]
    assert booking["appointment_date"]
    assert booking["appointment_time"]
    assert booking["hospital_branch"]
    assert booking["patient_name"]
    assert booking["phone"]
    assert booking["age"]
    assert booking["gender"]
    assert booking["city_area"]
    assert booking["symptoms"]
    assert booking["created_at"]


def test_get_booking_direct_db(client):
    fields = {
        "doctor": "Dr. Kavita Rao",
        "department": "Orthopedics",
        "appointment_date": "2026-10-08",
        "appointment_time": "14:00",
        "hospital_branch": "City Centre",
        "patient_name": "Anita Verma",
        "phone": "9876543210",
        "age": 42,
        "gender": "female",
        "city_area": "Andheri",
        "symptoms": "shoulder pain",
    }
    row_id = db.book("sess-direct-test", fields)
    res = client.get("/api/bookings/sess-direct-test")
    assert res.status_code == 200
    data = res.json()
    assert data["session_id"] == "sess-direct-test"
    assert data["booking_id"] == f"HB-{row_id:04d}"
    assert data["pdf_url"] == "/api/bookings/sess-direct-test/pdf"
    assert data["doctor"] == "Dr. Kavita Rao"
    assert data["patient_name"] == "Anita Verma"
