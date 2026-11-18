"""IRS domain checks using retained source spans and controlled HTTP responses."""

from __future__ import annotations

from pathlib import Path
from urllib.parse import parse_qs, urlencode, urlsplit

import httpx
import pytest
from fastmcp import Client, FastMCP
from fastmcp.exceptions import ToolError

from example_server import utils
from example_server.models import SourceMetadata
from example_server.tools import irm, products
from example_server.utils import FetchedPage, UpstreamServiceError

FIXTURES = Path(__file__).parent / "fixtures" / "irs_public"
ORIGIN = "https://www.irs.gov"
CURRENT = ORIGIN + "/forms-instructions-and-publications"
PRIOR = ORIGIN + "/prior-year-forms-and-instructions"
IRM_DOCUMENTS = {
    "/irm/part1/irm_01-011-002": "irm-01-011-002.html",
    "/irm/part2/irm_02-008-009": "irm-02-008-009.html",
    "/irm/part21/irm_21-008-005r": "irm-21-008-005r.html",
}


def source_page(text: str, url: str, *, requested_url: str | None = None):
    return FetchedPage(
        text=text,
        source=SourceMetadata(
            requested_url=requested_url or url,
            url=url,
            retrieved_at_utc="2026-10-22T00:00:00+00:00",
            content_type="text/html; charset=UTF-8",
            status_code=200,
        ),
    )


