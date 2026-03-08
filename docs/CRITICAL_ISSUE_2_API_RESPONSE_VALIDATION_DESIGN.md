# CRITICAL ISSUE 2: API Response Validation
## Design Document for StorageRationalizer

**Issue:** No API response validation
**Severity:** CRITICAL
**Impact:** Data corruption, silent file deletion failures
**Status:** DESIGN (ready for implementation)
**Date:** March 8, 2026

---

## EXECUTIVE SUMMARY

### Current Risk
The application makes API calls to OneDrive (Microsoft Graph) and Google Drive to restore deleted files. Currently:
- Only HTTP status codes are checked (200, 201, 202, 204 are considered "success")
- Response bodies are NOT validated
- If API returns error JSON but HTTP 200, file is marked as "restored" despite being deleted
- Database is updated to mark file as restored even if restore actually failed
- Result: **Silent data loss** — user thinks file is restored, but it's still deleted

### Required Fixes
1. **OneDrive Graph API responses** — Parse and validate response bodies
2. **Google Drive API responses** — Parse and validate response bodies
3. **File ID verification** — Confirm response contains requested file ID
4. **Error detection** — Check for error messages in response JSON
5. **Transaction safety** — Only mark as restored AFTER validation succeeds

### Files Affected
- `tools/rollback.py` — OneDrive restore (lines 445-453)
- `phase2/verifier.py` — OneDrive file metadata reads (lines 186-244)
- `phase3/cleaner.py` — OneDrive batch operations (lines 269-270)
- `phase1/scanner.py` — OneDrive token acquisition (lines 740-751)

---

## VULNERABILITY ANALYSIS

### 1. OneDrive Graph API Restore (rollback.py, lines 445-453)

**Current Code:**
```python
resp = requests.post(
    f"https://graph.microsoft.com/v1.0/me/drive/items/{cid}/restore",
    headers={"Authorization": f"Bearer {token}"},
    json={"parentReference": {"id": parent_id}},
    timeout=30
)
if resp.status_code in (200, 201, 202, 204):
    return True, "Restored"
return False, f"HTTP {resp.status_code}: {resp.text[:300]}"
```

**Vulnerability:**
- ❌ HTTP 200 doesn't mean restore succeeded
- ❌ Response body not parsed for errors
- ❌ No check for `error` field in JSON response
- ❌ File ID not verified in response
- ❌ Doesn't distinguish between "invalid token" and "file not found"

**Attack Vector:**
```json
// API returns HTTP 200 but with error
{
  "error": {
    "code": "invalidRequest",
    "message": "Invalid parent reference"
  }
}
```
→ Current code marks file as restored ❌

**Impact:** File is NOT restored, but DB says it is → **silent data loss**

---

### 2. OneDrive Metadata Read (verifier.py, lines 186-244)

**Current Code:**
```python
resp = requests.get(
    f"https://graph.microsoft.com/v1.0/me/drive/items/{file_id}",
    headers={"Authorization": f"Bearer {token}"},
    timeout=30
)
if resp.status_code == 200:
    meta = resp.json()
    # Use meta without validation
```

**Vulnerability:**
- ❌ No error field check before using response
- ❌ If API returns `{"error": {...}}`, code still tries to access fields
- ❌ Doesn't verify file_id in response matches requested ID
- ❌ No timeout handling on download reads (line 244)

**Attack Vector:**
```json
// Deleted file response
{
  "error": {
    "code": "itemNotFound",
    "message": "The resource was not found"
  }
}
```
→ Code crashes trying to access fields on error object ❌

---

### 3. OneDrive Batch Operations (cleaner.py, lines 269-270)

**Current Code:**
```python
resp = _requests.post(
    "https://graph.microsoft.com/v1.0/$batch",
    headers={"Authorization": f"Bearer {token}"},
    json=batch_payload,
    timeout=30
)
# Process batch without validating each request result
```

