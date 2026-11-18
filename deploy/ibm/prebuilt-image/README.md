# IBM Cloud Deployment (Prebuilt Image) + watsonx Orchestrate

Deploy existing IRS server images to **IBM Cloud Code Engine**, producing public streamable-HTTP endpoints. Optional **watsonx Orchestrate** registration follows hosting as separate client configuration.

Supplied script pulls caller-provided `IMAGE` references from public registries. It requires Code Engine administrative authority without registry write access. Image builds, publication, and Git operations remain outside this script.

Related capabilities: [`../code-engine-git-build/`](../code-engine-git-build/README.md) builds Git source and pushes into ICR; [`../local-mcp-toolkit/`](../local-mcp-toolkit/README.md) prepares or registers local stdio tools. These outcomes can coexist.

Hosting, toolkit registration, IRS tool execution, and agent use each need their own result evidence. Deployment alone establishes neither toolkit registration nor successful IRS reads.

## Supplying public IRS server images

Set nonempty `IMAGE` before deployment, using publicly pullable references such as `ghcr.io/<user>/<repo>:tag`. Supplied images must contain intended IRS implementation and expose `/mcp` and `/health` on configured `CE_PORT`; unrelated public images cannot establish IRS tool capability. No built IRS image reference or image-publication workflow ships with this kit.

**Optional image publication through GHCR**