def fixture_text(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


def synthetic_part_index(path: str) -> str:
    """Synthetic routing response; href reuses observed retained body URL."""
    return f'<main><a href="{path}">Observed IRM document route</a></main>'


@pytest.fixture
def fixture_fetch(monkeypatch):
    calls = []

    async def fetch(url, params=None):
        request_url = url + ("?" + urlencode(params) if params else "")
        calls.append(request_url)
        parsed = urlsplit(request_url)
        if parsed.path in IRM_DOCUMENTS:
            return source_page(fixture_text(IRM_DOCUMENTS[parsed.path]), request_url)
        for document in IRM_DOCUMENTS:
            if parsed.path == document.rsplit("/", 1)[0]:
                return source_page(synthetic_part_index(document), request_url)
        if parsed.path == urlsplit(CURRENT).path:
            page = parse_qs(parsed.query).get("page", ["0"])[0]
            name = (
                "current-catalog-page-2.html" if page == "1" else "current-catalog.html"
            )
            return source_page(fixture_text(name), request_url)
        if parsed.path == urlsplit(PRIOR).path:
            query = parse_qs(parsed.query).get("find", [""])[0]
            name = (
                "prior-instruction-catalog.html"
                if "instructions" in query
                else "prior-catalog.html"
            )
            return source_page(fixture_text(name), request_url)
        raise AssertionError(f"Unmapped fixture request: {request_url}")

    monkeypatch.setattr(irm, "fetch_irs_html", fetch)
    monkeypatch.setattr(products, "fetch_irs_html", fetch)
    return calls


async def call_tool(name: str, arguments: dict):
    server = FastMCP("IRS fixture checks")
    irm.register(server)
    products.register(server)
    async with Client(server) as client:
        returned = await client.call_tool(name, arguments)
        assert not returned.is_error
        return returned.structured_content


def mock_reference_document(monkeypatch, citation: str, body: str):
    numbers = [int(value) for value in citation.split(".")[:3]]
    document = ".".join(str(value) for value in numbers)
    path = f"/irm/part{numbers[0]}/irm_{numbers[0]:02}-{numbers[1]:03}-{numbers[2]:03}"
    final_url = "https://irs.gov" + path
    calls = []
    html = f"""<article class="node--type-pup-xmlbc" about="{path}">
      <div class="section"><h2>{document} Document</h2>
        <div class="section" id="selected"><h3>{citation} References</h3>
          {body}
        </div>
      </div>
    </article>"""

    async def fetch(url, params=None):
        calls.append(url)
        if url == f"{ORIGIN}/irm/part{numbers[0]}":
            return source_page(synthetic_part_index(path), url)
        assert url == ORIGIN + path
        return source_page(html, final_url, requested_url=url)

    monkeypatch.setattr(irm, "fetch_irs_html", fetch)
    return calls, final_url


@pytest.mark.asyncio
@pytest.mark.parametrize("citation", ["1.11.2.5.2", "10.8.1.1.2"])
async def test_body_links_keep_wording_targets_and_final_document_base(
    monkeypatch, citation
):
    calls, final_url = mock_reference_document(
        monkeypatch,
        citation,
        """<p>Read <a href="https://www.archives.gov/cui">NARA CUI</a>
          and <a href="../references?first=1&amp;second=2#note">source reference</a>.
        </p>""",
    )
    result = await call_tool("get_irm_passage", {"citation": citation})
    (paragraph,) = [
        block
        for block in result["passages"][0]["blocks"]
        if block["kind"] == "paragraph"
    ]
    assert paragraph["text"] == "Read NARA CUI and source reference."
    assert paragraph["links"] == [
        {
            "text": "NARA CUI",
            "href": "https://www.archives.gov/cui",
            "url": "https://www.archives.gov/cui",
        },
        {
            "text": "source reference",
            "href": "../references?first=1&second=2#note",
            "url": "https://irs.gov/irm/references?first=1&second=2#note",
        },
    ]
    assert result["source"]["url"] == final_url
    assert len(calls) == 2
    assert all(url.startswith(ORIGIN + "/irm/") for url in calls)


@pytest.mark.asyncio
async def test_links_keep_block_attachment_repetition_and_unresolved_siblings(
    monkeypatch,
):
    _, final_url = mock_reference_document(
        monkeypatch,
        "2.8.9.1.3",
        """<ol><li><a href="#selected">return</a></li>
          <li><a href="#selected">return again</a></li></ol>
        <table><tr><td><a href="https://home.treasury.gov/">Treasury</a></td></tr></table>
        <div class="note"><p><a href="http://[">unresolved</a>
          <a href="../other">usable sibling</a></p></div>
        <a href=""></a>
        <template><a href="https://hidden.example/">hidden</a></template>""",
    )
    result = await call_tool("get_irm_passage", {"citation": "2.8.9.1.3"})
    blocks = result["passages"][0]["blocks"]
    (ordered,) = [block for block in blocks if block["kind"] == "ordered_list"]
    assert [link["text"] for link in ordered["links"]] == ["return", "return again"]
    assert [link["url"] for link in ordered["links"]] == [
        final_url + "#selected",
        final_url + "#selected",
    ]
    (table,) = [block for block in blocks if block["kind"] == "table"]
    assert [link["text"] for link in table["links"]] == ["Treasury"]
    (note,) = [block for block in blocks if block["kind"] == "note"]
    assert note["links"][0] == {"text": "unresolved", "href": "http://[", "url": None}
    assert note["links"][1]["url"] == "https://irs.gov/irm/other"
    (empty,) = [block for block in blocks if block["kind"] == "text"]
    assert empty["text"] == ""
    assert empty["links"] == [{"text": "", "href": "", "url": final_url}]
    assert not any(
        link["text"] == "hidden" for block in blocks for link in block["links"]
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("citation", ["1.11.2.5.2", "10.8.1.1.2"])
async def test_preformatted_content_keeps_indentation_tabs_and_blank_lines(
    monkeypatch, citation
):
    expected = "  first\tvalue\n\n\tsecond  \n    nested\n  last\n"
    calls, _ = mock_reference_document(
        monkeypatch,
        citation,
        "<p>Ordinary   spacing stays readable.</p>"
        "<pre>  first\tvalue\n\n\tsecond  \n"
        "<code>    nested</code><br>  last\n</pre>",
    )
    result = await call_tool("get_irm_passage", {"citation": citation})
    blocks = result["passages"][0]["blocks"]
    (preformatted,) = [block for block in blocks if block["kind"] == "pre"]
    assert preformatted["text"] == expected
    (paragraph,) = [block for block in blocks if block["kind"] == "paragraph"]
    assert paragraph["text"] == "Ordinary spacing stays readable."
    assert len(calls) == 2


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "body,kind,expected",
    [
        (
            '<div class="note"><p>Before</p>'
            "<pre>  first\tvalue\n\n    last</pre><p>After</p></div>",
            "note",
            "  first\tvalue\n\n    last",
        ),
        (
            "<blockquote><pre>  first\tvalue\n\n    last</pre></blockquote>",
            "blockquote",
            "  first\tvalue\n\n    last",
        ),
        (
            "<ol><li>Item<pre>  first\tvalue\n\n    last</pre></li></ol>",
            "ordered_list",
            "1. Item\n     first\tvalue\n   \n       last",
        ),
        (
            "<table><tr><td><pre>  first\tvalue\n\n    last</pre></td></tr></table>",
            "table",
            "  first\tvalue<br><br>    last",
        ),
    ],
)
async def test_preformatted_content_keeps_owning_block_context(
    monkeypatch, body, kind, expected
):
    mock_reference_document(monkeypatch, "2.8.9.1.3", body)
    result = await call_tool("get_irm_passage", {"citation": "2.8.9.1.3"})
    (block,) = [
        block for block in result["passages"][0]["blocks"] if block["kind"] == kind
    ]
    assert expected in block["text"]
    if kind == "note":
        assert block["text"].index("Before") < block["text"].index(expected)
        assert block["text"].index(expected) < block["text"].index("After")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "body,kind,expected",
    [
        (
            '<div class="note">Before<pre>  alpha\t</pre>After<pre>beta</pre>End</div>',
            "note",
            "Before\n  alpha\t\nAfter\nbeta\nEnd",
        ),
        (
            "<blockquote><pre>alpha</pre><pre>beta</pre></blockquote>",
            "blockquote",
            "\nalpha\n\nbeta\n",
        ),
    ],
)
async def test_embedded_pre_blocks_keep_boundaries_with_adjacent_content(
    monkeypatch, body, kind, expected
):
    mock_reference_document(monkeypatch, "2.8.9.1.3", body)
    result = await call_tool("get_irm_passage", {"citation": "2.8.9.1.3"})
    (block,) = [
        block for block in result["passages"][0]["blocks"] if block["kind"] == kind
    ]
    assert block["text"] == expected


