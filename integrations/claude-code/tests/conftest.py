import pytest
import respx


@pytest.fixture
def mock_api():
    """Provide a respx mock router for the memory API."""
    with respx.mock(base_url="http://localhost:8920") as mock:
        yield mock
