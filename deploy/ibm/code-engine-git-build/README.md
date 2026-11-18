# IBM Code Engine — Build-from-Git Deployment

Deploy IRS server source to **IBM Cloud Code Engine** through **public Git builds**. Supplied script clones configured source, builds its `Dockerfile` **server-side**, pushes into configured **IBM Container Registry (ICR) namespace**, and deploys resulting image. Local Docker and manual pushes are unnecessary.

This kit uses explicit ICR coordinates and registry-capable API keys. [`../prebuilt-image/`](../prebuilt-image/README.md) supports deployment when callers already supply public IRS images; [`../local-mcp-toolkit/`](../local-mcp-toolkit/README.md) supports local preparation and stdio registration. These outcomes can coexist, subject to their independent inputs and authority.

## How it differs from the prebuilt-image kit

| | This kit | `../prebuilt-image/` |
|---|---|---|
| Source | Code Engine builds configured **Git source** | Caller supplies existing **public IRS image** reference |
| Local Docker | **Not needed** | Not needed (image already built) |
| Image registry | Pushes to **your ICR namespace** | Any public registry (e.g. GHCR) |
| Extra IBM authority | **ICR namespace + API key** | None |

---

## Part 1 — Prerequisites

### 1.1 Install the CLI + plugins

```bash
curl -fsSL https://clis.cloud.ibm.com/install/osx | sh    # or .../linux
ibmcloud plugin install code-engine
ibmcloud plugin install container-registry
```

### 1.2 Log in and discover your account's values

```bash
ibmcloud login --sso
ibmcloud resource groups      # NOTE: many accounts have NO "Default" group
ibmcloud regions
ibmcloud cr region            # your CURRENT ICR region + domain
ibmcloud cr namespace-list    # existing ICR namespaces (may be pre-provisioned)
```

> **Account-reality gotchas:**
>
> - **Resource group:** use queried account values; available groups can include generated names such as `eid-<hash>`.
> - **ICR region:** registry targeting remains independent of Code Engine region. Use queried registry coordinates rather than assuming they match application region.
> - **Namespace reuse:** existing authorized namespaces avoid namespace creation; registry push permission remains required.

Required administrative authority covers Code Engine project/app operations, registry-secret configuration, and ICR pushes. Namespace creation requires additional authority only when configured namespace is absent. IAM API-key creation is unnecessary when callers already hold suitable keys. Account entitlement must permit Code Engine projects.

### 1.3 Configure the deploy env file

```bash
cp deploy/ibm/code-engine-git-build/.env.example deploy/ibm/code-engine-git-build/.env
# edit using queried account values; set GIT_REPO_URL to intended PUBLIC source
set -a; source deploy/ibm/code-engine-git-build/.env; set +a
```

Supplied script configures no Git credentials, so source must support anonymous cloning. Public application reads do not themselves require public source; [IBM repository builds](https://cloud.ibm.com/docs/codeengine?topic=codeengine-app-source-code) support additional source configurations outside this script. Point source inputs at intended IRS implementation.

### 1.4 Provide an IBM Cloud API key (for the ICR push secret)

Supply existing registry-capable keys through `IBMCLOUD_API_KEY`, or create keys when authorized. Following optional creation example also requires `jq`:

```bash
export IBMCLOUD_API_KEY="$(ibmcloud iam api-key-create ce-icr-push \
    -d 'Code Engine ICR push' --output json | jq -r .apikey)"
```

If unset, script prompts with hidden input. Keys populate Code Engine registry secrets; keep them outside committed files and retain them while dependent registry operations need access. Remove task-owned keys during teardown after their dependencies end.

---

## Part 2 — Deploy (build from Git)

```bash
set -a; source deploy/ibm/code-engine-git-build/.env; set +a
bash deploy/ibm/code-engine-git-build/deploy-build-from-git.sh
```

Repeated runs create or update configured resources:

1. Verify CLI login, and target configured region and resource group.
2. Create or reuse configured ICR namespace.
3. Create or select configured Code Engine project.
4. Create or update registry secret from supplied API key.
5. Run `ce app create/update --build-source …`: clone → build → push → deploy.
6. Print public application URL and ICR image reference.

### Smoke-test

```bash
bash deploy/ibm/code-engine-git-build/smoke-test.sh https://<app>.<region>.codeengine.appdomain.cloud
```

Smoke checks require Bash, `curl`, repository checkout, and repository runtime dependencies installed in selected Python environment. Wrapper uses `${PYTHON:-python}` and accepts application base URLs or explicit `/mcp` URLs. `/health` must return HTTP 200; response bodies remain uninterpreted. [Shared MCP checker](../../../tools/check_mcp_http.py) initializes MCP and reads every `tools/list` page, checking expected IRS tool names. Initialization, discovery, and cleanup share default budget of 60 seconds; pass `--timeout-seconds 120` after URL to adjust. IRS requests, PDF interpretation, and Orchestrate use require separate tool execution.

Confirm the image landed in ICR:

```bash
ibmcloud cr region-set "${ICR_REGION}"
ibmcloud cr images --restrict "${ICR_NAMESPACE}"
```

---

## Part 3 — Register in watsonx Orchestrate

Optional remote registration uses deployed `/mcp` URL with `streamable_http`. Follow **Part 3** of [`../prebuilt-image/README.md`](../prebuilt-image/README.md#part-3--register-in-watsonx-orchestrate-saas), using application URL printed by this kit. Those SaaS registration instructions add ADK, instance access, and administrative credentials; Code Engine hosting and anonymous MCP reads remain independent. Toolkit listing, IRS execution, and agent use retain separate validation steps.

---

## Teardown

```bash
set -a; source deploy/ibm/code-engine-git-build/.env; set +a
ibmcloud ce app delete --name "${CE_APP_NAME}" -f
# ibmcloud ce registry delete --name "${CE_REGISTRY_SECRET}" -f
# ibmcloud ce project delete --name "${CE_PROJECT}" -f
ibmcloud cr region-set "${ICR_REGION}"
# ibmcloud cr image-rm "${ICR_DOMAIN}/${ICR_NAMESPACE}/${CE_APP_NAME}:${IMAGE_TAG}"
# ibmcloud iam api-key-delete ce-icr-push
```

---

## Files in this directory

| File | Purpose |
|---|---|
| `.env.example` | Deployment coordinates template (copy to `.env`, no secrets) |
| `deploy-build-from-git.sh` | Idempotent build-from-Git deploy (namespace → secret → build+deploy) |
| `smoke-test.sh` | HTTP health and MCP initialization/discovery checks; no IRS tool calls |
| `README.md` | This runbook |

## Known gaps / notes

- **API key handling:** script reads `IBMCLOUD_API_KEY` or prompts with hidden input, then stores credentials in Code Engine registry secrets through IBM APIs. It writes no local credential file. Key lifecycle follows dependent registry operations and caller ownership.
- **Region pairing:** the ICR region is independent of the Code Engine region;
  set `ICR_REGION` / `ICR_DOMAIN` from `ibmcloud cr region`.
- **Anonymous IRS reads:** public MCP access intentionally requires no caller credentials. IBM administrative login and registry keys remain separate from MCP requests.
