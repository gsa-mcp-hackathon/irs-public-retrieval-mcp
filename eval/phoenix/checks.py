"""Independent source/artifact observations alongside model verdicts."""

from __future__ import annotations

import base64
import binascii
from typing import Any


def structured_results(calls: list[dict[str, Any]]):
    """Yield structured MCP outputs, retaining raw calls separately."""
    for call in calls:
        result = call.get("result", {})
        body = result.get("structuredContent")
        if isinstance(body, dict):
            yield body


def _dates(value: Any):
    if isinstance(value, dict):
        if isinstance(value.get("value"), str) and "meaning" in value:
            yield value
        for child in value.values():
            yield from _dates(child)
    elif isinstance(value, list):
        for child in value:
            yield from _dates(child)


def literal_observations(answer: str, fields: list[dict], calls: list[dict]) -> list:
    """Check exact characters and retained-role support, without semantic scoring."""
    actual_dates = [date for body in structured_results(calls) for date in _dates(body)]
    observations = []
    for field in fields:
        value = field["value"]
        matching_roles = [
            date
            for date in actual_dates
            if date.get("meaning") == field.get("meaning")
            and " ".join(field.get("context", "").split())
            == " ".join(date.get("context", "").split())
        ]
        observations.append(
            {
                "reference": field,
                "exact_value_present_in_answer": value in answer,
                "reference_matches_current_tool_field": any(
                    date.get("value") == value for date in matching_roles
                ),
                "current_matching_role_fields": matching_roles,
                "scope": (
                    "Character presence and source-field support only; "
                    "answer-role semantics need separate assessment"
                ),
            }
        )
    return observations


def pdf_observations(calls: list[dict]) -> list[dict]:
    """Inspect actual MCP PDF bytes against accompanying acquisition metadata."""
    observations = []
    for call in calls:
        result = call.get("result", {})
        metadata = result.get("structuredContent") or {}
        for block in result.get("content", []):
            resource = block.get("resource", {})
            if not isinstance(resource.get("blob"), str):
                continue
            item = {
                "tool": call.get("name"),
                "uri": resource.get("uri"),
                "mime_type": resource.get("mimeType"),
                "metadata_byte_count": metadata.get("byte_count"),
                "scope": "Artifact integrity; printed edition/content unassessed",
            }
            try:
                data = base64.b64decode(resource["blob"], validate=True)
            except (binascii.Error, ValueError):
                item["valid_base64"] = False
            else:
                item.update(
                    valid_base64=True,
                    decoded_byte_count=len(data),
                    byte_count_matches=len(data) == metadata.get("byte_count"),
                    pdf_signature=data.startswith(b"%PDF-"),
                    pdf_mime=resource.get("mimeType") == "application/pdf",
                    uri_matches_source=(
                        resource.get("uri") == metadata.get("source", {}).get("url")
                    ),
                )
            observations.append(item)
    return observations


def independent_checks(example: dict, output: dict) -> dict:
    """Keep tool use, source observations, and answer findings independently scoped."""
    calls = output.get("tool_calls", [])
    return {
        "tool_call_attempts": len(calls),
        "tool_results_returned": sum(
            isinstance(call.get("result"), dict) for call in calls
        ),
        "tool_names": [call.get("name") for call in calls],
        "tool_failures": [
            {
                "name": call.get("name"),
                "error_type": call.get("error_type"),
                "failure_kind": (
                    "client_exception" if call.get("error_type") else "mcp_error_result"
                ),
            }
            for call in calls
            if call.get("error_type") or call.get("result", {}).get("isError")
        ],
        "literal_fields": literal_observations(
            output.get("answer", ""),
            example["expected"].get("literal_fields", []),
            calls,
        ),
        "pdf_artifacts": pdf_observations(calls),
        "verdict_scope": "Separate observations; no aggregate accuracy inference",
    }
