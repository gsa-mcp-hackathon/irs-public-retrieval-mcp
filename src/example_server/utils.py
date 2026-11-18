"""Shared helpers: HTTP client, response formatting, and pagination.

Import these from your tool modules instead of re-implementing them. Keeping
I/O and formatting here keeps each tool file focused on its own logic.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from html.parser import HTMLParser
from typing import Any, Iterator
from urllib.parse import unquote, urljoin, urlsplit, urlunsplit

import httpx

from example_server.models import SourceMetadata

# Legacy example helpers retain upstream sample controls.
# Federal APIs can be slow or intermittently unresponsive — always use an
# explicit timeout. Bump this for large exports.
DEFAULT_TIMEOUT = 30.0
MAX_RESPONSE_BYTES = 5_000_000

# Keep outbound origins operator-controlled. Do not replace this with a tool
# argument; add another narrowly scoped client when integrating another API.
API_BASE_URL = "https://api.example.gov/v1/"


class UpstreamServiceError(RuntimeError):
    """Sanitized external-service failure safe to return to an MCP client."""


def _validate_relative_path(path: str) -> str:
    """Reject paths that could select or escape the configured API origin."""
    parsed = urlsplit(path)
    decoded_path = parsed.path
    for _ in range(3):
        decoded = unquote(decoded_path)
        if decoded == decoded_path:
            break
        decoded_path = decoded
    segments = decoded_path.replace("\\", "/").split("/")
    if (
        not path
        or parsed.scheme
        or parsed.netloc
        or parsed.query
        or parsed.fragment
        or decoded_path.startswith(("/", "\\"))
        or any(segment in {".", ".."} for segment in segments)
    ):
        raise ValueError("path must be a relative API path without a query or fragment")
    return path


async def fetch_json(
    path: str,
    params: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
    timeout: float = DEFAULT_TIMEOUT,
) -> Any:
    """GET a path from the fixed API origin and return parsed JSON.

    Raises:
        ValueError: if path could select or escape the configured API origin.
        UpstreamServiceError: with a sanitized message for external failures.
    """
    safe_path = _validate_relative_path(path)
    try:
        async with httpx.AsyncClient(
            base_url=API_BASE_URL,
            follow_redirects=False,
            timeout=timeout,
            trust_env=False,
        ) as client:
            async with client.stream(
                "GET", safe_path, params=params, headers=headers
            ) as response:
                response.raise_for_status()
                content = bytearray()
                async for chunk in response.aiter_bytes():
                    content.extend(chunk)
                    if len(content) > MAX_RESPONSE_BYTES:
                        raise UpstreamServiceError(
                            "Upstream response exceeded the size limit."
                        )
                return json.loads(content)
    except UpstreamServiceError:
        raise
    except httpx.HTTPStatusError as exc:
        raise UpstreamServiceError(
            f"Upstream service returned status {exc.response.status_code}."
        ) from None
    except (httpx.DecodingError, json.JSONDecodeError, UnicodeDecodeError):
        raise UpstreamServiceError("Upstream service returned invalid JSON.") from None
    except httpx.RequestError:
        raise UpstreamServiceError("Upstream service request failed.") from None


def paginate(items: list[Any], limit: int, offset: int) -> dict[str, Any]:
    """Slice a list and return a standard pagination envelope.

    Returns a dict with `total`, `count`, `offset`, `items`, `has_more`, and
    `next_offset` — the shape recommended in the MCP best-practices guide.
    """
    total = len(items)
    window = items[offset : offset + limit]
    next_offset = offset + len(window)
    return {
        "total": total,
        "count": len(window),
        "offset": offset,
        "items": window,
        "has_more": next_offset < total,
        "next_offset": next_offset if next_offset < total else None,
    }


@dataclass(eq=False)
class HtmlNode:
    """HTML structure for source-specific domain parsing."""

    tag: str
    attrs: dict[str, str] = field(default_factory=dict)
    children: list["HtmlNode | str"] = field(default_factory=list)
    parent: "HtmlNode | None" = field(default=None, repr=False)

    def iter(self, tag: str | None = None) -> Iterator["HtmlNode"]:
        if tag is None or self.tag == tag:
            yield self
        for child in self.children:
            if isinstance(child, HtmlNode):
                yield from child.iter(tag)

    def text(self, separator: str = " ") -> str:
        if self.tag in {"script", "style", "template"}:
            return ""
        pieces = []
        for child in self.children:
            value = child.text(separator) if isinstance(child, HtmlNode) else child
            value = re.sub(r"\s+", " ", value).strip()
            if value:
                pieces.append(value)
        return separator.join(pieces)


class _SourceHTMLParser(HTMLParser):
    _VOID = {
        "area",
        "base",
        "br",
        "col",
        "embed",
        "hr",
        "img",
        "input",
        "link",
        "meta",
        "param",
        "source",
        "track",
        "wbr",
    }

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.root = HtmlNode("document")
        self.stack = [self.root]

    def handle_starttag(self, tag, attrs) -> None:
        node = HtmlNode(tag, dict((key, value or "") for key, value in attrs))
        node.parent = self.stack[-1]
        node.parent.children.append(node)
        if tag not in self._VOID:
            self.stack.append(node)

    def handle_startendtag(self, tag, attrs) -> None:
        self.handle_starttag(tag, attrs)
        if tag not in self._VOID:
            self.handle_endtag(tag)

    def handle_endtag(self, tag) -> None:
        for index in range(len(self.stack) - 1, 0, -1):
            if self.stack[index].tag == tag:
                del self.stack[index:]
                break

    def handle_data(self, data) -> None:
        self.stack[-1].children.append(data)


def parse_html(text: str) -> HtmlNode:
    """Retain HTML node order for domain-specific extraction."""
    parser = _SourceHTMLParser()
    parser.feed(text)
    parser.close()
    return parser.root


def public_irs_url(base: str, href: str) -> str:
    """Resolve links within supported anonymous IRS.gov web origins."""
    candidate = urljoin(base, href)
    try:
        parsed = urlsplit(candidate)
        valid = (
            parsed.scheme == "https"
            and parsed.hostname in {"www.irs.gov", "irs.gov"}
            and parsed.port in {None, 443}
            and parsed.username is None
            and parsed.password is None
        )
    except ValueError:
        valid = False
    if not valid:
        raise ValueError("Supported anonymous HTTPS IRS.gov URL required.")
    return candidate


@dataclass
class FetchedPage:
    text: str
    source: SourceMetadata


@dataclass
class FetchedBytes:
    content: bytes
    source: SourceMetadata


def _positive_environment_number(name: str, *, integer: bool = False):
    raw = os.environ.get(name)
    if raw is None or raw == "":
        return None
    try:
        value = int(raw) if integer else float(raw)
    except ValueError:
        raise ValueError(f"{name} requires positive numeric configuration.") from None
    if value <= 0 or value == float("inf") or value != value:
        raise ValueError(f"{name} requires positive numeric configuration.")
    return value


async def fetch_irs_bytes(
    url: str,
    params: dict[str, Any] | None = None,
    *,
    media_types: set[str],
    response_kind: str,
) -> FetchedBytes:
    """Read anonymous public bytes with deployment-local network controls."""
    requested = public_irs_url(url, url)
    parsed = urlsplit(requested)
    target = urlunsplit(parsed._replace(fragment=""))
    timeout = _positive_environment_number("IRS_HTTP_TIMEOUT_SECONDS")
    byte_limit = _positive_environment_number("IRS_HTTP_MAX_BYTES", integer=True)
    visited: set[str] = set()
    try:
        async with httpx.AsyncClient(
            follow_redirects=False, trust_env=True, timeout=timeout
        ) as client:
            while True:
                request = client.build_request("GET", target, params=params)
                request_url = str(request.url)
                if request_url in visited or len(visited) > client.max_redirects:
                    raise UpstreamServiceError("IRS source redirect did not resolve.")
                visited.add(request_url)
                if len(visited) == 1:
                    requested = request_url
                async with client.stream("GET", target, params=params) as response:
                    if response.status_code in {301, 302, 303, 307, 308}:
                        location = response.headers.get("location")
                        if not location:
                            raise UpstreamServiceError(
                                "IRS redirect lacked destination."
                            )
                        target = public_irs_url(str(response.url), location)
                        target = urlunsplit(urlsplit(target)._replace(fragment=""))
                        params = None
                        continue
                    response.raise_for_status()
                    content_type = response.headers.get("content-type", "")
                    media_type = content_type.split(";", 1)[0].strip().lower()
                    if media_type not in media_types:
                        raise UpstreamServiceError(
                            "IRS source returned unsupported "
                            f"{response_kind} media type."
                        )
                    content = bytearray()
                    async for chunk in response.aiter_bytes():
                        content.extend(chunk)
                        if byte_limit is not None and len(content) > byte_limit:
                            raise UpstreamServiceError(
                                "IRS response exceeded configured byte budget."
                            )
                    return FetchedBytes(
                        content=bytes(content),
                        source=SourceMetadata(
                            requested_url=requested,
                            url=str(response.url),
                            retrieved_at_utc=datetime.now(timezone.utc).isoformat(),
                            content_type=content_type,
                            status_code=response.status_code,
                        ),
                    )
    except httpx.HTTPStatusError as exc:
        raise UpstreamServiceError(
            f"IRS source returned HTTP {exc.response.status_code}."
        ) from None
    except httpx.RequestError:
        raise UpstreamServiceError("IRS source request failed.") from None


async def fetch_irs_html(url: str, params: dict[str, Any] | None = None) -> FetchedPage:
    """Read anonymous public HTML with deployment-local network controls."""
    fetched = await fetch_irs_bytes(
        url,
        params,
        media_types={"text/html", "application/xhtml+xml"},
        response_kind="HTML",
    )
    decoded = httpx.Response(
        fetched.source.status_code,
        headers={"content-type": fetched.source.content_type},
        content=fetched.content,
    )
    return FetchedPage(text=decoded.text, source=fetched.source)
