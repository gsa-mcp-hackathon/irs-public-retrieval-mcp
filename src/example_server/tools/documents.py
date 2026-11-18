"""Anonymous public IRS PDF acquisition."""

from __future__ import annotations

import base64

from fastmcp import FastMCP
from fastmcp.tools import ToolResult
from mcp import types as mcp_types

from example_server.models import IrsDocumentResult
from example_server.utils import fetch_irs_bytes


def register(mcp: FastMCP) -> None:
    """Register anonymous IRS PDF retrieval."""

    @mcp.tool(
        name="get_irs_document",
        output_schema=IrsDocumentResult.model_json_schema(),
        annotations={
            "title": "Get IRS PDF document",
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": True,
        },
    )
    async def get_irs_document(document_url: str) -> ToolResult:
        """Retrieve anonymous public IRS PDF bytes from document_url.

        Supply catalog matches[].url or another supported HTTPS IRS.gov URL.
        Returns embedded application/pdf content with final source URL and
        acquisition metadata. PDF text extraction and edition validation
        require separate inspection.
        """
        fetched = await fetch_irs_bytes(
            document_url, media_types={"application/pdf"}, response_kind="PDF"
        )
        metadata = IrsDocumentResult(
            source=fetched.source, byte_count=len(fetched.content)
        )
        return ToolResult(
            content=[
                mcp_types.EmbeddedResource(
                    type="resource",
                    resource=mcp_types.BlobResourceContents(
                        uri=fetched.source.url,
                        mimeType="application/pdf",
                        blob=base64.b64encode(fetched.content).decode("ascii"),
                    ),
                ),
                mcp_types.TextContent(type="text", text=metadata.model_dump_json()),
            ],
            structured_content=metadata.model_dump(),
        )