**Vulnerability:**
- ❌ Batch operations have per-request response codes
- ❌ Only checking HTTP 200 for batch container
- ❌ Individual requests in batch may fail while container returns 200
- ❌ No validation of batch response structure

**Attack Vector:**
```json
{
  "responses": [
    {
      "id": "1",
      "status": 404,
      "body": {
        "error": {
          "code": "itemNotFound",
          "message": "File not found"
        }
      }
    }
  ]
}
```
→ Batch HTTP 200, but individual request failed, still marked as processed ❌

---

## REQUIRED VALIDATION RULES

### Rule 1: OneDrive Single Restore Endpoint
**Endpoint:** `POST /me/drive/items/{id}/restore`

**Success Response:**
```json
{
  "id": "<file-id>",
  "name": "<filename>",
  "parentReference": {
    "id": "<parent-id>"
  },
  "webUrl": "..."
}
```

**Validation Checklist:**
- ✅ HTTP status is 200
- ✅ Response has `id` field
- ✅ Response `id` matches requested `{id}`
- ✅ No `error` field in response
- ✅ Response is valid JSON
- ✅ Response body is not empty

**Error Response (must reject):**
```json
{
  "error": {
    "code": "itemNotFound",
    "message": "The resource was not found"
  }
}
```

**Validation Rule:** If response contains `error` key, treat as failure regardless of HTTP status

---

### Rule 2: OneDrive Metadata Read Endpoint
**Endpoint:** `GET /me/drive/items/{id}`

**Success Response:**
```json
{
  "id": "<file-id>",
  "name": "<filename>",
  "size": 12345,
  "deleted": false
}
```

**Validation Checklist:**
- ✅ HTTP status is 200
- ✅ Response has `id` field
- ✅ Response `id` matches requested `{id}`
- ✅ No `error` field in response
- ✅ `deleted` field is false (if present)
- ✅ Response is valid JSON

**Error Cases (must handle):**
- `itemNotFound` (404) — File is deleted or inaccessible
- `invalidRange` (416) — Range header invalid for file size
- `accessDenied` (403) — Token lacks permissions
- `throttled` (429) — Rate limited, should retry with backoff
- `serviceUnavailable` (503) — Temporary outage, should retry

---

### Rule 3: OneDrive Batch Operations
**Endpoint:** `POST /$batch`

**Batch Response Structure:**
```json
{
  "responses": [
    {
      "id": "1",
      "status": 200,
      "body": {
        "id": "<file-id>",
        ...
      }
    },
    {
      "id": "2",
      "status": 404,
      "body": {
        "error": {
          "code": "itemNotFound"
        }
      }
    }
  ]
}
```

**Validation Checklist:**
- ✅ HTTP status for batch container is 200
- ✅ `responses` array exists
- ✅ For each response in batch:
  - ✅ Check `status` code (not HTTP status)
  - ✅ If `status >= 400`, treat as failed
  - ✅ If `body.error` exists, treat as failed
  - ✅ If `status == 200` and no error, process

**Batch Failure Rules:**
- Individual batch request failed → skip that request, log error, continue others
- Multiple failures → return partial failure status, log details
- All failures → return total failure

---

### Rule 4: Google Drive API (Future Implementation)
**Placeholder for Google Drive validation rules**

Currently not showing API calls in grepped output, but when implemented:
- Validate Google Drive API responses similarly
- Check for `error` field in response
- Verify file IDs in batch operations
- Handle rate limiting (429) with exponential backoff

---

## IMPLEMENTATION STRATEGY

### Phase 1: Create Response Validators (No Breaking Changes)

Create `tools/api_validators.py` with reusable validation functions:

```python
# tools/api_validators.py

from typing import Tuple, Dict, Any
import logging

logger = logging.getLogger(__name__)

class APIResponseError(Exception):
    """Raised when API response validation fails"""
    def __init__(self, message: str, response_body: Dict = None, status_code: int = None):
        self.message = message
        self.response_body = response_body
        self.status_code = status_code
        super().__init__(message)


def validate_json_response(resp, expected_status_codes: list = [200]) -> Dict[str, Any]:
    """
    Validate and parse JSON response.

    Args:
        resp: requests.Response object
        expected_status_codes: List of valid HTTP status codes

    Returns:
        Dict: Parsed JSON response

    Raises:
        APIResponseError: If validation fails
    """
    # Step 1: Check HTTP status code
    if resp.status_code not in expected_status_codes:
        try:
            body = resp.json()
        except:
            body = resp.text[:300]
        raise APIResponseError(
            f"HTTP {resp.status_code}: {resp.text[:300]}",
            response_body=body,
            status_code=resp.status_code
        )

    # Step 2: Parse JSON
    try:
        data = resp.json()
    except Exception as e:
        raise APIResponseError(
            f"Invalid JSON response: {str(e)}",
            response_body=resp.text[:300],
            status_code=resp.status_code
        )

    # Step 3: Check for error field
    if isinstance(data, dict) and "error" in data:
        error_obj = data["error"]
        error_msg = error_obj.get("message", "Unknown error")
        error_code = error_obj.get("code", "unknown")
        raise APIResponseError(
            f"API error [{error_code}]: {error_msg}",
            response_body=data,
            status_code=resp.status_code
        )

    return data


def validate_restore_response(resp, expected_file_id: str) -> Dict[str, Any]:
    """
    Validate OneDrive restore endpoint response.

    Args:
        resp: requests.Response object
        expected_file_id: Cloud ID that was requested for restore

    Returns:
        Dict: Validated response

    Raises:
        APIResponseError: If validation fails
    """
    # Step 1: Validate JSON and check for errors
    data = validate_json_response(resp, expected_status_codes=[200, 201, 202])

    # Step 2: Verify required fields
    if "id" not in data:
        raise APIResponseError(
            "Restore response missing 'id' field",
            response_body=data,
            status_code=resp.status_code
        )

    # Step 3: Verify file ID matches
    if data["id"] != expected_file_id:
        raise APIResponseError(
            f"File ID mismatch: requested {expected_file_id}, got {data['id']}",
            response_body=data,
            status_code=resp.status_code
        )

    logger.info(f"Restore validated: file {expected_file_id} restored successfully")
    return data


def validate_metadata_response(resp, expected_file_id: str) -> Dict[str, Any]:
    """
    Validate OneDrive metadata endpoint response.

    Args:
        resp: requests.Response object
        expected_file_id: File ID that was requested

    Returns:
        Dict: Validated response

    Raises:
        APIResponseError: If validation fails
    """
    # Step 1: Validate JSON and check for errors
    data = validate_json_response(resp, expected_status_codes=[200])

    # Step 2: Verify required fields
    if "id" not in data:
        raise APIResponseError(
            "Metadata response missing 'id' field",
            response_body=data,
            status_code=resp.status_code
        )

    # Step 3: Verify file ID matches
    if data["id"] != expected_file_id:
        raise APIResponseError(
            f"File ID mismatch: requested {expected_file_id}, got {data['id']}",
            response_body=data,
            status_code=resp.status_code
        )

    # Step 4: Check if file is deleted (if field present)
    if "deleted" in data and data["deleted"] is True:
        raise APIResponseError(
            f"File {expected_file_id} is marked as deleted",
            response_body=data,
            status_code=resp.status_code
        )

    logger.info(f"Metadata validated: file {expected_file_id}")
    return data


def validate_batch_response(resp, expected_request_count: int) -> Dict[str, Any]:
    """
    Validate OneDrive batch endpoint response.

    Args:
        resp: requests.Response object
        expected_request_count: Number of requests in batch

    Returns:
        Dict: Validated batch response with per-request status

    Raises:
        APIResponseError: If batch container validation fails
    """
    # Step 1: Validate JSON and check for errors
    data = validate_json_response(resp, expected_status_codes=[200])

    # Step 2: Verify batch structure
    if "responses" not in data:
        raise APIResponseError(
            "Batch response missing 'responses' array",
            response_body=data,
            status_code=resp.status_code
        )

    responses = data["responses"]
    if not isinstance(responses, list):
        raise APIResponseError(
            "Batch 'responses' is not an array",
            response_body=data,
            status_code=resp.status_code
        )

    if len(responses) != expected_request_count:
        raise APIResponseError(
            f"Batch response count mismatch: expected {expected_request_count}, got {len(responses)}",
            response_body=data,
            status_code=resp.status_code
        )

    # Step 3: Check per-request results (don't raise, just log)
    failed_count = 0
    for idx, resp_item in enumerate(responses):
        status = resp_item.get("status", 0)
        if status >= 400:
            body = resp_item.get("body", {})
            error_msg = body.get("error", {}).get("message", "Unknown error")
            logger.warning(f"Batch request {idx} failed: HTTP {status} - {error_msg}")
            failed_count += 1
        elif "error" in resp_item.get("body", {}):
            logger.warning(f"Batch request {idx} has error in body despite HTTP 200")
            failed_count += 1

    if failed_count > 0:
        logger.warning(f"Batch: {failed_count}/{expected_request_count} requests failed")

    return data
```

