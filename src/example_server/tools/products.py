"""Public IRS catalog discovery retaining source continuation context."""

from __future__ import annotations

import asyncio
import re
from typing import Annotated, Literal
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from fastmcp import FastMCP
from pydantic import Field

from example_server.models import (
    CatalogContinuation,
    CatalogPage,
    ProductMatch,
    ProductsResult,
    SourceDate,
    SourceLink,
)
from example_server.utils import (
    FetchedPage,
    HtmlNode,
    UpstreamServiceError,
    fetch_irs_html,
    parse_html,
    public_irs_url,
)

Catalog = Literal["current", "prior"]
CatalogSelection = Literal["current", "prior", "both"]

_ORIGIN = "https://www.irs.gov"
_PATHS: dict[Catalog, str] = {
    "current": "/forms-instructions-and-publications",
    "prior": "/prior-year-forms-and-instructions",
}


def _context_url(
    url: str, catalog: Catalog, query: str, tax_year: int | None
) -> tuple[str, list[str]]:
    """Validate catalog identity and restore omitted caller filters."""
    safe_url = public_irs_url(_ORIGIN, url)
    parts = urlsplit(safe_url)
    if parts.path.rstrip("/") != _PATHS[catalog]:
        raise ValueError("Continuation URL must retain selected IRS catalog route.")
    pairs = parse_qsl(parts.query, keep_blank_values=True)
    expected = {"find": query}
    if catalog == "prior" and tax_year is not None:
        expected["date"] = str(tax_year)
    restored: list[str] = []
    for key, value in expected.items():
        supplied = [item for name, item in pairs if name == key]
        if supplied and any(item != value for item in supplied):
            raise ValueError(f"Continuation {key} conflicts with caller filters.")
        if not supplied:
            pairs.append((key, value))
            restored.append(key)
    for key in ("product_number", "title", "date"):
        if key not in expected and any(item for name, item in pairs if name == key):
            raise ValueError(f"Continuation {key} conflicts with caller filters.")
    return urlunsplit(parts._replace(query=urlencode(pairs), fragment="")), restored


def _url_identity(url: str) -> tuple[str, str, tuple[tuple[str, str], ...]]:
    parts = urlsplit(url)
    return (
        parts.netloc,
        parts.path.rstrip("/"),
        tuple(sorted(parse_qsl(parts.query, keep_blank_values=True))),
    )


def _content(root: HtmlNode, catalog: Catalog) -> HtmlNode | None:
    main = next(root.iter("main"), None)
    if main is None:
        return None
    for article in main.iter("article"):
        if article.attrs.get("about", "").rstrip("/") == _PATHS[catalog]:
            return article
    return main


def _catalog_table(content: HtmlNode) -> tuple[HtmlNode | None, list[HtmlNode]]:
    required = {"product number", "title", "revision date"}
    for table in content.iter("table"):
        headers = list(table.iter("th"))
        if required.issubset({header.text().casefold() for header in headers}):
            return table, headers
    return None, []


def _source_link(anchor: HtmlNode, base_url: str) -> SourceLink | None:
    href = anchor.attrs.get("href")
    if not href:
        return None
    try:
        url = public_irs_url(base_url, href)
    except ValueError:
        return None
    text = anchor.text() or anchor.attrs.get("title", "")
    return SourceLink(text=text, url=url)


def _inside(node: HtmlNode, ancestor: HtmlNode) -> bool:
    current: HtmlNode | None = node
    while current is not None:
        if current is ancestor:
            return True
        current = current.parent
    return False


def _related_content_links(
    content: HtmlNode, table: HtmlNode, product: str, base_url: str
) -> list[SourceLink]:
    """Retain explicitly named product links from surrounding catalog content."""
    links = []
    product_words = " ".join(re.findall(r"\w+", product.casefold()))
    if not product_words:
        return links
    for anchor in content.iter("a"):
        if _inside(anchor, table):
            continue
        wording = " ".join(
            re.findall(
                r"\w+", (anchor.text() + " " + anchor.attrs.get("title", "")).casefold()
            )
        )
        if not re.search(
            r"\b(instructions?|corrections?|changes|developments)\b", wording
        ):
            continue
        if f" {product_words} " not in f" {wording} ":
            continue
        link = _source_link(anchor, base_url)
        if link is not None:
            links.append(link)
    return links


