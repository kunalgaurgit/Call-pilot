"""LLM adapters. Agent code only depends on: chat(system, history, tools) -> LLMReply.

History format (provider-neutral, owned by agent.py):
  {"role": "user",  "text": str}
  {"role": "model", "text": str, "calls": [{"name": str, "args": dict}], "raw": <provider object or None>}
  {"role": "tool",  "results": [{"name": str, "response": dict}]}
"""
import json
from dataclasses import dataclass, field
from pathlib import Path

DEMOS = Path(__file__).parent / "demos"


@dataclass
class LLMReply:
    text: str = ""
    calls: list = field(default_factory=list)  # [{"name": str, "args": dict}]
    raw: object = None  # provider content to replay verbatim in history (keeps Gemini thought signatures)


class FakeLLM:
    """Replays scripted replies in order. Used by tests and the offline demo mode."""

    def __init__(self, replies):
        self.replies = list(replies)
        self.calls = 0

    def chat(self, system, history, tools):
        if self.calls >= len(self.replies):
            raise RuntimeError("FakeLLM script exhausted")
        r = self.replies[self.calls]
        self.calls += 1
        return LLMReply(text=r.get("text", ""), calls=r.get("calls", []))

    @staticmethod
    def load_demo(config_id, subs: dict | None = None):
        """demos/<config_id>.json -> (user_lines, FakeLLM)."""
        text = (DEMOS / f"{config_id}.json").read_text(encoding="utf-8")
        if subs:
            for k, v in subs.items():
                text = text.replace(f"{{{{{k}}}}}", str(v))
        demo = json.loads(text)
        return [t["user"] for t in demo["turns"]], FakeLLM(r for t in demo["turns"] for r in t["llm"])


import logging
import os
import re
import time
from google import genai
from google.genai import errors, types

import httpx

_TIMEOUT_EXCEPTIONS = (TimeoutError, httpx.TimeoutException)

# Full Flash models only (no Lite), tried in order; out-of-quota ones are skipped until Google's retry time.
# gemini-3.5-flash is last: its free tier allows only 20 requests/day.
DEFAULT_MODELS = "gemini-3.6-flash,gemini-3-flash-preview,gemini-3.5-flash"
# MINIMAL thinking measured ~2x faster per request than the model default with correct tool use (2026-10-07).
DEFAULT_THINKING = "minimal"

# Written into .env by older run.bat; Lite and 3.5-only, so swap it for the current list.
_LEGACY_MODELS = "gemini-3.5-flash,gemini-3.1-flash-lite"
# Pause after a model is overloaded (503/500) or times out; demand spikes usually pass within a minute.
_BUSY_PAUSE_S = 30

# model -> time.time() when it may be tried again (quota hit or busy). Shared by all calls in this process.
_COOLDOWN: dict[str, float] = {}


def _retry_after_s(e: Exception) -> float:
    """Google's RetryInfo delay from a 429, else 60 s; capped at a day."""
    m = re.search(r"retryDelay'?\"?:\s*'?\"?(\d+(?:\.\d+)?)s", str(e))
    return min(float(m.group(1)), 86400.0) if m else 60.0


def cooling_models() -> dict[str, int]:
    """Models paused (quota or busy), with seconds left."""
    now = time.time()
    return {m: int(t - now) for m, t in _COOLDOWN.items() if t > now}


def tool_to_declaration(spec: dict) -> types.FunctionDeclaration:
    """Convert JSON schema tool spec to types.FunctionDeclaration."""
    params = spec.get("parameters")
    clean_params = None
    if params is not None:
        clean_props = {}
        for prop_name, prop_spec in params.get("properties", {}).items():
            p = {}
            if "type" in prop_spec:
                p["type"] = prop_spec["type"]
            if "description" in prop_spec:
                p["description"] = prop_spec["description"]
            clean_props[prop_name] = p
        clean_params = {
            "type": params.get("type", "object"),
            "properties": clean_props,
        }
        if "required" in params:
            clean_params["required"] = list(params["required"])
    return types.FunctionDeclaration(
        name=spec["name"],
        description=spec.get("description", ""),
        parameters=clean_params,
    )


def convert_history(history: list) -> list:
    """Convert neutral history format to Gemini types.Content list."""
    contents = []
    for item in history:
        role = item.get("role")
        if role == "user":
            contents.append(
                types.Content(
                    role="user",
                    parts=[types.Part.from_text(text=item.get("text", ""))],
                )
            )
        elif role == "model":
            if item.get("raw") is not None:
                contents.append(item["raw"])
            else:
                parts = []
                text = item.get("text")
                if text:
                    parts.append(types.Part.from_text(text=text))
                for call in item.get("calls", []):
                    parts.append(
                        types.Part.from_function_call(
                            name=call["name"],
                            args=call.get("args") or {},
                        )
                    )
                if not parts:
                    parts.append(types.Part.from_text(text=""))
                contents.append(types.Content(role="model", parts=parts))
        elif role == "tool":
            parts = []
            for res in item.get("results", []):
                parts.append(
                    types.Part.from_function_response(
                        name=res.get("name", ""),
                        response=res.get("response"),
                    )
                )
            contents.append(types.Content(role="user", parts=parts))
    return contents


