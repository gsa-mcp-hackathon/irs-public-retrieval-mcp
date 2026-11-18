import asyncio
import json
import sys
from contextlib import contextmanager
from io import StringIO
from pathlib import Path
from types import SimpleNamespace

from eval.phoenix import run_experiment as module


def test_function_transport_with_different_echo_continues_domain_cases(monkeypatch):
    calls = []

    class Sink(StringIO):
        last_flushed = 0

        def flush(self):
            self.last_flushed = self.tell()

    sink = Sink()

    def expect_phase(name):
        latest = json.loads(sink.getvalue().splitlines()[-1])
        assert latest["kind"] == "phase_started"
        assert latest["phase"] == name
        assert sink.last_flushed == sink.tell()

    class Client:
        def __init__(self, **kwargs):
            pass

        async def __aenter__(self):
            expect_phase("model_client_setup")
            return self

        async def __aexit__(self, *args):
            calls.append("model_client_closed")

    class Role:
        api_key = "synthetic-value"
        base_url = "http://localhost:1/v1"

        def describe(self):
            return {"configured_model": "caller-model"}

        def agent_model(self, client):
            return "offline-model"

    class Agent:
        connection = {"protocol_version": "offline-fixture"}

        def __init__(self, model, prompt, command):
            assert prompt == "caller-selected procedure"

        async def __aenter__(self):
            expect_phase("mcp_connection")
            calls.append("mcp_entered")
            return self

        async def __aexit__(self, *args):
            calls.append("mcp_closed")

        async def run(self, query):
            expect_phase("agent_case")
            assert query == "source question"
            calls.append("domain_case")
            return {"answer": "source answer", "tool_calls": []}

    async def smoke(model):
        expect_phase("function_smoke")
        return {"function_calls": ["observed"], "receipt_reproduced": False}

    monkeypatch.setitem(sys.modules, "openai", SimpleNamespace(AsyncOpenAI=Client))
    monkeypatch.setitem(
        sys.modules,
        "eval.phoenix.agent",
        SimpleNamespace(IrsPublicRetrievalAgent=Agent, smoke_test=smoke),
    )
    monkeypatch.setattr(module.ModelRole, "from_environment", lambda *args: Role())
    monkeypatch.setattr(
        module,
        "load_examples",
        lambda path: [
            {
                "id": "caller-case",
                "input": {"query": "source question"},
                "expected": {"responses": "HIDDEN REFERENCE"},
                "metadata": {},
            }
        ],
    )
    original_read_text = Path.read_text

    def read_text(path, *args, **kwargs):
        if path == Path("caller-procedure.txt"):
            return "caller-selected procedure"
        return original_read_text(path, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", read_text)
    args = SimpleNamespace(
        agent_model="caller-model",
        judge_model=None,
        no_judge=True,
        smoke_only=False,
        dataset=Path("caller-cases.jsonl"),
        case_id=None,
        system_prompt=Path("caller-procedure.txt"),
        server_command=None,
    )
    status = asyncio.run(module.run(args, sink, {}, {}))
    records = [json.loads(line) for line in sink.getvalue().splitlines()]
    assert status == 0
    assert (
        next(row for row in records if row["kind"] == "function_smoke")["result"][
            "receipt_reproduced"
        ]
        is False
    )
    assert next(row for row in records if row["kind"] == "case")["id"] == "caller-case"
    returned = next(i for i, row in enumerate(records) if row["kind"] == "agent_return")
    case_recorded = next(i for i, row in enumerate(records) if row["kind"] == "case")
    assert returned < case_recorded
    assert calls == ["mcp_entered", "domain_case", "mcp_closed", "model_client_closed"]


def test_tracing_phase_is_flushed_before_failed_startup(monkeypatch):
    from eval.phoenix import tracing

    sink = StringIO()

    @contextmanager
    def writer(*args, **kwargs):
        yield sink

    @contextmanager
    def fail_startup(*args, **kwargs):
        record = json.loads(sink.getvalue().splitlines()[-1])
        assert record["kind"] == "phase_started"
        assert record["phase"] == "tracing_setup"
        raise RuntimeError("not-a-provider-failure")
        yield

    monkeypatch.setattr(Path, "mkdir", lambda *args, **kwargs: None)
    monkeypatch.setattr(Path, "open", writer)
    monkeypatch.setattr(tracing, "tracing", fail_startup)
    monkeypatch.setattr(sys, "argv", ["eval", "--output", "caller-output.jsonl"])
    assert module.main() == 1
    records = [json.loads(line) for line in sink.getvalue().splitlines()]
    assert records[-1]["kind"] == "execution_failed"
    assert records[-1]["phase"] == "tracing_setup"
    assert "not-a-provider-failure" not in str(records)
