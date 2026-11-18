"""HTTP protocol checks without cloud, IRS, or subprocess requests."""

from __future__ import annotations

import asyncio
import importlib.util
import inspect
import json
import unittest
from contextlib import asynccontextmanager
from pathlib import Path
from unittest.mock import patch

from mcp import ClientSession, types
from starlette.requests import Request
from starlette.responses import JSONResponse

try:
    import httpx2
    from mcp.client.streamable_http import streamable_http_client
    from mcp.server.lowlevel import Server
    from mcp.server.streamable_http_manager import StreamableHTTPSessionManager

    CURRENT_HTTP_FIXTURES = "on_list_tools" in inspect.signature(Server).parameters
except ImportError:
    CURRENT_HTTP_FIXTURES = False

PROBE_PATH = Path(__file__).resolve().parents[1] / "tools/check_mcp_http.py"
SPEC = importlib.util.spec_from_file_location("check_mcp_http", PROBE_PATH)
probe = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(probe)

IRS_TOOLS = ("get_irm_passage", "find_irs_products", "get_irs_document")
ENDPOINT = "http://localhost/custom/mcp"


def tool(name):
    return types.Tool(name=name, inputSchema={"type": "object"})


@asynccontextmanager
async def use_asgi(app, *, legacy_streams=False):
    async with httpx2.AsyncClient(
        transport=httpx2.ASGITransport(app=app), trust_env=False
    ) as client:

        @asynccontextmanager
        async def transport(url):
            async with streamable_http_client(url, http_client=client) as streams:
                yield (
                    (*streams, lambda: "fixture-session") if legacy_streams else streams
                )

        with patch.object(probe, "streamable_http_client", transport):
            yield


@asynccontextmanager
async def serve(list_tools, *, legacy_streams=False):
    server = Server("HTTP fixture", version="test", on_list_tools=list_tools)
    manager = StreamableHTTPSessionManager(server, json_response=True)
    requests = []

    async def app(scope, receive, send):
        body = bytearray()

        async def record_receive():
            message = await receive()
            if message["type"] == "http.request":
                body.extend(message.get("body", b""))
                if not message.get("more_body", False) and body:
                    requests.append(
                        {
                            "path": scope["path"],
                            "headers": dict(scope["headers"]),
                            **json.loads(body),
                        }
                    )
            return message

        await manager.handle_request(scope, record_receive, send)

    async with manager.run(), use_asgi(app, legacy_streams=legacy_streams):
        yield requests


