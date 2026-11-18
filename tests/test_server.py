"""Registration and deployment-selected transport behavior."""

from __future__ import annotations

import os

import pytest
from fastmcp import FastMCP

from example_server import app
from example_server.app import mcp
from example_server.config import Settings


def test_server_is_importable():
    assert mcp is not None


def test_server_has_name():
    assert mcp.name == "IRS Public Retrieval"


@pytest.fixture
def transport_environment(monkeypatch):
    for name in tuple(os.environ):
        if name.casefold() == "mcp_transport":
            monkeypatch.delenv(name)
    return monkeypatch


def test_default_transport_is_stdio(transport_environment):
    """Unset configuration retains stdio independently from local dotenv files."""
    assert Settings(_env_file=None).mcp_transport == "stdio"


@pytest.mark.parametrize("name", ["MCP_TRANSPORT", "mcp_transport", "McP_TrAnSpOrT"])
def test_transport_configuration_accepts_environment(name, transport_environment):
    transport_environment.setenv(name, "streamable-http")
    assert Settings(_env_file=None).mcp_transport == "streamable-http"


@pytest.mark.parametrize(
    ("platform_env", "configured_transport", "expected"),
    [
        ({}, "stdio", {"transport": "stdio"}),
        ({"PORT": ""}, "stdio", {"transport": "stdio"}),
        (
            {},
            "streamable-http",
            {"transport": "streamable-http", "host": "127.0.0.7", "port": 9321},
        ),
        (
            {"PORT": "8123"},
            "stdio",
            {"transport": "http", "host": "0.0.0.0", "port": 8123},
        ),
        (
            {"DATABRICKS_APP_PORT": "8765", "PORT": "8123"},
            "streamable-http",
            {"transport": "http", "host": "0.0.0.0", "port": 8765},
        ),
    ],
)
def test_main_uses_selected_transport(
    platform_env, configured_transport, expected, monkeypatch
):
    """Select caller settings or platform ports without starting listeners."""
    for name in ("DATABRICKS_APP_PORT", "PORT"):
        monkeypatch.delenv(name, raising=False)
    for name, value in platform_env.items():
        monkeypatch.setenv(name, value)
    monkeypatch.setattr(
        app,
        "settings",
        Settings(
            _env_file=None,
            mcp_transport=configured_transport,
            mcp_host="127.0.0.7",
            mcp_port=9321,
        ),
    )
    calls = []
    monkeypatch.setattr(app.mcp, "run", lambda **kwargs: calls.append(kwargs))

    app.main()

    assert calls == [expected]


def test_tools_register_without_error():
    from example_server.tools import register_tools

    register_tools(FastMCP("test"))  # must not raise


def test_prompts_register_without_error():
    from example_server.prompts import register_prompts

    register_prompts(FastMCP("test"))  # must not raise


def test_resources_register_without_error():
    from example_server.resources import register_resources

    register_resources(FastMCP("test"))  # must not raise


def test_routes_register_without_error():
    from example_server.routes import register_routes

    register_routes(FastMCP("test"))  # must not raise


@pytest.mark.asyncio
async def test_irs_tools_are_discoverable():
    """Implemented IRS tools remain discoverable through MCP."""
    tools = await mcp.list_tools()
    tool_names = {t.name for t in tools}
    assert {"get_irm_passage", "find_irs_products", "get_irs_document"} <= tool_names
