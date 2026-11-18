"""Library-owned agent/MCP execution with raw tool observations."""

from __future__ import annotations

import json
import os
import secrets
import shutil
from contextlib import AsyncExitStack
from datetime import datetime, timezone
from pathlib import Path

from fastmcp import Client
from fastmcp.client.transports import StdioTransport
from pydantic_ai import Agent, ModelMessagesTypeAdapter, capture_run_messages
from pydantic_ai.mcp import MCPToolset
from pydantic_core import to_jsonable_python

from .errors import failure_details
from .models import anonymous_server_environment

REPO_ROOT = Path(__file__).resolve().parents[2]


class RecordingClient(Client):
    """Observe public library calls; protocol and conversion stay library-owned."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.observations: list[dict] = []

    async def call_tool(self, name, arguments=None, **kwargs):
        item = {
            "name": name,
            "arguments": arguments,
            "started_at_utc": datetime.now(timezone.utc).isoformat(),
        }
        self.observations.append(item)
        try:
            result = await super().call_tool(name, arguments, **kwargs)
            item["result"] = {
                "content": to_jsonable_python(result.content, by_alias=True),
                "structuredContent": to_jsonable_python(
                    result.structured_content, by_alias=True
                ),
                "isError": result.is_error,
            }
            return result
        except Exception as exc:
            item["error_type"] = type(exc).__name__
            raise
        finally:
            item["completed_at_utc"] = datetime.now(timezone.utc).isoformat()


class IrsPublicRetrievalAgent:
    def __init__(
        self, model, system_prompt: str, server_command: list[str] | None = None
    ):
        command = server_command or [
            shutil.which("uv") or "uv",
            "run",
            "--no-sync",
            "--project",
            str(REPO_ROOT),
            "example-server",
        ]
        transport = StdioTransport(
            command=command[0],
            args=command[1:],
            cwd=str(REPO_ROOT),
            env=anonymous_server_environment(dict(os.environ)),
            keep_alive=False,
        )
        self.client = RecordingClient(transport)
        self.toolset = MCPToolset(self.client, tool_error_behavior="failed")
        self.agent = Agent(
            model,
            instructions=system_prompt,
            toolsets=[self.toolset],
            model_settings={"temperature": 0},
            name="irs_public_retrieval_eval",
        )
        self.command = command
        self.stack = AsyncExitStack()
        self.connection: dict = {}

    async def __aenter__(self):
        try:
            await self.stack.enter_async_context(self.agent)
            tools = await self.client.list_tools()
            self.connection = {
                "protocol_version": self.client.protocol_version,
                "server_info": to_jsonable_python(self.client.server_info),
                "tools": [to_jsonable_python(tool, by_alias=True) for tool in tools],
                "command": self.command,
                "cwd": str(REPO_ROOT),
            }
            return self
        except BaseException:
            await self.stack.aclose()
            raise

    async def __aexit__(self, *args):
        await self.stack.aclose()

    async def run(self, query: str) -> dict:
        """Generation receives question only; reference data stays with evaluator."""
        start = len(self.client.observations)
        with capture_run_messages() as messages:
            try:
                result = await self.agent.run(query)
            except Exception as exc:
                failure = {
                    "answer": "",
                    **failure_details(exc),
                    "tool_calls": self.client.observations[start:],
                }
                try:
                    failure["messages"] = json.loads(
                        ModelMessagesTypeAdapter.dump_json(messages)
                    )
                except Exception as capture_error:
                    failure["message_capture_error_type"] = type(capture_error).__name__
                return failure
        return {
            "answer": result.output,
            "usage": to_jsonable_python(result.usage),
            "messages": json.loads(result.all_messages_json()),
            "tool_calls": self.client.observations[start:],
        }


async def smoke_test(model) -> dict:
    """Exercise actual model call, local function execution, and returned receipt."""
    observed = []
    receipt = secrets.token_hex(12)
    agent = Agent(model, model_settings={"temperature": 0})

    @agent.tool_plain
    def receipt_probe(value: str) -> str:
        """Return opaque execution receipt associated with supplied value."""
        observed.append(value)
        return f"{value}:{receipt}"

    result = await agent.run(
        "Call receipt_probe with value 'function-smoke', then reproduce its returned "
        "receipt exactly. Receipt is supplied only through function execution."
    )
    return {
        "function_calls": observed,
        "answer": result.output,
        "receipt_reproduced": f"function-smoke:{receipt}" in result.output,
        "messages": json.loads(result.all_messages_json()),
        "usage": to_jsonable_python(result.usage),
    }
