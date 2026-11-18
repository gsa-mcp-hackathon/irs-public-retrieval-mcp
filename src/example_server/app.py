"""IRS retrieval entry point with existing FastMCP transport selection.

Domain modules register implemented tools; routes retain health/version reads.
Source layout also retains upstream example prompts/resources independently.
"""

from __future__ import annotations

import os

from fastmcp import FastMCP

from example_server.config import settings
from example_server.routes import register_routes
from example_server.tools import register_tools

mcp = FastMCP(
    name="IRS Public Retrieval",
    instructions=(
        "Anonymous public IRS.gov IRM passages, forms/instructions catalog lookup, "
        "and PDF retrieval. Request citations, product/year inputs, or official "
        "document URLs; inspect source identity, dates, notices, match status, "
        "and catalog continuation. Catalog attribution and PDF response media "
        "do not establish PDF-cover identity."
    ),
)

# Wire up everything the server exposes. Each aggregator lives in its submodule.
register_tools(mcp)
register_routes(mcp)


def main() -> None:
    """Start the server, choosing a transport based on the environment.

    Precedence:
      1. A platform-injected port (Databricks `DATABRICKS_APP_PORT` or a generic
         `PORT`) → run HTTP on that port. Cloud hosts set this for you.
      2. `MCP_TRANSPORT=streamable-http` in the environment → run HTTP on
         `MCP_HOST`:`MCP_PORT` (see config.py / .env).
      3. Otherwise → stdio, which is how local clients (Claude Desktop, Claude
         Code, Zed) launch the server as a subprocess.
    """
    platform_port = os.getenv("DATABRICKS_APP_PORT") or os.getenv("PORT")

    if platform_port:
        mcp.run(transport="http", host="0.0.0.0", port=int(platform_port))
    elif settings.mcp_transport == "streamable-http":
        mcp.run(
            transport="streamable-http",
            host=settings.mcp_host,
            port=settings.mcp_port,
        )
    else:
        mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
