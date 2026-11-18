"""Current public IRM passages with matching from body hierarchy."""

from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import unquote, urljoin, urlsplit

from fastmcp import FastMCP

from example_server.models import (
    IrmPassage,
    IrmPassageResult,
    SourceBlock,
    SourceBodyImage,
    SourceBodyLink,
    SourceDate,
    SourceLink,
)
from example_server.utils import (
    HtmlNode,
    UpstreamServiceError,
    fetch_irs_html,
    parse_html,
    public_irs_url,
)

_CITATION = re.compile(r"\d+(?:\.\d+){2,}")
_DOCUMENT_PATH = re.compile(
    r"/irm/part(?P<route_part>\d+)/irm_(?P<part>\d+)-"
    r"(?P<chapter>\d+)-(?P<section>\d+)(?:[^\d/][^/]*)?"
)
_DATE = re.compile(
    r"\b(?:\d{2}-\d{2}-\d{4}|\d{1,2}-[A-Za-z]{3}-\d{4}|"
    r"[A-Za-z]+\s+\d{1,2},\s+\d{4})\b"
)
_HEADINGS = {"h1", "h2", "h3", "h4", "h5", "h6"}
_QUALIFICATIONS = {"note", "caution", "warning", "important", "tip", "example"}
_SKIP = {"script", "style", "template", "noscript"}


@dataclass
class _Section:
    node: HtmlNode
    citation: str
    title: str
    info: str


def _classes(node: HtmlNode) -> set[str]:
    return set(node.attrs.get("class", "").split())


def _children(node: HtmlNode) -> list[HtmlNode]:
    return [child for child in node.children if isinstance(child, HtmlNode)]


def _within(node: HtmlNode, ancestor: HtmlNode) -> bool:
    while node is not None:
        if node is ancestor:
            return True
        node = node.parent
    return False


def _canonical(citation: str) -> str:
    return ".".join(str(int(segment)) for segment in citation.split("."))


def _document_route(
    root: HtmlNode,
    index_url: str,
    document_citation: str,
) -> SourceLink:
    """Select unique observed part index link matching document numbers."""
    requested = tuple(int(segment) for segment in document_citation.split("."))
    routes: dict[str, SourceLink] = {}
    for anchor in root.iter("a"):
        href = anchor.attrs.get("href", "")
        if not href:
            continue
        try:
            destination = public_irs_url(index_url, href)
        except ValueError:
            continue
        parsed = urlsplit(destination)
        match = _DOCUMENT_PATH.fullmatch(unquote(parsed.path))
        if match is None:
            continue
        numbers = tuple(
            int(match.group(name)) for name in ("part", "chapter", "section")
        )
        if numbers != requested or int(match.group("route_part")) != requested[0]:
            continue
        target = parsed._replace(fragment="").geturl()
        routes.setdefault(target, SourceLink(text=anchor.text(), url=destination))
    if not routes:
        raise UpstreamServiceError(
            f"Unresolved observed route for IRM {document_citation} "
            f"in public part index {index_url}."
        )
    if len(routes) != 1:
        raise UpstreamServiceError(
            f"Ambiguous observed routes for IRM {document_citation} "
            f"in public part index {index_url}: " + ", ".join(routes)
        )
    return next(iter(routes.values()))