@pytest.mark.asyncio
@pytest.mark.parametrize("citation", ["1.11.2.5.2", "10.8.1.1.2"])
async def test_images_keep_order_attributes_block_attachment_and_document_base(
    monkeypatch, citation
):
    calls, final_url = mock_reference_document(
        monkeypatch,
        citation,
        '<p>Before <img src="../images/diagram.svg?x=1&amp;y=2" '
        'alt="Diagram &amp; notes"> after.</p>'
        '<img src="/images/standalone.png"><img src="/images/standalone.png" alt="">'
        '<ol><li>Choose <img src="//images.example/branch.png" alt="Branch"></li></ol>'
        '<table><tr><td><img src="/images/table.png" alt="Table"></td></tr></table>'
        '<div class="note"><img src="/images/repeated.png" alt="First">'
        '<img src="/images/repeated.png" alt="Again"><img alt="Missing source"></div>'
        '<template><img src="/hidden.png" alt="Hidden"></template>',
    )
    result = await call_tool("get_irm_passage", {"citation": citation})
    blocks = result["passages"][0]["blocks"]
    image_owners = [block for block in blocks if block["images"]]
    assert [block["kind"] for block in image_owners] == [
        "paragraph",
        "image",
        "image",
        "ordered_list",
        "table",
        "note",
    ]
    assert image_owners[0]["images"] == [
        {
            "src": "../images/diagram.svg?x=1&y=2",
            "alt": "Diagram & notes",
            "url": "https://irs.gov/irm/images/diagram.svg?x=1&y=2",
        }
    ]
    assert image_owners[0]["text"] == "Before Diagram & notes after."
    assert image_owners[1]["images"][0]["alt"] is None
    assert image_owners[2]["images"][0]["alt"] == ""
    assert image_owners[1]["images"][0]["url"] == (
        "https://irs.gov/images/standalone.png"
    )
    assert image_owners[3]["images"][0]["url"] == ("https://images.example/branch.png")
    assert image_owners[4]["images"][0]["alt"] == "Table"
    assert [image["alt"] for image in image_owners[5]["images"]] == [
        "First",
        "Again",
        "Missing source",
    ]
    assert image_owners[5]["images"][2] == {
        "src": None,
        "alt": "Missing source",
        "url": None,
    }
    assert result["source"]["url"] == final_url
    assert len(calls) == 2


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "src",
    [
        "http://[",
        "javascript:alert(1)",
        "data:image/png;base64,AA==",
        "https://example.com:invalid/image.png",
    ],
)
async def test_unresolved_images_retain_source_without_additional_fetch(
    monkeypatch, src
):
    calls, _ = mock_reference_document(
        monkeypatch, "2.8.9.1.3", f'<img src="{src}" alt="Source image">'
    )
    result = await call_tool("get_irm_passage", {"citation": "2.8.9.1.3"})
    (image,) = [
        image for block in result["passages"][0]["blocks"] for image in block["images"]
    ]
    assert image == {"src": src, "alt": "Source image", "url": None}
    assert len(calls) == 2


