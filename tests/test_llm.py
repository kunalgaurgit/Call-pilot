"""Unit tests for llm.py (Job 2b)."""
import json
import time
from pathlib import Path
import pytest
from google import genai
from google.genai import types, errors
import llm


def _make_api_error(code: int = 429, message: str = "Resource exhausted") -> errors.APIError:
    """Helper to instantiate APIError."""
    return errors.APIError(code, {"message": message})


def test_tool_spec_to_function_declaration(monkeypatch):
    """Tool spec -> FunctionDeclaration strips extra keys (enum, pattern, format)."""
    captured = {}

    class FakeModels:
        def generate_content(self, model, contents, config):
            captured["config"] = config
            return types.GenerateContentResponse(candidates=[])

    class FakeClient:
        def __init__(self, **kwargs):
            self.models = FakeModels()

    monkeypatch.setattr(genai, "Client", FakeClient)

    gemini = llm.GeminiLLM(api_key="test-key", model="gemini-2.5-flash")

    tool_spec = {
        "name": "update_fields",
        "description": "Update customer booking fields",
        "parameters": {
            "type": "object",
            "properties": {
                "phone": {
                    "type": "string",
                    "description": "10 digits phone number",
                    "pattern": r"^[6-9]\d{9}$",
                    "enum": ["9876543210"],
                    "format": "phone",
                },
                "service": {
                    "type": "string",
                    "description": "Requested service",
                },
            },
            "required": ["phone"],
        },
    }

    gemini.chat("system prompt", [], [tool_spec])

    assert "config" in captured
    tools = captured["config"].tools
    assert len(tools) == 1
    decls = tools[0].function_declarations
    assert len(decls) == 1
    decl = decls[0]
    assert decl.name == "update_fields"

    params = decl.parameters
    props = params.get("properties") if isinstance(params, dict) else params.properties
    assert "phone" in props
    phone_prop = props["phone"]
    if isinstance(phone_prop, dict):
        assert set(phone_prop.keys()) <= {"type", "description"}
        assert phone_prop["type"] == "string"
        assert phone_prop["description"] == "10 digits phone number"
        assert "pattern" not in phone_prop
        assert "enum" not in phone_prop
        assert "format" not in phone_prop
    else:
        assert getattr(phone_prop, "pattern", None) is None
        assert getattr(phone_prop, "enum", None) is None


def test_history_conversion_and_raw_reuse(monkeypatch):
    """History conversion maps user, tool, model parts and reuses raw verbatim."""
    captured = {}

    class FakeModels:
        def generate_content(self, model, contents, config):
            captured["contents"] = contents
            return types.GenerateContentResponse(candidates=[])

    class FakeClient:
        def __init__(self, **kwargs):
            self.models = FakeModels()

    monkeypatch.setattr(genai, "Client", FakeClient)
    gemini = llm.GeminiLLM(api_key="test-key", model="gemini-2.5-flash")

    raw_preserved = types.Content(
        role="model",
        parts=[types.Part.from_text(text="Preserved model turn with thoughts")],
    )

    history = [
        {"role": "user", "text": "I want a haircut"},
        {
            "role": "model",
            "text": "Sure, what time?",
            "calls": [{"name": "update_fields", "args": {"service": "haircut"}}],
            "raw": None,
        },
        {
            "role": "tool",
            "results": [
                {"name": "update_fields", "response": {"saved": {"service": "haircut"}}}
            ],
        },
        {
            "role": "model",
            "text": "Confirmed",
            "calls": [],
            "raw": raw_preserved,
        },
    ]

    gemini.chat("system", history, [])

    contents = captured["contents"]
    assert len(contents) == 4

    # 1. user turn
    assert contents[0].role == "user"
    assert contents[0].parts[0].text == "I want a haircut"

    # 2. model turn built from text + function_call
    assert contents[1].role == "model"
    part_texts = [p.text for p in contents[1].parts if getattr(p, "text", None)]
    assert "Sure, what time?" in part_texts
    fc_parts = [p.function_call for p in contents[1].parts if getattr(p, "function_call", None)]
    assert len(fc_parts) == 1
    assert fc_parts[0].name == "update_fields"
    assert dict(fc_parts[0].args) == {"service": "haircut"}

    # 3. tool turn
    assert contents[2].role == "user"
    fr_parts = [p.function_response for p in contents[2].parts if getattr(p, "function_response", None)]
    assert len(fr_parts) == 1
    assert fr_parts[0].name == "update_fields"
    assert dict(fr_parts[0].response) == {"saved": {"service": "haircut"}}

    # 4. model turn with raw -> reused verbatim
    assert contents[3] is raw_preserved


