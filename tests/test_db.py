"""Unit tests for db.py (Job 2b)."""
import sqlite3
import pytest
import db


@pytest.fixture
def test_db(tmp_path):
    db_file = tmp_path / "test_callpilot.db"
    db.init(db_file)
    return db_file


def test_init_creates_table(tmp_path):
    db_file = tmp_path / "init_check.db"
    db.init(db_file)
    assert db_file.exists()
    with sqlite3.connect(db_file) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='records'")
        table = cursor.fetchone()
        assert table is not None


def test_save_and_get(test_db):
    record = {
        "session_id": "sess-1",
        "business_id": "salon_booking",
        "business": "The Glamour Room",
        "action": "book_appointment",
        "status": "completed",
        "fields": {"customer_name": "Alice", "service": "haircut"},
        "summary": "Booking confirmed for Alice",
        "escalation_reason": None,
        "transcript": [{"role": "customer", "text": "Hi"}],
        "consent": True,
        "started_at": "2026-10-06T10:00:00Z",
        "ended_at": "2026-10-06T10:05:00Z",
    }
    rec_id = db.save(record)
    assert isinstance(rec_id, int)
    assert rec_id > 0

    fetched = db.get(rec_id)
    assert fetched is not None
    assert fetched["id"] == rec_id
    assert fetched["session_id"] == "sess-1"
    assert fetched["business_id"] == "salon_booking"
    assert fetched["status"] == "completed"
    assert fetched["fields"] == {"customer_name": "Alice", "service": "haircut"}
    assert fetched["summary"] == "Booking confirmed for Alice"


def test_get_nonexistent(test_db):
    assert db.get(9999) is None


def test_list_records_order_and_limit(test_db):
    ids = []
    for i in range(5):
        rec = {
            "session_id": f"sess-{i}",
            "business_id": "salon_booking",
            "status": "completed",
            "summary": f"Summary {i}",
        }
        ids.append(db.save(rec))

    records = db.list_records(limit=3)
    assert len(records) == 3
    # Newest first
    assert records[0]["id"] == ids[-1]
    assert records[1]["id"] == ids[-2]
    assert records[2]["id"] == ids[-3]
    assert records[0]["session_id"] == "sess-4"


def test_list_records_business_filter(test_db):
    db.save({"session_id": "s1", "business_id": "salon", "status": "completed"})
    db.save({"session_id": "s2", "business_id": "hospital", "status": "completed"})
    db.save({"session_id": "s3", "business_id": "salon", "status": "escalated"})

    salon_records = db.list_records(business_id="salon")
    assert len(salon_records) == 2
    assert all(r["business_id"] == "salon" for r in salon_records)

    hospital_records = db.list_records(business_id="hospital")
    assert len(hospital_records) == 1
    assert hospital_records[0]["session_id"] == "s2"

    empty_records = db.list_records(business_id="nonexistent")
    assert empty_records == []
