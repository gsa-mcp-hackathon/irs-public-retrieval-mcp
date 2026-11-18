# Anonymous IRS public retrieval

MCP tools resolve public IRS.gov IRM citations, locate forms/instructions through current and prior-year product catalogs, and retrieve official PDF bytes. Caller-selected citations, product queries, years, and document URLs drive retrieval. Results preserve source identity, acquisition metadata, date meanings, qualifications, encountered notices, and catalog continuation alongside useful content.

## Available tools

| Tool | Caller inputs | Returned scope |
| --- | --- | --- |
| `get_irm_passage` | `citation`: dotted IRM citation identifying section or numbered descendant | Matching body passages in source order, native dates, literal TOC links with reached body identity, encountered notices and match disposition. |
| `find_irs_products` | `query`; optional `tax_year`: complete four-digit annual catalog Revision Date labels (tax-year applicability unverified); `catalog`: `current`, `prior`, or `both`; optional returned `continuation` object | Catalog-attributed products, titles, years/revision wording, official document links, related encountered links, and source-native next-page navigation. |
| `get_irs_document` | `document_url`: supported HTTPS IRS.gov URL, including returned catalog document links | Embedded `application/pdf` resource containing response bytes, final source URL, acquisition metadata, and byte count. |

All tools perform anonymous HTTPS GET reads. Supported web origins are `https://www.irs.gov` and `https://irs.gov`; source-linked redirects receive origin validation before further requests. Tools expose retrieval, without submission or authenticated IRS operations.

## Install and run

From cloned repository root, install locked runtime dependencies and start stdio with Python 3.11+ and `uv`:

```sh
uv sync --locked --no-dev
uv run --no-sync python deploy/ibm/local-mcp-toolkit/server.py
```

