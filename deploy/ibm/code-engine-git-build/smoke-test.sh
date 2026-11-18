#!/usr/bin/env bash
# Check HTTP health, MCP initialization, and IRS tool discovery.
# Requires repository checkout, curl, and Python with project dependencies.
# Usage: bash deploy/ibm/code-engine-git-build/smoke-test.sh <base-url-or-mcp-url> [probe-options]
set -euo pipefail

INPUT_URL="${1:?usage: smoke-test.sh <base-url-or-mcp-url> [probe-options]}"
shift
REPO_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../../.." && pwd)"
PYTHON="${PYTHON:-python}"
URLS="$("${PYTHON}" "${REPO_ROOT}/tools/check_mcp_http.py" "${INPUT_URL}" --resolve-app-url)"
HEALTH_URL="${URLS%%$'\n'*}"
MCP_URL="${URLS#*$'\n'}"

echo "Checking HTTP health: ${HEALTH_URL}"
HEALTH_CODE="$(curl --fail --silent --show-error --output /dev/null \
  --write-out '%{http_code}' "${HEALTH_URL}")"
if [[ "${HEALTH_CODE}" != "200" ]]; then
  echo "FAIL: health check returned HTTP ${HEALTH_CODE}" >&2
  exit 1
fi
echo "PASS: health returned HTTP 200"

exec "${PYTHON}" "${REPO_ROOT}/tools/check_mcp_http.py" "${MCP_URL}" \
  --expect-tool get_irm_passage \
  --expect-tool find_irs_products \
  --expect-tool get_irs_document \
  "$@"
