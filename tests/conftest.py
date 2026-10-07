import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


@pytest.fixture(autouse=True)
def _isolate_call_logs(tmp_path, monkeypatch):
    """Keep test calls out of the real logs/ folder and skip the live Gemini check at startup."""
    import app as app_module
    monkeypatch.setattr(app_module, "LOG_DIR", tmp_path / "logs")
    monkeypatch.setattr(app_module, "check_ai", lambda: app_module.AI_HEALTH)
