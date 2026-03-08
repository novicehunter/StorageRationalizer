#!/usr/bin/env python3
"""
StorageRationalizer — API Response Validators
Reusable validators for OneDrive (Microsoft Graph) and Google Drive API responses.

Fixes CRITICAL Issue 2: No API Response Validation
- Validates response bodies, not just HTTP status codes
- Checks for error fields in JSON responses
- Verifies file IDs match requested IDs
- Validates per-request results in batch operations
- Prevents silent file deletion/restore failures

Usage:
    from tools.api_validators import APIResponseError, validate_restore_response
    from tools.api_validators import validate_metadata_response, validate_batch_response
"""

import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class APIResponseError(Exception):
    """Raised when API response validation fails."""

    def __init__(self, message: str, response_body: Any = None, status_code: Optional[int] = None):
        self.message = message
        self.response_body = response_body
        self.status_code = status_code
        super().__init__(message)


def validate_json_response(resp, context: str = "") -> Dict[str, Any]:
    """
    Validate and parse a JSON API response.

    Checks:
    - HTTP status code is in expected list (default: [200])
    - Response body is valid JSON
    - Response does not contain an 'error' field

    Args:
        resp: requests.Response object
        context: Optional string for more descriptive error messages

    Returns:
        Dict: Parsed JSON response body

    Raises:
        APIResponseError: If status code is unexpected, JSON is invalid,
                          or response contains an error field
    """
    ctx = f" [{context}]" if context else ""

    # Step 1: Check HTTP status code (caller may override via wrapper)
    expected_codes = [200]
    if resp.status_code not in expected_codes:
        try:
            body = resp.json()
        except Exception:
            body = resp.text[:300] if hasattr(resp, "text") else str(resp)
        raise APIResponseError(
            f"HTTP {resp.status_code}: {resp.text[:300] if hasattr(resp, 'text') else ''}{ctx}",
            response_body=body,
            status_code=resp.status_code,
        )

    # Step 2: Parse JSON
    try:
        data = resp.json()
    except Exception as e:
        raise APIResponseError(
            f"Invalid JSON response{ctx}: {str(e)}",
            response_body=resp.text[:300] if hasattr(resp, "text") else "",
            status_code=resp.status_code,
        )

    # Step 3: Check for error field (API can return HTTP 200 but with error body)
    if isinstance(data, dict) and "error" in data:
        error_obj = data["error"]
        if isinstance(error_obj, dict):
            error_msg = error_obj.get("message", "Unknown error")
            error_code = error_obj.get("code", "unknown")
        else:
            error_msg = str(error_obj)
            error_code = "unknown"
        raise APIResponseError(
            f"API error [{error_code}]: {error_msg}{ctx}",
            response_body=data,
            status_code=resp.status_code,
        )

    return data


def _validate_json_with_codes(
    resp, expected_status_codes: List[int], context: str = ""
) -> Dict[str, Any]:
    """
    Internal helper: validate JSON response with a custom list of expected status codes.

    Args:
        resp: requests.Response object
        expected_status_codes: List of acceptable HTTP status codes
        context: Optional context string for error messages

    Returns:
        Dict: Parsed JSON response body

    Raises:
        APIResponseError: If validation fails
    """
    ctx = f" [{context}]" if context else ""

    # Step 1: Check HTTP status code
    if resp.status_code not in expected_status_codes:
        try:
            body = resp.json()
        except Exception:
            body = resp.text[:300] if hasattr(resp, "text") else ""
        raise APIResponseError(
            f"HTTP {resp.status_code}: {resp.text[:300] if hasattr(resp, 'text') else ''}{ctx}",
            response_body=body,
            status_code=resp.status_code,
        )

    # Step 2: Parse JSON
    try:
        data = resp.json()
    except Exception as e:
        raise APIResponseError(
            f"Invalid JSON response{ctx}: {str(e)}",
            response_body=resp.text[:300] if hasattr(resp, "text") else "",
            status_code=resp.status_code,
        )

    # Step 3: Check for error field
    if isinstance(data, dict) and "error" in data:
        error_obj = data["error"]
        if isinstance(error_obj, dict):
            error_msg = error_obj.get("message", "Unknown error")
            error_code = error_obj.get("code", "unknown")
        else:
            error_msg = str(error_obj)
            error_code = "unknown"
        raise APIResponseError(
            f"API error [{error_code}]: {error_msg}{ctx}",
            response_body=data,
            status_code=resp.status_code,
        )

    return data


def validate_restore_response(resp, expected_file_id: str, context: str = "") -> Dict[str, Any]:
    """
    Validate an OneDrive restore endpoint response.

    Endpoint: POST /me/drive/items/{id}/restore

    Checks:
    - HTTP status is 200, 201, or 202
    - Response is valid JSON with no error field
    - Response contains an 'id' field
    - Response 'id' matches the requested file ID

    Args:
        resp: requests.Response object
        expected_file_id: Cloud file ID that was requested for restore
        context: Optional context string for error messages

    Returns:
        Dict: Validated response body

    Raises:
        APIResponseError: If any validation check fails
    """
    ctx = context or f"restore:{expected_file_id}"

    # Step 1: Validate JSON and check HTTP status + error fields
    data = _validate_json_with_codes(resp, expected_status_codes=[200, 201, 202], context=ctx)

    # Step 2: Verify required 'id' field is present
    if "id" not in data:
        raise APIResponseError(
            f"Restore response missing 'id' field [{ctx}]",
            response_body=data,
            status_code=resp.status_code,
        )

    # Step 3: Verify returned file ID matches requested file ID
    if data["id"] != expected_file_id:
        raise APIResponseError(
            f"File ID mismatch: requested {expected_file_id}, got {data['id']} [{ctx}]",
            response_body=data,
            status_code=resp.status_code,
        )

    logger.info(
        "Restore validated: file %s restored successfully (%s)",
        expected_file_id,
        data.get("name", ""),
    )
    return data


