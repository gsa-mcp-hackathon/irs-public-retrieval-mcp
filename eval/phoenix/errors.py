"""Useful source locations without exception payloads or frame locals."""

from __future__ import annotations

import traceback


def failure_details(error: Exception) -> dict:
    details = {
        "error_type": type(error).__name__,
        "source_frames": [
            {"file": frame.filename, "line": frame.lineno, "function": frame.name}
            for frame in traceback.extract_tb(error.__traceback__)
        ],
    }
    status = getattr(error, "status_code", None)
    if isinstance(status, int) and 100 <= status <= 599:
        details["http_status"] = status
    return details
