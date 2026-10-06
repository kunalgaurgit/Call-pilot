import json
import re
import sys
from datetime import date
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import agent
from llm import FakeLLM


@pytest.fixture
def salon_config():
    path = ROOT / "configs" / "salon_booking.json"
    return json.loads(path.read_text(encoding="utf-8"))


@pytest.fixture
def hospital_config():
    path = ROOT / "configs" / "hospital_helpline.json"
    return json.loads(path.read_text(encoding="utf-8"))


# --- validate() tests ---


@pytest.mark.parametrize(
    "field,value,today,expected_ok,expected_val",
    [
        # text: non-empty
        ({"name": "name", "type": "text"}, "  Alice  ", date(2026, 10, 6), True, "Alice"),
        ({"name": "name", "type": "text"}, "", date(2026, 10, 6), False, None),
        ({"name": "name", "type": "text"}, "   ", date(2026, 10, 6), False, None),
        # text with pattern: normalize = upper-case + remove spaces, fullmatch
        (
            {"name": "tracking_id", "type": "text", "pattern": r"^[A-Z]{2}[0-9]{8}$"},
            "  ss 1234 5678  ",
            date(2026, 10, 6),
            True,
            "SS12345678",
        ),
        (
            {"name": "tracking_id", "type": "text", "pattern": r"^[A-Z]{2}[0-9]{8}$"},
            "invalid_id",
            date(2026, 10, 6),
            False,
            None,
        ),
        # phone: keep digits; 12 starting 91 -> drop 91; 11 starting 0 -> drop 0; must match [6-9]\d{9}
        ({"name": "phone", "type": "phone"}, "9876543210", date(2026, 10, 6), True, "9876543210"),
        ({"name": "phone", "type": "phone"}, "+91 98765 43210", date(2026, 10, 6), True, "9876543210"),
        ({"name": "phone", "type": "phone"}, "09876543210", date(2026, 10, 6), True, "9876543210"),
        ({"name": "phone", "type": "phone"}, "12345", date(2026, 10, 6), False, None),
        ({"name": "phone", "type": "phone"}, "5876543210", date(2026, 10, 6), False, None),
        ({"name": "phone", "type": "phone"}, "987654321099", date(2026, 10, 6), False, None),
        # date: >= today, normalized ISO string
        ({"name": "date", "type": "date"}, "2026-10-06", date(2026, 10, 6), True, "2026-10-06"),
        ({"name": "date", "type": "date"}, "2026-10-07", date(2026, 10, 6), True, "2026-10-07"),
        ({"name": "date", "type": "date"}, "2026-10-05", date(2026, 10, 6), False, None),
        ({"name": "date", "type": "date"}, "bad-date", date(2026, 10, 6), False, None),
        # time: normalized HH:MM, min/max bounds
        (
            {"name": "time", "type": "time", "min": "10:00", "max": "20:00"},
            "10:00",
            date(2026, 10, 6),
            True,
            "10:00",
        ),
        (
            {"name": "time", "type": "time", "min": "10:00", "max": "20:00"},
            "17:00:00",
            date(2026, 10, 6),
            True,
            "17:00",
        ),
        (
            {"name": "time", "type": "time", "min": "10:00", "max": "20:00"},
            "09:30",
            date(2026, 10, 6),
            False,
            None,
        ),
        (
            {"name": "time", "type": "time", "min": "10:00", "max": "20:00"},
            "20:30",
            date(2026, 10, 6),
            False,
            None,
        ),
        ({"name": "time", "type": "time"}, "14:15", date(2026, 10, 6), True, "14:15"),
        ({"name": "time", "type": "time"}, "bad-time", date(2026, 10, 6), False, None),
        # enum: case-insensitive -> canonical
        (
            {"name": "service", "type": "enum", "enum": ["haircut", "hair colour", "facial"]},
            "Haircut",
            date(2026, 10, 6),
            True,
            "haircut",
        ),
        (
            {"name": "service", "type": "enum", "enum": ["haircut", "hair colour", "facial"]},
            "  HAIR COLOUR  ",
            date(2026, 10, 6),
            True,
            "hair colour",
        ),
        (
            {"name": "service", "type": "enum", "enum": ["haircut", "hair colour", "facial"]},
            "massage",
            date(2026, 10, 6),
            False,
            None,
        ),
        # int: int(), optional min/max
        ({"name": "count", "type": "int", "min": 1, "max": 10}, "5", date(2026, 10, 6), True, 5),
        ({"name": "count", "type": "int", "min": 1, "max": 10}, "0", date(2026, 10, 6), False, None),
        ({"name": "count", "type": "int", "min": 1, "max": 10}, "11", date(2026, 10, 6), False, None),
        ({"name": "count", "type": "int"}, "not-an-int", date(2026, 10, 6), False, None),
    ],
)
def test_validate(field, value, today, expected_ok, expected_val):
    ok, result = agent.validate(field, value, today)
    assert ok is expected_ok
    if expected_ok:
        assert result == expected_val
    else:
        assert isinstance(result, str)
        assert len(result) > 0


