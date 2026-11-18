# watsonx Orchestrate — Local MCP Toolkit (stdio)

Prepare existing IRS server code for **local MCP toolkit** import, or register it in watsonx Orchestrate. After import, Orchestrate installs package-root `requirements.txt` and runs `server.py` **over stdio inside Orchestrate runtime**. This route creates no public HTTP endpoint.

| Outcome | Caller supplies | Result |
|---|---|---|
| **Preparation only** | Repository source, Python 3.11+, and toolkit metadata | Flattened package and generated YAML for inspection |
| **Local toolkit registration** | Prepared source, ADK, intended Orchestrate target, and compatible administrative credentials | Imported stdio toolkit inside Orchestrate |
| **Hosted HTTP service** | Hosting configuration from [`../code-engine-git-build/`](../code-engine-git-build/README.md) or [`../prebuilt-image/`](../prebuilt-image/README.md) | Public `/mcp` endpoint for remote clients |

Local preparation, local registration, and HTTP hosting can coexist. Registration requires ADK and source on importing machines; subsequent Orchestrate execution depends on target runtime and network access.

## How it reuses this template

`server.py` imports existing FastMCP app (`example_server.app:mcp`) and runs it over stdio. Registration script stages **flattened** package contents, preserving current tool implementations. Re-import after source or dependency changes.

```
deploy/ibm/local-mcp-toolkit/
├── server.py           # stdio entrypoint: `from example_server.app import mcp; mcp.run(transport="stdio")`
├── requirements.txt    # runtime dependency lower bounds staged beside package
├── toolkit.yaml        # import config template (kind: mcp, command: python server.py, tools: *)
├── register-toolkit.sh # stage flattened package_root + activate ADK env + import (idempotent)
├── read-environment.py # compare exact configured ADK environment identity before activation
├── .env.example        # instance URL + env/toolkit names (no secrets)
└── README.md           # this runbook
```

