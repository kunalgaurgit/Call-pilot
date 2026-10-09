import json
import sys
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
def ai_doctor_config():
    path = ROOT / "configs" / "ai_doctor.json"
    return json.loads(path.read_text(encoding="utf-8"))


@pytest.fixture
def test_db(tmp_path):
    db_file = tmp_path / "test_ai_doctor.db"
    db.init(db_file)
    return db_file


@pytest.fixture
def client(tmp_path):
    test_db_path = tmp_path / "test_app_ai_doctor.db"
    db.init(test_db_path)
    SESSIONS.clear()
    with TestClient(app) as tc:
        yield tc
    SESSIONS.clear()


@pytest.mark.parametrize(
    "case_name,fields,expected_status,reason_keyword,expected_med_names,excluded_med_names",
    [
        (
            "minor_ok",
            {
                "condition": "headache",
                "symptoms": "mild headache",
                "duration_days": 1,
                "severity": "mild",
                "patient_name": "Rahul",
                "age": 28,
                "gender": "male",
                "allergies": "none",
                "pregnant": "no",
            },
            "ok",
            None,
            ["Paracetamol"],
            [],
        ),
        (
            "severe",
            {
                "condition": "headache",
                "symptoms": "severe headache",
                "duration_days": 1,
                "severity": "severe",
                "patient_name": "Rahul",
                "age": 28,
                "gender": "male",
                "allergies": "none",
            },
            "referred",
            "severe",
            [],
            [],
        ),
        (
            "child_under_12",
            {
                "condition": "headache",
                "symptoms": "headache",
                "duration_days": 1,
                "severity": "mild",
                "patient_name": "Child",
                "age": 8,
                "gender": "male",
                "allergies": "none",
            },
            "referred",
            "12",
            [],
            [],
        ),
        (
            "over_max_days",
            {
                "condition": "headache",
                "symptoms": "headache",
                "duration_days": 5,
                "severity": "mild",
                "patient_name": "Rahul",
                "age": 28,
                "gender": "male",
                "allergies": "none",
            },
            "referred",
            "days",
            [],
            [],
        ),
        (
            "allergy_drops_only_med",
            {
                "condition": "fever",
                "symptoms": "fever",
                "duration_days": 1,
                "severity": "mild",
                "patient_name": "Rahul",
                "age": 28,
                "gender": "male",
                "allergies": "paracetamol",
            },
            "referred",
            "allerg",
            [],
            [],
        ),
        (
            "pregnancy_drops_avoid_pregnant_med",
            {
                "condition": "muscle_pain",
                "symptoms": "muscle sprain",
                "duration_days": 2,
                "severity": "mild",
                "patient_name": "Priya",
                "age": 26,
                "gender": "female",
                "pregnant": "yes",
                "allergies": "none",
            },
            "ok",
            None,
            ["Paracetamol"],
            ["Ibuprofen"],
        ),
        (
            "pregnancy_referred_when_no_safe_meds_remain",
            {
                "condition": "muscle_pain",
                "symptoms": "muscle sprain",
                "duration_days": 2,
                "severity": "mild",
                "patient_name": "Priya",
                "age": 26,
                "gender": "female",
                "pregnant": "yes",
                "allergies": "paracetamol",
            },
            "referred",
            "pregnancy",
            [],
            [],
        ),
        (
            "unknown_condition",
            {
                "condition": "fracture",
                "symptoms": "broken bone",
                "duration_days": 1,
                "severity": "mild",
                "patient_name": "Rahul",
                "age": 28,
                "gender": "male",
                "allergies": "none",
            },
            "referred",
            "formulary",
            [],
            [],
        ),
    ],
)
def test_build_rx_table_driven(
    ai_doctor_config, case_name, fields, expected_status, reason_keyword, expected_med_names, excluded_med_names
):
    rx = agent.build_rx(ai_doctor_config, fields)
    assert rx["status"] == expected_status
    if expected_status == "ok":
        assert "condition" in rx
        assert "spoken" in rx and len(rx["spoken"]) > 0
        med_names = [m["name"] for m in rx.get("medicines", [])]
        for name in expected_med_names:
            assert name in med_names
        for name in excluded_med_names:
            assert name not in med_names
    else:
        assert "reason" in rx
        if reason_keyword:
            assert reason_keyword.lower() in rx["reason"].lower()