---

### Phase 2: Update rollback.py (Restore Function)

**Before:**
```python
resp = requests.post(
    f"https://graph.microsoft.com/v1.0/me/drive/items/{cid}/restore",
    headers={"Authorization": f"Bearer {token}"},
    json={"parentReference": {"id": parent_id}},
    timeout=30
)
if resp.status_code in (200, 201, 202, 204):
    return True, "Restored"
return False, f"HTTP {resp.status_code}: {resp.text[:300]}"
```

**After:**
```python
try:
    resp = requests.post(
        f"https://graph.microsoft.com/v1.0/me/drive/items/{cid}/restore",
        headers={"Authorization": f"Bearer {token}"},
        json={"parentReference": {"id": parent_id}},
        timeout=30
    )

    # Validate response before marking as restored
    validated = api_validators.validate_restore_response(resp, expected_file_id=cid)

    logger.info(f"File {cid} restored: {validated.get('name', cid)}")
    return True, "Restored"

except api_validators.APIResponseError as e:
    logger.error(f"Restore validation failed for {cid}: {e.message}")
    return False, f"Restore failed: {e.message}"
except requests.Timeout:
    logger.error(f"Restore request timed out for {cid}")
    return False, "Timeout"
except Exception as e:
    logger.error(f"Unexpected error restoring {cid}: {str(e)}")
    return False, f"Error: {str(e)}"
```

---

### Phase 3: Update verifier.py (Metadata Read)

**Before:**
```python
resp = requests.get(
    f"https://graph.microsoft.com/v1.0/me/drive/items/{file_id}",
    headers={"Authorization": f"Bearer {token}"},
    timeout=30
)
if resp.status_code == 200:
    meta = resp.json()
    # Use meta directly
```

**After:**
```python
try:
    resp = requests.get(
        f"https://graph.microsoft.com/v1.0/me/drive/items/{file_id}",
        headers={"Authorization": f"Bearer {token}"},
        timeout=30
    )

    # Validate response before using data
    meta = api_validators.validate_metadata_response(resp, expected_file_id=file_id)
    # Now safe to use meta

except api_validators.APIResponseError as e:
    logger.error(f"Metadata validation failed for {file_id}: {e.message}")
    return None  # or raise, depending on caller expectations
except requests.Timeout:
    logger.error(f"Metadata request timed out for {file_id}")
    return None
except Exception as e:
    logger.error(f"Unexpected error reading metadata for {file_id}: {str(e)}")
    return None
```

---

### Phase 4: Update cleaner.py (Batch Operations)

**Before:**
```python
resp = _requests.post(
    "https://graph.microsoft.com/v1.0/$batch",
    headers={"Authorization": f"Bearer {token}"},
    json=batch_payload,
    timeout=30
)
# Process results without per-request validation
```

