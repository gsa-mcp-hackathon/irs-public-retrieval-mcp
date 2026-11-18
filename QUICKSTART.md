# Quickstart — IRS public retrieval

Connect local MCP clients to implemented IRS passage, product-catalog, and PDF retrieval tools.

## 1. Install prerequisites

You need [uv](https://docs.astral.sh/uv/) (a fast Python package manager):

```bash
pip install uv     # or: brew install uv
```

## 2. Set up the project

```bash
cp .env.example .env
uv sync
```

## 3. Run the server

```bash
uv run python main.py
```

The server starts in **stdio** mode and waits for a client to connect over
stdin/stdout. That's correct — it doesn't print a URL, because a local MCP
server is launched *by* the client as a subprocess. Press `Ctrl-C` to stop it.

## 4. Connect a client

### Claude Code

Create or edit `.mcp.json` (or your user MCP settings) with the **absolute path**
to this repo:

```json
{
  "mcpServers": {
    "irs-public-retrieval": {
      "command": "uv",
      "args": ["run", "example-server"],
      "cwd": "/absolute/path/to/irs-public-retrieval-mcp"
    }
  }
}
```

### Claude Desktop

Add the same block to
`~/Library/Application Support/Claude/claude_desktop_config.json` (macOS) or
`%APPDATA%\Claude\claude_desktop_config.json` (Windows), then restart Claude
Desktop.

Once connected, call `get_irm_passage` with example arguments:

```json
{"citation": "1.11.2.5.2"}
```

Call `find_irs_products` with caller-selected query, year, and catalog controls, for example:

```json
{"query": "1040", "tax_year": 2024, "catalog": "both"}
```

Inspect returned product, title, revision, and catalog identities, then pass selected `matches[].url` as `document_url` to `get_irs_document`. Returned PDF bytes establish document acquisition; cover/year inspection and model PDF understanding require separate evidence. See [available tools](README.md#available-tools) for inputs and returned scope.

## 5. Verify everything

```bash
uv sync --group dev
uv run pytest tests/ -v      # tests pass
uv run ruff check .          # lint clean
```

## 6. Test HTTP mode (optional)

Cloud hosts run the server over HTTP. Try it locally:

```bash
MCP_TRANSPORT=streamable-http uv run python main.py
# in another terminal:
curl http://localhost:8000/health      # {"status":"healthy",...}
```

---

## Next steps

- **Review retrieval semantics** — inspect [IRM passage identity](README.md#irm-passage-identity), [product and edition identity](README.md#product-and-edition-identity), and [PDF document acquisition](README.md#pdf-document-acquisition).
- **Review local entry points** — `example_server` package and `example-server` command retain upstream identities; see [local stdio use](README.md#local-stdio-use).
- **Review deployment options** — existing [deployment kits](deploy/README.md) cover IBM watsonx Orchestrate and Databricks; target hosting/client acceptance requires deployment-specific verification.
- **Review evaluation evidence** — see [recorded observations](README.md#evaluation-observations) and [evaluation guide](eval/README.md).
