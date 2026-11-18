import asyncio
import json
from dataclasses import dataclass

from eval.phoenix.judges import create_judges, judge_evidence, judge_output
from eval.phoenix.models import ModelRole, anonymous_server_environment


def test_server_receives_network_context_without_model_credentials():
    result = anonymous_server_environment(
        {
            "PATH": "caller-path",
            "HTTPS_PROXY": "http://loopback",
            "OPENAI_API_KEY": "not-for-irs-server",
            "JUDGE_API_KEY": "not-for-irs-server",
            "PORT": "9999",
            "MCP_TRANSPORT": "streamable-http",
        }
    )
    assert result == {
        "PATH": "caller-path",
        "HTTPS_PROXY": "http://loopback",
        "MCP_TRANSPORT": "stdio",
        "PYTHONUTF8": "1",
    }


def test_role_receipt_retains_port_omits_credentials_and_query():
    role = ModelRole(
        "agent",
        "caller-model",
        base_url="http://user:secret@localhost:8243/v1?key=secret",
    )
    assert role.describe()["endpoint"] == "http://localhost:8243/v1"
    assert "secret" not in str(role.describe())


def test_judge_projection_omits_binary_but_retains_source_metadata():
    output = {
        "tool_calls": [
            {"result": {"blob": "YWJj", "uri": "https://www.irs.gov/file.pdf"}}
        ]
    }
    evidence = judge_evidence(output)
    assert "YWJj" not in evidence
    assert "https://www.irs.gov/file.pdf" in evidence
    assert output["tool_calls"][0]["result"]["blob"] == "YWJj"


def test_judges_receive_failed_generation_and_complete_blob_disposition():
    output = {
        "answer": "",
        "error_type": "ModelHTTPError",
        "http_status": 413,
        "source_frames": [{"file": "C:/private/local-frame.py"}],
        "api_key": "not-for-judge-context",
        "tool_calls": [{"result": {"resource": {"blob": "YWJj"}}}],
    }
    serialized = judge_evidence(output)
    evidence = json.loads(serialized)
    assert evidence["generation"] == {
        "outcome": "failed",
        "error_type": "ModelHTTPError",
        "http_status": 413,
        "answer_present": False,
        "failure_disposition": "request_payload_too_large",
    }
    resource = evidence["tool_calls"][0]["result"]["resource"]["blob"]
    assert resource["complete_returned_blob_retained_in_raw_tool_record"] is True
    assert resource["projection"] == "whole_returned_blob_omitted_from_judge_context"
    assert "YWJj" not in serialized
    assert "private/local-frame" not in serialized
    assert "not-for-judge-context" not in serialized


def test_judge_scores_preserve_dataclass_fields_and_errors():
    @dataclass
    class Score:
        label: str
        explanation: str

    class Successful:
        async def async_evaluate(self, values):
            assert values["query"] == "question"
            return [Score("incorrect", "wrong literal")]

    class Failed:
        async def async_evaluate(self, values):
            raise RuntimeError("unavailable")

    result = asyncio.run(
        judge_output(
            {"correctness": Successful(), "scope": Failed()},
            {"input": {"query": "question"}, "expected": {}},
            {"answer": "answer"},
        )
    )
    assert result["correctness"][0]["label"] == "incorrect"
    assert result["scope"] == {"error_type": "RuntimeError", "status": "unassessed"}


def test_judge_factory_keeps_retry_setting_with_library_and_closes_clients(monkeypatch):
    import sys
    from types import SimpleNamespace

    captured = {}

    def llm(**kwargs):
        # Installed Phoenix OpenAI factory supplies max_retries=0 itself.
        assert "max_retries" not in kwargs
        captured.update(kwargs)
        return object()

    monkeypatch.setitem(
        sys.modules,
        "phoenix.evals",
        SimpleNamespace(LLM=llm, ClassificationEvaluator=lambda **kwargs: kwargs),
    )

    async def probe():
        async with create_judges(
            ModelRole(
                "judge",
                "caller-model",
                base_url="http://localhost:8123/v1",
                api_key="synthetic-key",
            )
        ) as judges:
            assert "{evidence}" in judges["scope"]["prompt_template"]
            assert not captured["async_client_kwargs"]["http_client"].is_closed

    asyncio.run(probe())
    assert captured["async_client_kwargs"]["http_client"].is_closed
    assert captured["sync_client_kwargs"]["http_client"].is_closed
