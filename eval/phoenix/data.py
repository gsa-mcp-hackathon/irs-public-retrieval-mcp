"""Caller-selected datasets with generation and reference inputs separated."""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

import yaml


def load_examples(path: Path) -> list[dict[str, Any]]:
    """Read CSV or JSONL without exposing references to agent generation."""
    with path.open(encoding="utf-8-sig", newline="") as stream:
        if path.suffix.lower() == ".csv":
            records = list(csv.DictReader(stream))
        else:
            records = [json.loads(line) for line in stream if line.strip()]
    examples = []
    for index, record in enumerate(records):
        query = record.get("query")
        if not isinstance(query, str) or not query.strip():
            raise ValueError(f"Dataset row {index}: nonempty query required")
        expected = record.get("expected")
        if expected is None:
            expected = {"responses": record.get("responses", "")}
        elif isinstance(expected, str):
            expected = json.loads(expected)
        literal_fields = record.get("literal_fields", [])
        if isinstance(literal_fields, str):
            literal_fields = json.loads(literal_fields or "[]")
        source = record.get("source", {})
        if isinstance(source, str):
            source = json.loads(source or "{}")
        examples.append(
            {
                "id": str(record.get("id") or index),
                "input": {"query": query},
                "expected": {**expected, "literal_fields": literal_fields},
                "metadata": {"source": source},
            }
        )
    return examples


def resolve_dataset(registry: Path, name: str) -> Path:
    """Resolve registry-relative source path."""
    definitions = yaml.safe_load(registry.read_text(encoding="utf-8"))
    entry = definitions["datasets"][name]
    return (registry.parent / entry["path"]).resolve()
