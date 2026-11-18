"""Typed IRS retrieval results alongside retained upstream example inputs."""

from __future__ import annotations

from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field


class ResponseFormat(str, Enum):
    """How a tool should shape its return value.

    - JSON     → machine-readable dict/list (best for chaining tool calls)
    - MARKDOWN → human-readable text (best for direct display)
    """

    JSON = "json"
    MARKDOWN = "markdown"


class PaginationParams(BaseModel):
    """Reusable pagination inputs for list-style tools.

    Federal APIs almost always paginate. Expose these to the caller (or handle
    paging internally) and return `has_more` / `next_offset` in your response.
    """

    limit: int = Field(
        default=20,
        ge=1,
        le=100,
        description="Maximum number of items to return (1–100).",
    )
    offset: int = Field(
        default=0,
        ge=0,
        description="Number of items to skip from the start of the result set.",
    )


class SourceMetadata(BaseModel):
    """Observed anonymous public response identity."""

    requested_url: str
    url: str
    retrieved_at_utc: str
    content_type: str
    status_code: int


class IrsDocumentResult(BaseModel):
    """Acquisition metadata accompanying embedded PDF bytes."""

    source: SourceMetadata
    byte_count: int


class SourceDate(BaseModel):
    """Native date wording with individually attributed meaning."""

    value: str
    meaning: str
    context: str = ""


class SourceBodyLink(BaseModel):
    """Visible wording, decoded source href, and document-relative destination."""

    text: str
    href: str
    url: str | None


class SourceBodyImage(BaseModel):
    """Decoded image attributes and document-relative HTTP(S) destination."""

    src: str | None
    alt: str | None
    url: str | None


class SourceBlock(BaseModel):
    """Ordered passage content retaining block role."""

    kind: str
    text: str
    links: list[SourceBodyLink] = Field(default_factory=list)
    images: list[SourceBodyImage] = Field(default_factory=list)


class SourceLink(BaseModel):
    """Literal link wording and resolved public destination."""

    text: str
    url: str
    reached_citation: str | None = None
    reached_title: str | None = None


class IrmPassage(BaseModel):
    citation: str
    title: str
    url: str
    blocks: list[SourceBlock]
    dates: list[SourceDate]


class IrmPassageResult(BaseModel):
    requested_citation: str
    match_disposition: Literal["matched", "not_found", "ambiguous"]
    passages: list[IrmPassage]
    navigation: list[SourceLink]
    notices: list[str]
    extent: str
    document_citation: str
    source: SourceMetadata
    route_source: SourceMetadata | None = None
    document_route: SourceLink | None = None


class CatalogContinuation(BaseModel):
    """Source-provided page link bound to caller search context."""

    url: str
    source_url: str | None = None
    catalog: Literal["current", "prior"]
    query: str
    tax_year: int | None = Field(
        default=None,
        description=(
            "Requested annual Revision Date filter retained for continuation "
            "context; tax-year applicability remains unverified."
        ),
    )


class ProductMatch(BaseModel):
    product: str
    title: str
    year: str | None = Field(
        description=(
            "Complete four-digit annual catalog Revision Date label; null for "
            "other revision wording. Tax-year applicability remains unverified."
        )
    )
    url: str
    catalog: Literal["current", "prior"]
    catalog_url: str
    dates: list[SourceDate]
    related_links: list[SourceLink]
    identity_basis: str = "catalog attribution"
    catalog_fields: dict[str, str]


class CatalogPage(BaseModel):
    source: SourceMetadata
    catalog: Literal["current", "prior"]
    rows_observed: int
    source_extent: str
    catalog_structure_recognized: bool = True
    next: CatalogContinuation | None = None
    pagination_disposition: Literal[
        "available", "not_observed", "unresolved", "unassessed"
    ] = Field(
        default="unassessed",
        description=(
            "Observed source navigation: usable continuation, no Next observed, "
            "unresolved Next/structure, or unassessed. Unresolved navigation can "
            "retain usable siblings; no Next observed establishes no wider "
            "catalog-completeness claim."
        ),
    )


class ProductsResult(BaseModel):
    query: str
    tax_year: int | None = Field(
        description=(
            "Requested annual Revision Date filter echoed from caller; "
            "tax-year applicability remains unverified."
        )
    )
    catalog: Literal["current", "prior", "both"]
    matches: list[ProductMatch]
    catalog_failures: dict[str, str] = Field(default_factory=dict)
    notices: list[str]
    extent: str
    pages: list[CatalogPage]