def test_agent_submit_creates_rx_and_booking_id(ai_doctor_config):
    fake = FakeLLM([
        {
            "calls": [
                {
                    "name": "update_fields",
                    "args": {
                        "symptoms": "headache",
                        "duration_days": 1,
                        "severity": "mild",
                    },
                }
            ],
        },
        {"text": "Could you provide your name, age, gender, and any allergies?"},
        {
            "calls": [
                {
                    "name": "update_fields",
                    "args": {
                        "patient_name": "Rahul Sharma",
                        "age": 28,
                        "gender": "male",
                        "allergies": "none",
                        "condition": "headache",
                    },
                }
            ],
        },
        {"text": "I can prepare a prescription for tension headache. Shall I prepare your prescription?"},
        {
            "calls": [
                {
                    "name": "submit",
                    "args": {
                        "confirmed": True,
                        "summary": "Rahul Sharma (28, male) - Tension Headache. Symptoms: headache (1 days, mild).",
                    },
                }
            ]
        },
    ])
    ag = agent.Agent(ai_doctor_config, fake, session_id="test-submit-sess-12345")
    ag.greet()

    res1 = ag.turn("I have a mild headache since yesterday.")
    assert res1["state"] == "collecting"

    res2 = ag.turn("My name is Rahul Sharma, 28, male, no allergies.")
    assert res2["state"] == "confirming"

    res3 = ag.turn("Yes, please prepare it.")
    assert res3["state"] == "done"
    assert ag.state == "done"
    assert ag.record is not None
    assert ag.record["status"] == "completed"
    assert ag.record["booking_id"].startswith("RX-")
    assert ag.rx_id == ag.record["booking_id"]
    assert ag.rx_id.startswith("RX-")
    assert "rx" in ag.record
    assert ag.record["rx"]["status"] == "ok"
    assert ag.record["rx"]["condition"] == "Tension Headache"
    assert len(ag.record["rx"]["medicines"]) > 0
    assert ag.rx_id in res3["reply"]
    assert "AI demo" in res3["reply"]


def test_agent_escalate_referral(ai_doctor_config):
    fake = FakeLLM([
        {
            "calls": [
                {
                    "name": "escalate",
                    "args": {"reason": "referral: severe pain requiring immediate physician examination"},
                }
            ]
        }
    ])
    ag = agent.Agent(ai_doctor_config, fake, session_id="test-referral-sess")
    ag.greet()

    res = ag.turn("I have unbearable pain and cannot walk.")
    assert res["state"] == "escalated"
    assert ag.state == "escalated"
    assert ag.record is not None
    assert ag.record["status"] == "referred"
    assert ag.record["escalation_reason"] == "referral: severe pain requiring immediate physician examination"
    assert "Referred to doctor" in ag.record["summary"]
    assert "108" not in res["reply"]
    assert "108" not in ag.record["summary"]
    assert res["reply"] == ai_doctor_config["referral_message"]


def test_agent_submit_referred_on_severe_symptoms(ai_doctor_config):
    fake = FakeLLM([
        {
            "calls": [
                {
                    "name": "update_fields",
                    "args": {
                        "symptoms": "headache",
                        "duration_days": 1,
                        "severity": "severe",
                        "patient_name": "Rahul Sharma",
                        "age": 28,
                        "gender": "male",
                        "allergies": "none",
                        "condition": "headache",
                    },
                }
            ],
        },
        {"text": "Shall I proceed?"},
        {
            "calls": [
                {
                    "name": "submit",
                    "args": {"confirmed": True, "summary": "Rahul Sharma (28, male) - Severe headache."},
                }
            ]
        },
    ])
    ag = agent.Agent(ai_doctor_config, fake, session_id="test-severe-submit-sess")
    ag.greet()
    ag.turn("My head hurts severely.")
    res = ag.turn("Yes proceed")
    assert res["state"] == "escalated"
    assert ag.record["status"] == "referred"
    assert "108" not in res["reply"]
    assert "doctor" in res["reply"].lower()


