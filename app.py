import copy
import json
import logging
import os
import re
import time
import unicodedata
from datetime import date, datetime
from pathlib import Path

from fastapi import FastAPI, HTTPException, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
import httpx
from fpdf import FPDF

import db
from agent import Agent, doctor_slots
from llm import make_llm

logger = logging.getLogger("callpilot")

# Tiny stdlib .env loader
_env_file = Path(__file__).parent / ".env"
if _env_file.exists():
    for _line in _env_file.read_text(encoding="utf-8").splitlines():
        _line = _line.strip()
        if not _line or _line.startswith("#"):
            continue
        if "=" in _line:
            _k, _v = _line.split("=", 1)
            _v = _v.strip()
            if len(_v) >= 2 and ((_v[0] == '"' and _v[-1] == '"') or (_v[0] == "'" and _v[-1] == "'")):
                _v = _v[1:-1]
            os.environ.setdefault(_k.strip(), _v)


def load_configs() -> dict[str, dict]:
    configs = {}
    configs_dir = Path(__file__).parent / "configs"
    if configs_dir.exists():
        for p in sorted(configs_dir.glob("*.json")):
            try:
                data = json.loads(p.read_text(encoding="utf-8"))
                if "id" in data:
                    configs[data["id"]] = data
            except Exception:
                pass
    return configs


CONFIGS = load_configs()
db.init()

SESSIONS: dict[str, dict] = {}


def get_default_mode() -> str:
    return "gemini" if os.environ.get("LLM_MODE", "gemini").lower() == "gemini" and os.environ.get("GEMINI_API_KEY") else "fake"


def _finish(agent, cfg: dict) -> int | None:
    rec = agent.record if agent else None
    if not rec:
        return None
    record_id = db.save(rec)
    webhook_url = cfg.get("webhook_url") if cfg else None
    if webhook_url:
        try:
            httpx.post(webhook_url, json=rec, timeout=5.0)
        except Exception as exc:
            logger.warning("Webhook POST failed for url %s: %s", webhook_url, exc)
    return record_id


def _sweep_idle():
    now = time.time()
    for sid, sess in list(SESSIONS.items()):
        if now - sess.get("last", 0) > 15 * 60:
            agent = sess.get("agent")
            if agent:
                agent.hangup()
                _finish(agent, agent.config)
            SESSIONS.pop(sid, None)


_PHONE_RE = re.compile(r"(?<!\d)(?:\d[\s-]*){9,}\d(?!\d)")


def _mask_match(m: re.Match) -> str:
    digits = re.sub(r"\D", "", m.group(0))
    return "******" + digits[-4:]


def _mask_text(text: str) -> str:
    if not isinstance(text, str):
        return text
    return _PHONE_RE.sub(_mask_match, text)


def mask(record: dict | None) -> dict | None:
    if not record or not isinstance(record, dict):
        return record
    rec = copy.deepcopy(record)
    fields = rec.get("fields")
    if isinstance(fields, dict):
        for k, v in fields.items():
            if isinstance(v, str):
                fields[k] = _mask_text(v)
    summary = rec.get("summary")
    if isinstance(summary, str):
        rec["summary"] = _mask_text(summary)
    esc = rec.get("escalation_reason")
    if isinstance(esc, str):
        rec["escalation_reason"] = _mask_text(esc)
    transcript = rec.get("transcript")
    if isinstance(transcript, list):
        for entry in transcript:
            if isinstance(entry, dict) and isinstance(entry.get("text"), str):
                entry["text"] = _mask_text(entry["text"])
    return rec


class StartRequest(BaseModel):
    config_id: str
    use_fake: bool = False
    session_id: str | None = None


class TurnRequest(BaseModel):
    text: str = ""


app = FastAPI(title="Call Pilot")


@app.get("/api/status")
def get_status():
    return {
        "mode": get_default_mode(),
        "model": os.environ.get("GEMINI_MODEL", "gemini-3.5-flash,gemini-3.1-flash-lite"),
    }


@app.get("/api/configs")
def get_configs():
    return [
        {
            "id": cfg.get("id"),
            "business": cfg.get("business", ""),
            "purpose": cfg.get("purpose", ""),
        }
        for cfg in CONFIGS.values()
    ]


def _book(sid: str, fields: dict) -> str:
    return f"HB-{db.book(sid, fields):04d}"


