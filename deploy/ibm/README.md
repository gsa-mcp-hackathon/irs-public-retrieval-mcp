# IBM watsonx Orchestrate — Deployment Kits

These kits support local toolkit preparation, Orchestrate registration, and public HTTP hosting. Use whichever outcomes fit current work; local preparation and hosted deployment can coexist.

| Kit | Transport / where it runs | Caller supplies | Result |
|---|---|---|---|
| **[`local-mcp-toolkit/`](local-mcp-toolkit/)** | stdio inside Orchestrate after import | Repository source and Python for preparation; compatible ADK, intended Orchestrate target, and compatible administrative authentication for registration | Prepared package with `--prepare-only`, or imported local toolkit |
| **[`code-engine-git-build/`](code-engine-git-build/)** | streamable-HTTP on IBM Code Engine | Reachable public Git source, Code Engine authority, explicit ICR coordinates, and registry-capable API key | Server-side build, registry push, and hosted `/mcp` endpoint |
| **[`prebuilt-image/`](prebuilt-image/)** | streamable-HTTP on IBM Code Engine | Existing publicly pullable IRS server image and Code Engine authority | Hosted `/mcp` endpoint using supplied `IMAGE` |

## Choosing supported outcomes

- **Prepare or register local stdio tools:** `local-mcp-toolkit/` stages existing server code without container hosting. Preparation needs neither IBM credentials nor ADK installation. Registration ships code into Orchestrate.
- **Build and host from Git with ICR access:** `code-engine-git-build/` builds server-side and pushes into configured ICR namespace. Supplied script assumes public source because it configures no Git credentials.
- **Host existing images:** `prebuilt-image/` deploys supplied public images without registry write access. Image production and publication remain separate caller work; supplied script requires nonempty `IMAGE`.

Code Engine hosting ends with public application URLs. Optional Orchestrate remote-toolkit registration uses deployed `/mcp` URLs with `streamable_http`. Toolkit import, target tool discovery, IRS tool execution, and agent use require separate validation.

## Prerequisites by action

- **Local preparation:** repository source and Python 3.11+.
- **Code Engine hosting:** IBM Cloud CLI, `code-engine` plugin, authenticated administrative access, and project/app authority. Git builds additionally use `container-registry`, ICR access, and registry-secret credentials. Account entitlement must permit Code Engine projects.
- **Supplied Orchestrate registration steps:** compatible Orchestrate ADK, intended instance URL, and administrative API key. Local registration defaults `WXO_ENV_TYPE` to `ibm_iam` and checks exact environment identity before activation; remote runbook shows SaaS registration. Other IBM environment types require target-specific configuration and compatible authentication.

IBM-published ADK 2.19.1 declares Python `>=3.11,<3.15`; installed and target ADK versions require independent verification. See [ADK package metadata](https://pypi.org/project/ibm-watsonx-orchestrate/) and [IBM environment documentation](https://developer.watson-orchestrate.ibm.com/environment/initiate_environment).

Each kit includes runbook instructions, nonsecret `.env.example` coordinates, and scripts. Package indexes, trust configuration, and network access follow caller environments; preparation alone establishes no dependency-installation or target-runtime result.

## Anonymous public reads and administrative access

Hosted IRS tools intentionally accept anonymous public reads. IBM Cloud deployment and Orchestrate administration authenticate separately; their API keys do not become MCP caller credentials. Local stdio registration creates no public HTTP endpoint. Public application access does not itself require public source or public container images; supplied hosting scripts make their own qualified source and registry choices.
