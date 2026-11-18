"""PDF acquisition checks through controlled HTTP and actual MCP clients."""

from __future__ import annotations

import base64
import json
from datetime import datetime, timezone

import httpx
import pytest
from fastmcp import Client, FastMCP
from fastmcp.exceptions import ToolError

from example_server import utils
from example_server.tools import documents


def http_transport(monkeypatch, handler):
    monkeypatch.delenv("IRS_HTTP_MAX_BYTES", raising=False)
    monkeypatch.delenv("IRS_HTTP_TIMEOUT_SECONDS", raising=False)
    original = httpx.AsyncClient
    calls = []
    client_options = []

    def recorded_handler(request):
        calls.append(str(request.url))
        return handler(request)

    def client(**kwargs):
        client_options.append(kwargs)
        return original(transport=httpx.MockTransport(recorded_handler), **kwargs)

    monkeypatch.setattr(utils.httpx, "AsyncClient", client)
    return calls, client_options


async def call_document(document_url):
    server = FastMCP("IRS document checks")
    documents.register(server)
    async with Client(server) as client:
        return await client.call_tool(
            "get_irs_document", {"document_url": document_url}
        )


def returned_pdf(result):
    assert not result.is_error
    (embedded,) = [item for item in result.content if item.type == "resource"]
    assert result.content[0] is embedded
    (receipt,) = [item for item in result.content if item.type == "text"]
    assert json.loads(receipt.text) == result.structured_content
    assert embedded.resource.mime_type == "application/pdf"
    return embedded.resource


@pytest.mark.parametrize(
    "document_url",
    [
        "https://www.irs.gov/pub/irs-pdf/f1040.pdf",
        "https://www.irs.gov/pub/irs-prior/i1040gi--2021.pdf",
        "https://www.irs.gov/pub/irs-pdf/p15.pdf",
        "https://irs.gov/pub/irs-prior/f941--2020.pdf",
        "https://www.irs.gov/download?asset=opaque-94c7&year=1881",
    ],
)
@pytest.mark.asyncio
async def test_mcp_document_returns_exact_bytes_and_source_metadata(
    monkeypatch, document_url
):
    content = b"%PDF-1.7\n\x00\xff\x80\r\nopaque response bytes\n%%EOF\n"
    content_type = "Application/PDF; observed=synthetic"
    calls, options = http_transport(
        monkeypatch,
        lambda request: httpx.Response(
            200, content=content, headers={"content-type": content_type}
        ),
    )
    result = await call_document(document_url)
    resource = returned_pdf(result)
    assert base64.b64decode(resource.blob, validate=True) == content
    assert resource.uri == document_url
    metadata = result.structured_content
    assert metadata["byte_count"] == len(content)
    assert set(metadata) == {"source", "byte_count"}
    source = metadata["source"]
    assert source["requested_url"] == document_url
    assert source["url"] == resource.uri
    assert source["content_type"] == content_type
    assert source["status_code"] == 200
    assert datetime.fromisoformat(source["retrieved_at_utc"]).tzinfo == timezone.utc
    assert calls == [document_url]
    assert options[0]["follow_redirects"] is False
    assert options[0]["trust_env"] is True
    assert options[0]["timeout"] is None


@pytest.mark.asyncio
async def test_document_schema_and_read_only_annotations_are_discoverable():
    server = FastMCP("IRS document discovery")
    documents.register(server)
    async with Client(server) as client:
        (tool,) = await client.list_tools()
    assert tool.name == "get_irs_document"
    assert tool.input_schema["required"] == ["document_url"]
    assert tool.output_schema["required"] == ["source", "byte_count"]
    assert tool.annotations.read_only_hint is True
    assert tool.annotations.destructive_hint is False
    assert tool.annotations.idempotent_hint is True
    assert tool.annotations.open_world_hint is True


@pytest.mark.asyncio
async def test_document_redirect_binds_resource_to_final_source(monkeypatch):
    initial = "https://www.irs.gov/download?asset=opaque#page=2"
    final = "https://www.irs.gov/pub/irs-prior/observed-file.pdf?edition=2022"
    content = b"\x00\xffPDF response"

    def handler(request):
        if request.url.path == "/download":
            return httpx.Response(
                308,
                headers={
                    "location": "/pub/irs-prior/observed-file.pdf?edition=2022#page=1"
                },
            )
        return httpx.Response(
            200, content=content, headers={"content-type": "application/pdf"}
        )

    calls, _ = http_transport(monkeypatch, handler)
    result = await call_document(initial)
    resource = returned_pdf(result)
    assert resource.uri == final
    assert base64.b64decode(resource.blob) == content
    assert result.structured_content["source"]["requested_url"] == (
        "https://www.irs.gov/download?asset=opaque"
    )
    assert result.structured_content["source"]["url"] == final
    assert calls == ["https://www.irs.gov/download?asset=opaque", final]


@pytest.mark.parametrize(
    "url",
    [
        "http://www.irs.gov/pub/file.pdf",
        "https://www.irs.gov.example.com/file.pdf",
        "https://localhost/file.pdf",
        "https://user:secret@www.irs.gov/file.pdf",
        "https://www.irs.gov:8443/file.pdf",
        "file:///pub/file.pdf",
    ],
)
@pytest.mark.asyncio
async def test_document_rejects_unsupported_origin_before_request(monkeypatch, url):
    calls, options = http_transport(
        monkeypatch, lambda request: pytest.fail("Unexpected request")
    )
    with pytest.raises(ToolError, match="Supported anonymous HTTPS IRS.gov URL"):
        await call_document(url)
    assert calls == []
    assert options == []


