#!/usr/bin/env python3
"""Initialize anonymous Streamable HTTP MCP sessions and discover tools.

Uses installed MCP SDK Streamable HTTP support in caller-selected environments.
Discovery validates protocol responses without calling tools.
"""

from __future__ import annotations

import argparse
import asyncio
import inspect
import json
import math
import sys
from collections.abc import Collection, Sequence
from urllib.parse import urlsplit, urlunsplit

from mcp import ClientSession, types

try:
    from mcp.client import streamable_http as http_transport
except ImportError:
    http_transport = None

# SDK 1.x uses streamablehttp_client; SDK 2.x uses streamable_http_client.
streamable_http_client = getattr(
    http_transport, "streamable_http_client", None
) or getattr(http_transport, "streamablehttp_client", None)


class ProbeError(Exception):
    """Report incomplete or unexpected discovery."""


def _parse_url(url: str):
    endpoint = urlsplit(url)
    if endpoint.scheme not in {"http", "https"} or not endpoint.hostname:
        raise ProbeError("MCP endpoint must use HTTP or HTTPS with hostname.")
    if endpoint.username is not None or endpoint.password is not None:
        raise ProbeError("Anonymous probes require URLs without credentials.")
    if "\r" in url or "\n" in url:
        raise ProbeError("Probe URLs must exclude literal line breaks.")
    return endpoint


def resolve_app_urls(url: str) -> tuple[str, str]:
    """Resolve caller application roots or explicit MCP paths before requests."""
    endpoint = _parse_url(url)
    path = endpoint.path.rstrip("/")
    base_path = path.removesuffix("/mcp")
    health = urlunsplit(endpoint._replace(path=base_path + "/health", fragment=""))
    mcp = urlunsplit(endpoint._replace(path=base_path + "/mcp", fragment=""))
    return health, mcp


async def discover(
    endpoint_url: str,
    *,
    expected_tools: Collection[str] = (),
    timeout_seconds: float = 60.0,
) -> dict[str, object]:
    """Check caller endpoints and expectations within caller-adjustable budgets."""
    _parse_url(endpoint_url)
    if not math.isfinite(timeout_seconds) or timeout_seconds <= 0:
        raise ProbeError("Timeout seconds must be positive and finite.")
    if streamable_http_client is None:
        raise ProbeError(
            "Installed MCP SDK lacks Streamable HTTP client support; "
            "select compatible Python environments. Verified runtime: MCP 2.3.0."
        )

    names: set[str] = set()
    seen_cursors: set[str] = set()
    pages = 0
    async with asyncio.timeout(timeout_seconds):
        async with streamable_http_client(endpoint_url) as streams:
            # SDK 1.x also returns session-ID callbacks after these streams.
            read, write = streams[:2]
            async with ClientSession(read, write) as session:
                initialized = await session.initialize()
                uses_params = (
                    "params" in inspect.signature(session.list_tools).parameters
                )
                cursor = None
                while True:
                    params = (
                        types.PaginatedRequestParams(cursor=cursor)
                        if cursor is not None
                        else None
                    )
                    if uses_params:
                        listed = await session.list_tools(params=params)
                    else:
                        listed = await session.list_tools(cursor=cursor)
                    listing = listed.model_dump(by_alias=True)
                    pages += 1
                    names.update(tool.name for tool in listed.tools)
                    cursor = listing.get("nextCursor")
                    if cursor is None:
                        break
                    if cursor in seen_cursors:
                        raise ProbeError(
                            "Tool discovery repeated continuation cursor; "
                            "completion remains unverified."
                        )
                    seen_cursors.add(cursor)

    missing = set(expected_tools) - names
    if missing:
        raise ProbeError(f"Expected tools missing: {', '.join(sorted(missing))}")

    initialization = initialized.model_dump(
        mode="json", by_alias=True, exclude_none=True
    )
    return {
        "endpoint": endpoint_url,
        "protocol_version": initialization["protocolVersion"],
        "server": initialization["serverInfo"],
        "tool_names": sorted(names),
        "discovery_pages": pages,
        "expected_tools": sorted(set(expected_tools)),
        "verified": ["MCP initialization", "complete tool discovery"],
        "tools_called": False,
        "unverified": ["IRS retrieval", "PDF understanding", "client platform use"],
    }


def _failure_message(error: BaseException) -> str:
    if isinstance(error, BaseExceptionGroup):
        return "; ".join(_failure_message(child) for child in error.exceptions)
    if isinstance(error, TimeoutError):
        return "Probe time budget expired; discovery remains unverified."
    return f"{type(error).__name__}: {error}"


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("url", help="Exact Streamable HTTP MCP endpoint URL.")
    parser.add_argument(
        "--resolve-app-url",
        action="store_true",
        help="Print health/MCP URLs for application roots or MCP URLs; no requests.",
    )
    parser.add_argument(
        "--expect-tool",
        action="append",
        default=[],
        help="Require discovered tool name; repeat for further expectations.",
    )
    parser.add_argument(
        "--timeout-seconds",
        type=float,
        default=60.0,
        help=(
            "Overall probe budget in seconds (default: 60); "
            "increase for expected cold starts or longer discovery."
        ),
    )
    arguments = parser.parse_args(argv)
    try:
        if arguments.resolve_app_url:
            # Shell consumers require LF separators even with Windows Python.
            output = "\n".join(resolve_app_urls(arguments.url)) + "\n"
            sys.stdout.buffer.write(output.encode("utf-8"))
            return 0
        result = asyncio.run(
            discover(
                arguments.url,
                expected_tools=arguments.expect_tool,
                timeout_seconds=arguments.timeout_seconds,
            )
        )
    except Exception as error:
        print(f"FAIL: {_failure_message(error)}", file=sys.stderr)
        return 1
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