@pytest.mark.asyncio
async def test_retained_irm_exhibit_keeps_images_and_description_routes(monkeypatch):
    path = "/irm/part2/irm_02-127-002"
    document_url = ORIGIN + path
    calls = []
    excerpt = fixture_text("irm-02-127-002-exhibit-3.html")
    # Public exhibit markup stays unchanged inside explicitly synthetic framing.
    framed = (
        f'<article class="node--type-pup-xmlbc" about="{path}">'
        '<div class="section"><h2>2.127.2 Fixture document</h2>'
        + excerpt
        + "</div></article>"
    )

    async def fetch(url, params=None):
        calls.append(url)
        if url == ORIGIN + "/irm/part2":
            return source_page(synthetic_part_index(path), url)
        assert url == document_url
        return source_page(framed, url)

    monkeypatch.setattr(irm, "fetch_irs_html", fetch)
    result = await call_tool("get_irm_passage", {"citation": "2.127.2"})
    (passage,) = result["passages"]
    blocks = passage["blocks"]
    image_blocks = [
        (index, block) for index, block in enumerate(blocks) if block["kind"] == "image"
    ]
    assert [block["images"][0]["url"] for _, block in image_blocks] == [
        ORIGIN + "/pub/xml_bc/60808506.gif",
        ORIGIN + "/pub/xml_bc/60808507.gif",
    ]
    for (index, block), number, media in zip(
        image_blocks, ("1a", "1b"), ("439521", "439526")
    ):
        assert block["images"][0]["alt"].startswith("This is an Image:")
        assert blocks[index - 1]["text"] == "Figure 2.127.2-" + number
        assert blocks[index + 1]["kind"] == "blockquote"
        assert "Weekly TSR" in blocks[index + 1]["text"]
        assert blocks[index + 2]["links"][0]["url"] == ORIGIN + "/media/" + media
    assert calls == [ORIGIN + "/irm/part2", document_url]


@pytest.mark.asyncio
async def test_dates_body_citation_survives_misleading_toc(fixture_fetch):
    result = await call_tool("get_irm_passage", {"citation": "1.11.2.5.2"})
    assert result["match_disposition"] == "matched"
    (passage,) = result["passages"]
    assert passage["citation"] == "1.11.2.5.2"
    assert passage["title"] == "Determine IRM Dates"
    assert passage["url"].endswith("#id77")
    (navigation,) = result["navigation"]
    assert navigation["url"].endswith("#id44")
    assert navigation["reached_citation"] == "1.11.2.3.2"
    assert navigation["reached_title"] == "IRM Catalog Number"
    assert any("Body citations govern matching" in value for value in result["notices"])
    assert fixture_fetch == [
        ORIGIN + "/irm/part1",
        ORIGIN + "/irm/part1/irm_01-011-002",
    ]


@pytest.mark.asyncio
async def test_catalog_and_numbering_qualifications_remain_in_body(fixture_fetch):
    catalog = await call_tool("get_irm_passage", {"citation": "1.11.2.3.2"})
    changes = await call_tool("get_irm_passage", {"citation": "1.11.2.6.1.3"})
    catalog_text = "\n".join(item["text"] for item in catalog["passages"][0]["blocks"])
    change_text = "\n".join(item["text"] for item in changes["passages"][0]["blocks"])
    assert (
        "When M&P assigns a catalog number, it is permanently associated "
        "with the IRM section and the primary topic."
    ) in catalog_text
    assert (
        "M&P cannot re-use the IRM number nor the catalog number unless it's "
        "for the same or a similar topic."
    ) in catalog_text
    assert (
        "If an IRM section is obsoleted, SPDER and M&P archive both the IRM "
        "number and catalog number."
    ) in catalog_text
    assert (
        "If reissuing an IRM later with the same or a similar topic, SPDER "
        "and M&P can restore the IRM number and catalog number."
    ) in catalog_text
    assert "Base the subsection numbering" in change_text
    assert (
        "Base the subsection numbering off the accepted changes version "
        "of the XML file."
    ) in change_text
    assert (
        "Subsection numbering based off the tracked changes file can result "
        "in erroneous references when adding, deleting and renaming subsections."
    ) in change_text
    assert (
        "Consider using a crosswalk to identify the content’s original "
        "and new location."
    ) in change_text
    assert "[th" in change_text and "[td" in change_text


