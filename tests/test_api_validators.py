#!/usr/bin/env python3
"""
Tests for tools/api_validators.py

Covers CRITICAL Issue 2: API Response Validation
Tests that validators correctly detect:
- Valid responses
- Error fields in JSON (HTTP 200 but error body)
- File ID mismatches
- Batch per-request failures
- Invalid JSON
- Deleted file metadata
"""

import pytest
from unittest.mock import Mock

from tools.api_validators import (
    APIResponseError,
    validate_json_response,
    validate_restore_response,
    validate_metadata_response,
    validate_batch_response,
)

# ── Test 1: Valid restore response ────────────────────────────────────────────


def test_valid_restore_response():
    """HTTP 200 with correct file ID and name — should succeed and return data."""
    mock_response = Mock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "id": "file-123",
        "name": "document.docx",
        "parentReference": {"id": "folder-456"},
        "webUrl": "https://onedrive.live.com/file-123",
    }

    result = validate_restore_response(mock_response, expected_file_id="file-123")

    assert result["id"] == "file-123"
    assert result["name"] == "document.docx"


# ── Test 2: Restore response with error field (HTTP 200 but error body) ───────


def test_restore_response_with_error_field():
    """
    HTTP 200 but response body contains 'error' key.
    Current code would mark this as success — validator must catch it.
    """
    mock_response = Mock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "error": {
            "code": "invalidRequest",
            "message": "Invalid parent reference",
        }
    }

    with pytest.raises(APIResponseError) as exc_info:
        validate_restore_response(mock_response, expected_file_id="file-123")

    assert "invalidRequest" in str(exc_info.value)


# ── Test 3: Restore response with wrong file ID ───────────────────────────────


def test_restore_response_with_wrong_file_id():
    """
    HTTP 200 but response body contains a different file ID.
    Could indicate a confused API or race condition — must reject.
    """
    mock_response = Mock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "id": "file-789",  # Different from requested "file-123"
        "name": "other-document.docx",
    }

    with pytest.raises(APIResponseError) as exc_info:
        validate_restore_response(mock_response, expected_file_id="file-123")

    assert "File ID mismatch" in str(exc_info.value)


# ── Test 4: Batch response with mixed success/failure ────────────────────────


def test_batch_response_with_mixed_success_failure():
    """
    Batch container HTTP 200, but individual requests have mixed results.
    Validator should log failures but still return the data (caller handles per-item results).
    """
    mock_response = Mock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "responses": [
            {
                "id": "0",
                "status": 200,
                "body": {"id": "file-1", "name": "doc1.docx"},
            },
            {
                "id": "1",
                "status": 404,
                "body": {
                    "error": {
                        "code": "itemNotFound",
                        "message": "The resource was not found",
                    }
                },
            },
            {
                "id": "2",
                "status": 200,
                "body": {"id": "file-3", "name": "doc3.docx"},
            },
        ]
    }

    # Should NOT raise — per-request failures are logged, not raised
    result = validate_batch_response(mock_response, expected_request_count=3)

    assert "responses" in result
    assert len(result["responses"]) == 3
    assert result["responses"][0]["status"] == 200
    assert result["responses"][1]["status"] == 404  # Failed but processed by caller
    assert result["responses"][2]["status"] == 200


# ── Test 5: Invalid JSON response ────────────────────────────────────────────


def test_invalid_json_response():
    """
    HTTP 200 but response body is not valid JSON.
    validate_json_response should raise APIResponseError.
    """
    mock_response = Mock()
    mock_response.status_code = 200
    mock_response.json.side_effect = ValueError("No JSON object could be decoded")
    mock_response.text = "Internal Server Error"

    with pytest.raises(APIResponseError) as exc_info:
        validate_json_response(mock_response)

    assert "Invalid JSON" in str(exc_info.value)


# ── Test 6: Metadata response with deleted flag ───────────────────────────────


def test_metadata_response_with_deleted_flag():
    """
    HTTP 200 but metadata shows file is marked as deleted.
    Validator must detect and reject this case.
    """
    mock_response = Mock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "id": "file-123",
        "name": "deleted-doc.docx",
        "deleted": True,
    }

    with pytest.raises(APIResponseError) as exc_info:
        validate_metadata_response(mock_response, expected_file_id="file-123")

    assert "marked as deleted" in str(exc_info.value)


# ── Additional edge case tests ────────────────────────────────────────────────


def test_restore_response_http_error():
    """Non-200 HTTP status should raise APIResponseError."""
    mock_response = Mock()
    mock_response.status_code = 404
    mock_response.text = '{"error": {"code": "itemNotFound", "message": "Not found"}}'
    mock_response.json.return_value = {"error": {"code": "itemNotFound", "message": "Not found"}}

    with pytest.raises(APIResponseError) as exc_info:
        validate_restore_response(mock_response, expected_file_id="file-123")

    assert exc_info.value.status_code == 404


def test_batch_response_missing_responses_key():
    """Batch response without 'responses' key should raise APIResponseError."""
    mock_response = Mock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"value": []}  # Missing 'responses'

    with pytest.raises(APIResponseError) as exc_info:
        validate_batch_response(mock_response, expected_request_count=2)

    assert "missing 'responses' array" in str(exc_info.value)


def test_batch_response_count_mismatch():
    """Batch response with wrong number of responses should raise APIResponseError."""
    mock_response = Mock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "responses": [
            {"id": "0", "status": 200, "body": {}},
        ]
    }

    with pytest.raises(APIResponseError) as exc_info:
        validate_batch_response(mock_response, expected_request_count=3)

    assert "count mismatch" in str(exc_info.value)


def test_metadata_response_missing_id_field():
    """Metadata response without 'id' field should raise APIResponseError."""
    mock_response = Mock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "name": "document.docx",
        "size": 12345,
        # Missing 'id' field
    }

    with pytest.raises(APIResponseError) as exc_info:
        validate_metadata_response(mock_response, expected_file_id="file-123")

    assert "missing 'id' field" in str(exc_info.value)


def test_valid_metadata_response():
    """Valid metadata response — should succeed and return data."""
    mock_response = Mock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "id": "file-456",
        "name": "photo.jpg",
        "size": 2048000,
        "@microsoft.graph.downloadUrl": "https://example.com/download/photo.jpg",
    }

    result = validate_metadata_response(mock_response, expected_file_id="file-456")

    assert result["id"] == "file-456"
    assert result["name"] == "photo.jpg"


def test_api_response_error_attributes():
    """APIResponseError should store message, response_body, and status_code."""
    err = APIResponseError(
        message="Test error",
        response_body={"error": "bad"},
        status_code=500,
    )

    assert err.message == "Test error"
    assert err.response_body == {"error": "bad"}
    assert err.status_code == 500
    assert str(err) == "Test error"


def test_restore_response_202_accepted():
    """HTTP 202 Accepted is a valid restore status."""
    mock_response = Mock()
    mock_response.status_code = 202
    mock_response.json.return_value = {
        "id": "file-999",
        "name": "async-restore.docx",
    }

    result = validate_restore_response(mock_response, expected_file_id="file-999")
    assert result["id"] == "file-999"