def _next_page(
    content: HtmlNode,
    table: HtmlNode,
    base_url: str,
    catalog: Catalog,
    query: str,
    tax_year: int | None,
    notices: list[str],
) -> tuple[
    CatalogContinuation | None, Literal["available", "not_observed", "unresolved"]
]:
    scope = table.parent
    while scope is not None and "view" not in scope.attrs.get("class", "").split():
        scope = scope.parent
    scope = scope or content
    destinations: list[str] = []
    unresolved = False
    for anchor in scope.iter("a"):
        if "next" not in anchor.attrs.get("rel", "").split():
            continue
        link = _source_link(anchor, base_url)
        if link is None:
            unresolved = True
            notices.append(f"{catalog}: unsupported source Next destination withheld.")
        elif link.url not in destinations:
            destinations.append(link.url)
    if not destinations:
        return None, "unresolved" if unresolved else "not_observed"
    if len(destinations) != 1:
        notices.append(f"{catalog}: multiple source Next destinations require review.")
        return None, "unresolved"
    source_url = destinations[0]
    try:
        url, restored = _context_url(source_url, catalog, query, tax_year)
    except ValueError as exc:
        notices.append(f"{catalog}: source Next withheld. {exc}")
        return None, "unresolved"
    parts = urlsplit(url)
    pairs = parse_qsl(parts.query, keep_blank_values=True)
    supplied_keys = {key for key, _ in pairs}
    for key, value in parse_qsl(urlsplit(base_url).query, keep_blank_values=True):
        if key != "page" and key not in supplied_keys:
            pairs.append((key, value))
            if key not in restored:
                restored.append(key)
    url = urlunsplit(parts._replace(query=urlencode(pairs)))
    if _url_identity(url) == _url_identity(base_url):
        notices.append(f"{catalog}: source Next repeats observed catalog page.")
        return None, "unresolved"
    if restored:
        names = ", ".join(restored)
        notices.append(
            f"{catalog}: source Next omitted {names}; continuation.url restores "
            "observed filters and continuation.source_url retains literal source link."
        )
    return (
        CatalogContinuation(
            url=url,
            source_url=source_url,
            catalog=catalog,
            query=query,
            tax_year=tax_year,
        ),
        "unresolved" if unresolved else "available",
    )