def test_validate_enum_error_lists_options():
    field = {"name": "service", "type": "enum", "enum": ["haircut", "facial"]}
    ok, msg = agent.validate(field, "massage", date(2026, 10, 6))
    assert ok is False
    assert "haircut" in msg and "facial" in msg


# --- tool_specs() and system_prompt() tests ---


def test_tool_specs_schema_and_keys(salon_config):
    ag = agent.Agent(salon_config, FakeLLM([]))
    specs = ag.tool_specs()
    assert len(specs) == 3
    tool_map = {t["name"]: t for t in specs}
    assert set(tool_map.keys()) == {"update_fields", "submit", "escalate"}

    def check_no_forbidden_keys(node):
        if isinstance(node, dict):
            for k in ("enum", "pattern", "format"):
                assert k not in node, f"Forbidden key '{k}' found in tool spec"
            for v in node.values():
                check_no_forbidden_keys(v)
        elif isinstance(node, list):
            for item in node:
                check_no_forbidden_keys(item)

    check_no_forbidden_keys(specs)

    # update_fields: one property per config field, all string, none required
    uf = tool_map["update_fields"]["parameters"]
    config_field_names = {f["name"] for f in salon_config["fields"]}
    assert set(uf["properties"].keys()) == config_field_names
    for prop in uf["properties"].values():
        assert prop["type"] == "string"
    assert uf.get("required", []) == []

    # submit: confirmed boolean required
    sub = tool_map["submit"]["parameters"]
    assert "confirmed" in sub["required"]
    assert sub["properties"]["confirmed"]["type"] == "boolean"

    # escalate: reason string required
    esc = tool_map["escalate"]["parameters"]
    assert "reason" in esc["required"]
    assert esc["properties"]["reason"]["type"] == "string"


def test_system_prompt(salon_config):
    today = date(2026, 10, 6)
    ag = agent.Agent(salon_config, FakeLLM([]), today=today)
    prompt = ag.system_prompt()
    assert salon_config["business"] in prompt
    assert salon_config["purpose"] in prompt
    assert salon_config["tone"] in prompt
    assert "submit" in prompt
    assert "2026-10-06" in prompt
    for field in salon_config["fields"]:
        assert field["label"] in prompt


# --- greet(), hangup(), and turn() flow tests ---


def test_greet(salon_config):
    ag = agent.Agent(salon_config, FakeLLM([]))
    greeting = ag.greet()
    assert greeting == salon_config["greeting"]
    assert len(ag.transcript) == 1
    assert ag.transcript[0] == {"role": "agent", "text": salon_config["greeting"]}