def test_fake_llm_demo_end_to_end_and_pdf(client):
    # 1. Start call using FakeLLM demo mode with ai_doctor config
    start_res = client.post("/api/call/start", json={"config_id": "ai_doctor", "use_fake": True})
    assert start_res.status_code == 200
    start_data = start_res.json()
    sid = start_data["session_id"]
    hints = start_data["hints"]
    assert len(hints) == 3

    # 2. Replay demo turns
    last_turn_res = None
    for hint in hints:
        turn_res = client.post(f"/api/call/{sid}/turn", json={"text": hint})
        assert turn_res.status_code == 200
        last_turn_res = turn_res.json()

    # 3. Final turn asserts: state done, booking_id starts with RX-, pdf_url is /api/prescriptions/{sid}/pdf
    assert last_turn_res is not None
    assert last_turn_res["state"] == "done"
    assert last_turn_res["booking_id"].startswith("RX-")
    rx_id = last_turn_res["booking_id"]
    assert last_turn_res["pdf_url"] == f"/api/prescriptions/{sid}/pdf"
    assert "rx" in last_turn_res
    assert last_turn_res["rx"]["status"] == "ok"
    assert last_turn_res["rx"]["condition"] == "Tension Headache"

    # 4. GET /api/prescriptions/{sid}/pdf -> 200 application/pdf
    pdf_res = client.get(f"/api/prescriptions/{sid}/pdf")
    assert pdf_res.status_code == 200
    assert "application/pdf" in pdf_res.headers["content-type"]
    assert pdf_res.content.startswith(b"%PDF")
    assert f'filename="{rx_id}.pdf"' in pdf_res.headers.get("content-disposition", "")

    # Also stacked route GET /api/bookings/{sid}/pdf works
    booking_pdf_res = client.get(f"/api/bookings/{sid}/pdf")
    assert booking_pdf_res.status_code == 200
    assert "application/pdf" in booking_pdf_res.headers["content-type"]
    assert booking_pdf_res.content.startswith(b"%PDF")

    # 5. GET /api/bookings/{sid} fallback JSON has booking_id RX-
    booking_res = client.get(f"/api/bookings/{sid}")
    assert booking_res.status_code == 200
    booking_data = booking_res.json()
    assert booking_data["session_id"] == sid
    assert booking_data["booking_id"] == rx_id
    assert booking_data["booking_id"].startswith("RX-")
    assert booking_data["patient_name"] == "Rahul Sharma"
    assert booking_data["pdf_url"] == f"/api/prescriptions/{sid}/pdf"
    assert "rx" in booking_data
    assert booking_data["rx"]["status"] == "ok"

    # Also stacked route GET /api/prescriptions/{sid} returns the same JSON
    prescription_json_res = client.get(f"/api/prescriptions/{sid}")
    assert prescription_json_res.status_code == 200
    assert prescription_json_res.json()["booking_id"] == rx_id

    # 6. GET pdf for unknown session -> 404
    unknown_pdf_res = client.get("/api/prescriptions/nonexistent-session-id/pdf")
    assert unknown_pdf_res.status_code == 404

    unknown_booking_pdf = client.get("/api/bookings/nonexistent-session-id/pdf")
    assert unknown_booking_pdf.status_code == 404

    # 7. GET pdf for referred session -> 404
    ref_sid = "sess-referred-test-404"
    db.save({
        "session_id": ref_sid,
        "business_id": "ai_doctor",
        "business": "AI Doctor",
        "status": "referred",
        "summary": "Referred to doctor: severe symptoms",
        "escalation_reason": "referral: severe symptoms",
        "fields": {
            "patient_name": "Test Patient",
            "symptoms": "chest pain",
            "severity": "severe",
        },
    })

    ref_pdf_res = client.get(f"/api/prescriptions/{ref_sid}/pdf")
    assert ref_pdf_res.status_code == 404

    ref_booking_pdf_res = client.get(f"/api/bookings/{ref_sid}/pdf")
    assert ref_booking_pdf_res.status_code == 404

    ref_booking_json = client.get(f"/api/bookings/{ref_sid}")
    assert ref_booking_json.status_code == 404