def booking_pdf(appt: dict, hospital: str) -> bytes:
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Helvetica", "B", 16)
    pdf.cell(0, 10, f"{hospital} - Appointment Slip", new_x="LMARGIN", new_y="NEXT", align="C")
    pdf.set_font("Helvetica", "B", 12)
    pdf.cell(0, 10, f"Booking ID: HB-{appt['id']:04d}", new_x="LMARGIN", new_y="NEXT", align="C")
    pdf.ln(5)
    
    def clean(s):
        return unicodedata.normalize("NFKD", str(s)).encode("ascii", "ignore").decode()
    
    spoken_d = date.fromisoformat(appt["appointment_date"]).strftime("%A %d %B").replace(" 0", " ")
    
    rows = [
        ("Patient", appt.get("patient_name", "")),
        ("Age/Gender", f"{appt.get('age', '')}/{appt.get('gender', '')}"),
        ("Mobile", appt.get("phone", "")),
        ("City/Area", appt.get("city_area", "")),
        ("Health problem", appt.get("symptoms", "")),
        ("Department", appt.get("department", "")),
        ("Doctor", appt.get("doctor", "")),
        ("Date", spoken_d),
        ("Time", appt.get("appointment_time", "")),
        ("Branch", appt.get("hospital_branch", "")),
        ("Booked at", datetime.fromisoformat(appt["created_at"]).astimezone().strftime("%d %b %Y, %I:%M %p")),
    ]
    
    for k, v in rows:
        pdf.set_font("Helvetica", "B", 12)
        pdf.cell(40, 10, clean(k) + ":")
        pdf.set_font("Helvetica", "", 12)
        pdf.multi_cell(0, 10, clean(v), new_x="LMARGIN", new_y="NEXT")
    
    pdf.ln(10)
    pdf.set_font("Helvetica", "I", 10)
    pdf.cell(0, 10, "Please arrive 15 minutes early. This is not a medical diagnosis.", new_x="LMARGIN", new_y="NEXT", align="C")
    return bytes(pdf.output())


@app.post("/api/call/start")
def start_call(body: StartRequest):
    _sweep_idle()
    if body.config_id not in CONFIGS:
        raise HTTPException(status_code=404, detail="Unknown config")

    config = CONFIGS[body.config_id]
    use_fake = body.use_fake or (get_default_mode() == "fake")
    subs = None
    if use_fake and "doctors" in config:
        s = doctor_slots(config, date.today(), db.taken_slots(), "Orthopedics")
        if s:
            subs = {
                "SLOT_DOCTOR": s[0]["doctor"],
                "SLOT_DATE": s[0]["slots"][0]["date"],
                "SLOT_TIME": s[0]["slots"][0]["time"],
                "SLOT_DAY": s[0]["slots"][0]["day"]
            }
    llm, hints = make_llm(body.config_id, use_fake=use_fake, subs=subs)

    agent = Agent(config=config, llm=llm, session_id=body.session_id, book=_book, taken=db.taken_slots)
    greeting = agent.greet()
    sid = agent.session_id
    SESSIONS[sid] = {"agent": agent, "last": time.time()}

    return {
        "session_id": sid,
        "greeting": greeting,
        "consent_notice": config.get("consent_notice", ""),
        "business": config.get("business", ""),
        "mode": "fake" if use_fake else "gemini",
        "hints": hints,
    }


@app.post("/api/call/{sid}/turn")
def call_turn(sid: str, body: TurnRequest = TurnRequest()):
    if sid not in SESSIONS:
        raise HTTPException(status_code=404, detail="Session not found")

    text = (body.text or "").strip()
    if not text or len(text) > 500:
        raise HTTPException(status_code=400, detail="Text must be between 1 and 500 characters")

    session = SESSIONS[sid]
    session["last"] = time.time()
    agent: Agent = session["agent"]

    out = agent.turn(text)
    record = out.get("record")
    record_id = None

    res = dict(out)
    if record:
        record_id = _finish(agent, agent.config)
        SESSIONS.pop(sid, None)
        if "booking_id" in record:
            res["booking_id"] = record["booking_id"]
            res["pdf_url"] = f"/api/bookings/{sid}/pdf"
        res["record"] = mask(record)
    res["record_id"] = record_id
    return res


@app.get("/api/bookings/{session_id}/pdf")
def download_pdf(session_id: str):
    appt = db.get_appointment(session_id)
    if not appt:
        raise HTTPException(status_code=404, detail="Appointment not found")
    hospital = next((c["business"] for c in CONFIGS.values() if "doctors" in c), "Hospital")
    pdf_bytes = booking_pdf(appt, hospital)
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="HB-{appt["id"]:04d}.pdf"'}
    )


@app.post("/api/call/{sid}/hangup")
def hangup(sid: str):
    session = SESSIONS.pop(sid, None)
    if session:
        agent = session.get("agent")
        if agent:
            agent.hangup()
            _finish(agent, agent.config)
    return {"ok": True}


@app.get("/api/records")
def list_records(business_id: str | None = None, limit: int = 100):
    limit = max(1, min(500, limit))
    records = db.list_records(business_id=business_id, limit=limit)
    return [mask(r) for r in records]


@app.get("/api/records/{id}")
def get_record(id: int):
    rec = db.get(id)
    if not rec:
        raise HTTPException(status_code=404, detail="Record not found")
    return mask(rec)


STATIC_DIR = Path(__file__).parent / "static"
STATIC_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/", StaticFiles(directory=str(STATIC_DIR), html=True), name="static")
