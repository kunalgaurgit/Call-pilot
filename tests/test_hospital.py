import json
import sqlite3
import sys
from datetime import date, timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import agent
from app import app, SESSIONS
import db
from llm import FakeLLM


@pytest.fixture
def hospital_config():
    path = ROOT / "configs" / "hospital_helpline.json"
    return json.loads(path.read_text(encoding="utf-8"))


@pytest.fixture
def test_db(tmp_path):
    db_file = tmp_path / "test_hospital.db"
    db.init(db_file)
    return db_file


@pytest.fixture
def client(tmp_path):
    test_db_path = tmp_path / "test_app_hospital.db"
    db.init(test_db_path)
    SESSIONS.clear()
    with TestClient(app) as tc:
        yield tc
    SESSIONS.clear()


def test_doctor_slots_starts_tomorrow_respects_days_excludes_taken_caps(hospital_config):
    today = date(2026, 10, 6)  # Tuesday

    # 1. Starts tomorrow
    slots = agent.doctor_slots(hospital_config, today, frozenset(), "Orthopedics")
    assert len(slots) > 0
    for doc in slots:
        for slot in doc["slots"]:
            slot_d = date.fromisoformat(slot["date"])
            assert slot_d >= today + timedelta(days=1)
            assert slot_d <= today + timedelta(days=7)

    # 2. Respects days: Dr. Kavita Rao only works Tue, Thu, Sat
    kavita = next((s for s in slots if s["doctor"] == "Dr. Kavita Rao"), None)
    if kavita:
        for slot in kavita["slots"]:
            slot_d = date.fromisoformat(slot["date"])
            assert slot_d.strftime("%a") in ["Tue", "Thu", "Sat"]

    # 3. Excludes taken
    first_doc = slots[0]["doctor"]
    first_slot = slots[0]["slots"][0]
    taken = {(first_doc, first_slot["date"], first_slot["time"])}
    slots_after_taken = agent.doctor_slots(hospital_config, today, taken, "Orthopedics")
    first_doc_slots_after = next(s for s in slots_after_taken if s["doctor"] == first_doc)
    assert not any(
        s["date"] == first_slot["date"] and s["time"] == first_slot["time"]
        for s in first_doc_slots_after["slots"]
    )

    # 4. Caps 2 doctors x 3 slots
    all_dept_slots = agent.doctor_slots(hospital_config, today, frozenset(), department=None, max_doctors=2, max_slots=3)
    assert len(all_dept_slots) <= 2
    for doc in all_dept_slots:
        assert 1 <= len(doc["slots"]) <= 3


def test_after_gating_error_without_fail_count_increment(hospital_config):
    today = date(2026, 10, 6)
    ag = agent.Agent(hospital_config, FakeLLM([]), today=today)
    ag.greet()

    # Attempting to set department before symptoms
    fake = FakeLLM([
        {"calls": [{"name": "update_fields", "args": {"department": "Orthopedics"}}]},
        {"text": "Please provide symptoms first."},
        {"calls": [{"name": "update_fields", "args": {"department": "Orthopedics"}}]},
        {"text": "Please provide symptoms first."},
        {"calls": [{"name": "update_fields", "args": {"department": "Orthopedics"}}]},
        {"text": "Please provide symptoms first."},
    ])
    ag.llm = fake

    ag.turn("I want Orthopedics")
    assert "department" not in ag.fields
    assert ag.fail_count.get("department", 0) == 0

    ag.turn("Still Orthopedics")
    assert ag.fail_count.get("department", 0) == 0

    ag.turn("Please Orthopedics")
    assert ag.fail_count.get("department", 0) == 0
    assert ag.state != "escalated"

    tool_msg = next(m for m in reversed(ag.history) if m.get("role") == "tool")
    err = tool_msg["results"][0]["response"]["errors"]["department"]
    assert "Not yet. First get: Health problem." in err


def test_check_doctors_tool_result(hospital_config):
    today = date(2026, 10, 6)
    fake = FakeLLM([
        {"calls": [{"name": "check_doctors", "args": {"department": "Orthopedics"}}]},
        {"text": "Doctor Arjun Mehta is available."},
    ])
    ag = agent.Agent(hospital_config, fake, today=today)
    ag.greet()
    ag.turn("Check doctors for Orthopedics")

    tool_msg = next(m for m in reversed(ag.history) if m.get("role") == "tool")
    assert tool_msg["results"][0]["name"] == "check_doctors"
    tool_resp = tool_msg["results"][0]["response"]
    assert "doctors" in tool_resp
    assert len(tool_resp["doctors"]) > 0
    assert tool_resp["doctors"][0]["doctor"] == "Dr. Arjun Mehta"

    # Department with no slots returns error dict
    fake_empty = FakeLLM([
        {"calls": [{"name": "check_doctors", "args": {"department": "Neurology"}}]},
        {"text": "No slots."},
    ])
    ag_empty = agent.Agent(hospital_config, fake_empty, today=today)
    ag_empty.greet()
    ag_empty.turn("Check Neurology")
    tool_msg2 = next(m for m in reversed(ag_empty.history) if m.get("role") == "tool")
    assert tool_msg2["results"][0]["response"] == {"error": "No free slots in that department this week."}


