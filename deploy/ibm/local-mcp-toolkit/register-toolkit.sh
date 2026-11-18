#!/usr/bin/env bash
# Register this MCP server as a LOCAL MCP toolkit in watsonx Orchestrate.
#
# A local MCP toolkit ships this server's code to Orchestrate, which installs it
# (via requirements.txt at package_root) and runs `python server.py` over stdio
# INSIDE the Orchestrate runtime — no HTTP endpoint, no Code Engine, no container.
#
# Prerequisites:
#   - Python 3.11-3.14
#   - ADK installed:  pip install --upgrade ibm-watsonx-orchestrate
#   - Config:         cp .env.example .env && edit
#
# Usage:
#   set -a; source deploy/ibm/local-mcp-toolkit/.env; set +a
#   #   export WXO_API_KEY="<your key>"     # else you'll be prompted (hidden)
#   bash deploy/ibm/local-mcp-toolkit/register-toolkit.sh
#   bash deploy/ibm/local-mcp-toolkit/register-toolkit.sh --prepare-only
set -euo pipefail

# --- Select preparation or registration --------------------------------------
PREPARE_ONLY=false
case "${1:-}" in
  --prepare-only) PREPARE_ONLY=true; shift ;;
  "") ;;
  *) echo "Usage: $0 [--prepare-only]" >&2; exit 2 ;;