@pytest.mark.asyncio
async def test_date_roles_remain_distinct(fixture_fetch):
    result = await call_tool("get_irm_passage", {"citation": "02.008.009.01.003"})
    (passage,) = result["passages"]
    assert result["requested_citation"] == "02.008.009.01.003"
    assert passage["citation"] == "2.8.9.1.3"
    assert passage["title"] == "Roles and Responsibilities"
    assert passage["url"].endswith("#id11")
    roles = {(item["meaning"], item["value"]) for item in passage["dates"]}
    assert ("Manual Transmittal date", "October 07, 2026") in roles
    assert ("IRM effective date", "01-01-2027") in roles
    assert ("Subsection date", "10-07-2026") in roles
    assert result["source"]["retrieved_at_utc"] == "2026-10-22T00:00:00+00:00"


@pytest.mark.asyncio
async def test_observed_filename_suffix_and_source_block_structure(fixture_fetch):
    result = await call_tool("get_irm_passage", {"citation": "21.8.5.4.2"})
    (passage,) = result["passages"]
    assert result["document_route"]["url"].endswith("irm_21-008-005r")
    assert passage["title"] == "Initial Review Form 8288-B or Formal Letter Application"
    text = "\n".join(item["text"] for item in passage["blocks"])
    assert "Form 8288-B" in text
    assert "[th" in text and "[td" in text
    assert "Note:" in text
    assert (
        "The withholding agent and transferee (buyer) are generally the same person."
    ) in text
    assert any(item["kind"] == "ordered_list" for item in passage["blocks"])
    table_rows = [line for line in text.splitlines() if "[td" in line]
    response = next(line for line in table_rows if "1) Response is received" in line)
    assert "Continue to process application" in response
    assert "90- day processing window begins" in response
    no_response = next(
        line
        for line in table_rows
        if "2) No response is received by the end of 30 days" in line
    )
    assert "Reject the 8288-B application" in no_response
    assert "NO REPLY" in no_response
    assert no_response.index("Letter 3313") < no_response.index("Letter 3316")
    lines = text.splitlines()
    name = next(
        index
        for index, line in enumerate(lines)
        if "Contains the name and TIN of the withholding agent" in line
    )
    note = next(
        index
        for index, line in enumerate(lines)
        if "withholding agent and transferee (buyer) are generally" in line
    )
    mailing = next(
        index
        for index, line in enumerate(lines)
        if "Withholding Certificate mailing address" in line
    )
    assert name < note < mailing
    assert len(lines[note]) - len(lines[note].lstrip()) > (
        len(lines[mailing]) - len(lines[mailing].lstrip())
    )


@pytest.mark.parametrize("citation", ["1.11", "dates", "https://www.irs.gov/irm/part1"])
@pytest.mark.asyncio
async def test_invalid_citations_do_not_fetch(citation, fixture_fetch):
    with pytest.raises(ToolError, match="three dotted numeric segments"):
        await call_tool("get_irm_passage", {"citation": citation})
    assert fixture_fetch == []


@pytest.mark.asyncio
async def test_missing_body_citation_returns_not_found(fixture_fetch):
    result = await call_tool("get_irm_passage", {"citation": "1.11.2.999"})
    assert result["match_disposition"] == "not_found"
    assert result["passages"] == []
    assert result["document_citation"] == "1.11.2"


@pytest.mark.parametrize("routing", ["missing", "ambiguous", "different_body"])
@pytest.mark.asyncio
async def test_unresolved_routing_or_body_identity_is_not_success(monkeypatch, routing):
    async def fetch(url, params=None):
        if url.endswith("/part1"):
            text = synthetic_part_index("/irm/part1/irm_01-011-002")
            if routing == "missing":
                text = "<main>No observed route</main>"
            if routing == "ambiguous":
                text += synthetic_part_index("/irm/part1/irm_01-011-002a")
            return source_page(text, url)
        return source_page(fixture_text("irm-02-008-009.html"), url)

    monkeypatch.setattr(irm, "fetch_irs_html", fetch)
    with pytest.raises(ToolError, match="route|hierarchy"):
        await call_tool("get_irm_passage", {"citation": "1.11.2.5.2"})