def test_submit_books_via_hook_and_done_reply(hospital_config):
    today = date(2026, 10, 6)
    called_with = {}

    def mock_book(session_id, fields):
        called_with["session_id"] = session_id
        called_with["fields"] = dict(fields)
        return "HB-0042"

    ag = agent.Agent(hospital_config, FakeLLM([]), today=today, book=mock_book, taken=lambda: set())
    ag.fields = {
        "symptoms": "knee pain",
        "department": "Orthopedics",
        "doctor": "Dr. Arjun Mehta",
        "appointment_date": "2026-10-07",
        "appointment_time": "10:00",
        "patient_name": "Rahul Sharma",
        "phone": "9876543210",
        "age": 34,
        "gender": "male",
        "city_area": "Andheri",
        "hospital_branch": "City Centre",
    }
    ag.state = "confirming"
    ag.greet()

    fake = FakeLLM([
        {"calls": [{"name": "submit", "args": {"confirmed": True, "summary": "Booking for Rahul"}}]}
    ])
    ag.llm = fake

    res = ag.turn("Yes, that is correct")
    assert ag.state == "done"
    assert res["state"] == "done"
    assert called_with["session_id"] == ag.session_id
    assert ag.booking_id == "HB-0042"
    assert ag.record["booking_id"] == "HB-0042"

    reply = res["reply"]
    assert "HB-0042" in reply
    assert "Wednesday 7 October" in reply or "Wednesday 07 October" in reply
    assert "Dr. Arjun Mehta" in reply
    assert "City Centre" in reply


def test_book_raising_value_error_clears_slot_and_state_not_done(hospital_config):
    today = date(2026, 10, 6)

    def failing_book(session_id, fields):
        raise ValueError("Slot already booked")

    ag = agent.Agent(hospital_config, FakeLLM([]), today=today, book=failing_book, taken=lambda: set())
    ag.fields = {
        "symptoms": "knee pain",
        "department": "Orthopedics",
        "doctor": "Dr. Arjun Mehta",
        "appointment_date": "2026-10-07",
        "appointment_time": "10:00",
        "patient_name": "Rahul Sharma",
        "phone": "9876543210",
        "age": 34,
        "gender": "male",
        "city_area": "Andheri",
        "hospital_branch": "City Centre",
    }
    ag.state = "confirming"
    ag.greet()

    fake = FakeLLM([
        {"calls": [{"name": "submit", "args": {"confirmed": True}}]},
        {"text": "That slot is not available. Let me find another."}
    ])
    ag.llm = fake

    res = ag.turn("Confirm please")
    assert ag.state != "done"
    assert "appointment_date" not in ag.fields
    assert "appointment_time" not in ag.fields
    assert ag.fields["patient_name"] == "Rahul Sharma"

    tool_msg = next(m for m in reversed(ag.history) if m.get("role") == "tool")
    assert tool_msg["results"][0]["response"]["ok"] is False
    assert "That slot is not available" in tool_msg["results"][0]["response"]["error"]


def test_submit_with_slot_outside_schedule_rejected(hospital_config):
    today = date(2026, 10, 6)
    ag = agent.Agent(hospital_config, FakeLLM([]), today=today, taken=lambda: set())
    # 03:00 is outside Dr. Arjun Mehta's times
    ag.fields = {
        "symptoms": "knee pain",
        "department": "Orthopedics",
        "doctor": "Dr. Arjun Mehta",
        "appointment_date": "2026-10-07",
        "appointment_time": "03:00",
        "patient_name": "Rahul Sharma",
        "phone": "9876543210",
        "age": 34,
        "gender": "male",
        "city_area": "Andheri",
        "hospital_branch": "City Centre",
    }
    ag.state = "confirming"
    ag.greet()

    fake = FakeLLM([
        {"calls": [{"name": "submit", "args": {"confirmed": True}}]},
        {"text": "That slot is invalid."}
    ])
    ag.llm = fake

    ag.turn("Confirm booking")
    assert ag.state != "done"
    assert "appointment_date" not in ag.fields
    assert "appointment_time" not in ag.fields

    tool_msg = next(m for m in reversed(ag.history) if m.get("role") == "tool")
    assert tool_msg["results"][0]["response"]["ok"] is False
    assert "That slot is not available" in tool_msg["results"][0]["response"]["error"]