Stdio startup waits for MCP messages from connected clients. Stop standalone execution with `Ctrl+C`. Public IRS retrieval requires no API key; caller-configured proxy and CA environment still apply where needed. [Local stdio use](#local-stdio-use) includes Windows startup and client-subprocess examples; [deployment overview](deploy/README.md) links hosted options.

Example arguments illustrate caller inputs:

```json
{"citation": "1.11.2.5.2"}
```

```json
{"query": "1040", "tax_year": 2024, "catalog": "both"}
```

### IRM passage identity

Public part-index links determine document routes, including source-specific filename suffixes. Current HTML body hierarchy then determines citation matches. Route-index acquisition and selected document link remain distinct from document-body acquisition. TOC labels and fragment destinations retain separate identities, including mismatches. Requested section descendants retain ordered paragraphs, headings, lists and tables. Source dates remain attributed to their native roles; document revision, subsection date and effectivity can describe different events.

Use returned `passages[].citation`, title, body URL, and ordered blocks together when citing results. `navigation` exposes observed TOC destinations separately, so mismatched TOC fragments remain visible while matched body passages stay usable. Different caller-selected citations, such as `1.11.2.5.2` or `21.8.5.1`, can reach different document routes and date relationships without changing tool configuration.

Body blocks retain ordered `links` with visible wording, decoded source `href`, and document-relative `url`. Resolution uses final document URL; unresolvable destinations keep source `href` with `url: null`. Inline links support following cited IRS and further materials while preserving their originating content. Linked-source authority and applicability depend on reached source contents.

Body blocks retain ordered `images` with source `src`, nullable `alt`, and resolved HTTP(S) `url`; missing and empty alternative text remain distinct. Standalone images use `kind: "image"` blocks. Preformatted content preserves spacing and line breaks. Image metadata supports further inspection without automatically fetching image bytes.

Current public HTML retrieval establishes encountered passages and notices. Historical/as-of selection, exhaustive revision comparison and XML-to-HTML identifier correspondence require their own source selection and implementation. Public redactions or obsolete notices remain attached when encountered; missing notices establish no general completeness claim.

### Governance reference traversal

Read upstream Governance references through IRM Authority passages. For example, `{"citation":"10.8.1.1.2"}` exposes NIST SP 800-53 and FIPS 199/200 references beside originating IRM text. Returned links support continued reading through existing document readers, with source-specific dates and applicable scope attached to subsequent interpretation.

### Product and edition identity

Current and prior-year catalogs remain distinct source views. Inspect returned `product`, `title`, `year`, and `url` together: broad queries can return forms, instructions, schedules, and language variants. Annual revision labels can support catalog-year selection; month-dated or unqualified revision values retain uncertainty about tax-year applicability. PDF-cover year and document-body identity require separate document inspection.

Callers can vary query wording and catalog selection, for example:

```json
{"query": "instructions for form 1040", "tax_year": 2024, "catalog": "prior"}
```

Examples illustrate caller inputs without supplying defaults or exact-product guarantees. Product selection follows returned identity fields; PDF URLs supply document retrieval inputs for `get_irs_document`.

Related instruction/correction links retain observed catalog context. Retrieval extent covers inspected catalog pages and encountered links; complete correction discovery requires further source traversal.

### PDF document acquisition

Pass selected `matches[].url` from catalog results as `document_url`, or supply another supported IRS.gov document URL. `get_irs_document` returns MCP embedded PDF resources with exact response bytes and final HTTPS source URLs. Structured metadata includes requested/final URLs, UTC retrieval time, response content type, status code, and byte count. Resource MIME type is `application/pdf`.

```json
{"document_url": "https://www.irs.gov/pub/irs-prior/f1040--2024.pdf"}
```

Response media identifies acquired PDF content. PDF parsing, text extraction, product/year identity, and cover validation require separate inspection; filenames supply no identity claims. Current, prior-year, and opaque document routes use identical acquisition behavior.

### Catalog continuation

Return `next` objects can be supplied unchanged as `continuation` with matching query, tax year and catalog selection. Each object carries source catalog, search context and request URL. Optional `source_url` retains literal source-linked destination separately when source link omitted active filters and context-preserving request URL restores them. Conflicting catalog/query/year values are rejected before retrieval. Final responses must preserve requested query controls, including pagination and ordering, before catalog attribution proceeds.

Each `pages[]` entry owns its `next` object. With `catalog: "both"`, follow current and prior continuations independently while retaining original query, tax year, and catalog arguments. Continued calls return reached catalog pages, so preserve earlier sibling results. Empty `matches` with remaining `next` still leaves later rows available; follow observed links until selected catalog continuations end or caller intent stops traversal.

Each page also reports `pagination_disposition`: `available` identifies resolved navigation, `not_observed` means no Next link was observed, and `unresolved` identifies unresolved navigation or unrecognized catalog structure. Unresolved pages can retain usable `next` alongside unresolved sibling links. Missing `next` alone therefore does not establish completed traversal. Externally constructed page models retain `unassessed` until acquisition supplies disposition.

Page rows, source-reported extent and actual Next links qualify coverage. Complete current/prior catalog coverage follows observed continuation state; sample template offset pagination supplies no catalog completeness guarantee.

## Evaluation observations

November 16 [live-agent results](eval/README.md#november-16-live-agent-outcomes) add separate three-case suite: two IRM answers retain useful rules alongside literal/link/citation errors, while correct Form 1040/2024 selection delivers five complete PDFs before upstream HTTP 413 leaves answer empty. Source checks qualify same-route model verdicts; completed execution supplies no three-answer pass claim. Earlier 13 records retain original meanings and count.


[Evaluation report (PDF)](eval/evaluation-report.pdf) · [Checked answer and evaluation methods](eval/README.md#source-checked-answer-irm-date-selection).

Selected catalog follow-through found current Form 1040 revision 2025 and prior revision 2024, followed one Next hop per catalog, and retained partial coverage with further Next links. Selected current/prior 2025 PDF responses matched at recorded retrieval clocks, 220,237 bytes each; complete two-page extracted-text reading confirmed printed Form 1040/2025. Earlier IRM retrieval and 163,287-byte 2024 PDF acquisition/independent reading retain their original credit. Thirteen [evaluation records](eval/observations.json) preserve source URLs, inputs, dates, byte hashes, methods, outcomes, and source-to-answer limits.

Methodology combines live public reads, local HTTP invocation, native agent/tool use, reading of retained PDF pages, and source-to-answer comparisons. Successful three-tool use answered both requested subjects and kept catalog/PDF inspection limits visible. Later source-cued reconsideration added conditional IPU/IGM rules and removed unsupported whole-section date assignment; descendant navigation, specified-date constraints, and exact-looking date forms still had omissions or changes. PDF receipt, independent local reading, and model PDF understanding retain separate evidence.

Measured observations include per-run clocks, tool-call counts, PDF byte/page/text counts, and native reported token usage. Existing regression checks passed 120 tests plus 41 subtests; separate installed-package checks passed imports, dependency compatibility, health, and complete tool discovery. Representative aggregate accuracy, latency distribution, controlled no-tool comparison, and adversarial robustness remain unmeasured. October 30 records establish bounded catalog/document follow-through; broader cases, representative repeats, controlled baselines, scored measurements, and native model PDF understanding remain open.

Security considerations cover anonymous public data, supported origins/redirects, deployment TLS/proxy choices, optional request budgets, and untrusted retrieved text. Administrative authentication and model-provider credentials retain separate roles. Observed lessons favor preserving source identity, conditional rules, literal forms, and continuation through composition; useful retrieval and partial answer repair need their own limits alongside remaining work.

Current [source-checked answer](eval/README.md#source-checked-answer-irm-date-selection) turns retained IRS text into usable date-selection guidance. November 16 drafting/audit contributed useful material alongside false findings; owning source checks determined adopted guidance. Historical observations and recorded verification retain their original scopes.

## Local stdio use

Runtime selection follows caller choice or configured `uv` discovery, subject to existing `requires-python = ">=3.11"`; use `uv run --python <interpreter> ...` for explicit selection. Source package/import identity remains `example_server`, preserving upstream layout and deployment entry points. With runtime dependencies already installed:

```powershell
$env:PYTHONPATH = Join-Path (Get-Location) 'src'
& .\.venv\Scripts\python.exe .\deploy\ibm\local-mcp-toolkit\server.py
```

Official local-toolkit entry forces stdio. Standard `main.py` retains upstream transport selection, including platform-provided HTTP ports. [IBM deployment kits](deploy/ibm/README.md), [Databricks deployment kit](deploy/databricks/README.md) and [deployment overview](deploy/README.md) retain upstream hosting guidance; actual hosting/client integration needs deployment-specific configuration.

Image builds through [Dockerfile](Dockerfile) retain Python 3.11 defaults and project requirement `>=3.11`. Builds consume `uv.lock`, install runtime dependencies and packaged project without editable source links, and fail on stale locks. Startup selects `/app/.venv/bin/python`. Base images, uv tooling, build-backend inputs, and target network/runtime validation remain separate.

### FastMCP client subprocess

Client subprocess environment needs its own selection. Pass caller-configured source, proxy, CA, and request controls through `StdioTransport.env`: source startup and tool discovery can succeed while public retrieval still fails when required network fields are missing. Example assumes repository root as working directory and Python containing installed FastMCP client APIs shown below. Existing `PYTHONPATH` remains available alongside repository source; configured network values pass unchanged, and unset fields stay unset.

```python
import asyncio
import json
import os
import sys
from pathlib import Path

from fastmcp import Client
from fastmcp.client.transports import StdioTransport


async def main():
    project_root = Path.cwd().resolve()
    forward_names = {
        "HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "NO_PROXY",
        "http_proxy", "https_proxy", "all_proxy", "no_proxy",
        "SSL_CERT_FILE", "SSL_CERT_DIR",
        "IRS_HTTP_TIMEOUT_SECONDS", "IRS_HTTP_MAX_BYTES",
    }
    server_env = {
        name: value for name, value in os.environ.items() if name in forward_names
    }
    source_path = str(project_root / "src")
    existing_source_path = os.environ.get("PYTHONPATH")
    server_env["PYTHONPATH"] = (
        os.pathsep.join((source_path, existing_source_path))
        if existing_source_path else source_path
    )
    transport = StdioTransport(
        command=sys.executable,
        args=["-B", str(project_root / "deploy/ibm/local-mcp-toolkit/server.py")],
        cwd=str(project_root),
        env=server_env,
        keep_alive=False,
    )
    async with Client(transport) as client:
        print([tool.name for tool in await client.list_tools()])
        result = await client.call_tool_mcp(
            "get_irm_passage", {"citation": "3.11.10.6.2"}
        )
        if result.is_error:
            raise RuntimeError("Public retrieval failed; inspect tool error locally.")
        payload = result.structured_content
        if payload is None:
            payload = json.loads(
                next(part.text for part in result.content if part.type == "text")
            )
        print(json.dumps(payload, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
```

Explicit Python command and argument list preserve Windows drive paths without CLI source-selector parsing. Example selects `keep_alive=False` to close owned subprocess when client context exits; longer-lived clients can select supported reuse behavior. Environment values remain unprinted.

Tool discovery, successful public retrieval, passage matching, source interpretation, and downstream use require their respective checks. Inspect SDK `is_error`, payload `match_disposition`, source metadata, passage identities, ordered blocks, date roles, notices, and extent before using returned content. Existing server fetch already honors HTTPX network environment; caller subprocess forwarding supplies those configured fields without changing server implementation or public/internal source-selection guidance.

## Deployment-local network controls

Public reads use HTTPX environment-aware network behavior, retaining deployment proxy and TLS configuration. Tools neither load client credentials nor change global proxy/trust configuration. Standard HTTPX environment variables supply local proxy/CA choices.

Optional `IRS_HTTP_TIMEOUT_SECONDS` and `IRS_HTTP_MAX_BYTES` configure positive per-request timeout and decoded-response byte budget. Unset values impose no project-wide timeout/byte cap. Redirect handling uses HTTPX's existing redirect allowance and rejects repeated destinations or unsupported origins. These operational controls remain deployment-local; caller product limits and observed source page sizes describe different relationships.

HTTP failures identify actual status where available. TLS/transport failure, unexpected response media, and configured budget exhaustion remain retrieval failures, independently from successful zero-match parsing. Catalog failures and unrecognized catalog structure receive structured fields, preserving successful sibling reads. Source acquisition timestamps and requested/final URLs accompany parsed results and PDF resources.

## Tests

Run pytest through existing project development setup:

```sh
uv run pytest
```

Optional Windows reporting/cache controls:

```sh
uv run pytest -p no:cacheprovider -p no:faulthandler
```

Use optional route when otherwise passing runs encounter repeated Windows exception diagnostics or cache-path permission warnings. Flags disable pytest’s optional fault-handler reporting and cache writes for that invocation. Observed diagnostic causes remain unassigned; shared configuration retains existing settings.

## Source and implementation

[UPSTREAM-SOURCE.json](UPSTREAM-SOURCE.json) records official GSA starter revision. Initial import preserves exact upstream source; later domain changes remain ordinary Git history. Existing public `uv.lock` remains unchanged. Local IRS package supply and public/IBM package supply retain deployment-specific configuration while locked versions/artifacts remain shared.

Public source: [gsa-mcp-hackathon/irs-public-retrieval-mcp](https://github.com/gsa-mcp-hackathon/irs-public-retrieval-mcp).

Upstream [Registry metadata example](server.example.json) retains starter namespace, repository, and remote endpoint values for reference. Publisher namespace and deployed endpoint remain unbound. Registry submission needs verified prototype metadata and Registry validation.

Implementation reuses FastMCP, HTTPX, Pydantic and Python standard-library HTML parsing. IRM body and IRS catalog structures guide domain behavior. Existing unrelated example modules remain readable in source history/layout; exposed tool inventory contains implemented IRS tools.

Review [draft hackathon slides](docs/hackathon-presentation.pptx) and [presentation source](docs/hackathon-presentation.json), now incorporating 13 retained observations through November 5 UTC. Catalog continuation, overlapping current/prior membership, and independently read 2025 PDFs extend earlier examples.

Selected [4:40 captioned recorded workflow](docs/irs-public-mcp-recorded-workflow.mp4) joins recorded MCP requests/results, returned source inspection, independent PDF reading, and separately dated answer comparison. PPTX embeds same recording immediately after cover; source-navigation slide links internally to playback. Source clocks retain recorded scope. Playback depends on presentation viewer media support.

Earlier [3:36 silent slide walkthrough](docs/hackathon-visual-draft.mp4) remains available with [original scope and validation](docs/hackathon-visual-draft.json). Earlier media and current selected recording retain distinct content and validation roles.

Rebuild editable presentation from committed JSON and local media:

```bash
uv run --script tools/build_presentation.py docs/hackathon-presentation.json
```

Renderer supports caller-selected `--output`, optional `--preview-dir`, and font lookup through `--font-dir`. Local media paths resolve beside JSON. Link targets accept URI strings or `{"slide_id":"recorded-workflow"}` objects; media layouts embed source bytes and generate posters when no poster image is supplied. Inline script dependencies keep presentation tooling separate from server runtime. Recorded candidate checks used python-pptx 1.0.2 and Pillow 13.0.0.

Focused renderer capability checks use inline test dependencies:

```bash
uv run --script tools/tests/test_build_presentation.py
```
