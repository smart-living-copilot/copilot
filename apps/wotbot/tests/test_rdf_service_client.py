import pytest

from wotbot.clients.rdf_service import RdfServiceError, _decode_response_payload


def test_decode_response_payload_returns_json_object() -> None:
    assert _decode_response_payload(200, '{"status": "ok"}') == {"status": "ok"}


def test_decode_response_payload_uses_json_error_detail() -> None:
    with pytest.raises(RdfServiceError, match="Unknown prefix: wd"):
        _decode_response_payload(400, '{"detail": "Unknown prefix: wd"}')


def test_decode_response_payload_preserves_structured_error_detail() -> None:
    with pytest.raises(RdfServiceError) as exc_info:
        _decode_response_payload(
            504,
            '{"detail": {"category": "timeout", "message": "timed out", "retryable": true}}',
        )

    assert str(exc_info.value) == "timed out"
    assert exc_info.value.status == 504
    assert exc_info.value.category == "timeout"
    assert exc_info.value.retryable is True


def test_decode_response_payload_preserves_non_json_error_body() -> None:
    with pytest.raises(RdfServiceError, match="Internal Server Error"):
        _decode_response_payload(500, "Internal Server Error")


def test_decode_response_payload_rejects_non_object_success() -> None:
    with pytest.raises(ValueError, match="non-object"):
        _decode_response_payload(200, "[]")