def test_escalation_phrase_without_llm(salon_config):
    # FakeLLM([]) with 0 replies ensures no LLM call is made (would fail if called)
    ag = agent.Agent(salon_config, FakeLLM([]))
    ag.greet()
    res = ag.turn("I want to speak with a human please")
    assert res["state"] == "escalated"
    assert res["reply"] == salon_config["escalation_message"]
    assert res["record"] is not None
    assert res["record"]["status"] == "escalated"
    assert res["record"]["escalation_reason"] == "customer asked for a human"
    assert ag.state == "escalated"


def test_escalation_phrase_word_boundary(salon_config):
    # 'humanity' should not match 'human' with word boundaries
    fake = FakeLLM([{"text": "Hello, how can I help?"}])
    ag = agent.Agent(salon_config, fake)
    ag.greet()
    res = ag.turn("I care about humanity")
    assert res["state"] == "collecting"
    assert fake.calls == 1


def test_max_turns_escalates(salon_config):
    cfg = dict(salon_config, max_turns=2)
    fake = FakeLLM([
        {"text": "What is your name?"},
        {"text": "What is your phone?"},
    ])
    ag = agent.Agent(cfg, fake)
    ag.greet()
    res1 = ag.turn("Turn 1")
    assert res1["state"] == "collecting"
    assert fake.calls == 1

    res2 = ag.turn("Turn 2")
    assert res2["state"] == "collecting"
    assert fake.calls == 2

    # Turn 3 exceeds max_turns (2) -> escalate without LLM call
    res3 = ag.turn("Turn 3")
    assert res3["state"] == "escalated"
    assert fake.calls == 2
    assert res3["record"]["status"] == "escalated"
    assert res3["record"]["escalation_reason"] == "turn limit reached"


def test_two_failures_on_same_field_escalates(salon_config):
    fake = FakeLLM([
        {"calls": [{"name": "update_fields", "args": {"phone": "12345"}}]},
        {"text": "Please provide a valid 10-digit number."},
        {"calls": [{"name": "update_fields", "args": {"phone": "555"}}]},
    ])
    ag = agent.Agent(salon_config, fake)
    ag.greet()
    res1 = ag.turn("My phone is 12345")
    assert res1["state"] == "collecting"

    res2 = ag.turn("My phone is 555")
    assert res2["state"] == "escalated"
    assert res2["record"]["status"] == "escalated"
    assert "could not validate Mobile number" in res2["record"]["escalation_reason"]


def test_submit_before_confirmation_rejected(salon_config):
    fake = FakeLLM([
        {"calls": [{"name": "submit", "args": {"confirmed": False, "summary": "Test"}}]},
        {"text": "Please confirm."},
    ])
    ag = agent.Agent(salon_config, fake)
    ag.greet()
    res = ag.turn("Hello")
    assert res["state"] == "collecting"
    tool_msg = next(m for m in reversed(ag.history) if m.get("role") == "tool")
    assert tool_msg["results"][0]["response"]["ok"] is False


def test_submit_without_readback_rejected(salon_config):
    # Customer provides all fields; LLM updates and submits in the same turn without customer confirmation
    fake = FakeLLM([
        {
            "calls": [
                {
                    "name": "update_fields",
                    "args": {
                        "customer_name": "Alice",
                        "phone": "9876543210",
                        "service": "haircut",
                        "date": "2026-10-10",
                        "time": "14:00",
                    },
                },
                {"name": "submit", "args": {"confirmed": True, "summary": "Done"}},
            ]
        },
        {"text": "I have Alice for haircut on 2026-10-10 at 14:00. Please confirm."},
    ])
    ag = agent.Agent(salon_config, fake, today=date(2026, 10, 6))
    ag.greet()
    res = ag.turn("I'm Alice, 9876543210, haircut, 2026-10-10, 14:00")
    assert res["state"] == "confirming"
    assert res["record"] is None
    tool_msg = next(m for m in reversed(ag.history) if m.get("role") == "tool")
    submit_res = tool_msg["results"][1]["response"]
    assert submit_res["ok"] is False
    assert submit_res["error"] == "Read all details back to the customer and get their confirmation before submitting."