@unittest.skipUnless(
    CURRENT_HTTP_FIXTURES,
    "HTTP integration fixtures require current SDK server/client APIs; "
    "legacy client support retains separate source-backed shape evidence.",
)
class HttpProbeTests(unittest.IsolatedAsyncioTestCase):
    async def test_initializes_stateful_http_and_discovers_expected_tools(self):
        async def list_tools(context, params):
            return types.ListToolsResult(tools=[tool(name) for name in IRS_TOOLS])

        async with serve(list_tools) as requests:
            result = await probe.discover(ENDPOINT, expected_tools=IRS_TOOLS)

        self.assertEqual(result["tool_names"], sorted(IRS_TOOLS))
        self.assertEqual(result["discovery_pages"], 1)
        self.assertIs(result["tools_called"], False)
        self.assertEqual(
            [request["method"] for request in requests],
            ["initialize", "notifications/initialized", "tools/list"],
        )
        self.assertEqual({request["path"] for request in requests}, {"/custom/mcp"})
        session_ids = [
            request["headers"].get(b"mcp-session-id") for request in requests
        ]
        self.assertIsNone(session_ids[0])
        self.assertTrue(session_ids[1])
        self.assertEqual(session_ids[1], session_ids[2])
        self.assertTrue(
            all(b"authorization" not in request["headers"] for request in requests)
        )

    async def test_follows_continuation_until_expected_tools_are_discovered(self):
        cursors = []

        async def list_tools(context, params):
            cursor = params.cursor if params else None
            cursors.append(cursor)
            if cursor is None:
                return types.ListToolsResult(tools=[tool("first")], nextCursor="")
            if cursor == "":
                return types.ListToolsResult(tools=[], nextCursor="last-page")
            return types.ListToolsResult(tools=[tool("caller_chosen_tool")])

        async with serve(list_tools):
            result = await probe.discover(
                ENDPOINT, expected_tools=["caller_chosen_tool"]
            )

        self.assertEqual(cursors, [None, "", "last-page"])
        self.assertEqual(result["discovery_pages"], 3)
        self.assertEqual(result["tool_names"], ["caller_chosen_tool", "first"])

    async def test_legacy_client_shapes_retain_http_session_and_continuation(self):
        # Public SDK v1.12.0 shapes: three streams, list_tools(cursor), wire aliases.
        # https://github.com/modelcontextprotocol/python-sdk/tree/v1.12.0/src/mcp
        class WireResult:
            def __init__(self, result):
                self.result = result
                self.tools = getattr(result, "tools", None)

            def model_dump(self, **kwargs):
                return self.result.model_dump(**kwargs)

        class LegacySession:
            def __init__(self, read, write):
                self.current = ClientSession(read, write)

            async def __aenter__(self):
                await self.current.__aenter__()
                return self

            async def __aexit__(self, *args):
                return await self.current.__aexit__(*args)

            async def initialize(self):
                return WireResult(await self.current.initialize())

            async def list_tools(self, cursor=None):
                params = types.PaginatedRequestParams(cursor=cursor)
                return WireResult(await self.current.list_tools(params=params))

        cursors = []

        async def list_tools(context, params):
            cursors.append(params.cursor if params else None)
            return types.ListToolsResult(
                tools=[tool("first" if len(cursors) == 1 else "wanted")],
                nextCursor="continue" if len(cursors) == 1 else None,
            )

        async with serve(list_tools, legacy_streams=True):
            with patch.object(probe, "ClientSession", LegacySession):
                result = await probe.discover(ENDPOINT, expected_tools=["wanted"])
        self.assertEqual(cursors, [None, "continue"])
        self.assertEqual(result["tool_names"], ["first", "wanted"])

    async def test_current_irs_app_http_discovery_without_tool_execution(self):
        from example_server.app import mcp

        app = mcp.http_app(json_response=True)
        async with app.lifespan(app), use_asgi(app):
            result = await probe.discover(
                "http://localhost/mcp", expected_tools=IRS_TOOLS
            )
        self.assertEqual(result["tool_names"], sorted(IRS_TOOLS))
        self.assertEqual(result["server"]["name"], "IRS Public Retrieval")
        self.assertIs(result["tools_called"], False)

    async def test_missing_expected_tools_fails_after_complete_discovery(self):
        async def list_tools(context, params):
            return types.ListToolsResult(tools=[tool("unrelated")])

        async with serve(list_tools):
            with self.assertRaisesRegex(
                probe.ProbeError, "Expected tools missing: wanted"
            ):
                await probe.discover(ENDPOINT, expected_tools=["wanted"])

    async def test_repeated_cursor_cannot_claim_complete_discovery(self):
        async def list_tools(context, params):
            return types.ListToolsResult(tools=[tool("wanted")], nextCursor="again")

        async with serve(list_tools):
            with self.assertRaises(Exception) as captured:
                await probe.discover(ENDPOINT, expected_tools=["wanted"])
        self.assertIn(
            "repeated continuation cursor", probe._failure_message(captured.exception)
        )

    async def test_jsonrpc_session_error_never_passes_as_discovery(self):
        for status_code in (200, 400, 500):
            with self.subTest(status_code=status_code):

                async def app(scope, receive, send):
                    request = await Request(scope, receive).json()
                    response = JSONResponse(
                        {
                            "jsonrpc": "2.0",
                            "id": request["id"],
                            "error": {"code": -32000, "message": "Missing session ID"},
                        },
                        status_code=status_code,
                    )
                    await response(scope, receive, send)

                async with use_asgi(app):
                    with self.assertRaises(Exception):
                        await probe.discover(ENDPOINT)

    async def test_caller_time_budget_bounds_stalled_discovery(self):
        async def list_tools(context, params):
            await asyncio.Event().wait()

        async with serve(list_tools):
            with self.assertRaises(Exception) as captured:
                await probe.discover(ENDPOINT, timeout_seconds=0.05)
        self.assertIn("time budget expired", probe._failure_message(captured.exception))

    async def test_rejects_unbounded_or_invalid_caller_timeout(self):
        for timeout in (0, -1, float("inf"), float("nan")):
            with self.subTest(timeout=timeout):
                with self.assertRaisesRegex(probe.ProbeError, "positive and finite"):
                    await probe.discover(ENDPOINT, timeout_seconds=timeout)

    async def test_missing_streamable_http_capability_reports_prerequisite(self):
        with patch.object(probe, "streamable_http_client", None):
            with self.assertRaisesRegex(probe.ProbeError, "lacks Streamable HTTP"):
                await probe.discover(ENDPOINT)


class CliTests(unittest.TestCase):
    def test_resolution_cli_emits_utf8_lf_for_shell_consumers(self):
        with patch("sys.stdout") as stdout:
            self.assertEqual(
                probe.main(["http://localhost/mcp?tenant=x", "--resolve-app-url"]), 0
            )
        output = stdout.buffer.write.call_args.args[0]
        self.assertNotIn(b"\r", output)
        self.assertEqual(
            output.decode("utf-8").splitlines(),
            ["http://localhost/health?tenant=x", "http://localhost/mcp?tenant=x"],
        )

    def test_resolves_application_and_mcp_urls_with_queries_and_fragments(self):
        for supplied, prefix in (
            ("http://localhost", "http://localhost"),
            ("http://localhost/mcp/", "http://localhost"),
            ("http://localhost/nested/", "http://localhost/nested"),
            ("http://localhost/nested/mcp", "http://localhost/nested"),
        ):
            for suffix in ("", "?tenant=x", "?tenant=x#client-fragment"):
                with self.subTest(supplied=supplied, suffix=suffix):
                    query = "?tenant=x" if suffix else ""
                    self.assertEqual(
                        probe.resolve_app_urls(supplied + suffix),
                        (prefix + "/health" + query, prefix + "/mcp" + query),
                    )

    def test_url_credentials_fail_before_resolution_without_echoing_credentials(self):
        for url in ("http://name:secret@localhost/mcp", "http://name@localhost"):
            with self.subTest(url=url), patch("sys.stderr") as stderr:
                self.assertEqual(probe.main([url, "--resolve-app-url"]), 1)
                message = "".join(call.args[0] for call in stderr.write.call_args_list)
                self.assertIn("URLs without credentials", message)
                self.assertNotIn("name", message)
                self.assertNotIn("secret", message)

    def test_cli_reports_failure_with_nonzero_exit(self):
        async def fail(*args, **kwargs):
            raise probe.ProbeError("Expected tools missing: requested")

        with patch.object(probe, "discover", fail), patch("sys.stderr") as stderr:
            self.assertEqual(probe.main([ENDPOINT, "--expect-tool", "requested"]), 1)
        self.assertIn(
            "FAIL: ProbeError: Expected tools missing: requested",
            "".join(call.args[0] for call in stderr.write.call_args_list),
        )


if __name__ == "__main__":
    unittest.main()
