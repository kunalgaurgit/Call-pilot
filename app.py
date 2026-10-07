import copy
import json
import logging
import os
import re
import socket
import threading
import time
import unicodedata
from collections import deque
from datetime import date, datetime
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
import httpx
from fpdf import FPDF

import db
from agent import Agent, doctor_slots
from llm import DEFAULT_MODELS, cooling_models, make_llm

# The Android app gives up on a turn after 25 s; answer (even with an apology) before that.
# Each Gemini request may take up to 10 s, so 20 s fits a tool call plus the spoken reply.
TURN_BUDGET_S = 20

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
            log_event(sid, "system", "Call timed out (15 min idle)")


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


LOG_DIR = Path(__file__).parent / "logs"
# ponytail: in-memory feed of the last 1000 events, lost on restart; the JSONL files are the durable copy
LIVE: deque = deque(maxlen=1000)
_live_lock = threading.Lock()
_live_seq = 0
AI_HEALTH = {"state": "unknown", "error": "", "checked_at": None}


def _now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="milliseconds")


def log_event(sid: str | None, role: str, text: str, **extra) -> None:
    """Live feed + logs/calls-YYYY-MM-DD.jsonl. Roles: system, caller, agent, tool, error."""
    global _live_seq
    ev = {"ts": _now_iso(), "sid": sid, "role": role, "text": _mask_text(text), **extra}
    with _live_lock:
        _live_seq += 1
        ev["seq"] = _live_seq
        LIVE.append(ev)
        try:
            LOG_DIR.mkdir(exist_ok=True)
            with open(LOG_DIR / f"calls-{date.today().isoformat()}.jsonl", "a", encoding="utf-8") as f:
                f.write(json.dumps(ev, ensure_ascii=False) + "\n")
        except OSError as exc:
            logger.warning("Call log write failed: %s", exc)


def _set_ai(state: str, error: str = "") -> None:
    AI_HEALTH.update(state=state, error=error, checked_at=_now_iso())


class _TrackedLLM:
    """Wraps the live LLM: records AI health and logs tool calls / errors per call."""

    def __init__(self, inner, sid: str | None):
        self.inner, self.sid = inner, sid

    def chat(self, *args, **kwargs):
        t0 = time.perf_counter()
        try:
            r = self.inner.chat(*args, **kwargs)
        except Exception as exc:
            err = f"{type(exc).__name__}: {exc}"[:500]
            _set_ai("error", err)
            if self.sid:
                log_event(self.sid, "error", err, ms=round((time.perf_counter() - t0) * 1000))
            raise
        _set_ai("ok")
        if self.sid:
            for call in r.calls or []:
                log_event(self.sid, "tool", f"{call.get('name')} {json.dumps(call.get('args') or {}, ensure_ascii=False)}")
        return r


def check_ai() -> dict:
    """One tiny Gemini request to confirm the key and model work."""
    if get_default_mode() != "gemini":
        _set_ai("demo")
        return AI_HEALTH
    try:
        llm, _ = make_llm("", use_fake=False)
        _TrackedLLM(llm, None).chat("Reply with the single word OK.", [{"role": "user", "text": "ping"}])
    except Exception as exc:
        logger.warning("AI health check failed: %s", exc)
    return AI_HEALTH


class StartRequest(BaseModel):
    config_id: str
    use_fake: bool = False
    session_id: str | None = None


class TurnRequest(BaseModel):
    text: str = ""


app = FastAPI(title="Call Pilot")


def discovery_reply(msg: bytes, port: int) -> bytes | None:
    if msg.strip() == b"CALLPILOT_DISCOVER":
        return f"CALLPILOT {port}".encode("ascii")
    return None


def _udp_discovery_worker():
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.bind(("0.0.0.0", 8002))
    except OSError as exc:
        logger.warning("UDP discovery bind failed: %s", exc)
        return
    while True:
        try:
            data, addr = sock.recvfrom(1024)
            reply = discovery_reply(data, int(os.environ.get("CALLPILOT_PORT", "8001")))
            if reply:
                sock.sendto(reply, addr)
        except Exception as exc:
            logger.debug("UDP discovery error: %s", exc)


@app.on_event("startup")
def _start_discovery():
    threading.Thread(target=_udp_discovery_worker, daemon=True).start()
    threading.Thread(target=check_ai, daemon=True).start()


@app.get("/api/status")
def get_status():
    return {
        "mode": get_default_mode(),
        "model": os.environ.get("GEMINI_MODEL", DEFAULT_MODELS),
        "ai": AI_HEALTH,
        "paused_models": cooling_models(),
        "active_calls": len(SESSIONS),
    }


@app.post("/api/ai/check")
def recheck_ai():
    return check_ai()


@app.get("/api/live")
def live_events(after: int = 0):
    with _live_lock:
        if after > _live_seq:  # server restarted since the client's last poll
            after = 0
        events = [e for e in LIVE if e["seq"] > after]
    return {"events": [dict(e) for e in events], "active": list(SESSIONS.keys())}


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
def start_call(body: StartRequest, request: Request):
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
    sid = agent.session_id
    if not use_fake:
        agent.llm = _TrackedLLM(llm, sid)
    greeting = agent.greet()
    SESSIONS[sid] = {"agent": agent, "last": time.time(), "lock": threading.Lock()}
    client = request.client.host if request.client else "?"
    log_event(sid, "system", f"Call started - {config.get('business', body.config_id)} ({'demo' if use_fake else 'live AI'})",
              client=client, config_id=body.config_id)
    log_event(sid, "agent", greeting)

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

    # One turn at a time per call: a caller repeating themselves after a phone timeout must not
    # run a second AI loop on the same history.
    with session["lock"]:
        if sid not in SESSIONS:
            raise HTTPException(status_code=404, detail="Session not found")
        log_event(sid, "caller", text)
        t0 = time.perf_counter()
        inner = getattr(agent.llm, "inner", None)
        if inner is not None:
            inner.deadline = time.monotonic() + TURN_BUDGET_S
        out = agent.turn(text)
        log_event(sid, "agent", out.get("reply", ""), ms=round((time.perf_counter() - t0) * 1000), state=out.get("state"))
    record = out.get("record")
    record_id = None

    res = dict(out)
    if record:
        record_id = _finish(agent, agent.config)
        SESSIONS.pop(sid, None)
        log_event(sid, "system", f"Call ended - {record.get('status', 'done')}"
                  + (f", booking {record['booking_id']}" if record.get("booking_id") else ""))
        if "booking_id" in record:
            res["booking_id"] = record["booking_id"]
            res["pdf_url"] = f"/api/bookings/{sid}/pdf"
        res["record"] = mask(record)
    res["record_id"] = record_id
    return res


@app.get("/api/bookings/{session_id}")
def get_booking(session_id: str):
    appt = db.get_appointment(session_id)
    if not appt:
        raise HTTPException(status_code=404, detail="Appointment not found")
    res = dict(appt)
    res["booking_id"] = f"HB-{appt['id']:04d}"
    res["pdf_url"] = f"/api/bookings/{session_id}/pdf"
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
        log_event(sid, "system", "Caller hung up")
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
