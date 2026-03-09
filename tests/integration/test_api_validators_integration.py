"""
Integration tests for api_validators.py.

Tests the full validate_restore_response / validate_metadata_response /
validate_batch_response flow using mock requests.Response objects.
Covers happy paths, missing fields, ID mismatches, HTTP errors, and
partial-failure batch scenarios.
"""

import pytest
from unittest.mock import MagicMock

from tools.api_validators import (
    APIResponseError,
    validate_batch_response,
    validate_json_response,
    validate_metadata_response,
    validate_restore_response,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def make_response(status_code: int, json_body):
    """Build a mock requests.Response with the given status and JSON body."""
    mock = MagicMock()
    mock.status_code = status_code
    mock.json.return_value = json_body
    mock.text = str(json_body)
    return mock


# ---------------------------------------------------------------------------
# validate_restore_response
# ---------------------------------------------------------------------------


class TestValidateRestoreResponse:
    def test_valid_200_response(self):
        resp = make_response(200, {"id": "file_abc", "name": "doc.pdf"})
        data = validate_restore_response(resp, expected_file_id="file_abc")
        assert data["id"] == "file_abc"

    def test_valid_201_response(self):
        resp = make_response(201, {"id": "file_abc"})
        data = validate_restore_response(resp, expected_file_id="file_abc")
        assert data["id"] == "file_abc"

    def test_valid_202_response(self):
        resp = make_response(202, {"id": "file_abc"})
        data = validate_restore_response(resp, expected_file_id="file_abc")
        assert data["id"] == "file_abc"

    def test_http_400_raises(self):
        resp = make_response(400, {"error": {"code": "invalidRequest", "message": "Bad request"}})
        with pytest.raises(APIResponseError) as exc_info:
            validate_restore_response(resp, expected_file_id="file_abc")
        assert exc_info.value.status_code == 400

    def test_http_404_raises(self):
        resp = make_response(404, {"error": {"code": "itemNotFound", "message": "Not found"}})
        with pytest.raises(APIResponseError) as exc_info:
            validate_restore_response(resp, expected_file_id="file_abc")
        assert exc_info.value.status_code == 404

    def test_http_500_raises(self):
        resp = make_response(500, {})
        with pytest.raises(APIResponseError) as exc_info:
            validate_restore_response(resp, expected_file_id="file_abc")
        assert exc_info.value.status_code == 500

    def test_missing_id_field_raises(self):
        resp = make_response(200, {"name": "doc.pdf"})  # no 'id'
        with pytest.raises(APIResponseError, match="missing 'id'"):
            validate_restore_response(resp, expected_file_id="file_abc")

    def test_id_mismatch_raises(self):
        resp = make_response(200, {"id": "different_id"})
        with pytest.raises(APIResponseError, match="mismatch"):
            validate_restore_response(resp, expected_file_id="file_abc")

    def test_error_field_in_200_response_raises(self):
        """API can return HTTP 200 but include an error field — must be rejected."""
        resp = make_response(200, {"error": {"code": "generalException", "message": "Oops"}})
        with pytest.raises(APIResponseError, match="generalException"):
            validate_restore_response(resp, expected_file_id="file_abc")

    def test_context_string_included_in_error(self):
        resp = make_response(404, {})
        with pytest.raises(APIResponseError):
            validate_restore_response(resp, expected_file_id="f1", context="my-context")


# ---------------------------------------------------------------------------
# validate_metadata_response
# ---------------------------------------------------------------------------


class TestValidateMetadataResponse:
    def test_valid_metadata(self):
        resp = make_response(200, {"id": "file_xyz", "name": "photo.jpg", "size": 2048})
        data = validate_metadata_response(resp, expected_file_id="file_xyz")
        assert data["id"] == "file_xyz"

    def test_http_404_raises(self):
        resp = make_response(404, {})
        with pytest.raises(APIResponseError):
            validate_metadata_response(resp, expected_file_id="file_xyz")

    def test_missing_id_field_raises(self):
        resp = make_response(200, {"name": "photo.jpg"})
        with pytest.raises(APIResponseError, match="missing 'id'"):
            validate_metadata_response(resp, expected_file_id="file_xyz")

    def test_id_mismatch_raises(self):
        resp = make_response(200, {"id": "wrong_id"})
        with pytest.raises(APIResponseError, match="mismatch"):
            validate_metadata_response(resp, expected_file_id="file_xyz")

    def test_deleted_file_raises(self):
        resp = make_response(200, {"id": "file_xyz", "deleted": True})
        with pytest.raises(APIResponseError, match="deleted"):
            validate_metadata_response(resp, expected_file_id="file_xyz")

    def test_deleted_false_is_valid(self):
        resp = make_response(200, {"id": "file_xyz", "deleted": False})
        data = validate_metadata_response(resp, expected_file_id="file_xyz")
        assert data["id"] == "file_xyz"

    def test_metadata_without_deleted_field_is_valid(self):
        resp = make_response(200, {"id": "file_xyz", "name": "doc.pdf"})
        data = validate_metadata_response(resp, expected_file_id="file_xyz")
        assert data["id"] == "file_xyz"

    def test_201_status_raises(self):
        """Metadata endpoint only accepts 200."""
        resp = make_response(201, {"id": "file_xyz"})
        with pytest.raises(APIResponseError):
            validate_metadata_response(resp, expected_file_id="file_xyz")


# ---------------------------------------------------------------------------
# validate_batch_response
# ---------------------------------------------------------------------------


class TestValidateBatchResponse:
    def test_all_successful_responses(self):
        responses = [{"id": str(i), "status": 200, "body": {}} for i in range(3)]
        resp = make_response(200, {"responses": responses})
        data = validate_batch_response(resp, expected_request_count=3)
        assert len(data["responses"]) == 3

    def test_partial_failures_return_data(self):
        """Partial failures should NOT raise — caller handles per-item results."""
        responses = [
            {"id": "0", "status": 200, "body": {}},
            {"id": "1", "status": 404, "body": {"error": {"message": "not found"}}},
            {"id": "2", "status": 200, "body": {}},
        ]
        resp = make_response(200, {"responses": responses})
        data = validate_batch_response(resp, expected_request_count=3)
        assert len(data["responses"]) == 3

    def test_all_failed_responses_return_data(self):
        """All per-item failures should NOT raise — caller handles results."""
        responses = [{"id": str(i), "status": 500, "body": {}} for i in range(3)]
        resp = make_response(200, {"responses": responses})
        data = validate_batch_response(resp, expected_request_count=3)
        assert len(data["responses"]) == 3

    def test_missing_responses_array_raises(self):
        resp = make_response(200, {"other_field": "value"})
        with pytest.raises(APIResponseError, match="missing 'responses'"):
            validate_batch_response(resp, expected_request_count=1)

    def test_responses_not_list_raises(self):
        resp = make_response(200, {"responses": "not-a-list"})
        with pytest.raises(APIResponseError, match="not an array"):
            validate_batch_response(resp, expected_request_count=1)

    def test_count_mismatch_raises(self):
        responses = [{"id": "0", "status": 200, "body": {}}]
        resp = make_response(200, {"responses": responses})
        with pytest.raises(APIResponseError, match="count mismatch"):
            validate_batch_response(resp, expected_request_count=3)

    def test_http_500_on_batch_container_raises(self):
        resp = make_response(500, {})
        with pytest.raises(APIResponseError):
            validate_batch_response(resp, expected_request_count=1)

    def test_top_level_error_field_raises(self):
        resp = make_response(200, {"error": {"code": "serviceError", "message": "down"}})
        with pytest.raises(APIResponseError, match="serviceError"):
            validate_batch_response(resp, expected_request_count=1)

    def test_empty_batch(self):
        resp = make_response(200, {"responses": []})
        data = validate_batch_response(resp, expected_request_count=0)
        assert data["responses"] == []


# ---------------------------------------------------------------------------
# validate_json_response (generic)
# ---------------------------------------------------------------------------


class TestValidateJsonResponse:
    def test_valid_200_json(self):
        resp = make_response(200, {"key": "value"})
        data = validate_json_response(resp)
        assert data["key"] == "value"

    def test_non_200_raises(self):
        resp = make_response(403, {})
        with pytest.raises(APIResponseError) as exc_info:
            validate_json_response(resp)
        assert exc_info.value.status_code == 403

    def test_error_field_in_body_raises(self):
        resp = make_response(200, {"error": {"code": "accessDenied", "message": "No access"}})
        with pytest.raises(APIResponseError, match="accessDenied"):
            validate_json_response(resp)

    def test_error_field_string_value(self):
        resp = make_response(200, {"error": "something went wrong"})
        with pytest.raises(APIResponseError):
            validate_json_response(resp)

    def test_context_in_response(self):
        resp = make_response(200, {"result": "ok"})
        data = validate_json_response(resp, context="my-operation")
        assert data["result"] == "ok"
