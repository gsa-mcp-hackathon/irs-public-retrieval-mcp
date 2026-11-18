from eval.phoenix.errors import failure_details
from eval.phoenix.models import display_endpoint


def test_error_frames_exclude_exception_payload_and_locals():
    try:
        raise ValueError("credential-like-payload-must-not-appear")
    except ValueError as error:
        result = failure_details(error)
    assert result["error_type"] == "ValueError"
    assert result["source_frames"][-1]["function"] == (
        "test_error_frames_exclude_exception_payload_and_locals"
    )
    assert "credential-like-payload" not in str(result)


def test_trace_endpoint_display_omits_credential_components():
    assert display_endpoint(
        "https://u:secret@localhost:6006/v1/traces?k=secret#secret"
    ) == ("https://localhost:6006/v1/traces")


def test_supported_http_status_is_retained_without_response_body():
    class ModelFailure(Exception):
        status_code = 413
        body = "private-response-body"

    result = failure_details(ModelFailure("credential-like-message"))
    assert result["http_status"] == 413
    assert "private-response-body" not in str(result)
    assert "credential-like-message" not in str(result)