@pytest.mark.parametrize(
    "destination",
    ["https://example.com/file.pdf", "http://www.irs.gov/file.pdf"],
)
@pytest.mark.asyncio
async def test_document_rejects_redirect_before_next_request(monkeypatch, destination):
    url = "https://www.irs.gov/opaque"
    calls, _ = http_transport(
        monkeypatch,
        lambda request: httpx.Response(302, headers={"location": destination}),
    )
    with pytest.raises(ToolError, match="Supported anonymous HTTPS IRS.gov URL"):
        await call_document(url)
    assert calls == [url]


@pytest.mark.parametrize("redirect_mode", ["loop", "missing", "exhaustion"])
@pytest.mark.asyncio
async def test_document_unresolved_redirects_fail(monkeypatch, redirect_mode):
    url = "https://www.irs.gov/route/0"

    def handler(request):
        if redirect_mode == "missing":
            return httpx.Response(302)
        destination = "/route/0"
        if redirect_mode == "loop":
            destination = "/route/1" if request.url.path.endswith("0") else "/route/0"
        if redirect_mode == "exhaustion":
            destination = f"/route/{int(request.url.path.rsplit('/', 1)[1]) + 1}"
        return httpx.Response(302, headers={"location": destination})

    calls, _ = http_transport(monkeypatch, handler)
    expected = "lacked destination" if redirect_mode == "missing" else "did not resolve"
    with pytest.raises(ToolError, match=expected):
        await call_document(url)
    if redirect_mode == "missing":
        assert calls == [url]
    elif redirect_mode == "loop":
        assert calls == [url, "https://www.irs.gov/route/1"]
    else:
        assert len(calls) == len(set(calls))
        assert calls[0] == url
        assert len(calls) > 2


@pytest.mark.parametrize("status", [403, 404, 503])
@pytest.mark.asyncio
async def test_document_status_failure_is_sanitized(monkeypatch, status):
    http_transport(
        monkeypatch,
        lambda request: httpx.Response(
            status, content=b"private diagnostic", headers={"content-type": "text/html"}
        ),
    )
    with pytest.raises(ToolError, match=f"IRS source returned HTTP {status}") as error:
        await call_document("https://www.irs.gov/opaque")
    assert "private diagnostic" not in str(error.value)


@pytest.mark.parametrize("failure", [httpx.ConnectError, httpx.ReadTimeout])
@pytest.mark.asyncio
async def test_document_transport_failure_is_sanitized(monkeypatch, failure):
    def handler(request):
        raise failure("private diagnostic", request=request)

    http_transport(monkeypatch, handler)
    with pytest.raises(ToolError, match="IRS source request failed") as error:
        await call_document("https://www.irs.gov/opaque")
    assert "private diagnostic" not in str(error.value)


@pytest.mark.parametrize("content_type", ["text/html", "application/octet-stream", ""])
@pytest.mark.asyncio
async def test_document_requires_pdf_response_media(monkeypatch, content_type):
    http_transport(
        monkeypatch,
        lambda request: httpx.Response(
            200, content=b"%PDF-1.7\n", headers={"content-type": content_type}
        ),
    )
    with pytest.raises(ToolError, match="unsupported PDF media type"):
        await call_document("https://www.irs.gov/opaque.pdf")


@pytest.mark.asyncio
async def test_document_configured_byte_boundary_and_timeout(monkeypatch):
    content = b"\x00\xffresponse bytes"
    _, options = http_transport(
        monkeypatch,
        lambda request: httpx.Response(
            200, content=content, headers={"content-type": "application/pdf"}
        ),
    )
    monkeypatch.setenv("IRS_HTTP_TIMEOUT_SECONDS", "2.75")
    monkeypatch.setenv("IRS_HTTP_MAX_BYTES", str(len(content)))
    result = await call_document("https://www.irs.gov/opaque")
    assert base64.b64decode(returned_pdf(result).blob) == content
    assert options[0]["timeout"] == 2.75
    monkeypatch.setenv("IRS_HTTP_MAX_BYTES", str(len(content) - 1))
    with pytest.raises(ToolError, match="configured byte budget"):
        await call_document("https://www.irs.gov/opaque")


@pytest.mark.asyncio
async def test_document_byte_exhaustion_closes_stream_before_remaining_content(
    monkeypatch,
):
    observed = []

    class ContentStream(httpx.AsyncByteStream):
        async def __aiter__(self):
            for chunk in [b"PDF", b"\x00\xff", b"unread remainder"]:
                observed.append(chunk)
                yield chunk

        async def aclose(self):
            observed.append("closed")

    http_transport(
        monkeypatch,
        lambda request: httpx.Response(
            200, stream=ContentStream(), headers={"content-type": "application/pdf"}
        ),
    )
    monkeypatch.setenv("IRS_HTTP_MAX_BYTES", "3")
    with pytest.raises(ToolError, match="configured byte budget"):
        await call_document("https://www.irs.gov/opaque")
    assert observed == [b"PDF", b"\x00\xff", "closed"]


@pytest.mark.parametrize(
    "name,value",
    [
        ("IRS_HTTP_TIMEOUT_SECONDS", "nan"),
        ("IRS_HTTP_TIMEOUT_SECONDS", "0"),
        ("IRS_HTTP_MAX_BYTES", "-1"),
        ("IRS_HTTP_MAX_BYTES", "1.5"),
    ],
)
@pytest.mark.asyncio
async def test_document_invalid_deployment_control_prevents_request(
    monkeypatch, name, value
):
    calls, options = http_transport(
        monkeypatch, lambda request: pytest.fail("Unexpected request")
    )
    monkeypatch.setenv(name, value)
    with pytest.raises(ToolError, match="positive numeric configuration"):
        await call_document("https://www.irs.gov/opaque")
    assert calls == []
    assert options == []
