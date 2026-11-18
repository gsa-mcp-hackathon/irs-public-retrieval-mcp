import asyncio
import json
from types import SimpleNamespace

import pytest
from pydantic_ai import Agent, ModelMessagesTypeAdapter
from pydantic_ai.messages import ModelResponse, TextPart, ToolCallPart, ToolReturnPart
from pydantic_ai.models.function import FunctionModel
from pydantic_ai.usage import RequestUsage
from pydantic_core import to_jsonable_python

from eval.phoenix import agent as module

SOURCE = {
    "url": "https://www.irs.gov/caller-selected-reference",
    "text": "Caller-owned public reference text.",
}


def subject(sdk_agent, observations):
    # Exercise maintained run method without constructing stdio transport.
    wrapper = object.__new__(module.IrsPublicRetrievalAgent)
    wrapper.agent = sdk_agent
    wrapper.client = SimpleNamespace(observations=observations)
    return wrapper


def add_reference_tool(agent, observations):
    @agent.tool_plain
    def lookup_reference(key: str) -> dict:
        """Read caller-owned offline reference."""
        assert key == "public-reference"
        observations.append(
            {"name": "lookup_reference", "arguments": {"key": key}, "result": SOURCE}
        )
        return SOURCE


def reference_call():
    return ModelResponse(
        [ToolCallPart("lookup_reference", {"key": "public-reference"})],
        usage=RequestUsage(input_tokens=17, output_tokens=5),
    )


def returned_reference(messages):
    return [
        part
        for message in messages
        for part in message.parts
        if isinstance(part, ToolReturnPart) and part.tool_name == "lookup_reference"
    ]


@pytest.mark.asyncio
async def test_failed_followup_retains_model_tool_source_and_error_history(monkeypatch):
    observations = [{"name": "earlier-unrelated-call"}]
    calls = 0

    async def model(messages, info):
        nonlocal calls
        calls += 1
        if calls == 1:
            return reference_call()
        assert returned_reference(messages)[0].content == SOURCE
        raise ValueError("controlled adapter failure")

    sdk_agent = Agent(
        FunctionModel(model), instructions="Use supplied public references."
    )
    add_reference_tool(sdk_agent, observations)
    monkeypatch.setenv("AGENT_API_KEY", "synthetic-unrelated-environment-secret")
    output = await subject(sdk_agent, observations).run("Read public reference.")

    assert calls == 2
    assert output["answer"] == ""
    assert output["error_type"] == "ValueError"
    assert any(frame["function"] == "model" for frame in output["source_frames"])
    assert output["tool_calls"] == observations[1:]
    messages = ModelMessagesTypeAdapter.validate_python(output["messages"])
    assert returned_reference(messages)[0].content == SOURCE
    response = next(
        message for message in output["messages"] if message["kind"] == "response"
    )
    assert response["usage"]["input_tokens"] == 17
    assert response["usage"]["output_tokens"] == 5
    assert "usage" not in output  # Failed-request totals are unavailable.
    assert "synthetic-unrelated-environment-secret" not in json.dumps(output)
    assert "controlled adapter failure" not in json.dumps(output)


@pytest.mark.asyncio
async def test_tool_failure_preserves_prior_exchange_and_interrupted_state():
    observations = []
    calls = 0

    async def model(messages, info):
        nonlocal calls
        calls += 1
        if calls == 1:
            return reference_call()
        assert returned_reference(messages)[0].content == SOURCE
        return ModelResponse([ToolCallPart("inspect_reference", {})])

    sdk_agent = Agent(FunctionModel(model))
    add_reference_tool(sdk_agent, observations)

    @sdk_agent.tool_plain
    def inspect_reference() -> str:
        """Exercise controlled local adapter failure after reference acquisition."""
        raise RuntimeError("controlled tool failure")

    output = await subject(sdk_agent, observations).run("Read and inspect reference.")
    assert output["error_type"] == "RuntimeError"
    messages = ModelMessagesTypeAdapter.validate_python(output["messages"])
    assert returned_reference(messages)[0].content == SOURCE
    assert output["messages"][-1]["kind"] == "request"
    assert output["messages"][-1]["state"] == "interrupted"
    assert any(
        frame["function"] == "inspect_reference" for frame in output["source_frames"]
    )


@pytest.mark.asyncio
async def test_success_output_matches_original_sdk_result():
    observations = []
    results = []

    async def model(messages, info):
        if not returned_reference(messages):
            return reference_call()
        return ModelResponse([TextPart("Answer supported by supplied reference.")])

    sdk_agent = Agent(FunctionModel(model))
    add_reference_tool(sdk_agent, observations)

    async def recorded_run(query):
        result = await sdk_agent.run(query)
        results.append(result)
        return result

    output = await subject(SimpleNamespace(run=recorded_run), observations).run(
        "Read public reference."
    )
    (result,) = results
    assert output == {
        "answer": result.output,
        "usage": to_jsonable_python(result.usage),
        "messages": json.loads(result.all_messages_json()),
        "tool_calls": observations,
    }


@pytest.mark.asyncio
async def test_cancellation_propagates_and_capture_context_does_not_leak():
    observations = []

    async def cancelled_model(messages, info):
        if not returned_reference(messages):
            return reference_call()
        raise asyncio.CancelledError

    sdk_agent = Agent(FunctionModel(cancelled_model))
    add_reference_tool(sdk_agent, observations)
    with pytest.raises(asyncio.CancelledError):
        await subject(sdk_agent, observations).run("Cancelled public request.")

    async def next_model(messages, info):
        return ModelResponse([TextPart("Independent result.")])

    next_output = await subject(Agent(FunctionModel(next_model)), []).run(
        "Independent public request."
    )
    assert next_output["answer"] == "Independent result."
    assert "Cancelled public request." not in json.dumps(next_output["messages"])


@pytest.mark.asyncio
async def test_message_serialization_failure_preserves_original_error(monkeypatch):
    async def model(messages, info):
        raise ValueError("controlled generation failure")

    class FailingSerializer:
        @staticmethod
        def dump_json(messages):
            raise TypeError("controlled capture failure")

    monkeypatch.setattr(module, "ModelMessagesTypeAdapter", FailingSerializer)
    output = await subject(Agent(FunctionModel(model)), []).run("Public request.")
    assert output["error_type"] == "ValueError"
    assert output["message_capture_error_type"] == "TypeError"
    assert output["tool_calls"] == []
    assert "messages" not in output