@pytest.mark.asyncio
async def test_current_catalog_keeps_product_kind_year_and_extent(fixture_fetch):
    result = await call_tool(
        "find_irs_products", {"query": "1040", "catalog": "current"}
    )
    matches = {item["product"]: item for item in result["matches"]}
    assert matches["Form 1040"]["year"] == "2025"
    assert matches["Form 1040"]["url"].endswith("/pub/irs-pdf/f1040.pdf")
    assert matches["Instruction 1040"]["url"].endswith("/pub/irs-pdf/i1040gi.pdf")
    assert "1040-SR" in matches["Instruction 1040"]["title"]
    assert "Publication 1040" in matches
    assert matches["Form 1040-C"]["year"] is None
    assert any(
        item["value"] == "02/27/2026" and item["meaning"] == "Posted Date"
        for item in matches["Instruction 1040"]["dates"]
    )
    (page,) = result["pages"]
    assert page["rows_observed"] == 25
    assert "1 - 25" in page["source_extent"] and "83" in page["source_extent"]
    assert page["next"]["query"] == "1040"
    assert page["pagination_disposition"] == "available"


@pytest.mark.asyncio
async def test_explicit_2024_selection_does_not_substitute_current_alias(fixture_fetch):
    result = await call_tool("find_irs_products", {"query": "1040", "tax_year": 2024})
    exact = [item for item in result["matches"] if item["product"] == "Form 1040"]
    assert len(exact) == 1
    assert exact[0]["catalog"] == "prior"
    assert exact[0]["year"] == "2024"
    assert exact[0]["url"].endswith("/pub/irs-prior/f1040--2024.pdf")
    assert all(item["year"] == "2024" for item in result["matches"])
    assert any("date=2024" in url for url in fixture_fetch)


@pytest.mark.asyncio
async def test_prior_instruction_kind_and_year_remain_joined(fixture_fetch):
    result = await call_tool(
        "find_irs_products",
        {"query": "instructions for form 1040", "tax_year": 2024, "catalog": "prior"},
    )
    (match,) = [
        item for item in result["matches"] if item["product"] == "Instruction 1040"
    ]
    assert match["year"] == "2024"
    assert "1040-SR" in match["title"]
    assert match["url"].endswith("/pub/irs-prior/i1040gi--2024.pdf")


@pytest.mark.asyncio
async def test_continuation_keeps_page_and_filters(fixture_fetch):
    first = await call_tool(
        "find_irs_products", {"query": "1040", "catalog": "current"}
    )
    continuation = first["pages"][0]["next"]
    fixture_fetch.clear()
    second = await call_tool(
        "find_irs_products",
        {"query": "1040", "catalog": "both", "continuation": continuation},
    )
    (page,) = second["pages"]
    assert len(fixture_fetch) == 1
    assert "page=1" in fixture_fetch[0]
    assert "find=1040" in fixture_fetch[0]
    assert page["catalog"] == "current"
    assert "26 - 50" in page["source_extent"] and "83" in page["source_extent"]
    assert second["matches"][0]["product"] == "Form 1040 (Schedule 3)"


@pytest.mark.parametrize(
    "changed", [{"query": "1099"}, {"tax_year": 2024}, {"catalog": "prior"}]
)
@pytest.mark.asyncio
async def test_continuation_conflicts_fail_before_fetch(fixture_fetch, changed):
    arguments = {"query": "1040", "catalog": "current"}
    first = await call_tool("find_irs_products", arguments)
    arguments["continuation"] = first["pages"][0]["next"]
    arguments.update(changed)
    fixture_fetch.clear()
    with pytest.raises(ToolError, match="Continuation"):
        await call_tool("find_irs_products", arguments)
    assert fixture_fetch == []


@pytest.mark.parametrize(
    "mode", ["upstream", "wrong_route", "filter_dropped", "missing_table"]
)
@pytest.mark.asyncio
async def test_catalog_failure_keeps_sibling_and_absence_scope(
    monkeypatch, fixture_fetch, mode
):
    normal = products.fetch_irs_html

    async def fetch(url, params=None):
        if url == PRIOR:
            if mode == "upstream":
                raise UpstreamServiceError("Controlled source failure")
            requested = url + "?" + urlencode(params)
            if mode == "missing_table":
                return source_page("<main>Service notice</main>", requested)
            final = ORIGIN + "/unrelated?find=1040" if mode == "wrong_route" else url
            return source_page(
                fixture_text("prior-catalog.html"), final, requested_url=requested
            )
        return await normal(url, params)

    monkeypatch.setattr(products, "fetch_irs_html", fetch)
    result = await call_tool("find_irs_products", {"query": "1040"})
    assert any(item["catalog"] == "current" for item in result["matches"])
    assert not any(item["catalog"] == "prior" for item in result["matches"])
    if mode == "missing_table":
        prior = next(item for item in result["pages"] if item["catalog"] == "prior")
        assert not prior["catalog_structure_recognized"]
        assert prior["pagination_disposition"] == "unresolved"
        assert any("absence unverified" in value for value in result["notices"])
    else:
        assert "prior" in result["catalog_failures"]


