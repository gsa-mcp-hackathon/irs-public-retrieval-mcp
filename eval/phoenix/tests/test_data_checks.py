import base64
import json
from io import StringIO
from pathlib import Path

from eval.phoenix.checks import (
    independent_checks,
    literal_observations,
    pdf_observations,
)
from eval.phoenix.data import load_examples, resolve_dataset


def test_generation_input_excludes_ground_truth(monkeypatch):
    source = Path("caller-cases.jsonl")
    serialized = (
        json.dumps(
            {
                "id": "source-question",
                "query": "Retrieve official source.",
                "expected": {"responses": "HIDDEN REFERENCE"},
                "source": {"acquired": "2026-11-05T00:22:18Z"},
            }
        )
        + "\n"
    )
    monkeypatch.setattr(Path, "open", lambda self, **kwargs: StringIO(serialized))
    row = load_examples(source)[0]
    assert row["input"] == {"query": "Retrieve official source."}
    assert row["expected"]["responses"] == "HIDDEN REFERENCE"
    assert row["metadata"]["source"]["acquired"] == "2026-11-05T00:22:18Z"


def test_registry_path_uses_registry_directory(monkeypatch):
    registry = Path("caller-config") / "datasets.yaml"
    monkeypatch.setattr(
        Path,
        "read_text",
        lambda self, **kwargs: (
            "datasets:\n  caller-dataset:\n    path: ../inputs/questions.csv\n"
        ),
    )
    assert (
        resolve_dataset(registry, "caller-dataset")
        == (registry.parent / "../inputs/questions.csv").resolve()
    )


def test_literal_characters_and_source_role_are_independent():
    field = {"value": "06-09-2026", "meaning": "Effective", "context": "Effective"}
    calls = [
        {
            "result": {
                "structuredContent": {
                    "dates": [
                        {**field, "meaning": "Subsection", "context": "Subsection"}
                    ]
                }
            }
        }
    ]
    result = literal_observations("Effective 06‑09‑2026", [field], calls)[0]
    assert result["exact_value_present_in_answer"] is False
    assert result["reference_matches_current_tool_field"] is False


def test_changed_fresh_date_does_not_become_retained_reference_match():
    field = {"value": "06-09-2026", "meaning": "Effective", "context": "Effective"}
    fresh = {**field, "value": "11-17-2026"}
    calls = [{"result": {"structuredContent": {"dates": [fresh]}}}]
    result = literal_observations("Effective 11-17-2026", [field], calls)[0]
    assert result["reference_matches_current_tool_field"] is False
    assert result["current_matching_role_fields"] == [fresh]


def test_pdf_integrity_uses_actual_blob_and_current_receipt():
    pdf = b"%PDF-1.7\nowned synthetic bytes\n"
    resource_url = "https://www.irs.gov/pub/irs-prior/f1040--2024.pdf"
    calls = [
        {
            "name": "get_irs_document",
            "result": {
                "structuredContent": {
                    "source": {"url": resource_url},
                    "byte_count": len(pdf) + 1,
                },
                "content": [
                    {
                        "type": "resource",
                        "resource": {
                            "uri": resource_url,
                            "mimeType": "application/pdf",
                            "blob": base64.b64encode(pdf).decode(),
                        },
                    }
                ],
            },
        }
    ]
    result = pdf_observations(calls)[0]
    assert result["valid_base64"] is True
    assert result["pdf_signature"] is True
    assert result["uri_matches_source"] is True
    assert result["byte_count_matches"] is False
    assert "unassessed" in result["scope"]


def test_invalid_blob_is_observation_not_success():
    calls = [{"result": {"content": [{"resource": {"blob": "not base64"}}]}}]
    assert pdf_observations(calls)[0]["valid_base64"] is False


def test_call_attempts_returned_results_and_failure_kinds_stay_distinct():
    observations = independent_checks(
        {"expected": {}},
        {
            "tool_calls": [
                {"name": "never_returned", "error_type": "ConnectionError"},
                {"name": "returned_error", "result": {"isError": True}},
            ]
        },
    )
    assert observations["tool_call_attempts"] == 2
    assert observations["tool_results_returned"] == 1
    assert [item["failure_kind"] for item in observations["tool_failures"]] == [
        "client_exception",
        "mcp_error_result",
    ]