def _parse_catalog(
    fetched: FetchedPage, catalog: Catalog, query: str, tax_year: int | None
) -> tuple[CatalogPage, list[ProductMatch], list[str]]:
    notices: list[str] = []
    content = _content(parse_html(fetched.text), catalog)
    table, headers = _catalog_table(content) if content is not None else (None, [])
    if content is None or table is None:
        notices.append(
            f"{catalog}: expected catalog table unavailable; "
            "product absence unverified."
        )
        return (
            CatalogPage(
                source=fetched.source,
                catalog=catalog,
                rows_observed=0,
                source_extent="Expected catalog table unavailable in returned HTML.",
                catalog_structure_recognized=False,
                pagination_disposition="unresolved",
            ),
            [],
            notices,
        )

    header_names = [header.text() for header in headers]
    header_ids = {
        header.attrs["id"]: header.text()
        for header in headers
        if header.attrs.get("id")
    }
    matches = []
    rows_observed = 0
    unqualified_years = 0
    unusable_rows = 0
    for row in table.iter("tr"):
        cells = [
            child
            for child in row.children
            if isinstance(child, HtmlNode) and child.tag == "td"
        ]
        if not cells:
            continue
        rows_observed += 1
        fields: dict[str, str] = {}
        field_nodes: dict[str, HtmlNode] = {}
        for index, cell in enumerate(cells):
            names = [
                header_ids[item]
                for item in cell.attrs.get("headers", "").split()
                if item in header_ids
            ]
            name = (
                names[0]
                if names
                else header_names[index]
                if index < len(header_names)
                else ""
            )
            if name:
                fields[name] = cell.text()
                field_nodes[name.casefold()] = cell
        number_cell = field_nodes.get("product number")
        title_cell = field_nodes.get("title")
        revision_cell = field_nodes.get("revision date")
        if number_cell is None or title_cell is None or revision_cell is None:
            unusable_rows += 1
            continue
        revision = revision_cell.text()
        year = revision if re.fullmatch(r"\d{4}", revision) else None
        if year is None:
            unqualified_years += 1
        if tax_year is not None and year != str(tax_year):
            continue
        document = next(
            (
                link
                for anchor in number_cell.iter("a")
                if (link := _source_link(anchor, fetched.source.url)) is not None
            ),
            None,
        )
        if document is None:
            unusable_rows += 1
            continue
        product = number_cell.text()
        related_links = [
            link
            for anchor in row.iter("a")
            if (link := _source_link(anchor, fetched.source.url)) is not None
            and link.url != document.url
        ]
        related_links.extend(
            _related_content_links(content, table, product, fetched.source.url)
        )
        unique_links = {link.url: link for link in related_links}
        matches.append(
            ProductMatch(
                product=product,
                title=title_cell.text(),
                year=year,
                url=document.url,
                catalog=catalog,
                catalog_url=fetched.source.url,
                dates=[
                    SourceDate(
                        value=value,
                        meaning=name,
                        context=f"{catalog} catalog row: {product}",
                    )
                    for name, value in fields.items()
                    if "date" in name.casefold() and value
                ],
                related_links=list(unique_links.values()),
                identity_basis=(
                    "Catalog product number, title, revision label, and document "
                    "link; document body unverified."
                ),
                catalog_fields=fields,
            )
        )
    summary = next(
        (
            node.text()
            for node in content.iter()
            if node.attrs.get("id") == "solr-results-summary"
        ),
        "Source result summary unavailable.",
    )
    if unqualified_years:
        notices.append(
            f"{catalog}: {unqualified_years} observed rows have month-dated or "
            "unqualified revision labels; tax-year applicability remains unverified."
            + (
                " Requested annual-year matching excludes those rows."
                if tax_year is not None
                else ""
            )
        )
    if unusable_rows:
        notices.append(
            f"{catalog}: {unusable_rows} observed rows lack usable identity/link "
            "structure; product absence remains unverified."
        )
    next_page, pagination_disposition = _next_page(
        content, table, fetched.source.url, catalog, query, tax_year, notices
    )
    return (
        CatalogPage(
            source=fetched.source,
            catalog=catalog,
            rows_observed=rows_observed,
            source_extent=summary,
            next=next_page,
            pagination_disposition=pagination_disposition,
        ),
        matches,
        notices,
    )


