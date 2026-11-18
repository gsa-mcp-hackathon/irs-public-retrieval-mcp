"""Run caller-selected public cases through actual MCP tools and model judges."""

from __future__ import annotations

import argparse
import asyncio
import json
import platform
import sys
from contextlib import AsyncExitStack
from datetime import datetime, timezone
from importlib.metadata import version
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from eval.phoenix.data import load_examples, resolve_dataset
from eval.phoenix.errors import failure_details
from eval.phoenix.models import ModelRole


def server_argv(value: str) -> list[str]:
    """Retain child flags as argv rather than parsing them as evaluator flags."""
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError as exc:
        raise argparse.ArgumentTypeError("JSON argv array required") from exc
    if (
        not isinstance(parsed, list)
        or not parsed
        or any(not isinstance(item, str) or not item for item in parsed)
    ):
        raise argparse.ArgumentTypeError("Nonempty JSON string argv array required")
    return parsed


def emit_record(sink, value: dict):
    sink.write(json.dumps(value, ensure_ascii=False) + "\n")
    sink.flush()


async def run(args, sink, trace_configuration, state):
    def emit(value):
        emit_record(sink, value)

    def phase(name, **context):
        state.clear()
        state.update(phase=name, **context)
        emit(
            {
                "kind": "phase_started",
                **state,
                "at_utc": datetime.now(timezone.utc).isoformat(),
            }
        )

    phase("model_setup")
    from openai import AsyncOpenAI

    from eval.phoenix.agent import IrsPublicRetrievalAgent, smoke_test
    from eval.phoenix.checks import independent_checks
    from eval.phoenix.judges import create_judges, judge_output

    phase("configuration")
    role = ModelRole.from_environment("agent", args.agent_model)
    judge_role = (
        None
        if args.no_judge or args.smoke_only
        else ModelRole.from_environment("judge", args.judge_model)
    )
    request_path = args.dataset or resolve_dataset(args.registry, args.dataset_name)
    examples = load_examples(request_path)
    if not examples:
        raise ValueError("Dataset requires nonempty cases")
    if args.case_id:
        wanted = set(args.case_id)
        examples = [row for row in examples if row["id"] in wanted]
        if wanted - {row["id"] for row in examples}:
            raise ValueError("Requested dataset case IDs were not found")

    emit(
        {
            "kind": "configuration",
            "started_at_utc": datetime.now(timezone.utc).isoformat(),
            "agent": role.describe(),
            "judge": judge_role.describe() if judge_role else None,
            "same_configured_model_roles": (
                judge_role is not None
                and (role.provider, role.model, role.base_url)
                == (judge_role.provider, judge_role.model, judge_role.base_url)
            ),
            "trace": trace_configuration,
            "model_settings": {"temperature": 0},
            "runtime": {
                "python": platform.python_version(),
                "packages": {
                    name: version(name)
                    for name in (
                        "pydantic-ai-slim",
                        "fastmcp-slim",
                        "mcp",
                        "openai",
                        "arize-phoenix-evals",
                        "arize-phoenix-otel",
                    )
                },
            },
            "dataset": str(request_path),
        }
    )
    async with AsyncExitStack() as stack:
        phase("model_client_setup")
        client = await stack.enter_async_context(
            AsyncOpenAI(base_url=role.base_url, api_key=role.api_key, max_retries=0)
        )
        model = role.agent_model(client)
        phase("function_smoke")
        probe = await smoke_test(model)
        emit({"kind": "function_smoke", "result": probe})
        if not probe["function_calls"]:
            return 1
        if args.smoke_only:
            return 0
        judges = None
        if judge_role:
            phase("judge_setup")
            try:
                judges = await stack.enter_async_context(create_judges(judge_role))
            except Exception as exc:
                emit({"kind": "judges_unavailable", **failure_details(exc)})
        prompt = args.system_prompt.read_text(encoding="utf-8")
        phase("mcp_connection")
        async with IrsPublicRetrievalAgent(model, prompt, args.server_command) as agent:
            emit({"kind": "mcp_connection", "result": agent.connection})
            for example in examples:
                phase("agent_case", case_id=example["id"])
                output = await agent.run(example["input"]["query"])
                emit(
                    {
                        "kind": "agent_return",
                        "id": example["id"],
                        "answer": output.get("answer", ""),
                        "usage": output.get("usage"),
                        "error_type": output.get("error_type"),
                        "at_utc": datetime.now(timezone.utc).isoformat(),
                    }
                )
                phase("independent_checks", case_id=example["id"])
                observations = independent_checks(example, output)

                def judge_event(event):
                    if event["kind"] == "judge_started":
                        phase("judging", case_id=example["id"], judge=event["judge"])
                    else:
                        emit(
                            {
                                "kind": "phase_completed",
                                "phase": "judging",
                                "case_id": example["id"],
                                "judge": event["judge"],
                                "error_type": event.get("error_type"),
                                "at_utc": datetime.now(timezone.utc).isoformat(),
                            }
                        )

                verdicts = (
                    await judge_output(judges, example, output, judge_event)
                    if judges
                    else None
                )
                phase("case_recording", case_id=example["id"])
                emit(
                    {
                        "kind": "case",
                        "id": example["id"],
                        "input": example["input"],
                        "output": output,
                        "reference": example["expected"],
                        "reference_metadata": example["metadata"],
                        "independent_checks": observations,
                        "model_judgments": verdicts,
                    }
                )
                print(
                    json.dumps(
                        {
                            "case": example["id"],
                            "tool_call_attempts": observations["tool_call_attempts"],
                            "tool_results_returned": observations[
                                "tool_results_returned"
                            ],
                            "error_type": output.get("error_type"),
                        }
                    ),
                    flush=True,
                )
    emit(
        {
            "kind": "completed",
            "completed_at_utc": datetime.now(timezone.utc).isoformat(),
        }
    )
    return 0


