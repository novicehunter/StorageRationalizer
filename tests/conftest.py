import pytest
import tempfile
from pathlib import Path
from unittest.mock import MagicMock


@pytest.fixture
def temp_creds_dir():
    """Temporary credentials directory for testing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        path = Path(tmpdir) / "credentials"
        path.mkdir()
        (path / "encrypted").mkdir()
        yield path


@pytest.fixture
def temp_db():
    """Temporary SQLite database for testing."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        yield f.name


@pytest.fixture
def mock_onedrive_api():
    """Mock OneDrive API responses."""
    mock = MagicMock()
    mock.status_code = 200
    mock.json.return_value = {"id": "file_123"}
    return mock


@pytest.fixture
def mock_google_api():
    """Mock Google Drive API responses."""
    mock = MagicMock()
    mock.status_code = 200
    mock.json.return_value = {"id": "file_456"}
    return mock