def validate_metadata_response(resp, expected_file_id: str, context: str = "") -> Dict[str, Any]:
    """
    Validate an OneDrive file metadata endpoint response.

    Endpoint: GET /me/drive/items/{id}

    Checks:
    - HTTP status is 200
    - Response is valid JSON with no error field
    - Response contains an 'id' field
    - Response 'id' matches the requested file ID
    - File is not marked as deleted (if 'deleted' field is present)

    Args:
        resp: requests.Response object
        expected_file_id: File ID that was requested
        context: Optional context string for error messages

    Returns:
        Dict: Validated response body

    Raises:
        APIResponseError: If any validation check fails
    """
    ctx = context or f"metadata:{expected_file_id}"

    # Step 1: Validate JSON and check HTTP status + error fields
    data = _validate_json_with_codes(resp, expected_status_codes=[200], context=ctx)

    # Step 2: Verify required 'id' field is present
    if "id" not in data:
        raise APIResponseError(
            f"Metadata response missing 'id' field [{ctx}]",
            response_body=data,
            status_code=resp.status_code,
        )

    # Step 3: Verify returned file ID matches requested file ID
    if data["id"] != expected_file_id:
        raise APIResponseError(
            f"File ID mismatch: requested {expected_file_id}, got {data['id']} [{ctx}]",
            response_body=data,
            status_code=resp.status_code,
        )

    # Step 4: Check if file is marked as deleted (if field is present)
    if "deleted" in data and data["deleted"] is True:
        raise APIResponseError(
            f"File {expected_file_id} is marked as deleted [{ctx}]",
            response_body=data,
            status_code=resp.status_code,
        )

    logger.info("Metadata validated: file %s", expected_file_id)
    return data


def validate_batch_response(resp, expected_request_count: int, context: str = "") -> Dict[str, Any]:
    """
    Validate an OneDrive batch endpoint response.

    Endpoint: POST /$batch

    Checks:
    - HTTP status for the batch container is 200
    - Response is valid JSON with no top-level error field
    - Response contains a 'responses' array
    - Count of responses matches expected_request_count
    - Per-request: logs failures (status >= 400 or body.error present)
      but does NOT raise — callers process individual results

    Args:
        resp: requests.Response object
        expected_request_count: Number of requests that were sent in the batch
        context: Optional context string for error messages

    Returns:
        Dict: Validated batch response (with 'responses' array intact)

    Raises:
        APIResponseError: If batch container validation fails (not per-request failures)
    """
    ctx = context or "batch"

    # Step 1: Validate JSON and check HTTP status + top-level error field
    data = _validate_json_with_codes(resp, expected_status_codes=[200], context=ctx)

    # Step 2: Verify 'responses' array is present
    if "responses" not in data:
        raise APIResponseError(
            f"Batch response missing 'responses' array [{ctx}]",
            response_body=data,
            status_code=resp.status_code,
        )

    responses = data["responses"]
    if not isinstance(responses, list):
        raise APIResponseError(
            f"Batch 'responses' is not an array [{ctx}]",
            response_body=data,
            status_code=resp.status_code,
        )

    # Step 3: Verify response count matches expected
    if len(responses) != expected_request_count:
        raise APIResponseError(
            f"Batch response count mismatch: expected {expected_request_count}, "
            f"got {len(responses)} [{ctx}]",
            response_body=data,
            status_code=resp.status_code,
        )

    # Step 4: Check per-request results — log failures but don't raise
    # Callers are responsible for handling individual request results
    failed_count = 0
    for idx, resp_item in enumerate(responses):
        item_status = resp_item.get("status", 0)
        item_body = resp_item.get("body", {})
        item_id = resp_item.get("id", str(idx))

        if item_status >= 400:
            error_info = item_body.get("error", {}) if isinstance(item_body, dict) else {}
            error_msg = (
                error_info.get("message", "Unknown error")
                if isinstance(error_info, dict)
                else str(error_info)
            )
            logger.warning(
                "Batch request id=%s failed: HTTP %s - %s [%s]",
                item_id,
                item_status,
                error_msg,
                ctx,
            )
            failed_count += 1
        elif isinstance(item_body, dict) and "error" in item_body:
            logger.warning(
                "Batch request id=%s has error in body despite HTTP %s [%s]",
                item_id,
                item_status,
                ctx,
            )
            failed_count += 1

    if failed_count > 0:
        logger.warning(
            "Batch complete: %d/%d requests failed [%s]",
            failed_count,
            expected_request_count,
            ctx,
        )
    else:
        logger.info(
            "Batch validated: all %d requests succeeded [%s]",
            expected_request_count,
            ctx,
        )

    return data
