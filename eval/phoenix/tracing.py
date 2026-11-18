"""Optional local Phoenix lifetime and PydanticAI OpenTelemetry instrumentation."""

from __future__ import annotations

import os
import socket
import subprocess
import sys
import tempfile
import time
from contextlib import contextmanager
from pathlib import Path

from .models import anonymous_server_environment, display_endpoint


@contextmanager
def local_service(work_dir: Path, startup_timeout: float | None = None):
    """Use installed Phoenix CLI without launch_app's fixed five-second ceiling."""
    import httpx

    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    environment = anonymous_server_environment(dict(os.environ))
    environment.update(
        PHOENIX_WORKING_DIR=str(work_dir.resolve()),
        PHOENIX_HOST="127.0.0.1",
        PHOENIX_PORT=str(port),
        PHOENIX_GRPC_PORT="0",
        PHOENIX_TELEMETRY_ENABLED="false",
    )
    with (work_dir / "service.log").open("a", encoding="utf-8") as log:
        process = subprocess.Popen(
            [
                sys.executable,
                "-X",
                "utf8",
                "-m",
                "phoenix.server.main",
                "serve",
                "--no-internet",
            ],
            env=environment,
            stdout=log,
            stderr=subprocess.STDOUT,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        try:
            started = time.monotonic()
            base_url = f"http://127.0.0.1:{port}"
            with httpx.Client(trust_env=False, timeout=1) as client:
                while True:
                    if process.poll() is not None:
                        raise RuntimeError(
                            f"Phoenix exited during startup; inspect {log.name}"
                        )
                    try:
                        ready = client.get(base_url + "/readyz").status_code == 200
                    except httpx.HTTPError:
                        ready = False
                    if ready:
                        break
                    if (
                        startup_timeout is not None
                        and time.monotonic() - started >= startup_timeout
                    ):
                        raise TimeoutError(
                            "Caller-selected Phoenix startup time expired"
                        )
                    time.sleep(0.2)
            yield {"endpoint": base_url + "/v1/traces", "process_id": process.pid}
        finally:
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()


@contextmanager
def tracing(
    work_dir: Path,
    project: str,
    endpoint: str | None,
    local: bool,
    startup_timeout: float | None = None,
):
    """Keep runtime files in selected work directory and close owned services."""
    work_dir.mkdir(parents=True, exist_ok=True)
    old_work_dir = os.environ.get("PHOENIX_WORKING_DIR")
    os.environ["PHOENIX_WORKING_DIR"] = str(work_dir.resolve())
    old_temp = tempfile.tempdir
    tempfile.tempdir = str(work_dir.resolve())
    service = None
    local_receipt = None
    provider = None
    previous = None
    try:
        if local:
            service = local_service(work_dir, startup_timeout)
            local_receipt = service.__enter__()
            endpoint = local_receipt["endpoint"]
        if endpoint:
            from pydantic_ai import Agent
            from pydantic_ai.models.instrumented import InstrumentationSettings

            from phoenix.otel import register

            provider = register(
                endpoint=endpoint,
                project_name=project,
                protocol="http/protobuf",
                batch=True,
                set_global_tracer_provider=False,
                verbose=False,
            )
            previous = Agent._instrument_default
            Agent.instrument_all(
                InstrumentationSettings(
                    tracer_provider=provider, include_binary_content=False
                )
            )
        yield {
            "endpoint": display_endpoint(endpoint),
            "local_service": local_receipt,
            "project": project,
        }
    finally:
        try:
            if provider is not None:
                from pydantic_ai import Agent

                Agent.instrument_all(previous)
                try:
                    provider.force_flush()
                finally:
                    provider.shutdown()
        finally:
            try:
                if service is not None:
                    service.__exit__(None, None, None)
            finally:
                tempfile.tempdir = old_temp
                if old_work_dir is None:
                    os.environ.pop("PHOENIX_WORKING_DIR", None)
                else:
                    os.environ["PHOENIX_WORKING_DIR"] = old_work_dir
