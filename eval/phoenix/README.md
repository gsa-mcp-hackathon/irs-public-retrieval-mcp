# Agent use through Public MCP

Caller-selected models receive public IRS questions and use actual three-tool MCP interface. PydanticAI owns model/tool exchange; FastMCP owns stdio protocol and server lifetime. Recorder retains tool arguments, returned content, structured bodies, acquisition clocks, answer text, and reported model usage. Expected answers reach evaluators only.

## Setup and invocation

Use existing approved Python and package-index configuration. Evaluation dependencies stay in separate environment because original LangChain adapter examples target MCP SDK 1, while current server and Phoenix dependencies use MCP SDK 2. Installed PydanticAI provides maintained FastMCP integration. Root server environment remains independently installed.

```powershell
uv sync --project eval/phoenix --group dev --no-python-downloads
uv run --project eval/phoenix --no-sync python -m eval.phoenix.create_dataset --work-dir .cache/eval/phoenix
```

Run from repository root. Existing caller-owned credential/proxy lifecycle supplies model endpoint and credentials through process environment. Keep credentials outside source, datasets, trace settings, and anonymous IRS server. `AGENT_MODEL` and `JUDGE_MODEL` select roles independently; `AGENT_BASE_URL`/`JUDGE_BASE_URL` and `AGENT_API_KEY`/`JUDGE_API_KEY` override caller's `OPENAI_BASE_URL`/`OPENAI_API_KEY` bindings where needed. Model IDs, endpoints, and available setup remain caller inputs.

```powershell
uv run --project eval/phoenix --no-sync python -m eval.phoenix.run_experiment --agent-model $env:AGENT_MODEL --judge-model $env:JUDGE_MODEL --local-phoenix --output .cache/eval/run.jsonl
```

Each run first asks selected model to execute local receipt function. Tool execution and reproduced opaque receipt establish observed function use before MCP cases begin. `--smoke-only --no-judge` selects that probe alone. `--case-id` can repeat for selected cases; `--dataset`, `--registry`, and `--system-prompt` support caller-selected cases and prompts. `--no-judge` retains deterministic observations without model verdicts. `--server-command '["uv", "run", "--no-sync", "example-server"]'` supplies alternate JSON argv when needed, preserving child flags exactly. Default launches maintained `uv run --no-sync --project <repository> example-server` with repository cwd and explicit stdio selection.

`AGENT_PROVIDER`/`JUDGE_PROVIDER` accept `openai`, `openai-compatible`, and `watsonx-gateway` for existing compatible gateways. Native IBM agent setup remains separate: installed PydanticAI supplies no native Watsonx model adapter. IBM API key, project, regional endpoint, and function-capable model access were unavailable during implementation. IBM skill's actual function-calling requirement governs model choice; text-only chat capability does not establish tool use. Native IBM or additional gateway execution needs its own attained result. Distinct role variables or aliases likewise do not prove different backend models.

## Results and source checks

JSONL records flush phase entry before potentially slow tracing/service, model, MCP, and judge operations. Agent answers, reported usage, and errors reach immediate `agent_return` records before judging; final case records retain complete tool bodies, references, independent checks, and verdicts. `tool_call_attempts` counts client-call starts, while `tool_results_returned` counts recorded MCP returns, including error results. Client exceptions and returned MCP errors retain separate failure kinds. Successful source acquisition needs returned source/artifact evidence. Earlier run files retain their original field names and source-specific meanings. Read case findings individually: completed execution does not establish answer correctness, broad accuracy, cost savings, or model diversity.

Caught generation or adapter failures also retain available SDK model/tool messages, including source content, per-response usage, and interrupted states where supplied. Failed-request totals remain unknown when unavailable. Capture requires no Phoenix service; cancellation still propagates. Message-serialization failures retain original error/tool evidence with separate capture-error type. Process termination and restart recovery require separate durable receipts.

Optional `--local-phoenix` starts installed Phoenix CLI in owned loopback process, records endpoint/PID, sends PydanticAI OpenTelemetry traces, and closes service after run. Readiness uses actual database-ready endpoint; `--phoenix-startup-timeout` supplies optional caller-selected horizon. Runtime files stay beside selected output. Alternatively, `--phoenix-endpoint` selects existing OTLP HTTP endpoint. Local JSONL remains per-case results carrier; current runner creates no Phoenix experiment entity and associates no scores with uploaded datasets. Dataset upload is independent and explicit:

```powershell
uv run --project eval/phoenix --no-sync python -m eval.phoenix.create_dataset --upload --phoenix-url http://localhost:6006 --work-dir .cache/eval/phoenix
```

Retained cases cover source-native IRM date characters/roles, conditional filing-season date guidance, and prior-year Form 1040 catalog/PDF retrieval. Source metadata records retained acquisition scope. Current source may differ; evaluator preserves fresh evidence rather than declaring retained reference universally current. Literal checks establish exact-character presence and source-role support separately; model judgment still assesses answer-role semantics. PDF checks decode actual returned bytes, compare current receipt length/URI, and inspect PDF signature/MIME. Those checks establish neither printed tax year nor successful visual/content reading. Full PDF bodies remain in local tool records; model-judge projection supplies artifact metadata while omitting binary payload.

Phoenix correctness and scope verdicts remain model outputs. Judge evidence includes relevant generation outcome, error type, and supported HTTP status while excluding local stack paths and credentials. Binary projection identifies complete returned blobs retained outside judge context; it supplies no excerpt or inspection. Independent checks can contradict or qualify verdicts. Same-model judging retains potential shared blind spots; configured model identities and available request/response metadata remain available for comparison. Raw judge finish metadata and usage remain unavailable where libraries/receipts supply none.

## Focused verification

Disable unrelated pytest entry-point plugins so Phoenix's bundled plugin does not initialize user-home storage during ordinary unit checks. Pure data/path cases use in-memory inputs, and lifecycle cases use explicit stubs, so current focused suite needs no temporary-directory ACL boundary.

```powershell
$env:PYTEST_DISABLE_PLUGIN_AUTOLOAD = '1'
uv run --project eval/phoenix --no-sync python -m pytest eval/phoenix/tests -q -p pytest_asyncio.plugin -o asyncio_default_fixture_loop_scope=function
uv run --project eval/phoenix --no-sync ruff check eval/phoenix
```

Original acquired [evaluation skill](../../.agents/skills/mcp-eval/SKILL.md) supplied role/data/judge separation and Phoenix direction. IBM variant supplied Watsonx considerations. Current adapter choice follows installed APIs and [Prefect's PydanticAI scenario evaluations](https://github.com/PrefectHQ/prefect-mcp-server/blob/main/evals/README.md), with [support-oriented evaluation discussion](https://www.prefect.io/blog/is-your-mcp-server-actually-good) as further design context. Existing [recorded evaluations](../README.md) remain distinct from new executions.