**After:**
```python
try:
    resp = _requests.post(
        "https://graph.microsoft.com/v1.0/$batch",
        headers={"Authorization": f"Bearer {token}"},
        json=batch_payload,
        timeout=30
    )

    # Validate batch response structure
    batch_data = api_validators.validate_batch_response(
        resp,
        expected_request_count=len(batch_payload.get("requests", []))
    )

    # Process per-request results
    results = []
    for idx, resp_item in enumerate(batch_data["responses"]):
        status = resp_item.get("status", 0)
        body = resp_item.get("body", {})

        if status >= 400 or "error" in body:
            results.append({
                "request_id": resp_item.get("id"),
                "success": False,
                "error": body.get("error", {}).get("message", "Unknown error")
            })
        else:
            results.append({
                "request_id": resp_item.get("id"),
                "success": True,
                "data": body
            })

    return results

except api_validators.APIResponseError as e:
    logger.error(f"Batch validation failed: {e.message}")
    return []
except requests.Timeout:
    logger.error("Batch request timed out")
    return []
except Exception as e:
    logger.error(f"Unexpected error in batch operation: {str(e)}")
    return []
```

---

## TEST CASES

### Test 1: Valid Restore Response
```python
# Mock successful restore response
mock_response = Mock()
mock_response.status_code = 200
mock_response.json.return_value = {
    "id": "file-123",
    "name": "document.docx",
    "parentReference": {"id": "folder-456"}
}

result = api_validators.validate_restore_response(mock_response, "file-123")
assert result["id"] == "file-123"
assert result["name"] == "document.docx"
```

### Test 2: Restore Response with Error Field (HTTP 200 but error)
```python
# Mock error response with HTTP 200
mock_response = Mock()
mock_response.status_code = 200
mock_response.json.return_value = {
    "error": {
        "code": "invalidRequest",
        "message": "Invalid parent reference"
    }
}

with pytest.raises(APIResponseError) as exc:
    api_validators.validate_restore_response(mock_response, "file-123")
assert "invalidRequest" in str(exc.value)
```

### Test 3: Restore Response with Wrong File ID
```python
# Mock response with mismatched ID
mock_response = Mock()
mock_response.status_code = 200
mock_response.json.return_value = {
    "id": "file-789",  # Different ID!
    "name": "other-document.docx"
}

with pytest.raises(APIResponseError) as exc:
    api_validators.validate_restore_response(mock_response, "file-123")
assert "File ID mismatch" in str(exc.value)
```

### Test 4: Batch Response with Mixed Success/Failure
```python
# Mock batch response with per-request failures
mock_response = Mock()
mock_response.status_code = 200
mock_response.json.return_value = {
    "responses": [
        {
            "id": "1",
            "status": 200,
            "body": {"id": "file-1", "name": "doc1.docx"}
        },
        {
            "id": "2",
            "status": 404,
            "body": {"error": {"code": "itemNotFound", "message": "File not found"}}
        },
        {
            "id": "3",
            "status": 200,
            "body": {"id": "file-3", "name": "doc3.docx"}
        }
    ]
}

result = api_validators.validate_batch_response(mock_response, expected_request_count=3)
assert len(result["responses"]) == 3
assert result["responses"][0]["status"] == 200
assert result["responses"][1]["status"] == 404  # Failed but processed
```

### Test 5: Invalid JSON Response
```python
# Mock non-JSON response
mock_response = Mock()
mock_response.status_code = 200
mock_response.json.side_effect = ValueError("Invalid JSON")
mock_response.text = "Internal Server Error"

with pytest.raises(APIResponseError) as exc:
    api_validators.validate_json_response(mock_response)
assert "Invalid JSON" in str(exc.value)
```