def _plain(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def _list_marker(index: int, style: str) -> str:
    if style in {"A", "a"}:
        letters = ""
        while index > 0:
            index, remainder = divmod(index - 1, 26)
            letters = chr(ord("A") + remainder) + letters
        return letters.lower() if style == "a" else letters
    if style in {"i", "I"} and index > 0:
        roman = ""
        for number, symbol in (
            (1000, "M"),
            (900, "CM"),
            (500, "D"),
            (400, "CD"),
            (100, "C"),
            (90, "XC"),
            (50, "L"),
            (40, "XL"),
            (10, "X"),
            (9, "IX"),
            (5, "V"),
            (4, "IV"),
            (1, "I"),
        ):
            count, index = divmod(index, number)
            roman += symbol * count
        return roman.lower() if style == "i" else roman
    return str(index)


def _rendered_content(node: HtmlNode) -> str:
    """Trim layout whitespace while retaining preformatted descendants."""
    rendered = _render(node, preformatted=node.tag == "pre")
    return rendered if any(node.iter("pre")) else rendered.strip()


def _render(node: HtmlNode | str, *, preformatted: bool = False) -> str:
    """Retain source sequence, list nesting, table cells, and qualifications."""
    if isinstance(node, str):
        return node if preformatted else re.sub(r"\s+", " ", node)
    if node.tag in _SKIP:
        return ""
    if node.tag == "br":
        return "\n"
    if node.tag == "img":
        return node.attrs.get("alt", "")
    if preformatted:
        return "".join(_render(child, preformatted=True) for child in node.children)
    if node.tag == "pre":
        return "\n" + _render(node, preformatted=True) + "\n"
    if node.tag == "table":
        rows = []
        for row in node.iter("tr"):
            table = row.parent
            while table is not None and table.tag != "table":
                table = table.parent
            if table is not node:
                continue
            cells = []
            for cell in _children(row):
                if cell.tag not in {"td", "th"}:
                    continue
                spans = "".join(
                    f" {name}={cell.attrs[name]}"
                    for name in ("colspan", "rowspan")
                    if name in cell.attrs
                )
                text = _rendered_content(cell)
                text = text.replace("\n", "<br>").replace("|", "\\|")
                cells.append(f"[{cell.tag}{spans}] {text}")
            if cells:
                rows.append("| " + " | ".join(cells) + " |")
        captions = [
            _rendered_content(child)
            for child in _children(node)
            if child.tag == "caption"
        ]
        return "\n" + "\n".join(captions + rows) + "\n"
    if node.tag in {"ol", "ul"}:
        start = node.attrs.get("start", "1")
        index = int(start) if re.fullmatch(r"-?\d+", start) else 1
        rows = []
        for child in _children(node):
            if child.tag != "li":
                text = _rendered_content(child)
                if text:
                    rows.append(text)
                continue
            value = child.attrs.get("value", "")
            if node.tag == "ol" and re.fullmatch(r"-?\d+", value):
                index = int(value)
            marker = (
                _list_marker(index, node.attrs.get("type", "1")) + "."
                if node.tag == "ol"
                else "-"
            )
            lines = _rendered_content(child).splitlines()
            if lines:
                padding = " " * (len(marker) + 1)
                rows.append(marker + " " + lines[0])
                rows.extend(padding + line for line in lines[1:])
            index += 1
        return "\n" + "\n".join(rows) + "\n"
    content = "".join(_render(child) for child in node.children)
    if any(node.iter("pre")):
        return content
    content = re.sub(r"[ \t]+\n", "\n", content)
    if node.tag in _HEADINGS | {
        "p",
        "div",
        "section",
        "blockquote",
        "pre",
        "dl",
        "dt",
        "dd",
        "li",
    }:
        return "\n" + content.strip() + "\n"
    return content


def _section(node: HtmlNode) -> _Section | None:
    info_nodes = [
        child for child in _children(node) if "sectioninfo" in _classes(child)
    ]
    info = " ".join(child.text() for child in info_nodes)
    citation_match = _CITATION.match(info.strip())
    heading = None
    for child in _children(node):
        if child.tag in _HEADINGS:
            heading = child
            break
        if "titlepage" in _classes(child):
            heading = next(
                (item for item in child.iter() if item.tag in _HEADINGS), None
            )
            if heading is not None:
                break
    if heading is None:
        return None
    title = heading.text()
    if citation_match is None:
        citation_match = _CITATION.match(title)
    if citation_match is None:
        return None
    citation = _canonical(citation_match.group())
    title = re.sub(r"^" + re.escape(citation_match.group()) + r"\s*", "", title)
    return _Section(node, citation, title, info)


def _section_owner(node: HtmlNode, sections: dict[int, _Section]) -> _Section | None:
    while node is not None:
        if id(node) in sections:
            return sections[id(node)]
        node = node.parent
    return None


def _body(root: HtmlNode) -> tuple[list[_Section], list[_Section]]:
    sections = []
    for node in root.iter():
        if "section" in _classes(node):
            article = node.parent
            while article is not None and article.tag != "article":
                article = article.parent
            if (
                article is None
                or "node--type-pup-xmlbc" not in _classes(article)
                or not article.attrs.get("about", "").startswith("/irm/")
            ):
                continue
            section = _section(node)
            if section is not None:
                sections.append(section)
    indexed = {id(section.node): section for section in sections}
    documents = [
        section
        for section in sections
        if _section_owner(section.node.parent, indexed) is None
    ]
    return sections, documents


def _body_links(node: HtmlNode, document_url: str) -> list[SourceBodyLink]:
    links: list[SourceBodyLink] = []

    def visit(current: HtmlNode) -> None:
        if current.tag in _SKIP:
            return
        if current.tag == "a" and "href" in current.attrs:
            href = current.attrs["href"]
            try:
                destination = urljoin(document_url, href)
            except ValueError:
                destination = None
            links.append(
                SourceBodyLink(
                    text=_render(current).strip(), href=href, url=destination
                )
            )
        for child in _children(current):
            visit(child)

    visit(node)
    return links


def _body_images(node: HtmlNode, document_url: str) -> list[SourceBodyImage]:
    images: list[SourceBodyImage] = []

    def visit(current: HtmlNode) -> None:
        if current.tag in _SKIP:
            return
        if current.tag == "img":
            src = current.attrs.get("src")
            destination = None
            if src is not None:
                try:
                    resolved = urljoin(document_url, src)
                    parts = urlsplit(resolved)
                    if parts.scheme in {"http", "https"} and parts.hostname:
                        parts.port  # Validate explicitly supplied ports.
                        destination = resolved
                except ValueError:
                    pass
            images.append(
                SourceBodyImage(src=src, alt=current.attrs.get("alt"), url=destination)
            )
        for child in _children(current):
            visit(child)

    visit(node)
    return images


def _blocks(
    selected: _Section, sections: dict[int, _Section], document_url: str
) -> list[SourceBlock]:
    blocks: list[SourceBlock] = []

    def visit(node: HtmlNode) -> None:
        section = sections.get(id(node))
        if section is not None and section is not selected:
            if not section.citation.startswith(selected.citation + "."):
                return
        classes = _classes(node)
        if node.tag in _SKIP:
            return
        if classes & {"sectioninfo", "titlepage"}:
            text = _rendered_content(node)
            images = _body_images(node, document_url)
            if text or images:
                blocks.append(
                    SourceBlock(
                        kind="heading",
                        text=text,
                        links=_body_links(node, document_url),
                        images=images,
                    )
                )
            return
        kind = None
        if classes & _QUALIFICATIONS:
            kind = next(name for name in sorted(classes) if name in _QUALIFICATIONS)
        elif node.tag in _HEADINGS:
            kind = "heading"
        elif node.tag == "a" and "href" in node.attrs:
            kind = "text"
        elif node.tag == "img":
            kind = "image"
        elif node.tag in {"p", "pre", "blockquote", "table", "ol", "ul", "dl"}:
            kind = {
                "p": "paragraph",
                "ol": "ordered_list",
                "ul": "itemized_list",
            }.get(node.tag, node.tag)
        if kind is not None:
            text = _rendered_content(node)
            links = _body_links(node, document_url)
            images = _body_images(node, document_url)
            if text or links or images:
                blocks.append(
                    SourceBlock(kind=kind, text=text, links=links, images=images)
                )
            return
        for child in node.children:
            if isinstance(child, HtmlNode):
                visit(child)
            elif _plain(child):
                blocks.append(SourceBlock(kind="text", text=_plain(child)))

    visit(selected.node)
    return blocks


def _document_context(document: _Section) -> tuple[list[str], list[SourceDate]]:
    notices: list[str] = []
    dates: list[SourceDate] = []
    heading = ""
    content: list[str] = []

    def finish() -> None:
        if not heading:
            return
        text = "\n".join([heading] + content)
        notices.append(text)
        meaning = {
            "Manual Transmittal": "Manual Transmittal date",
            "Effective Date": "IRM effective date",
        }.get(heading)
        if meaning and content:
            for match in _DATE.finditer(content[0]):
                dates.append(
                    SourceDate(value=match.group(), meaning=meaning, context=text)
                )

    for child in document.node.children:
        if isinstance(child, HtmlNode) and "section" in _classes(child):
            break
        if isinstance(child, HtmlNode) and child.tag in _HEADINGS:
            finish()
            heading = child.text() if child.tag != "h2" else ""
            content = []
        elif heading:
            text = _render(child).strip()
            if text:
                content.append(text)
    finish()
    return notices, dates


def _navigation(
    root: HtmlNode,
    sections: list[_Section],
    citation: str,
    url: str,
) -> tuple[list[SourceLink], list[str]]:
    links: list[SourceLink] = []
    notices: list[str] = []
    indexed = {id(section.node): section for section in sections}
    anchors: dict[str, list[_Section]] = {}
    for node in root.iter():
        owner = _section_owner(node, indexed)
        if owner is None:
            continue
        for name in {node.attrs.get("id", ""), node.attrs.get("name", "")} - {""}:
            owners = anchors.setdefault(name, [])
            if all(owner is not existing for existing in owners):
                owners.append(owner)
    for node in root.iter("a"):
        if "xmlbc-link" not in _classes(node):
            continue
        if _section_owner(node, indexed) is not None:
            continue
        container = node.parent
        while container is not None and container.tag != "li":
            container = container.parent
        if container is None:
            continue
        label = _plain(
            "".join(
                _render(child)
                for child in container.children
                if isinstance(child, str) or child.tag not in {"ul", "ol"}
            )
        )
        literal = _CITATION.match(label)
        if literal is None:
            continue
        literal_citation = _canonical(literal.group())
        if literal_citation != citation and not literal_citation.startswith(
            citation + "."
        ):
            continue
        try:
            destination = public_irs_url(url, node.attrs.get("href", ""))
        except ValueError:
            notices.append(f"Unresolved source navigation: {label}")
            continue
        parsed = urlsplit(destination)
        local = parsed.path == urlsplit(url).path
        reached = anchors.get(unquote(parsed.fragment), []) if local else []
        owner = reached[0] if len(reached) == 1 else None
        links.append(
            SourceLink(
                text=label,
                url=destination,
                reached_citation=owner.citation if owner else None,
                reached_title=owner.title if owner else None,
            )
        )
        if owner and owner.citation != literal_citation:
            notices.append(
                f"TOC label {label!r} links to body IRM {owner.citation} "
                f"({owner.title}) at {destination}. Body citations govern matching."
            )
        elif len(reached) > 1:
            notices.append(
                f"Ambiguous body fragment for TOC label {label!r}: {destination}"
            )
        elif local and not reached:
            notices.append(
                f"Unresolved body fragment for TOC label {label!r}: {destination}"
            )
    return links, notices


def register(mcp: FastMCP) -> None:
    """Register current public IRM retrieval."""

    @mcp.tool(
        name="get_irm_passage",
        annotations={
            "title": "Get Current Public IRM Passage",
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": True,
        },
    )
    async def get_irm_passage(citation: str) -> IrmPassageResult:
        """Retrieve current anonymous public HTML by dotted numeric IRM citation.

        Supply at least three numeric segments, such as 1.11.2.5.2. Body
        citations determine matches. Results include descendant content in
        source order, source date roles, transmittal notices, and literal TOC
        navigation with reached body identities. Fetch metadata timestamps
        retrieval; source dates retain independently attributed meanings.
        Body blocks retain inline link wording and source hrefs, with
        document-relative destinations supporting further source navigation.
        Table cells retain header roles and source colspan/rowspan attributes.
        Public part index links select document routes, including observed
        filename suffixes. Missing or ambiguous routes raise source failures.
        """
        requested = citation.strip()
        if _CITATION.fullmatch(requested) is None:
            raise ValueError("citation requires at least three dotted numeric segments")
        normalized = _canonical(requested)
        segments = normalized.split(".")
        part = int(segments[0])
        document_citation = ".".join(segments[:3])
        part_page = await fetch_irs_html(f"https://www.irs.gov/irm/part{part}")
        route = _document_route(
            parse_html(part_page.text),
            part_page.source.url,
            document_citation,
        )
        page = await fetch_irs_html(route.url)
        url = page.source.url
        root = parse_html(page.text)
        sections, documents = _body(root)
        if not any(item.citation == document_citation for item in documents):
            raise UpstreamServiceError(
                "Fetched HTML did not expose expected IRM document body hierarchy."
            )
        indexed = {id(section.node): section for section in sections}
        notices: list[str] = []
        page_dates: list[SourceDate] = []
        document_dates: dict[int, list[SourceDate]] = {}
        document_ids = list(dict.fromkeys(item.citation for item in documents))
        for document in documents:
            context, dates = _document_context(document)
            notices.extend(context)
            document_dates[id(document.node)] = dates
        for node in root.iter():
            classes = _classes(node)
            if "pup-content-revision" in classes:
                text = node.text()
                notices.append(text)
                for match in _DATE.finditer(text):
                    page_dates.append(
                        SourceDate(
                            value=match.group(),
                            meaning="Page Last Reviewed or Updated",
                            context=text,
                        )
                    )
            if node.attrs.get("role") == "alert" or "alert" in classes:
                text = _render(node).strip()
                if text and text not in notices:
                    notices.append(text)
        navigation, navigation_notices = _navigation(root, sections, normalized, url)
        notices.extend(navigation_notices)
        matches = [item for item in sections if item.citation == normalized]
        if not matches:
            notices.append(f"No body section matched IRM {normalized} in fetched HTML.")
        if len(matches) > 1:
            notices.append(
                f"Multiple body sections matched IRM {normalized} in fetched HTML."
            )
        if len(document_ids) > 1:
            notices.append(
                "Multiple body document identities: " + ", ".join(document_ids)
            )
        passages = []
        for match in matches:
            dates = list(page_dates)
            for document in documents:
                if _within(match.node, document.node):
                    dates.extend(document_dates[id(document.node)])
            for item in sections:
                if not _within(item.node, match.node):
                    continue
                if item is not match and not item.citation.startswith(normalized + "."):
                    continue
                for date in _DATE.finditer(item.info):
                    dates.append(
                        SourceDate(
                            value=date.group(),
                            meaning="Subsection date",
                            context=f"IRM {item.citation} {item.title}: {item.info}",
                        )
                    )
            anchor = match.node.attrs.get("id", "")
            passages.append(
                IrmPassage(
                    citation=match.citation,
                    title=match.title,
                    url=public_irs_url(url, "#" + anchor) if anchor else url,
                    blocks=_blocks(match, indexed, url),
                    dates=dates,
                )
            )
        disposition = "matched" if len(matches) == 1 else "not_found"
        if len(matches) > 1 or (matches and len(document_ids) > 1):
            disposition = "ambiguous"
        return IrmPassageResult(
            requested_citation=requested,
            document_citation=document_citation,
            source=page.source,
            match_disposition=disposition,
            route_source=part_page.source,
            document_route=SourceLink(
                text=route.text,
                url=route.url,
                reached_citation=document_citation,
                reached_title=(documents[0].title if len(documents) == 1 else None),
            ),
            passages=passages,
            navigation=navigation,
            notices=notices,
            extent=(
                "Document route selected from observed public part index links. "
                "Current fetched public HTML; matched body sections include nested "
                "citation descendants in native order without passage truncation. "
                "TOC navigation remains separately attributed. Linked destinations "
                "and unavailable content remain outside fetched passage extent."
            ),
        )
