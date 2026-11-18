"""Phoenix model verdicts with reference and actual-source context."""

from __future__ import annotations

import json
from contextlib import asynccontextmanager
from dataclasses import asdict

import httpx


def judge_evidence(output: dict) -> str:
    """Supply actual tool bodies without pretending binary blobs were inspected."""

    def project(value):
        if isinstance(value, dict):
            return {
                key: (
                    {
                        "retained_base64_characters": len(item),
                        "projection": "whole_returned_blob_omitted_from_judge_context",
                        "complete_returned_blob_retained_in_raw_tool_record": True,
                        "content_inspection": "unassessed",
                    }
                    if key == "blob" and isinstance(item, str)
                    else project(item)
                )
                for key, item in value.items()
            }
        if isinstance(value, list):
            return [project(item) for item in value]
        return value

    error_type = output.get("error_type")
    status = output.get("http_status")
    generation = {
        "outcome": "failed" if error_type else "returned",
        "error_type": error_type,
        "http_status": status,
        "answer_present": bool(output.get("answer", "").strip()),
    }
    if status == 413:
        generation["failure_disposition"] = "request_payload_too_large"
    return json.dumps(
        {
            "generation": generation,
            "tool_calls": project(output.get("tool_calls", [])),
            "binary_projection_scope": (
                "Complete returned blobs remain in raw tool records outside judge "
                "context. This projection supplies metadata, no binary excerpt, "
                "and no content-inspection evidence."
            ),
        },
        ensure_ascii=False,
    )


@asynccontextmanager
async def create_judges(role):
    """Own SDK transport lifetimes while Phoenix retains judging protocol."""
    from phoenix.evals import LLM, ClassificationEvaluator

    async with httpx.AsyncClient() as async_http:
        with httpx.Client() as sync_http:
            if role.provider in {"openai", "openai-compatible", "watsonx-gateway"}:
                llm = LLM(
                    provider="openai",
                    model=role.model,
                    base_url=role.base_url,
                    api_key=role.api_key,
                    sync_client_kwargs={"http_client": sync_http},
                    async_client_kwargs={"http_client": async_http},
                )
            elif role.provider == "watsonx":
                # Existing LiteLLM adapter owns IBM IAM/project/model protocol.
                llm = LLM(provider="litellm", model="watsonx/" + role.model)
            else:
                raise ValueError(f"Unsupported judge provider: {role.provider}")
            yield {
                "correctness": ClassificationEvaluator(
                    name="correctness",
                    llm=llm,
                    prompt_template=(
                        "Assess answer against requested task and actual tool "
                        "evidence. "
                        "Reference describes retained source and may have changed; "
                        "Current observed source controls factual assessment. "
                        "Allow equivalent "
                        "formatting, units, and useful context. Explicit literal-field "
                        "requests require original characters and correct roles. "
                        "Receipt metadata alone does not prove PDF printed "
                        "edition/content. Return unassessed when available evidence "
                        "cannot resolve fit.\n"
                        "Generation failure or empty final answer cannot count as "
                        "correct merely because tool results contain useful facts. "
                        "Question: {query}\nAnswer: {answer}\n"
                        "Retained reference: {reference}\n"
                        "Actual tool evidence: {evidence}"
                    ),
                    choices=["correct", "incorrect", "unassessed"],
                    temperature=0,
                ),
                "scope": ClassificationEvaluator(
                    name="scope",
                    llm=llm,
                    prompt_template=(
                        "Domain is anonymous public IRS IRM, product catalog, and PDF "
                        "retrieval. Assess whether answer addresses requested question "
                        "within actual available evidence, or explains exact "
                        "unavailable information appropriately.\n"
                        "Assess supplied answer; do not generate replacement answer "
                        "or treat retained binary outside this context as excerpt.\n"
                        "Question: {query}\nAnswer: {answer}\n"
                        "Actual tool evidence: {evidence}"
                    ),
                    choices=["within_scope", "out_of_scope", "unassessed"],
                    temperature=0,
                ),
            }


async def judge_output(
    judges: dict, example: dict, output: dict, on_event=None
) -> dict:
    values = {
        "query": example["input"]["query"],
        "answer": output.get("answer", ""),
        "reference": json.dumps(example["expected"], ensure_ascii=False),
        "evidence": judge_evidence(output),
    }
    result = {}
    for name, evaluator in judges.items():
        if on_event:
            on_event({"kind": "judge_started", "judge": name})
        try:
            scores = await evaluator.async_evaluate(values)
            result[name] = [asdict(score) for score in scores]
        except Exception as exc:
            result[name] = {"error_type": type(exc).__name__, "status": "unassessed"}
        if on_event:
            on_event(
                {
                    "kind": "judge_completed",
                    "judge": name,
                    "error_type": (
                        result[name].get("error_type")
                        if isinstance(result[name], dict)
                        else None
                    ),
                }
            )
    return result