### Test 6: Metadata Response with Deleted Flag
```python
# Mock metadata showing file is deleted
mock_response = Mock()
mock_response.status_code = 200
mock_response.json.return_value = {
    "id": "file-123",
    "name": "deleted-doc.docx",
    "deleted": True
}

with pytest.raises(APIResponseError) as exc:
    api_validators.validate_metadata_response(mock_response, "file-123")
assert "marked as deleted" in str(exc.value)
```

---

## SECURITY CHECKLIST

- ✅ Response parsing is isolated in validators module
- ✅ All error messages are logged, not exposed to user
- ✅ File IDs are verified before trusting response
- ✅ Response body is validated before accessing fields
- ✅ Exceptions prevent silent failures
- ✅ Retry logic can be added without changing callers
- ✅ Timeout handling prevents hanging requests
- ✅ Batch operations validate per-request status, not just container

---

## ROLLOUT PLAN

### Step 1: Review & Feedback
- Review design with security team
- Confirm API response schemas match actual Microsoft Graph API
- Confirm Google Drive API validation requirements

### Step 2: Implementation
- Create `tools/api_validators.py` with all validators
- Update `tools/rollback.py` restore function (lines 445-453)
- Update `phase2/verifier.py` metadata reads (lines 186-244)
- Update `phase3/cleaner.py` batch operations (lines 269-270)
- Add error logging throughout

### Step 3: Testing
- Create `tests/test_api_validators.py` with all test cases above
- Run: `pytest tests/test_api_validators.py -v --cov`
- Verify coverage ≥ 80%
- Test with mock responses before hitting real APIs

### Step 4: Integration Testing
- Test restore of single file via OneDrive
- Test batch operations via OneDrive
- Test error handling (invalid token, file not found, etc.)
- Test metadata reads

### Step 5: Deployment
- Pre-commit hooks automatically validate
- GitHub Actions run full test suite
- After tests pass, safe to merge to main

---

## MONITORING & ALERTING

After deployment, monitor:
- Count of validation failures (should be low)
- Error types (itemNotFound, accessDenied, throttled, etc.)
- Response time distribution (identify slow APIs)
- Retry rates (exponential backoff effectiveness)

Alert on:
- Sudden spike in validation failures
- New error types not seen before
- Response times > 10 seconds

---

## APPENDIX: Microsoft Graph API Response Schemas

### Restore Endpoint Success (200, 201, 202)
```json
{
  "id": "string",
  "name": "string",
  "webUrl": "string",
  "parentReference": {
    "id": "string",
    "driveId": "string",
    "driveType": "string"
  },
  "size": 0,
  "lastModifiedDateTime": "2024-01-01T00:00:00Z",
  "deleted": false
}
```

### Restore Endpoint Error
```json
{
  "error": {
    "code": "string",
    "message": "string",
    "innerError": {
      "code": "string",
      "message": "string"
    }
  }
}
```

### Common Error Codes
- `itemNotFound` — File/folder not found
- `invalidRequest` — Bad request (invalid parent reference, etc.)
- `accessDenied` — No permission to access
- `throttled` — Rate limited, retry later with backoff
- `serviceUnavailable` — Temporary outage

### Batch Request Response
```json
{
  "responses": [
    {
      "id": "string",
      "status": 200,
      "body": {
        // Single item response (success)
      },
      "headers": {}
    },
    {
      "id": "string",
      "status": 404,
      "body": {
        "error": {
          "code": "itemNotFound",
          "message": "The resource was not found"
        }
      },
      "headers": {}
    }
  ]
}
```

---

## RELATED DOCUMENTS

- `SECURITY_AUDIT.md` — All 11 security issues
- `MASTER_SETUP_GUIDE.md` — Testing infrastructure
- `CLAUDE.md` — Project roadmap
- `tools/rollback.py` — Current restore implementation
- `phase2/verifier.py` — Current metadata reads
- `phase3/cleaner.py` — Current batch operations

---

## SIGN-OFF

**Design Status:** ✅ READY FOR IMPLEMENTATION
**Reviewed By:** [pending security team review]
**Implementation Owner:** [pending assignment]
**Target Completion:** [to be scheduled]