esac
if [[ $# -ne 0 ]]; then
  echo "Usage: $0 [--prepare-only]" >&2
  exit 2
fi

# --- Validate preparation config ---------------------------------------------
: "${TOOLKIT_NAME:?set TOOLKIT_NAME}"

# This script lives in the kit dir; toolkit.yaml sits next to it.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# repo root is three levels up: deploy/ibm/local-mcp-toolkit -> repo root
REPO_ROOT="$(cd "${SCRIPT_DIR}/../../.." && pwd)"
STAGE_DIR="${SCRIPT_DIR}/_stage"
TOOLKIT_YAML="${SCRIPT_DIR}/_toolkit.generated.yaml"

# The package to ship. If you renamed `example_server`, set PACKAGE_NAME to match
# (or export it before running).
PACKAGE_NAME="${PACKAGE_NAME:-example_server}"

echo "=== Target ==="
echo "  toolkit name:  ${TOOLKIT_NAME}"
echo "  package:       ${PACKAGE_NAME}"
echo ""

# --- Build a minimal, self-contained staging package_root --------------------
# Preserve flattened imports: package, server.py, and requirements.txt share
# package_root. Existing staging paths belong to this script.
echo "=== Staging minimal package_root at ${STAGE_DIR} ==="
rm -rf "${STAGE_DIR}"
mkdir -p "${STAGE_DIR}"
cp -R "${REPO_ROOT}/src/${PACKAGE_NAME}" "${STAGE_DIR}/${PACKAGE_NAME}"
cp "${SCRIPT_DIR}/server.py" "${STAGE_DIR}/server.py"
cp "${SCRIPT_DIR}/requirements.txt" "${STAGE_DIR}/requirements.txt"
find "${STAGE_DIR}" -type d -name '__pycache__' -prune -exec rm -rf {} + 2>/dev/null || true
STAGE_SIZE="$(du -sh "${STAGE_DIR}" | cut -f1)"
echo "  staged package_root size: ${STAGE_SIZE}"

# Quoted YAML scalars preserve caller metadata without adding dependencies.
# MSYS metadata exclusions apply only to this Python invocation.
if [[ "${TOOLKIT_DESCRIPTION+x}" ]]; then
  export TOOLKIT_DESCRIPTION
fi
TOOLKIT_NAME="${TOOLKIT_NAME}" \
  MSYS2_ENV_CONV_EXCL="${MSYS2_ENV_CONV_EXCL:+${MSYS2_ENV_CONV_EXCL};}TOOLKIT_NAME;TOOLKIT_DESCRIPTION" \
  "${PYTHON:-python}" - "${SCRIPT_DIR}/toolkit.yaml" "${TOOLKIT_YAML}" \
  "${STAGE_DIR}" <<'PY'
import json
import os
import sys
from pathlib import Path

if sys.version_info < (3, 11):
    raise SystemExit("Python 3.11 or newer required")

template, output, package_root = sys.argv[1:]
name = os.environ["TOOLKIT_NAME"]
values = {"package_root": package_root, "name": name}
if "TOOLKIT_DESCRIPTION" in os.environ:
    values["description"] = os.environ["TOOLKIT_DESCRIPTION"]

def yaml_string(value):
    # JSON escaping covers BMP characters; YAML escapes preserve higher codepoints.
    return '"' + "".join(
        f"\\U{ord(char):08x}" if ord(char) > 0xFFFF else json.dumps(char)[1:-1]
        for char in value
    ) + '"'

lines = Path(template).read_text(encoding="utf-8").splitlines(keepends=True)
with Path(output).open("w", encoding="utf-8", newline="\n") as generated:
    for line in lines:
        key = line.split(":", 1)[0]
        generated.write(
            f"{key}: {yaml_string(values[key])}\n" if key in values else line
        )
PY

if [[ "${PREPARE_ONLY}" == true ]]; then
  echo "=== Prepared ==="
  echo "  toolkit spec:  ${TOOLKIT_YAML}"
  echo "  package_root:  ${STAGE_DIR}"
  exit 0
fi

# --- Validate registration config --------------------------------------------
: "${WXO_ENV_NAME:?set WXO_ENV_NAME (source deploy/ibm/local-mcp-toolkit/.env)}"
: "${WXO_INSTANCE_URL:?set WXO_INSTANCE_URL}"
WXO_ENV_TYPE="${WXO_ENV_TYPE:-ibm_iam}"
echo "  env name:      ${WXO_ENV_NAME}"
echo "  instance URL:  ${WXO_INSTANCE_URL}"
echo "  auth type:     ${WXO_ENV_TYPE}"

# --- Confirm the ADK is installed ---------------------------------------------
if ! command -v orchestrate >/dev/null 2>&1; then
  echo "FATAL: 'orchestrate' not found. Install the ADK:" >&2
  echo "       pip install --upgrade ibm-watsonx-orchestrate" >&2
  exit 1
fi

# ADK 2.19.1 env list renders names/URLs only, with no structured/type output.
# Use native ADK Config for exact identity, including normal SDK defaults.
# Environment identity uses no auth-store access. Exit 3 means exact name absent.
# ADK_PYTHON permits staging and ADK to use independently selected interpreters.
read_environment_identity() {
  WXO_ENV_NAME="${WXO_ENV_NAME}" WXO_INSTANCE_URL="${WXO_INSTANCE_URL}" \
    WXO_ENV_TYPE="${WXO_ENV_TYPE}" \
    MSYS2_ENV_CONV_EXCL="${MSYS2_ENV_CONV_EXCL:+${MSYS2_ENV_CONV_EXCL};}WXO_ENV_NAME;WXO_INSTANCE_URL;WXO_ENV_TYPE" \
    "${ADK_PYTHON:-${PYTHON:-python}}" "${SCRIPT_DIR}/read-environment.py"
}
if read_environment_identity; then
  ENV_IDENTITY=matching
else
  ENV_STATUS=$?
  if [[ "${ENV_STATUS}" -eq 3 ]]; then
    ENV_IDENTITY=absent
  else
    exit "${ENV_STATUS}"
  fi
fi

# --- Obtain the API key (never written to disk) -------------------------------
API_KEY="${WXO_API_KEY:-}"
if [[ -z "${API_KEY}" ]]; then
  echo "=== watsonx Orchestrate API key ==="
  read -r -s -p "  API key (input hidden): " API_KEY
  echo ""
  if [[ -z "${API_KEY}" ]]; then
    echo "FATAL: no API key provided." >&2
    exit 1
  fi
fi

# --- Point the ADK at the instance and activate it ----------------------------
echo "=== Configuring ADK environment '${WXO_ENV_NAME}' ==="
if [[ "${ENV_IDENTITY}" == matching ]]; then
  echo "  exact environment name, URL, and auth type match — reusing."
else
  orchestrate env add --name "${WXO_ENV_NAME}" --url "${WXO_INSTANCE_URL}" --type "${WXO_ENV_TYPE}"
  if ! read_environment_identity; then
    echo "FATAL: ADK did not configure supplied environment identity." >&2
    exit 1
  fi
fi
orchestrate env activate "${WXO_ENV_NAME}" --api-key "${API_KEY}"
orchestrate env list

# --- Import (or re-import) the local MCP toolkit ------------------------------
echo "=== Importing local MCP toolkit '${TOOLKIT_NAME}' ==="
if orchestrate toolkits list 2>/dev/null | grep -q "${TOOLKIT_NAME}"; then
  echo "  toolkit exists — removing before re-import."
  orchestrate toolkits remove --name "${TOOLKIT_NAME}" || true
fi

orchestrate toolkits import -f "${TOOLKIT_YAML}"

# --- Clean up generated artifacts --------------------------------------------
rm -rf "${STAGE_DIR}" "${TOOLKIT_YAML}"

echo ""
echo "=== Registered ==="
orchestrate toolkits list
echo ""
echo "Next: build/edit an agent in the Orchestrate UI, add the '${TOOLKIT_NAME}'"
echo "tools, and chat-test a question (see README Part 3)."