Staging directory `_stage/` is git-ignored and contains sibling `example_server/`, `server.py`, and `requirements.txt` paths without `src/` nesting. Generated YAML points `package_root` there, keeping upload contents focused and preserving imports. Runtime requirements specify lower bounds; resolved dependency versions and successful target installation require independent evidence. See [IBM local-toolkit documentation](https://developer.watson-orchestrate.ibm.com/tools/toolkits/local_mcp_toolkits).

---

## Part 1 — Prerequisites by action

Preparation requires repository source and Python 3.11+; continue through **2.1a** without installing ADK or supplying IBM credentials. Registration additionally requires compatible ADK, intended Orchestrate instance, and authentication compatible with supplied API-key flow. `WXO_ENV_TYPE` defaults to `ibm_iam` for IBM Cloud. Other [IBM environment types](https://developer.watson-orchestrate.ibm.com/environment/initiate_environment) require target-specific configuration and can need additional authentication beyond supplied flow.

`ADK_PYTHON` selects Python containing installed ADK for environment-identity checks; default selection follows `PYTHON`, then `python`. Set it separately when staging Python and ADK use different environments. Selected interpreter must import installed ADK modules used for identity checks.

For registration, install ADK through caller-configured package indexes and trust settings:

```bash
pip install --upgrade ibm-watsonx-orchestrate   # Python 3.11-3.14
orchestrate --version
```

IBM-published ADK 2.19.1 declares Python `>=3.11,<3.15`; verify installed version and target compatibility independently. See [ADK package metadata](https://pypi.org/project/ibm-watsonx-orchestrate/). Preparation alone installs no runtime dependencies.

Find Orchestrate instance URL and API key on wxO service page in IBM Cloud (Resource List → intended watsonx Orchestrate instance). Pass API keys via `WXO_API_KEY`; keep credentials outside committed configuration. These administrative credentials remain separate from anonymous IRS tool requests.

---

## Part 2 — Register the toolkit

### 2.1 Configure the env file

```bash
cp deploy/ibm/local-mcp-toolkit/.env.example deploy/ibm/local-mcp-toolkit/.env
# edit: WXO_INSTANCE_URL, WXO_ENV_NAME, TOOLKIT_NAME, and WXO_ENV_TYPE
# optional: ADK_PYTHON when ADK uses separate Python environment
set -a; source deploy/ibm/local-mcp-toolkit/.env; set +a
```

### 2.1a Prepare without IBM access

Preparation requires Python 3.11+ and repository source. IBM credentials, ADK installation, and network access are unnecessary. `TOOLKIT_NAME` controls generated YAML `name`; optional `TOOLKIT_DESCRIPTION` controls generated `description`. Unset descriptions retain template defaults. Set `PYTHON` when preparation should use another installed Python executable.

```bash
TOOLKIT_NAME=irs_public_lookup \
TOOLKIT_DESCRIPTION='Retrieve public IRS manual passages with get_irm_passage, and locate forms, instructions, and publications with find_irs_products.' \
bash deploy/ibm/local-mcp-toolkit/register-toolkit.sh --prepare-only
```

`--prepare-only` retains ignored `_stage/` and `_toolkit.generated.yaml` for inspection. Staged contents preserve flattened package imports, `server.py`, and `requirements.txt`. Running without `--prepare-only` rebuilds these outputs before authentication, imports configured metadata, and removes generated outputs after successful registration.

### 2.2 Provide your API key and run the register script

```bash
export WXO_API_KEY="<your Orchestrate API key>"   # else prompted (hidden)
bash deploy/ibm/local-mcp-toolkit/register-toolkit.sh
```

Before activation, registration checks exact, case-sensitive environment names, literal URLs, and effective authentication types. Matching identities are reused; missing names are added and rechecked. Absent or empty configuration and absent environment sections count as requested names absent. Explicit stored auth types must match caller selections. Omitted or null stored types can match `ibm_iam` when selected ADK's URL resolver identifies IBM Cloud; unresolved inferred types require explicit configuration through ADK or distinct `WXO_ENV_NAME`. Native SDK configuration loading can initialize files and defaults, including protected local environments and Python registry settings, before identity checks. Conflicting, malformed, or unreadable identities stop before activation and toolkit import; those failures leave named target identity fields unchanged. Caller type selections must match installed ADK enum values exactly; comparison performs no URL or type normalization.

Registration stages flattened `package_root`, activates configured ADK environments after identity checks, imports caller-configured toolkit metadata, lists toolkits, and cleans up. Repeated runs pick up code and dependency changes. Toolkit listing confirms registration visibility; target dependency installation, tool discovery, and successful IRS calls need separate validation.

> **If you renamed the package** from `example_server`, run with
> `PACKAGE_NAME=<your_pkg>` exported (and update `server.py`'s import).

### 2.2a Corporate TLS interception (Zscaler / GSA network) — may be required

On a GSA-managed network the ADK's IAM login may fail with
`SSLCertVerificationError: unable to get local issuer certificate`. This is a
TLS-inspection proxy re-signing HTTPS with a private CA that Python's `certifi`
bundle doesn't trust. Fix by giving Python a CA bundle that includes the proxy
root exported from the keychain:

```bash
# 1. Confirm interception (issuer names your proxy, e.g. Zscaler):
openssl s_client -connect iam.cloud.ibm.com:443 -showcerts </dev/null 2>/dev/null \
  | openssl x509 -noout -issuer

# 2. Export the proxy root(s) from the macOS System keychain:
security find-certificate -a -c "Zscaler" -p /Library/Keychains/System.keychain \
  > /tmp/zscaler-roots.pem 2>/dev/null
security find-certificate -a -c "Zscaler" -p /System/Library/Keychains/SystemRootCertificates.keychain \
  >> /tmp/zscaler-roots.pem 2>/dev/null

# 3. Merge with certifi:
CERTIFI="$(python -c 'import certifi; print(certifi.where())')"
cat "$CERTIFI" /tmp/zscaler-roots.pem > /tmp/wxo-ca-bundle.pem

# 4. Point the ADK at the merged bundle IN THIS SHELL, then run the register script:
export SSL_CERT_FILE=/tmp/wxo-ca-bundle.pem
export REQUESTS_CA_BUNDLE=/tmp/wxo-ca-bundle.pem
```

### 2.3 (Optional) Start entrypoint locally

```bash
# From the repo root, with the repo installed (uv sync or pip install -e .):
python deploy/ibm/local-mcp-toolkit/server.py
# Waits for MCP stdio input; Ctrl-C exits. Startup alone verifies no tool calls.
```

Use compatible MCP clients for initialization, tool discovery, and representative IRS tool calls. Local client success and Orchestrate runtime success remain separate evidence.

See [FastMCP client subprocess example](../../../README.md#fastmcp-client-subprocess) for caller-selected source and network environment forwarding, result inspection, and owned-process cleanup.

---

## Part 3 — Validate target tools and optional agent use

Confirm target tool discovery and execute intended IRS tools with representative inputs. Inspect returned sources, then create or edit agents in Orchestrate UI, attach toolkit tools, and provide task instructions. Chat-test intended questions to establish agent use separately from toolkit import.

---

## Connections (only if your server needs secrets)

IRS tools retrieve public data anonymously, so `toolkit.yaml` declares no `connections`. Orchestrate administration still authenticates. Adaptations with credential-dependent tools can configure connections separately:

```bash
orchestrate connections add -a my_connection
for env in draft live; do
  orchestrate connections configure -a my_connection --env $env --type team --kind key_value
  orchestrate connections set-credentials -a my_connection --env $env -e "SECURE_VAR=value"
done
# then add `connections: [my_connection]` to toolkit.yaml
```

---

## Teardown

```bash
orchestrate toolkits remove --name "${TOOLKIT_NAME}"
```

---

## Known gaps / notes

- **Runs inside Orchestrate:** local stdio import produces no public endpoint. Validate target discovery, tool execution, and agent use at their actual consumers.
- **Runtime behavior:** startup cost, dependency resolution, and IRS network access depend on target runtime. Prepared files and toolkit listing establish none of those results.
- **Registration inputs:** importing machines need Python, ADK, repository source, intended instance configuration, and administrative authority. Preparation-only runs need source and Python.
