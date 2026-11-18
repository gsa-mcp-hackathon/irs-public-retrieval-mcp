"""Caller-selected model roles without stored credentials."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from urllib.parse import urlsplit, urlunsplit


def display_endpoint(value: str | None) -> str | None:
    """Retain route identity while omitting URL credentials and query values."""
    if not value:
        return None
    parsed = urlsplit(value)
    hostname = parsed.hostname or ""
    if ":" in hostname:
        hostname = f"[{hostname}]"
    authority = f"{hostname}:{parsed.port}" if parsed.port else hostname
    return urlunsplit((parsed.scheme, authority, parsed.path, "", ""))


@dataclass
class ModelRole:
    role: str
    model: str
    provider: str = "openai"
    base_url: str | None = None
    api_key: str | None = field(default=None, repr=False)

    @classmethod
    def from_environment(cls, role: str, model: str | None = None) -> ModelRole:
        prefix = role.upper()
        selected = model or os.getenv(f"{prefix}_MODEL")
        if not selected:
            raise ValueError(f"{prefix}_MODEL or corresponding CLI model required")
        return cls(
            role=role,
            model=selected,
            provider=os.getenv(f"{prefix}_PROVIDER", "openai"),
            base_url=os.getenv(f"{prefix}_BASE_URL") or os.getenv("OPENAI_BASE_URL"),
            api_key=os.getenv(f"{prefix}_API_KEY") or os.getenv("OPENAI_API_KEY"),
        )

    def describe(self) -> dict:
        return {
            "role": self.role,
            "provider": self.provider,
            "configured_model": self.model,
            "endpoint": display_endpoint(self.base_url),
            "backend_identity": "Configured route; backend revision unattested",
        }

    def agent_model(self, client):
        """Reuse PydanticAI's OpenAI-compatible model implementation."""
        from pydantic_ai.models.openai import OpenAIChatModel
        from pydantic_ai.providers.openai import OpenAIProvider

        if self.provider not in {"openai", "openai-compatible", "watsonx-gateway"}:
            raise ValueError(
                f"Agent provider {self.provider!r} needs supported adapter or "
                "existing OpenAI-compatible gateway; native IBM setup is separate"
            )
        return OpenAIChatModel(
            self.model, provider=OpenAIProvider(openai_client=client)
        )


def anonymous_server_environment(environment: dict[str, str]) -> dict[str, str]:
    """Pass OS/network context while excluding model credentials and host ports."""
    names = {
        "PATH",
        "PATHEXT",
        "SYSTEMROOT",
        "WINDIR",
        "COMSPEC",
        "USERPROFILE",
        "HOME",
        "TEMP",
        "TMP",
        "APPDATA",
        "LOCALAPPDATA",
        "PROGRAMDATA",
        "HTTP_PROXY",
        "HTTPS_PROXY",
        "ALL_PROXY",
        "NO_PROXY",
        "SSL_CERT_FILE",
        "SSL_CERT_DIR",
        "REQUESTS_CA_BUNDLE",
        "CURL_CA_BUNDLE",
    }
    selected = {
        key: value for key, value in environment.items() if key.upper() in names
    }
    selected["MCP_TRANSPORT"] = "stdio"
    selected["PYTHONUTF8"] = "1"
    return selected