def test_response_parsing(monkeypatch):
    """Response parsing extracts text, function calls, and raw candidate content."""
    content = types.Content(
        role="model",
        parts=[
            types.Part.from_text(text="I can help book that appointment."),
            types.Part.from_function_call(name="update_fields", args={"service": "haircut"}),
        ],
    )
    fake_resp = types.GenerateContentResponse(
        candidates=[types.Candidate(content=content)]
    )

    class FakeModels:
        def generate_content(self, model, contents, config):
            return fake_resp

    class FakeClient:
        def __init__(self, **kwargs):
            self.models = FakeModels()

    monkeypatch.setattr(genai, "Client", FakeClient)
    gemini = llm.GeminiLLM(api_key="test-key", model="gemini-2.5-flash")

    reply = gemini.chat("system", [], [])
    assert reply.text == "I can help book that appointment."
    assert reply.calls == [{"name": "update_fields", "args": {"service": "haircut"}}]
    assert reply.raw is content


def test_response_parsing_empty_candidates(monkeypatch):
    """Response with no candidates returns an empty LLMReply."""
    fake_resp = types.GenerateContentResponse(candidates=[])

    class FakeModels:
        def generate_content(self, model, contents, config):
            return fake_resp

    class FakeClient:
        def __init__(self, **kwargs):
            self.models = FakeModels()

    monkeypatch.setattr(genai, "Client", FakeClient)
    gemini = llm.GeminiLLM(api_key="test-key", model="gemini-2.5-flash")

    reply = gemini.chat("system", [], [])
    assert reply.text == ""
    assert reply.calls == []
    assert reply.raw is None


def test_429_pauses_model_and_falls_back_without_waiting(monkeypatch):
    """Out of quota: no sleep/retry on that model, next model answers, and later calls skip the paused one."""
    calls = []
    sleeps = []
    content = types.Content(role="model", parts=[types.Part.from_text(text="From the fallback")])
    ok_resp = types.GenerateContentResponse(candidates=[types.Candidate(content=content)])

    class FakeModels:
        def generate_content(self, model, contents, config):
            calls.append(model)
            if model == "primary-model":
                raise _make_api_error(429, "Quota exceeded")
            return ok_resp

    class FakeClient:
        def __init__(self, **kwargs):
            self.models = FakeModels()

    monkeypatch.setattr(genai, "Client", FakeClient)
    monkeypatch.setattr(time, "sleep", lambda s: sleeps.append(s))

    gemini = llm.GeminiLLM(api_key="test-key", model="primary-model,secondary-model")
    assert gemini.chat("system", [], []).text == "From the fallback"
    assert calls == ["primary-model", "secondary-model"]
    assert sleeps == []
    assert "primary-model" in llm.cooling_models()

    calls.clear()
    gemini.chat("system", [], [])
    assert calls == ["secondary-model"]  # paused model skipped


def test_retry_after_parsed_from_google_error():
    assert llm._retry_after_s(Exception("{'@type': '...RetryInfo', 'retryDelay': '65466s'}")) == 65466
    assert llm._retry_after_s(Exception('"retryDelay": "20.5s"')) == 20.5
    assert llm._retry_after_s(Exception("no hint")) == 60
    assert llm._retry_after_s(Exception("'retryDelay': '999999s'")) == 86400


def test_retry_exhausted_reraises(monkeypatch):
    """Single model out of quota: re-raises after one attempt, no sleeping."""
    sleeps = []

    class FakeModels:
        def generate_content(self, model, contents, config):
            raise _make_api_error(429, "Persistent rate limit")

    class FakeClient:
        def __init__(self, **kwargs):
            self.models = FakeModels()

    monkeypatch.setattr(genai, "Client", FakeClient)
    monkeypatch.setattr(time, "sleep", lambda s: sleeps.append(s))

    gemini = llm.GeminiLLM(api_key="test-key", model="gemini-2.5-flash")
    with pytest.raises(errors.APIError):
        gemini.chat("system", [], [])
    assert sleeps == []


def test_model_fallback_503_twice_then_second_model_answers(monkeypatch):
    """First model fails with 503 twice; falls back to second model which answers."""
    calls = []
    sleeps = []

    content = types.Content(
        role="model",
        parts=[types.Part.from_text(text="Fallback response")],
    )
    ok_resp = types.GenerateContentResponse(
        candidates=[types.Candidate(content=content)]
    )

    class FakeModels:
        def generate_content(self, model, contents, config):
            calls.append(model)
            if model == "primary-model":
                raise _make_api_error(503, "Service Unavailable")
            return ok_resp

    class FakeClient:
        def __init__(self, **kwargs):
            self.models = FakeModels()

    monkeypatch.setattr(genai, "Client", FakeClient)
    monkeypatch.setattr(time, "sleep", lambda s: sleeps.append(s))

    gemini = llm.GeminiLLM(api_key="test-key", model="primary-model,secondary-model")
    reply = gemini.chat("system", [], [])

    assert reply.text == "Fallback response"
    assert calls == ["primary-model", "primary-model", "secondary-model"]
    assert sleeps == [1]

    # Busy model is paused: the next turn goes straight to the healthy one.
    calls.clear()
    assert gemini.chat("system", [], []).text == "Fallback response"
    assert calls == ["secondary-model"]
    assert "primary-model" in llm.cooling_models()