def test_confirming_state_update_fields_and_submit_rejected(salon_config):
    fake = FakeLLM([
        {
            "calls": [
                {"name": "update_fields", "args": {"time": "17:00"}},
                {"name": "submit", "args": {"confirmed": True, "summary": "Done"}},
            ]
        },
        {"text": "Updated to 17:00. Please confirm before booking."},
    ])
    ag = agent.Agent(salon_config, fake, today=date(2026, 10, 6))
    ag.fields = {
        "customer_name": "Alice",
        "phone": "9876543210",
        "service": "haircut",
        "date": "2026-10-10",
        "time": "14:00",
    }
    ag.state = "confirming"
    ag.greet()

    res = ag.turn("Actually change the time to 5pm and confirm it")
    assert res["state"] == "confirming"
    assert ag.state == "confirming"
    assert res["record"] is None

    last_tool = next(m for m in reversed(ag.history) if m.get("role") == "tool")
    assert len(last_tool["results"]) == 2
    submit_res = last_tool["results"][1]["response"]
    assert submit_res["ok"] is False
    assert submit_res["error"] == "Read all details back to the customer and get their confirmation before submitting."


def test_llm_exception_apology_state_unchanged_history_rolled_back(salon_config):
    class ErrorLLM:
        def chat(self, system, history, tools):
            raise RuntimeError("API connection timeout")

    ag = agent.Agent(salon_config, ErrorLLM())
    ag.greet()
    initial_history = list(ag.history)
    initial_state = ag.state

    res = ag.turn("Hello there")
    assert res["reply"] == "Sorry, I had a technical problem. Could you please repeat that?"
    assert res["state"] == initial_state
    assert ag.state == initial_state
    assert ag.history == initial_history
    assert res["record"] is None


def test_hangup_abandoned_record(salon_config):
    ag = agent.Agent(salon_config, FakeLLM([]))
    ag.greet()
    assert ag.state == "collecting"

    rec = ag.hangup()
    assert rec is not None
    assert ag.state == "abandoned"
    assert rec["status"] == "abandoned"
    assert rec["business_id"] == "salon_booking"
    assert rec["session_id"] == ag.session_id
    assert ag.record == rec

    rec2 = ag.hangup()
    assert rec2 == rec
    assert ag.state == "abandoned"


def test_hangup_after_completed_returns_existing_record(salon_config):
    ag = agent.Agent(salon_config, FakeLLM([]))
    ag.state = "done"
    done_record = {"status": "completed", "session_id": ag.session_id}
    ag.record = done_record

    rec = ag.hangup()
    assert rec == done_record
    assert ag.state == "done"


def test_call_already_ended(salon_config):
    ag = agent.Agent(salon_config, FakeLLM([]))
    ag.state = "done"
    ag.record = {"status": "completed"}

    res = ag.turn("Are you there?")
    assert res["reply"] == "This call has already ended."


def test_empty_llm_response_escalates(salon_config):
    fake = FakeLLM([{"text": "", "calls": []}])
    ag = agent.Agent(salon_config, fake)
    ag.greet()
    res = ag.turn("Hello")
    assert res["state"] == "escalated"
    assert res["record"]["status"] == "escalated"
    assert res["record"]["escalation_reason"] == "no response from AI"


def test_loop_exhausted_apology(salon_config):
    fake = FakeLLM([
        {"calls": [{"name": "noop", "args": {}}]},
        {"calls": [{"name": "noop", "args": {}}]},
        {"calls": [{"name": "noop", "args": {}}]},
        {"calls": [{"name": "noop", "args": {}}]},
    ])
    ag = agent.Agent(salon_config, fake)
    ag.greet()
    res = ag.turn("Hello")
    assert res["reply"] == "Sorry, could you say that again?"
    assert fake.calls == 4


