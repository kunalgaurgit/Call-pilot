# Call Pilot: Configurable AI Voice Customer-Care Agent

Call Pilot is a configurable, multi-turn voice customer-care agent built as a lightweight, production-grade B.Tech MVP. It conducts natural spoken conversations with customers, collects and validates required business details, confirms accuracy with the caller, executes business actions (bookings, tickets), and securely stores masked structured records.

---

## Key Features

- **Voice-First Experience**: Uses browser-native Speech Recognition (STT) with push-to-talk/hands-free half-duplex and Speech Synthesis (TTS) with barge-in support.
- **Config-Driven Architecture**: Onboard new businesses in minutes with pure JSON configuration—zero code modifications required.
- **Strict Field Validation & Correction**: Validates input types (`text`, `phone`, `date`, `time`, `enum`, `int`), enforces patterns, handles corrections, and reads details back for customer confirmation before committing.
- **Instant Human Escalation & Emergency Detection**: Regex-based local detection of escalation keywords ("human", "manager", "staff member") and medical emergency triggers ("chest pain", "heart attack", "can't breathe") triggers immediate safety response without calling the LLM.
- **Privacy & PII Protection**: Phone numbers and sensitive information are automatically masked (`******1234`) in the dashboard, transcript, and REST API.
- **Dual Engine (Gemini / Offline Demo)**: Works with Google Gemini 2.5 Flash via official Google GenAI SDK, or offline using scripted deterministic replay (`FakeLLM`) without an API key or internet access.
- **Supervisor Dashboard**: Real-time activity monitoring with business filtering, auto-polling (3s), downloadable PDF appointment slips, and full JSON inspection.

---

## Architecture

The system maps the modular customer-care architecture into clean, decoupled components:

| Layer | Responsibilities | Implementation Files |
| :--- | :--- | :--- |
| **Configuration** | Business metadata, field specifications, validation constraints, prompts, escalation triggers | `configs/salon_booking.json`<br>`configs/hospital_helpline.json` |
| **Voice & UI** | Hands-free half-duplex STT, barge-in TTS, live captions, text fallback, responsive light/dark UI, booking card | `static/index.html`<br>`static/style.css` |
| **Supervisor Dashboard** | Live record table, business filtering, 3-second auto-poll, detail inspection, PDF slips, masked PII | `static/dashboard.html` |
| **Agent & State Machine** | Multi-turn dialogue loop, tool calling (`update_fields`, `submit`, `escalate`, `check_doctors`), validation, prerequisite gating, confirmation gate | `agent.py` |
| **LLM Provider** | Provider-neutral interface, Gemini 2.5 Flash client, thought-signature preservation, exponential retry, deterministic replay with dynamic slot substitution | `llm.py` |
| **Data & Persistence** | SQLite storage, appointments table with unique slot constraint, record retrieval, business filtering | `db.py` |
| **API & Server** | FastAPI endpoints, session lifecycle, idle cleanup (15 min), webhook dispatch, PII masking, PDF generation (`/api/bookings/{session_id}/pdf`), static file serving | `app.py` |
| **Test & Fixtures** | End-to-end replay fixtures and unit tests for agent logic, LLM adapter, database, and HTTP API | `demos/*.json`<br>`tests/` |

---

## Prerequisites & Installation

- **Operating System**: Windows 11, macOS, or Linux
- **Python**: Python 3.13.5 (or >= 3.11)
- **Browser**: Google Chrome or Microsoft Edge (recommended for Web Speech API support)

Install the pinned dependencies:

```bash
pip install -r requirements.txt
```

*Installed dependencies: `fastapi==0.135.1`, `uvicorn==0.41.0`, `google-genai==2.9.0`, `httpx==0.28.1`, `pytest==9.1.1`, `fpdf2==2.8.9`.*

---

## Configuration & Environment Setup

1. Copy the example environment file:
   ```bash
   cp .env.example .env
   ```
