# syntax=docker/dockerfile:1
# Container image for remote (streamable-HTTP) deployment.
#
# Used by:
#   - IBM Code Engine (deploy/ibm/)
#   - cloud.gov (docker image path) and any other container host
#
# The server serves MCP over streamable-HTTP at :8080/mcp with a health check
# at :8080/health. app.py auto-selects HTTP because PORT is set below.

FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PORT=8080

WORKDIR /app

# Install uv (fast, reproducible installs).
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Install locked runtime dependencies and packaged project.
COPY pyproject.toml uv.lock README.md ./
COPY src ./src
RUN uv sync --locked --no-dev --no-editable --no-cache --python /usr/local/bin/python

EXPOSE 8080

# PORT=8080 (set above) makes app.py run HTTP on that port automatically.
CMD ["/app/.venv/bin/python", "-m", "example_server.app"]