def _get(obj, key, default=None):
    return getattr(obj, key, default)


def parse_response(response) -> LLMReply:
    """Parse Gemini response into LLMReply, skipping thoughts."""
    if not response:
        return LLMReply()
    candidates = _get(response, "candidates")
    if not candidates:
        return LLMReply()
    candidate = candidates[0]
    finish_reason = _get(candidate, "finish_reason")
    if finish_reason and any(b in str(finish_reason).upper() for b in ("BLOCK", "SAFETY", "PROHIBITED")):
        return LLMReply()
    content = _get(candidate, "content")
    if content is None:
        return LLMReply()

    text_parts = []
    calls = []
    for part in _get(content, "parts") or []:
        if _get(part, "thought", False):
            continue
        t = _get(part, "text")
        if t:
            text_parts.append(t)
        fc = _get(part, "function_call")
        if fc:
            calls.append({"name": _get(fc, "name", ""), "args": dict(_get(fc, "args", {}) or {})})

    return LLMReply(
        text="".join(text_parts),
        calls=calls,
        raw=content,
    )


def _is_retryable(e: Exception) -> bool:
    if isinstance(e, errors.APIError) and getattr(e, "code", None) in (429, 500, 503, 504):
        return True
    return isinstance(e, _TIMEOUT_EXCEPTIONS)


class GeminiLLM:
    """Gemini LLM adapter using google-genai SDK."""

    def __init__(self, api_key: str, model: str, timeout_s: float = 10, client=None, thinking: str | None = None):
        self.api_key = api_key
        # time.monotonic() by which the current caller turn must be answered (set per turn by app.py); None = no limit.
        self.deadline: float | None = None
        # Gemini 3 thinking level (minimal/low/medium/high); None = model default. Lower = faster replies.
        self.thinking = thinking.strip().upper() if thinking and thinking.strip() else None
        if isinstance(model, str):
            self.models = [m.strip() for m in model.split(",") if m.strip()]
        elif isinstance(model, (list, tuple)):
            self.models = list(model)
        else:
            self.models = [model]
        self.model = self.models[0] if self.models else ""
        self.timeout_s = timeout_s
        self.client = client or genai.Client(
            api_key=api_key,
            http_options=types.HttpOptions(timeout=int(timeout_s * 1000)),
        )

    def chat(self, system: str, history: list, tools: list | None = None) -> LLMReply:
        contents = convert_history(history)
        tool_config = None
        if tools:
            tool_config = [types.Tool(function_declarations=[tool_to_declaration(t) for t in tools])]
        config = types.GenerateContentConfig(
            system_instruction=system,
            tools=tool_config,
            automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
            temperature=0.3,
            thinking_config=types.ThinkingConfig(thinking_level=self.thinking) if self.thinking else None,
        )

        # ponytail: raw content from model A replayed to fallback model B may lose thought-signature validity; acceptable for MVP.
        now = time.time()
        # Skip models out of quota; if every model is paused, try them all anyway (quota may be back).
        models = [m for m in self.models if _COOLDOWN.get(m, 0) <= now] or list(self.models)
        last_error = None
        for model in models:
            for attempt in range(2):
                # Only start a request that can time out before the turn's deadline (Google rejects deadlines < 10 s,
                # so the per-request timeout can't shrink; skip instead).
                if self.deadline and self.deadline - time.monotonic() < self.timeout_s:
                    raise last_error or TimeoutError("Turn time budget used up")
                try:
                    response = self.client.models.generate_content(
                        model=model,
                        contents=contents,
                        config=config,
                    )
                    return parse_response(response)
                except Exception as e:
                    if not _is_retryable(e):
                        raise
                    last_error = e
                    if getattr(e, "code", None) == 429:
                        # Out of quota: retrying this model is pointless until Google's retry time.
                        _COOLDOWN[model] = time.time() + _retry_after_s(e)
                        logging.warning("Gemini %s out of quota, pausing it for %ds", model, _retry_after_s(e))
                        break
                    if attempt == 1 or isinstance(e, _TIMEOUT_EXCEPTIONS):
                        # Overloaded/slow twice: skip it on the next turns too instead of re-paying the wait.
                        _COOLDOWN[model] = time.time() + _BUSY_PAUSE_S
                        logging.warning("Gemini %s busy (%s), pausing it for %ds", model, e, _BUSY_PAUSE_S)
                        break  # a timeout already cost timeout_s; move to the next model
                    time.sleep(1)
        if last_error is not None:
            raise last_error
        return LLMReply()


def make_llm(config_id: str, use_fake: bool = False, subs: dict | None = None):
    """Instantiate LLM: FakeLLM for demo/test mode, GeminiLLM for live mode."""
    if use_fake:
        hints, llm = FakeLLM.load_demo(config_id, subs=subs)
        return llm, hints
    api_key = os.environ["GEMINI_API_KEY"]
    model = os.environ.get("GEMINI_MODEL", DEFAULT_MODELS)
    if model.replace(" ", "") == _LEGACY_MODELS:
        model = DEFAULT_MODELS
    return GeminiLLM(api_key=api_key, model=model, thinking=os.environ.get("GEMINI_THINKING", DEFAULT_THINKING)), []
