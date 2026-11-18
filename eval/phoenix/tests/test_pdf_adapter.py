import base64
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastmcp import FastMCP
from pydantic_ai import BinaryContent
from pydantic_ai.mcp import MCPToolset

from eval.phoenix.agent import RecordingClient


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "document_url",
    [
        "https://www.irs.gov/pub/irs-pdf/caller-document.pdf",
        "https://irs.gov/download?asset=caller-selected&year=2024",
    ],
)
async def test_installed_adapter_preserves_receipt_and_binary(
    monkeypatch, document_url
):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[3] / "src"))
    from example_server.tools import documents

    content = b"%PDF-1.7\n\x00\xff\x80 caller-owned synthetic bytes\n%%EOF\n"
    metadata = documents.IrsDocumentResult(
        source={
            "requested_url": document_url,
            "url": document_url,
            "retrieved_at_utc": "2026-11-17T01:00:00+00:00",
            "content_type": "application/pdf",
            "status_code": 200,
        },
        byte_count=len(content),
    )

    async def fetch(url, **kwargs):
        assert url == document_url
        return SimpleNamespace(source=metadata.source, content=content)

    monkeypatch.setattr(documents, "fetch_irs_bytes", fetch)
    server = FastMCP("Offline receipt conversion")
    documents.register(server)
    client = RecordingClient(server)
    async with MCPToolset(client) as tools:
        mapped = await tools.direct_call_tool(
            "get_irs_document", {"document_url": document_url}
        )

    (binary,) = [part for part in mapped if isinstance(part, BinaryContent)]
    (receipt,) = [part for part in mapped if isinstance(part, dict)]
    assert binary.data == content
    assert binary.media_type == "application/pdf"
    assert receipt == metadata.model_dump()
    assert receipt["source"]["url"] == document_url
    (observation,) = client.observations
    raw = observation["result"]
    assert raw["structuredContent"] == receipt
    assert raw["content"][0]["type"] == "resource"
    resource = raw["content"][0]["resource"]
    assert resource["uri"] == document_url
    assert base64.b64decode(resource["blob"], validate=True) == content