def http_transport(monkeypatch, handler):
    monkeypatch.delenv("IRS_HTTP_MAX_BYTES", raising=False)
    monkeypatch.delenv("IRS_HTTP_TIMEOUT_SECONDS", raising=False)
    original = httpx.AsyncClient
    monkeypatch.setattr(
        utils.httpx,
        "AsyncClient",
        lambda **kwargs: original(transport=httpx.MockTransport(handler), **kwargs),
    )


@pytest.mark.asyncio
async def test_catalog_names_do_not_make_annual_populations_disjoint(fixture_fetch):
    result = await call_tool("find_irs_products", {"query": "1040", "tax_year": 2025})
    exact = [item for item in result["matches"] if item["product"] == "Form 1040"]
    assert {item["catalog"] for item in exact} == {"current", "prior"}
    assert {item["year"] for item in exact} == {"2025"}
    assert len({item["url"] for item in exact}) == 2


@pytest.mark.parametrize(
    "next_mode", ["omitted_filters", "repeats_page", "multiple_destinations"]
)
@pytest.mark.asyncio
async def test_source_next_keeps_literal_route_and_continuation(monkeypatch, next_mode):
    text = fixture_text("prior-catalog.html")
    if next_mode == "omitted_filters":
        text = text.replace("?find=1040&amp;page=1", "?page=1").replace(
            "?find=1040&page=1", "?page=1"
        )
    elif next_mode == "repeats_page":
        text = text.replace(
            "?find=1040&amp;page=1", "?find=1040&amp;date=2024"
        ).replace("?find=1040&page=1", "?find=1040&date=2024")
    else:
        text = text.replace(
            "</div></article>",
            '<a rel="next" href="?find=1040&amp;page=9">Alternate Next</a>'
            "</div></article>",
        )

    async def fetch(url, params=None):
        request = url + "?" + urlencode(params)
        return source_page(text, request)

    monkeypatch.setattr(products, "fetch_irs_html", fetch)
    result = await call_tool(
        "find_irs_products", {"query": "1040", "tax_year": 2024, "catalog": "prior"}
    )
    continuation = result["pages"][0]["next"]
    if next_mode == "omitted_filters":
        assert result["pages"][0]["pagination_disposition"] == "available"
        assert parse_qs(urlsplit(continuation["source_url"]).query) == {"page": ["1"]}
        assert parse_qs(urlsplit(continuation["url"]).query) == {
            "page": ["1"],
            "find": ["1040"],
            "date": ["2024"],
        }
    else:
        assert continuation is None
        assert result["pages"][0]["pagination_disposition"] == "unresolved"
        assert any("Next" in value for value in result["notices"])


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "navigation,expected,has_next",
    [
        ("", "not_observed", False),
        ('<a rel="next" href="https://example.com/next">Next</a>', "unresolved", False),
        ('<a rel="next" href="?find=1099&amp;page=1">Next</a>', "unresolved", False),
        (
            '<a rel="next" href="?find=1040&amp;date=2024&amp;page=1">Next</a>'
            '<a rel="next" href="https://example.com/next">Other Next</a>',
            "unresolved",
            True,
        ),
    ],
)
async def test_catalog_navigation_distinguishes_missing_and_unresolved_next(
    monkeypatch, navigation, expected, has_next
):
    before_table_end, _, _ = fixture_text("prior-catalog.html").rpartition("</table>")
    text = before_table_end + "</table>" + navigation + "</div></article></main>"

    async def fetch(url, params=None):
        request = url + "?" + urlencode(params)
        return source_page(text, request)

    monkeypatch.setattr(products, "fetch_irs_html", fetch)
    result = await call_tool(
        "find_irs_products", {"query": "1040", "tax_year": 2024, "catalog": "prior"}
    )
    (page,) = result["pages"]
    assert page["pagination_disposition"] == expected
    assert (page["next"] is not None) is has_next
    assert any(match["product"] == "Form 1040" for match in result["matches"])