def main():
    here = Path(__file__).resolve().parent
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path)
    parser.add_argument("--registry", type=Path, default=here / "datasets.yaml")
    parser.add_argument("--dataset-name", default="irs-public-retrieval")
    parser.add_argument("--case-id", action="append")
    parser.add_argument(
        "--system-prompt", type=Path, default=here / "prompts/system_prompt_v1.txt"
    )
    parser.add_argument("--agent-model")
    parser.add_argument("--judge-model")
    parser.add_argument("--no-judge", action="store_true")
    parser.add_argument("--smoke-only", action="store_true")
    parser.add_argument("--server-command", type=server_argv, metavar="JSON_ARGV")
    parser.add_argument("--phoenix-endpoint")
    parser.add_argument("--local-phoenix", action="store_true")
    parser.add_argument("--phoenix-startup-timeout", type=float)
    parser.add_argument("--project-name", default="irs-public-retrieval")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.phoenix_startup_timeout is not None and args.phoenix_startup_timeout <= 0:
        parser.error("Phoenix startup timeout must be positive when selected")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    from eval.phoenix.tracing import tracing

    with args.output.open("x", encoding="utf-8") as sink:
        state = {"phase": "tracing_setup"}
        emit_record(
            sink,
            {
                "kind": "phase_started",
                **state,
                "at_utc": datetime.now(timezone.utc).isoformat(),
            },
        )
        try:
            with tracing(
                args.output.parent / "phoenix",
                args.project_name,
                args.phoenix_endpoint,
                args.local_phoenix,
                args.phoenix_startup_timeout,
            ) as configuration:
                result = asyncio.run(run(args, sink, configuration, state))
                state.clear()
                state["phase"] = "owned_cleanup"
                emit_record(
                    sink,
                    {
                        "kind": "phase_started",
                        **state,
                        "at_utc": datetime.now(timezone.utc).isoformat(),
                    },
                )
        except Exception as exc:
            emit_record(
                sink, {"kind": "execution_failed", **state, **failure_details(exc)}
            )
            print(json.dumps({"error_type": type(exc).__name__}), flush=True)
            return 1
        emit_record(
            sink,
            {
                "kind": "owned_cleanup_completed",
                "at_utc": datetime.now(timezone.utc).isoformat(),
            },
        )
        return result


if __name__ == "__main__":
    raise SystemExit(main())
