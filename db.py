import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

DB_PATH = Path(__file__).parent / "callpilot.db"


@contextmanager
def _connection():
    conn = sqlite3.connect(str(DB_PATH), timeout=5)
    try:
        with conn:
            yield conn
    finally:
        conn.close()


class SlotTaken(ValueError):
    pass


def init(path=None):
    global DB_PATH
    if path is not None:
        DB_PATH = Path(path)
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with _connection() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS records (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT UNIQUE,
                business_id TEXT,
                status TEXT,
                created_at TEXT,
                data TEXT
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS appointments (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              session_id TEXT UNIQUE NOT NULL,
              doctor TEXT NOT NULL, department TEXT NOT NULL,
              appointment_date TEXT NOT NULL, appointment_time TEXT NOT NULL,
              hospital_branch TEXT, patient_name TEXT, phone TEXT, age INTEGER, gender TEXT, city_area TEXT, symptoms TEXT,
              created_at TEXT NOT NULL,
              UNIQUE(doctor, appointment_date, appointment_time)
            )
            """
        )


def save(record: dict) -> int:
    data = json.dumps(record)
    session_id = record.get("session_id")
    business_id = record.get("business_id")
    status = record.get("status")
    created_at = (
        record.get("created_at")
        or record.get("ended_at")
        or record.get("started_at")
        or datetime.now(timezone.utc).isoformat()
    )
    with _connection() as conn:
        if session_id:
            cur = conn.execute(
                """
                INSERT INTO records (session_id, business_id, status, created_at, data)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(session_id) DO UPDATE SET
                    business_id = excluded.business_id,
                    status = excluded.status,
                    created_at = excluded.created_at,
                    data = excluded.data
                """,
                (session_id, business_id, status, created_at, data),
            )
        else:
            cur = conn.execute(
                """
                INSERT INTO records (session_id, business_id, status, created_at, data)
                VALUES (?, ?, ?, ?, ?)
                """,
                (session_id, business_id, status, created_at, data),
            )
        return cur.lastrowid


def list_records(business_id: str | None = None, limit: int = 100) -> list[dict]:
    with _connection() as conn:
        if business_id:
            cur = conn.execute(
                "SELECT id, data FROM records WHERE business_id = ? ORDER BY id DESC LIMIT ?",
                (business_id, limit),
            )
        else:
            cur = conn.execute(
                "SELECT id, data FROM records ORDER BY id DESC LIMIT ?",
                (limit,),
            )
        rows = cur.fetchall()
        result = []
        for row in rows:
            rec = json.loads(row[1])
            rec["id"] = row[0]
            result.append(rec)
        return result


def get(id: int | str) -> dict | None:
    try:
        row_id = int(id)
    except (ValueError, TypeError):
        return None
    with _connection() as conn:
        cur = conn.execute(
            "SELECT id, data FROM records WHERE id = ?",
            (row_id,),
        )
        row = cur.fetchone()
        if not row:
            return None
        rec = json.loads(row[1])
        rec["id"] = row[0]
        return rec


def book(session_id: str, fields: dict) -> int:
    with _connection() as conn:
        cur = conn.execute("SELECT id FROM appointments WHERE session_id = ?", (session_id,))
        row = cur.fetchone()
        if row:
            return row[0]
        
        try:
            cur = conn.execute(
                """
                INSERT INTO appointments (
                    session_id, doctor, department, appointment_date, appointment_time,
                    hospital_branch, patient_name, phone, age, gender, city_area, symptoms, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    session_id, fields.get("doctor"), fields.get("department"),
                    fields.get("appointment_date"), fields.get("appointment_time"),
                    fields.get("hospital_branch"), fields.get("patient_name"),
                    fields.get("phone"), fields.get("age"), fields.get("gender"),
                    fields.get("city_area"), fields.get("symptoms"),
                    datetime.now(timezone.utc).isoformat()
                )
            )
            return cur.lastrowid
        except sqlite3.IntegrityError:
            raise SlotTaken("Slot is already taken")


def taken_slots() -> set[tuple[str, str, str]]:
    with _connection() as conn:
        cur = conn.execute("SELECT doctor, appointment_date, appointment_time FROM appointments")
        return set(cur.fetchall())


def get_appointment(session_id: str) -> dict | None:
    with _connection() as conn:
        conn.row_factory = sqlite3.Row
        cur = conn.execute("SELECT * FROM appointments WHERE session_id = ?", (session_id,))
        row = cur.fetchone()
        if not row:
            return None
        return dict(row)


def get_record_by_session(session_id: str) -> dict | None:
    with _connection() as conn:
        cur = conn.execute(
            "SELECT id, data FROM records WHERE session_id = ?",
            (session_id,),
        )
        row = cur.fetchone()
        if not row:
            return None
        rec = json.loads(row[1])
        rec["id"] = row[0]
        return rec