@pytest.mark.asyncio
async def test_duplicate_body_matches_remain_ambiguous(monkeypatch):
    text = fixture_text("irm-02-008-009.html")

    async def fetch(url, params=None):
        if url.endswith("/part2"):
            return source_page(synthetic_part_index("/irm/part2/irm_02-008-009"), url)
        extra = (
            '<div class="section"><div class="sectioninfo">'
            "2.8.9.1.3 (10-07-2026)</div><h4>Roles and Responsibilities</h4>"
            "<p>Controlled duplicate identity</p></div>"
        )
        return source_page(
            text.replace("</div></article>", extra + "</div></article>"), url
        )

    monkeypatch.setattr(irm, "fetch_irs_html", fetch)
    result = await call_tool("get_irm_passage", {"citation": "2.8.9.1.3"})
    assert result["match_disposition"] == "ambiguous"
    assert len(result["passages"]) == 2


@pytest.mark.asyncio
async def test_public_fetch_follows_same_origin_redirect(monkeypatch):
    calls = []

    def handler(request):
        calls.append(str(request.url))
        if request.url.path == "/irm/part21":
            return httpx.Response(
                302, headers={"location": "/irm/part21/irm_21-008-005r"}
            )
        return httpx.Response(
            200,
            text="<main>Retained route replay</main>",
            headers={"content-type": "text/html"},
        )

    http_transport(monkeypatch, handler)
    page = await utils.fetch_irs_html(ORIGIN + "/irm/part21")
    assert page.source.requested_url == ORIGIN + "/irm/part21"
    assert page.source.url.endswith("irm_21-008-005r")
    assert len(calls) == 2


@pytest.mark.asyncio
async def test_external_redirect_is_rejected_before_second_request(monkeypatch):
    calls = []

    def handler(request):
        calls.append(str(request.url))
        return httpx.Response(302, headers={"location": "https://example.com/login"})

    http_transport(monkeypatch, handler)
    with pytest.raises(ValueError):
        await utils.fetch_irs_html(ORIGIN + "/irm/part1")
    assert calls == [ORIGIN + "/irm/part1"]


@pytest.mark.parametrize(
    "status,content_type", [(404, "text/html"), (200, "application/pdf")]
)
@pytest.mark.asyncio
async def test_public_fetch_reports_status_and_non_html(
    monkeypatch, status, content_type
):
    http_transport(
        monkeypatch,
        lambda request: httpx.Response(
            status,
            content=b"controlled body",
            headers={"content-type": content_type},
        ),
    )
    with pytest.raises(UpstreamServiceError):
        await utils.fetch_irs_html(ORIGIN + "/irm/part1")


@pytest.mark.asyncio
async def test_public_fetch_uses_configured_byte_budget_without_shared_cap(monkeypatch):
    content = b"<p>x</p>"
    http_transport(
        monkeypatch,
        lambda request: httpx.Response(
            200, content=content, headers={"content-type": "text/html"}
        ),
    )
    monkeypatch.setenv("IRS_HTTP_MAX_BYTES", str(len(content)))
    assert (await utils.fetch_irs_html(ORIGIN + "/irm/part1")).text == content.decode()
    monkeypatch.setenv("IRS_HTTP_MAX_BYTES", str(len(content) - 1))
    with pytest.raises(UpstreamServiceError, match="configured byte budget"):
        await utils.fetch_irs_html(ORIGIN + "/irm/part1")


@pytest.mark.parametrize("media_type", ["text/html", "application/xhtml+xml"])
@pytest.mark.asyncio
async def test_public_html_preserves_charset_and_query_metadata(
    monkeypatch, media_type
):
    content = b"<main>caf\xe9</main>"
    content_type = media_type + "; charset=iso-8859-1"
    calls = []

    def handler(request):
        calls.append(str(request.url))
        return httpx.Response(
            200, content=content, headers={"content-type": content_type}
        )

    http_transport(monkeypatch, handler)
    page = await utils.fetch_irs_html(ORIGIN + "/catalog", params={"find": "café"})
    assert page.text == "<main>café</main>"
    assert page.source.requested_url == calls[0]
    assert page.source.url == calls[0]
    assert page.source.content_type == content_type
    assert parse_qs(urlsplit(calls[0]).query) == {"find": ["café"]}