def test_emergency_phrase_escalates_without_llm_or_booking(hospital_config):
    booked = []
    ag = agent.Agent(
        hospital_config,
        FakeLLM([]),  # 0 replies: raises if LLM is called
        today=date(2026, 10, 6),
        book=lambda sid, f: booked.append(sid) or "HB-0001",
    )
    ag.greet()

    res = ag.turn("I am having severe chest pain and difficulty breathing")
    assert ag.state == "escalated"
    assert res["state"] == "escalated"
    assert res["reply"] == hospital_config["emergency_message"]
    assert ag.record is not None
    assert ag.record["status"] == "escalated"
    assert ag.record["escalation_reason"] == "medical emergency"
    assert len(booked) == 0
    assert getattr(ag, "booking_id", None) is None


def test_hangup_zero_appointment_rows(hospital_config, test_db):
    ag = agent.Agent(
        hospital_config,
        FakeLLM([]),
        today=date(2026, 10, 6),
        book=lambda sid, f: f"HB-{db.book(sid, f):04d}",
        taken=db.taken_slots,
    )
    ag.greet()
    rec = ag.hangup()
    assert rec["status"] == "abandoned"
    db.save(rec)

    with sqlite3.connect(test_db) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM appointments")
        count = cursor.fetchone()[0]
        assert count == 0


def test_db_book_idempotent_and_slot_taken(test_db):
    fields = {
        "doctor": "Dr. Arjun Mehta",
        "department": "Orthopedics",
        "appointment_date": "2026-10-07",
        "appointment_time": "10:00",
        "hospital_branch": "City Centre",
        "patient_name": "Rahul",
        "phone": "9876543210",
        "age": 30,
        "gender": "male",
        "city_area": "Andheri",
        "symptoms": "knee pain",
    }

    # Book first time
    id1 = db.book("sess-1", fields)
    assert isinstance(id1, int)
    assert id1 > 0

    # Idempotent per session
    id2 = db.book("sess-1", fields)
    assert id2 == id1

    # Conflict on slot uniqueness with another session
    fields2 = dict(fields, patient_name="Amit")
    with pytest.raises(db.SlotTaken):
        db.book("sess-2", fields2)

    # taken_slots returns the slot
    taken = db.taken_slots()
    assert ("Dr. Arjun Mehta", "2026-10-07", "10:00") in taken

    # get_appointment returns record
    appt = db.get_appointment("sess-1")
    assert appt is not None
    assert appt["patient_name"] == "Rahul"
    assert appt["doctor"] == "Dr. Arjun Mehta"


def test_api_fake_demo_run_twice_different_slots(client):
    # Run 1
    start_res1 = client.post("/api/call/start", json={"config_id": "hospital_helpline", "use_fake": True})
    assert start_res1.status_code == 200
    data1 = start_res1.json()
    sid1 = data1["session_id"]
    hints1 = data1["hints"]

    last_res1 = None
    for hint in hints1:
        turn_res = client.post(f"/api/call/{sid1}/turn", json={"text": hint})
        assert turn_res.status_code == 200
        last_res1 = turn_res.json()

    assert last_res1 is not None
    assert last_res1["state"] == "done"
    assert "booking_id" in last_res1
    booking_id_1 = last_res1["booking_id"]
    appt1 = db.get_appointment(sid1)
    assert appt1 is not None
    slot1 = (appt1["doctor"], appt1["appointment_date"], appt1["appointment_time"])

    # Run 2
    start_res2 = client.post("/api/call/start", json={"config_id": "hospital_helpline", "use_fake": True})
    assert start_res2.status_code == 200
    data2 = start_res2.json()
    sid2 = data2["session_id"]
    hints2 = data2["hints"]

    last_res2 = None
    for hint in hints2:
        turn_res = client.post(f"/api/call/{sid2}/turn", json={"text": hint})
        assert turn_res.status_code == 200
        last_res2 = turn_res.json()

    assert last_res2 is not None
    assert last_res2["state"] == "done"
    assert "booking_id" in last_res2
    booking_id_2 = last_res2["booking_id"]
    appt2 = db.get_appointment(sid2)
    assert appt2 is not None
    slot2 = (appt2["doctor"], appt2["appointment_date"], appt2["appointment_time"])

    assert booking_id_1 != booking_id_2
    assert slot1 != slot2


def test_pdf_endpoint(client):
    res_404 = client.get("/api/bookings/nonexistent-session/pdf")
    assert res_404.status_code == 404

    fields = {
        "doctor": "Dr. Arjun Mehta",
        "department": "Orthopedics",
        "appointment_date": "2026-10-08",
        "appointment_time": "11:30",
        "hospital_branch": "City Centre",
        "patient_name": "राहुल शर्मा (René)",
        "phone": "9876543210",
        "age": 34,
        "gender": "male",
        "city_area": "Andheri",
        "symptoms": "knee pain",
    }
    db.book("sess-pdf-test", fields)

    res_pdf = client.get("/api/bookings/sess-pdf-test/pdf")
    assert res_pdf.status_code == 200
    assert "application/pdf" in res_pdf.headers["content-type"]
    assert res_pdf.content.startswith(b"%PDF")