def register(mcp: FastMCP) -> None:
    """Register anonymous IRS catalog discovery."""

    @mcp.tool(
        name="find_irs_products",
        annotations={
            "title": "Find IRS forms, instructions, and publications",
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": True,
        },
    )
    async def find_irs_products(
        query: str,
        tax_year: Annotated[
            int | None,
            Field(
                description=(
                    "Filter complete four-digit annual catalog Revision Date "
                    "labels; month-dated revisions do not qualify. Tax-year "
                    "applicability remains unverified."
                )
            ),
        ] = None,
        catalog: CatalogSelection = "both",
        continuation: CatalogContinuation | None = None,
    ) -> ProductsResult:
        """Search current/prior public IRS catalogs using native Find semantics.

        Initial calls read one source page per selected catalog. Continuations
        read only their referenced catalog page and retain query/year context.
        Annual Revision Date labels supply year matching; month-stamped revision
        dates do not establish tax-year applicability. Catalog labels identify
        products and kinds; document bodies, PDF covers, and correction coverage
        remain unverified. Related links retain encountered catalog context.
        """
        if not query.strip():
            raise ValueError("query requires nonempty catalog search wording.")
        if catalog not in {"current", "prior", "both"}:
            raise ValueError("catalog requires current, prior, or both.")
        requests: list[tuple[Catalog, str, dict[str, str] | None]] = []
        if continuation is not None:
            if continuation.query != query or continuation.tax_year != tax_year:
                raise ValueError(
                    "Continuation query/year context conflicts with caller."
                )
            if catalog != "both" and continuation.catalog != catalog:
                raise ValueError(
                    "Continuation catalog conflicts with caller selection."
                )
            url, _ = _context_url(
                continuation.url, continuation.catalog, query, tax_year
            )
            if continuation.source_url is not None:
                source_request, _ = _context_url(
                    continuation.source_url, continuation.catalog, query, tax_year
                )
                source_parts = urlsplit(source_request)
                request_parts = urlsplit(url)
                source_pairs = parse_qsl(source_parts.query, keep_blank_values=True)
                request_pairs = parse_qsl(request_parts.query, keep_blank_values=True)
                source_keys = {key for key, _ in source_pairs}
                if (
                    source_parts.netloc != request_parts.netloc
                    or source_parts.path.rstrip("/") != request_parts.path.rstrip("/")
                    or any(
                        sorted(value for key, value in source_pairs if key == name)
                        != sorted(value for key, value in request_pairs if key == name)
                        for name in source_keys
                    )
                ):
                    raise ValueError(
                        "Continuation request differs from source Next context."
                    )
            requests.append((continuation.catalog, url, None))
        else:
            selected: list[Catalog] = (
                ["current", "prior"] if catalog == "both" else [catalog]
            )
            for selected_catalog in selected:
                params = {"find": query}
                if selected_catalog == "prior" and tax_year is not None:
                    params["date"] = str(tax_year)
                requests.append(
                    (selected_catalog, _ORIGIN + _PATHS[selected_catalog], params)
                )
        responses = await asyncio.gather(
            *(fetch_irs_html(url, params=params) for _, url, params in requests),
            return_exceptions=True,
        )
        pages: list[CatalogPage] = []
        matches: list[ProductMatch] = []
        catalog_failures: dict[str, str] = {}
        notices = [
            "Years reflect annual catalog Revision Date labels; tax-year "
            "applicability and document-body identity remain unverified."
        ]
        for (selected_catalog, _, _), response in zip(requests, responses):
            if isinstance(response, (UpstreamServiceError, ValueError)):
                catalog_failures[selected_catalog] = str(response)
                notices.append(f"{selected_catalog}: catalog read failed. {response}")
                continue
            if isinstance(response, BaseException):
                raise response
            try:
                _, missing_filters = _context_url(
                    response.source.url, selected_catalog, query, tax_year
                )
                if missing_filters:
                    raise ValueError(
                        "Final response URL omitted caller filters: "
                        + ", ".join(missing_filters)
                        + "."
                    )
                requested_pairs = parse_qsl(
                    urlsplit(response.source.requested_url).query,
                    keep_blank_values=True,
                )
                final_pairs = parse_qsl(
                    urlsplit(response.source.url).query, keep_blank_values=True
                )
                changed_controls = [
                    name
                    for name in dict.fromkeys(key for key, _ in requested_pairs)
                    if sorted(value for key, value in requested_pairs if key == name)
                    != sorted(value for key, value in final_pairs if key == name)
                ]
                if changed_controls:
                    raise ValueError(
                        "Final response URL dropped or changed requested controls: "
                        + ", ".join(changed_controls)
                        + "."
                    )
            except ValueError as exc:
                catalog_failures[selected_catalog] = str(exc)
                notices.append(
                    f"{selected_catalog}: response context changed; "
                    f"catalog attribution withheld. {exc}"
                )
                continue
            page, observed_matches, observed_notices = _parse_catalog(
                response, selected_catalog, query, tax_year
            )
            pages.append(page)
            matches.extend(observed_matches)
            notices.extend(observed_notices)
        if tax_year is not None:
            notices.append(
                "Year matching covers observed annual revision labels only; "
                "empty matches do not establish unavailable products."
            )
        return ProductsResult(
            query=query,
            tax_year=tax_year,
            catalog=catalog,
            pages=pages,
            matches=matches,
            catalog_failures=catalog_failures,
            notices=notices,
            extent=(
                "Observed catalog pages only; source summaries and Next links "
                "retain pagination extent. Document bodies/PDF covers, linked "
                "instruction/correction bodies, and exhaustive correction "
                "coverage remain unverified."
            ),
        )
