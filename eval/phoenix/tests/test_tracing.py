import os
import tempfile
from contextlib import contextmanager
from io import StringIO
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest

from eval.phoenix import tracing as module


@pytest.mark.parametrize("prior", [None, "caller-existing-workdir"])
@pytest.mark.parametrize("fault", ["body", "register", "flush", "shutdown", "service"])
def test_cleanup_restores_context_after_faults(monkeypatch, prior, fault):
    import sys

    events = []
    old_temp = tempfile.tempdir
    if prior is None:
        monkeypatch.delenv("PHOENIX_WORKING_DIR", raising=False)
    else:
        monkeypatch.setenv("PHOENIX_WORKING_DIR", prior)
    monkeypatch.setattr(Path, "mkdir", lambda *args, **kwargs: None)

    class Agent:
        _instrument_default = "previous-instrumentation"

        @staticmethod
        def instrument_all(value):
            Agent._instrument_default = value

    def fail_at(stage):
        events.append(stage)
        if fault == stage:
            raise RuntimeError(stage)

    provider = SimpleNamespace(
        force_flush=lambda: fail_at("flush"),
        shutdown=lambda: fail_at("shutdown"),
    )

    def register(**kwargs):
        fail_at("register")
        return provider

    @contextmanager
    def service(*args):
        try:
            yield {"endpoint": "http://127.0.0.1:8123/v1/traces", "process_id": 42}
        finally:
            fail_at("service")

    monkeypatch.setattr(module, "local_service", service)
    monkeypatch.setitem(sys.modules, "phoenix.otel", SimpleNamespace(register=register))
    monkeypatch.setitem(sys.modules, "pydantic_ai", SimpleNamespace(Agent=Agent))
    monkeypatch.setitem(
        sys.modules,
        "pydantic_ai.models.instrumented",
        SimpleNamespace(InstrumentationSettings=lambda **kwargs: kwargs),
    )
    with pytest.raises(RuntimeError):
        with module.tracing(Path("owned-cache"), "caller-project", None, True):
            fail_at("body")
    assert os.environ.get("PHOENIX_WORKING_DIR") == prior
    assert tempfile.tempdir == old_temp
    assert Agent._instrument_default == "previous-instrumentation"
    assert "service" in events
    if fault != "register":
        assert "flush" in events
        assert "shutdown" in events


def test_owned_service_stops_after_body_error_and_filters_credentials(monkeypatch):
    events = []
    captured = {}

    class Process:
        pid = 42

        def poll(self):
            return None

        def terminate(self):
            events.append("terminate")

        def wait(self, **kwargs):
            events.append("wait")

    def popen(command, **kwargs):
        captured.update(command=command, **kwargs)
        return Process()

    class Http:
        def __init__(self, **kwargs):
            assert kwargs["trust_env"] is False

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def get(self, url):
            assert url.endswith("/readyz")
            return SimpleNamespace(status_code=200)

    monkeypatch.setenv("OPENAI_API_KEY", "not-for-trace-service")
    monkeypatch.setattr(module.subprocess, "Popen", popen)
    monkeypatch.setattr(Path, "open", lambda *args, **kwargs: StringIO())
    monkeypatch.setattr(httpx, "Client", Http)
    with pytest.raises(RuntimeError, match="body failure"):
        with module.local_service(Path("owned-cache")) as receipt:
            assert receipt["process_id"] == 42
            raise RuntimeError("body failure")
    assert events == ["terminate", "wait"]
    assert captured["env"]["PHOENIX_HOST"] == "127.0.0.1"
    assert "OPENAI_API_KEY" not in captured["env"]
    assert "--no-internet" in captured["command"]