def test_unknown_tool(salon_config):
    fake = FakeLLM([
        {"calls": [{"name": "unknown_tool", "args": {}}]},
        {"text": "I will assist you shortly."},
    ])
    ag = agent.Agent(salon_config, fake)
    ag.greet()
    res = ag.turn("Test unknown")
    tool_msg = next(m for m in reversed(ag.history) if m.get("role") == "tool")
    assert tool_msg["results"][0]["response"] == {"error": "unknown tool"}
    assert res["reply"] == "I will assist you shortly."


# --- End-to-end tests: Salon & Hospital ---


def test_salon_scripted_end_to_end(salon_config):
    # Tests salon booking end-to-end:
    # 1. Validation error on phone surfaced
    # 2. Correction of time from 16:00 to 17:00 resets can_submit requiring new read-back
    # 3. Confirmation completes booking with normalized fields and valid record shape
    today = date(2026, 10, 6)
    fake = FakeLLM([
        # Turn 1: service
        {"calls": [{"name": "update_fields", "args": {"service": "haircut"}}]},
        {"text": "Great! What is your name and mobile number?"},
        # Turn 2: invalid phone
        {"calls": [{"name": "update_fields", "args": {"customer_name": "Priya Sharma", "phone": "12345"}}]},
        {"text": "Thanks Priya. 12345 is invalid; please give a 10-digit number."},
        # Turn 3: valid phone
        {"calls": [{"name": "update_fields", "args": {"phone": "9876543210"}}]},
        {"text": "Got it. What date and time?"},
        # Turn 4: date + time -> read back
        {"calls": [{"name": "update_fields", "args": {"date": "2026-10-10", "time": "16:00"}}]},
        {"text": "Priya Sharma, haircut on 2026-10-10 at 16:00, phone 9876543210. Can you confirm?"},
        # Turn 5: customer corrects time to 17:00 -> resets can_submit -> model reads back again
        {"calls": [{"name": "update_fields", "args": {"time": "17:00"}}]},
        {"text": "Updated to 17:00. Please confirm."},
        # Turn 6: confirmation -> submit
        {"calls": [{"name": "submit", "args": {"confirmed": True, "summary": "Haircut booked for Priya Sharma"}}]},
    ])
    ag = agent.Agent(salon_config, fake, today=today)
    ag.greet()

    # Turn 1
    r1 = ag.turn("I want a haircut")
    assert r1["state"] == "collecting"

    # Turn 2: validation error
    r2 = ag.turn("I'm Priya Sharma and my phone is 12345")
    assert r2["state"] == "collecting"
    last_tool = next(m for m in reversed(ag.history) if m.get("role") == "tool")
    assert any("phone" in r.get("response", {}).get("errors", {}) for r in last_tool.get("results", []))

    # Turn 3
    r3 = ag.turn("My phone is 9876543210")
    assert r3["state"] == "collecting"

    # Turn 4: state becomes confirming
    r4 = ag.turn("October 10 at 4pm")
    assert r4["state"] == "confirming"

    # Turn 5: correction reset
    r5 = ag.turn("Make it 5 pm instead")
    assert r5["state"] == "confirming"

    # Turn 6: confirm and complete
    r6 = ag.turn("Yes, confirm it")
    assert r6["state"] == "done"
    assert ag.state == "done"
    assert r6["record"] is not None

    rec = r6["record"]
    assert rec["status"] == "completed"
    assert rec["business_id"] == "salon_booking"
    assert rec["action"] == "create_booking"
    assert rec["consent"] is True
    assert rec["fields"]["phone"] == "9876543210"
    assert rec["fields"]["service"] == "haircut"
    assert rec["fields"]["date"] == "2026-10-10"
    assert rec["fields"]["time"] == "17:00"

    expected_keys = {
        "session_id", "business_id", "business", "action", "status",
        "fields", "summary", "escalation_reason", "transcript",
        "consent", "started_at", "ended_at",
    }
    assert expected_keys.issubset(rec.keys())