def test_make_llm_replaces_legacy_model_list(monkeypatch):
    monkeypatch.setattr(genai, "Client", lambda **kw: None)
    monkeypatch.setenv("GEMINI_API_KEY", "k")
    monkeypatch.setenv("GEMINI_MODEL", "gemini-3.5-flash,gemini-3.1-flash-lite")
    gemini, _ = llm.make_llm("x")
    assert gemini.models == llm.DEFAULT_MODELS.split(",")


def test_model_fallback_non_retryable_400_raises_without_trying_second_model(monkeypatch):
    """Non-retryable 400 raises immediately without retrying or trying second model."""
    calls = []
    sleeps = []

    class FakeModels:
        def generate_content(self, model, contents, config):
            calls.append(model)
            raise _make_api_error(400, "Bad Request")

    class FakeClient:
        def __init__(self, **kwargs):
            self.models = FakeModels()

    monkeypatch.setattr(genai, "Client", FakeClient)
    monkeypatch.setattr(time, "sleep", lambda s: sleeps.append(s))

    gemini = llm.GeminiLLM(api_key="test-key", model="primary-model,secondary-model")
    with pytest.raises(errors.APIError) as exc_info:
        gemini.chat("system", [], [])

    assert exc_info.value.code == 400
    assert calls == ["primary-model"]
    assert len(sleeps) == 0


def test_fake_llm_load_demo_synthetic(tmp_path, monkeypatch):
    """FakeLLM.load_demo correctly parses user lines and script turns."""
    demo_data = {
        "config_id": "mock_config",
        "turns": [
            {"user": "Hello", "llm": [{"text": "Welcome! How can I help?"}]},
            {"user": "Need support", "llm": [{"text": "Sure, let's start."}]},
        ],
    }
    mock_file = tmp_path / "mock_config.json"
    mock_file.write_text(json.dumps(demo_data), encoding="utf-8")

    monkeypatch.setattr(llm, "DEMOS", tmp_path)
    user_lines, fake = llm.FakeLLM.load_demo("mock_config")

    assert user_lines == ["Hello", "Need support"]
    assert isinstance(fake, llm.FakeLLM)
    reply1 = fake.chat("sys", [], [])
    assert reply1.text == "Welcome! How can I help?"
    reply2 = fake.chat("sys", [], [])
    assert reply2.text == "Sure, let's start."


def test_fake_llm_load_demo_configs():
    """FakeLLM.load_demo works for both salon_booking and hospital_helpline."""
    for config_id in ("salon_booking", "hospital_helpline"):
        demo_file = llm.DEMOS / f"{config_id}.json"
        assert demo_file.exists(), f"Demo file {demo_file} must exist"
        user_lines, fake = llm.FakeLLM.load_demo(config_id)
        assert isinstance(user_lines, list)
        assert len(user_lines) > 0
        assert isinstance(fake, llm.FakeLLM)


def test_make_llm_fake(tmp_path, monkeypatch):
    """make_llm with use_fake=True loads demo and returns (llm, hints)."""
    demo_data = {
        "config_id": "salon_booking",
        "turns": [
            {"user": "Book haircut", "llm": [{"text": "Sure, what name?"}]},
        ],
    }
    salon_file = llm.DEMOS / "salon_booking.json"
    if not salon_file.exists():
        monkeypatch.setattr(llm, "DEMOS", tmp_path)
        (tmp_path / "salon_booking.json").write_text(json.dumps(demo_data), encoding="utf-8")

    fake_llm_inst, hints = llm.make_llm("salon_booking", use_fake=True)
    assert isinstance(fake_llm_inst, llm.FakeLLM)
    assert isinstance(hints, list)
    assert len(hints) > 0


def test_turn_deadline_skips_requests_that_cannot_finish_in_time(monkeypatch):
    """A request starts only if its full timeout fits before the turn deadline; otherwise raise without calling Gemini."""
    calls = []

    class FakeModels:
        def generate_content(self, model, contents, config):
            calls.append(model)
            return types.GenerateContentResponse(candidates=[types.Candidate(
                content=types.Content(role="model", parts=[types.Part.from_text(text="ok")]))])

    class FakeClient:
        def __init__(self, **kwargs):
            self.models = FakeModels()

    monkeypatch.setattr(genai, "Client", FakeClient)
    gemini = llm.GeminiLLM(api_key="k", model="m1,m2")
    gemini.deadline = time.monotonic() + gemini.timeout_s + 1
    assert gemini.chat("s", [], []).text == "ok"

    gemini.deadline = time.monotonic() + gemini.timeout_s - 1
    with pytest.raises(TimeoutError):
        gemini.chat("s", [], [])
    assert calls == ["m1"]