Caller-managed build and publication workflows can supply images through GHCR. See:
[Working with the Container registry (GitHub Docs)](https://docs.github.com/en/packages/working-with-a-github-packages-registry/working-with-the-container-registry)

For this script, published packages must permit anonymous image pulls. Public image access reflects omitted registry credentials in supplied script; anonymous MCP access does not itself require public images or public source.

## What gets deployed

- **Transport:** MCP over streamable-HTTP at `/mcp`; health check at `/health`
- **Port:** `8080` for images built from repository `Dockerfile`; match `CE_PORT` to supplied image

---

## Part 1 — Prerequisites

### 1.1 Configure the deploy env file

```bash
cp deploy/ibm/prebuilt-image/.env.example deploy/ibm/prebuilt-image/.env
# edit it:
#   - IBMCLOUD_REGION / IBMCLOUD_RESOURCE_GROUP: intended account coordinates
#   - CE_APP_NAME: your server's name
#   - CE_PROJECT / CE_PORT: intended project and container listen port
#   - IMAGE: existing publicly pullable IRS server image reference (required)
set -a; source deploy/ibm/prebuilt-image/.env; set +a
```

`.env` holds nonsecret deployment coordinates and remains git-ignored. IBM administrative credentials belong to CLI login configuration.

### 1.2 Install the IBM Cloud CLI + plugins

```bash
# macOS/Linux
curl -fsSL https://clis.cloud.ibm.com/install/osx | sh   # macOS
# or: curl -fsSL https://clis.cloud.ibm.com/install/linux | sh

ibmcloud plugin install code-engine
ibmcloud --version
```

Alternatively, use [IBM Cloud Shell](https://cloud.ibm.com/shell) and verify required CLI/plugin availability there.

### 1.3 Log in

```bash
ibmcloud login --sso          # federated / SSO accounts
# or: ibmcloud login --apikey <API_KEY>

ibmcloud resource groups      # note your group (often "Default", sometimes eid-<hash>)
ibmcloud regions              # pick one near you
```

Account entitlement and administrative permissions must permit Code Engine projects and applications.

---

## Part 2 — Deploy to Code Engine

```bash
set -a; source deploy/ibm/prebuilt-image/.env; set +a
bash deploy/ibm/prebuilt-image/deploy-code-engine.sh
```

Repeated runs create or update configured resources:

1. Verify CLI login, and target configured region and resource group.
2. Create or select Code Engine project `CE_PROJECT`.
3. Create or update configured app using required `IMAGE`.
4. Print public app, `/mcp`, and `/health` URLs.

Script sets `--min-scale 1`, `--cpu 0.5`, and `--memory 1G`. Warm-instance configuration does not establish tool latency or successful client use.

### Smoke-test the live endpoint

```bash
bash deploy/ibm/prebuilt-image/smoke-test.sh https://<app>.<region>.codeengine.appdomain.cloud
```

Smoke checks require Bash, `curl`, repository checkout, and repository runtime dependencies installed in selected Python environment. Wrapper uses `${PYTHON:-python}` and accepts application base URLs or explicit `/mcp` URLs. `/health` must return HTTP 200; response bodies remain uninterpreted. [Shared MCP checker](../../../tools/check_mcp_http.py) initializes MCP and reads every `tools/list` page, checking expected IRS tool names. Initialization, discovery, and cleanup share default budget of 60 seconds; pass `--timeout-seconds 120` after URL to adjust. IRS requests, PDF interpretation, and Orchestrate use require separate tool execution.

---

## Part 3 — Register in watsonx Orchestrate (SaaS)

watsonx Orchestrate imports a **remote MCP server** as a **toolkit**.

This optional section requires SaaS instance access and administrative API credentials. Code Engine hosting and anonymous MCP reads work independently of Orchestrate registration. Other Orchestrate environment types need target-specific configuration; see [IBM environment documentation](https://developer.watson-orchestrate.ibm.com/environment/initiate_environment).

### 3.1 Install the ADK

```bash
pip install --upgrade ibm-watsonx-orchestrate   # Python 3.11–3.14
orchestrate --version
```

IBM-published ADK 2.19.1 declares Python `>=3.11,<3.15`; verify installed version and target compatibility independently. Package indexes and trust configuration follow caller environments. See [ADK package metadata](https://pypi.org/project/ibm-watsonx-orchestrate/).

### 3.2 Point the ADK at your instance

Obtain intended **service instance URL** and administrative **API key** from Orchestrate SaaS UI (Settings → API details). Use fresh environment names or verify existing entries match intended instance before activation:

```bash
orchestrate env add --name gsa-hackathon --url "<YOUR_ORCHESTRATE_INSTANCE_URL>"
orchestrate env activate gsa-hackathon --api-key "<YOUR_ORCHESTRATE_API_KEY>"
orchestrate env list
```

### 3.3 Add your server as a toolkit

```bash
orchestrate toolkits add \
  --kind mcp \
  --name my_server \
  --description "<what your server does + tool names>" \
  --url "https://<app>.<region>.codeengine.appdomain.cloud/mcp" \
  --transport streamable_http \
  --tools "*"

orchestrate toolkits list
```

Keep `/mcp` and `--transport streamable_http` for this server. Transport errors require checking deployed endpoint, installed ADK version, and [IBM remote-toolkit documentation](https://developer.watson-orchestrate.ibm.com/tools/toolkits/remote_mcp_toolkits); supplied server exposes no legacy SSE route.

### 3.4 Create an agent that uses the toolkit

In Orchestrate UI, create or edit agents, attach imported tools, and provide task instructions. Confirm target tool discovery, execute intended IRS tools with representative inputs, and inspect returned sources before validating agent use. Toolkit listing alone establishes no successful tool execution.

---

## Teardown

```bash
set -a; source deploy/ibm/prebuilt-image/.env; set +a
ibmcloud ce app delete --name "${CE_APP_NAME}" -f
# ibmcloud ce project delete --name "${CE_PROJECT}" -f   # removes all apps in it
orchestrate toolkits remove --name my_server
```

---

## Files in this directory

| File | Purpose |
|---|---|
| `.env.example` | Deployment coordinates template (copy to `.env`, no secrets) |
| `deploy-code-engine.sh` | Idempotent deploy — pulls and deploys a prebuilt public image |
| `smoke-test.sh` | HTTP health and MCP initialization/discovery checks; no IRS tool calls |
| `README.md` | This runbook |

## Known gaps / notes

- **Image access:** supplied script requires existing public `IMAGE` and configures no registry credentials. IBM supports authenticated image pulls with separate configuration; see [Code Engine image deployment](https://cloud.ibm.com/docs/codeengine?topic=codeengine-deploy-app).
- **Administrative authority:** Code Engine login and project/app permissions remain required. This script performs neither Git builds nor registry pushes.
- **Anonymous IRS reads:** public MCP access intentionally requires no caller credentials. Deployment and Orchestrate administrative keys remain separate from MCP requests.