def test_salon_demo_end_to_end(salon_config):
    user_lines, fake_llm = FakeLLM.load_demo("salon_booking")
    ag = agent.Agent(salon_config, fake_llm, today=date(2026, 10, 6))
    ag.greet()
    res = None
    readback_turns = 0
    phone_error_seen = False
    for line in user_lines:
        res = ag.turn(line)
        if "12345" in line:
            last_tool = next(m for m in reversed(ag.history) if m.get("role") == "tool")
            assert any("phone" in r.get("response", {}).get("errors", {}) for r in last_tool.get("results", []))
            phone_error_seen = True
        if res["state"] == "confirming":
            readback_turns += 1

    assert phone_error_seen
    assert readback_turns >= 2
    assert ag.state == "done"
    assert res["state"] == "done"
    assert ag.record is not None
    rec = ag.record
    assert rec["status"] == "completed"
    assert rec["business_id"] == "salon_booking"
    assert rec["action"] == "create_booking"
    assert rec["consent"] is True
    assert ag.fields["time"] == "17:00"
    assert rec["fields"]["time"] == "17:00"
    assert re.fullmatch(r"[6-9]\d{9}", rec["fields"]["phone"])
    assert rec["fields"]["service"] in salon_config["fields"][2]["enum"]

    expected_keys = {
        "session_id", "business_id", "business", "action", "status",
        "fields", "summary", "escalation_reason", "transcript",
        "consent", "started_at", "ended_at",
    }
    assert expected_keys.issubset(rec.keys())


def test_hospital_scripted_end_to_end(hospital_config):
    fake = FakeLLM([
        {
            "calls": [
                {
                    "name": "update_fields",
                    "args": {
                        "symptoms": "knee pain",
                        "department": "Orthopedics",
                        "doctor": "Dr. Arjun Mehta",
                        "appointment_date": "2026-10-07",
                        "appointment_time": "10:00",
                        "patient_name": "Rahul Verma",
                        "phone": "919876543210",
                        "age": 30,
                        "gender": "male",
                        "city_area": "Andheri",
                        "hospital_branch": "City Centre",
                    },
                }
            ]
        },
        {"text": "I noted the appointment for Rahul Verma. Can you confirm?"},
        {
            "calls": [
                {"name": "submit", "args": {"confirmed": True, "summary": "Appointment booked for Rahul Verma"}}
            ]
        },
    ])
    ag = agent.Agent(hospital_config, fake, today=date(2026, 10, 6))
    ag.greet()
    res1 = ag.turn("I need an appointment for knee pain")
    assert res1["state"] == "confirming"
    assert ag.fields["patient_name"] == "Rahul Verma"
    assert ag.fields["phone"] == "9876543210"

    res2 = ag.turn("Yes, confirmed")
    assert res2["state"] == "done"
    assert res2["record"]["status"] == "completed"
    assert res2["record"]["business_id"] == "hospital_helpline"
    assert res2["record"]["action"] == "book_appointment"
    assert res2["record"]["fields"]["patient_name"] == "Rahul Verma"


def test_hospital_demo_end_to_end(hospital_config):
    today = date(2026, 10, 6)
    slots = agent.doctor_slots(hospital_config, today, frozenset(), "Orthopedics")
    subs = {
        "SLOT_DOCTOR": slots[0]["doctor"],
        "SLOT_DATE": slots[0]["slots"][0]["date"],
        "SLOT_TIME": slots[0]["slots"][0]["time"],
        "SLOT_DAY": slots[0]["slots"][0]["day"],
    }
    user_lines, fake_llm = FakeLLM.load_demo("hospital_helpline", subs=subs)
    ag = agent.Agent(hospital_config, fake_llm, today=today)
    ag.greet()
    res = None
    for line in user_lines:
        res = ag.turn(line)

    assert ag.state == "done"
    assert res["state"] == "done"
    assert ag.record is not None
    rec = ag.record
    assert rec["status"] == "completed"
    assert rec["business_id"] == "hospital_helpline"
    assert rec["action"] == "book_appointment"
    assert rec["fields"]["patient_name"] == "Rahul Sharma"
    assert rec["fields"]["department"] == "Orthopedics"