2. Configure `.env`:
   - Obtain a free API key from [Google AI Studio](https://aistudio.google.com).
   - Add your key to `.env`:
     ```env
     GEMINI_API_KEY=your-free-key-from-aistudio.google.com
     GEMINI_MODEL=gemini-3.5-flash,gemini-3.1-flash-lite
     LLM_MODE=gemini
     ```
   - **Offline / No API Key Mode**: If you do not have an API key, set `LLM_MODE=fake` to run offline with scripted demo replays.
3. Turn on the secret guard (once per clone). It blocks commits containing `.env`, keystores or API keys, so a key can't leak to GitHub and get auto-revoked:
   ```bash
   git config core.hooksPath .githooks
   ```

---

## Running the Application

**One click (Windows):** double-click `run.bat`. It automatically ensures requirements are installed, starts the server on port 8001, and opens the browser. Close the window to stop it.

Or start the FastAPI application with Uvicorn manually:

```bash
python -m uvicorn app:app --host 127.0.0.1 --port 8001
```

*(If port 8001 is occupied, use another port such as `--port 8002`, and change it in `run.bat` too.)*

Once running:
- Open the **Call Assistant** in Chrome or Edge: [http://127.0.0.1:8001](http://127.0.0.1:8001)
- Open the **Supervisor Dashboard**: [http://127.0.0.1:8001/dashboard.html](http://127.0.0.1:8001/dashboard.html)

---

## Demo Walkthrough Scripts

### 1. Salon Appointment Booking (`configs/salon_booking.json`)
Demonstrates booking, validation failure handling, customer correction, and confirmation.

1. **Select Business**: Choose **Glow Salon** on the call page.
2. **Start Call**: Click **Accept & start call**. The assistant greets you with the consent notice and asks what service you would like.
3. **Turn 1 (Intent & Service)**:
   - *Customer*: "I would like to book a haircut."
   - *Agent*: Acknowledges and asks for your name.
4. **Turn 2 (Name)**:
   - *Customer*: "My name is John Doe."
   - *Agent*: Requests your contact phone number.
5. **Turn 3 (Validation Failure Recovery)**:
   - *Customer*: "My phone is 12345."
   - *Agent*: Detects invalid phone format and asks politely for a valid 10-digit mobile number.
6. **Turn 4 (Correction)**:
   - *Customer*: "Sorry, it is 9876543210."
   - *Agent*: Validates phone number and asks for preferred appointment date and time.
7. **Turn 5 (Date & Time)**:
   - *Customer*: "Tomorrow at 4 PM." (or "2030-12-15 at 16:00")
   - *Agent*: Enters `confirming` state, reads all details back (Name, Service, Date, Time, Phone), and requests final confirmation.
8. **Turn 6 (Mid-confirmation Correction)**:
   - *Customer*: "Actually, can you make it 5 PM instead?"
   - *Agent*: Updates time to 17:00, re-reads updated details, and asks for confirmation again.
9. **Turn 7 (Final Confirmation)**:
   - *Customer*: "Yes, confirmed."
   - *Agent*: Commits booking via `submit` tool, returns confirmation message, and stores masked record in SQLite.

---

### 2. Hospital Appointment Helpline (`configs/hospital_helpline.json`)
Demonstrates symptom-guided department recommendation, real doctor slot checking, prerequisite gating, booking confirmation with conflict protection, emergency detection, and PDF appointment slip generation.

1. **Select Helpline**: Choose **CityCare Hospital** on the call page.
2. **Start Call**: Click **📞 Call Helpline**. The assistant greets you with the consent and medical notice.
3. **Turn 1 (Symptom & Department)**:
   - *Caller*: "Hi, I want to book an appointment, I have knee pain since a week."
   - *Agent*: Notes symptoms, suggests **Orthopedics** (explicitly noting it is a suggestion, not a medical diagnosis), and asks if you would like to proceed.
4. **Turn 2 (Slot Check)**:
   - *Caller*: "Yes please."
   - *Agent*: Calls `check_doctors` for Orthopedics, finds available open slots within the next 7 days, and offers up to 2 open slots (e.g. "Dr. Arjun Mehta is available on Thursday 8 October at 10:00. Shall I book it?").
5. **Turn 3 (Slot Selection)**:
   - *Caller*: "Yes, book it."
   - *Agent*: Locks doctor and slot, then asks for patient name and contact number.
6. **Turn 4 (Contact Details)**:
   - *Caller*: "My name is Rahul Sharma, mobile 98765 43210."
   - *Agent*: Validates phone number, asks for age and gender.
7. **Turn 5 (Demographics)**:
   - *Caller*: "I am 34, male."
   - *Agent*: Records age and gender, asks for city/area and nearest hospital branch (City Centre, North Campus, South Campus).
8. **Turn 6 (Branch & Read-Back)**:
   - *Caller*: "I live in Andheri, City Centre branch is nearest."
   - *Agent*: Enters confirming state, reads back all appointment details, and asks for final confirmation.
9. **Turn 7 (Confirmation & PDF)**:
   - *Caller*: "Yes, that's correct."
   - *Agent*: Validates slot against doctor schedule and checks for double-booking in SQLite, commits appointment, returns booking ID (e.g. `HB-0001`), speaks confirmation, and generates a downloadable PDF appointment slip.

#### Emergency Safety
The helpline enforces zero-latency safety for life-threatening conditions:
- **Emergency Keyword Detection**: Spoken phrases like "chest pain", "heart attack", "can't breathe", "heavy bleeding", or "seizure" trigger immediate local escalation without LLM invocation.
- **Immediate Advisory**: The assistant advises the caller to dial 108 or reach the nearest emergency room immediately and gracefully closes the call with `status: "escalated"` and `escalation_reason: "medical emergency"`. No booking is made.

#### Downloadable PDF Appointment Slip
Upon confirmed booking, callers and supervisors can download a standardized PDF slip via `/api/bookings/{session_id}/pdf`:
- Generated in-memory using `fpdf2` with core typography.
- Contains booking reference ID, patient demographics, department, doctor, spoken appointment date and time, hospital branch, and arrival instructions.

---

### 3. Immediate Human Escalation
Demonstrates deterministic local escalation without LLM invocation.

1. At any point in the call, say or type:
   - *"I want to talk to a human."* or *"Let me speak to a receptionist."*
2. **Outcome**: The agent immediately responds with the configured escalation message, ends the call, and records `status: "escalated"` with `escalation_reason: "customer request"`. No LLM request is made, preventing hallucination or stall.

---

## How to Add a New Business

To add support for a new business (e.g., table reservation, doctor appointment, taxi dispatch), create a new JSON configuration file under `configs/`:

### Example: `configs/doctor_clinic.json`
```json
{
  "id": "doctor_clinic",
  "business": "City Care Clinic",
  "purpose": "book patient consultations",
  "greeting": "Hello, thank you for calling City Care Clinic. I can schedule a doctor consultation for you. What specialty do you need?",
  "consent_notice": "This call is recorded by an AI assistant for appointment scheduling. Please use demo details.",
  "tone": "compassionate, professional and brief",
  "action": {
    "type": "booking",
    "name": "book_consultation"
  },
  "escalation_phrases": ["emergency", "doctor immediately", "human", "receptionist"],
  "escalation_message": "If this is a medical emergency, please call 112 immediately. I am alerting clinic staff to contact you.",
  "max_turns": 12,
  "webhook_url": "",
  "summary_template": "{patient_name} booked consultation with {department} on {date} at {time}. Contact: {phone}.",
  "fields": [
    {
      "name": "patient_name",
      "label": "Patient name",
      "type": "text",
      "required": true,
      "prompt": "Ask for the patient's full name."
    },
    {
      "name": "phone",
      "label": "Contact number",
      "type": "phone",
      "required": true,
      "prompt": "Ask for a 10-digit mobile number."
    },
    {
      "name": "department",
      "label": "Department",
      "type": "enum",
      "required": true,
      "enum": ["general medicine", "pediatrics", "dentistry", "dermatology"],
      "prompt": "Ask which clinic department or doctor specialty they need."
    },
    {
      "name": "date",
      "label": "Consultation date",
      "type": "date",
      "required": true,
      "prompt": "Ask for the consultation date (cannot be in the past)."
    },
    {
      "name": "time",
      "label": "Consultation time",
      "type": "time",
      "required": true,
      "min": "09:00",
      "max": "18:00",
      "prompt": "Ask for an appointment time between 9 AM and 6 PM."
    }
  ]
}
```

### Supported Field Types
- `text`: Non-empty string. Optional `pattern` regex (e.g. `^[A-Z]{2}[0-9]{8}$`).
- `phone`: Normalizes 10-digit Indian numbers (strips leading `+91`, `91`, or `0`; validates `[6-9]\d{9}`).
- `date`: Validates ISO date (`YYYY-MM-DD`) and prevents past dates.
- `time`: Validates 24-hour time (`HH:MM`) with optional `min` and `max` constraints.
- `enum`: Case-insensitive matching against a specified list of allowed string values.
- `int`: Integer number with optional `min` and `max` boundaries.

Restart the server—the new business appears in the business selector and API endpoints automatically.

---

## Limitations & Telephony Upgrade Path

### Current MVP Limitations
1. **Gemini Free-Tier Rate Limits**: Free tier API keys have strict rate limits (15 requests/minute). High-frequency calls may trigger 429 throttling (handled automatically via exponential backoff in `llm.py`).
2. **Data Privacy**: Free tier Gemini requests may be retained for model improvements. Strictly use synthetic/demo data; explicit consent is presented to users before each call.
3. **Browser Audio**: Voice interaction relies on the browser's Web Speech API (`SpeechRecognition` and `SpeechSynthesis`). It requires an active tab, supported browser (Chrome/Edge), and microphone permission.

### Production Telephony Upgrade Path
To transition Call Pilot into an enterprise production phone system:
1. **Telephony Ingestion**: Replace browser Web Speech API with **Twilio Voice** or **Telnyx**. Configure an incoming phone number with a WebSocket stream (Twilio Media Streams).
2. **Audio Streaming**:
   - Stream incoming caller audio chunks (μ-law, 8 kHz) to a server-side high-accuracy speech recognizer (e.g., **Deepgram Nova-2** or **AssemblyAI Streaming**).
   - Stream agent response text into a low-latency neural TTS engine (e.g., **Cartesia Sonic** or **ElevenLabs Turbo**) and pipe audio back to Twilio.
3. **Core Engine Reusability**: The core state machine (`agent.py`), business configuration layer (`configs/*.json`), database schema (`db.py`), and LLM tool calling logic (`llm.py`) remain completely unchanged.

---

## Running Automated Tests

Run the complete offline test suite with pytest:

```bash
python -m pytest -q
```

The test suite runs with no network calls and tests:
- `tests/test_agent.py`: Agent state transitions, field validation rules, multi-turn loop, read-back confirmation, corrections, and turn limits.
- `tests/test_llm.py`: Schema stripping, Gemini tool conversion, history formatting, thought signature retention, and FakeLLM replay.
- `tests/test_db.py`: SQLite appointments and record storage, schema initialization, listing, and business filtering.
- `tests/test_app.py`: FastAPI endpoints, PII masking verification, turn processing, and hangup beacon handling.
- `tests/test_hospital.py`: Doctor slot scheduling, prerequisite field gating, emergency triggers, database booking, and PDF generation.
