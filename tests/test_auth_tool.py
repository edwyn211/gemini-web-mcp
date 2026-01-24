import pytest
from unittest.mock import AsyncMock
from mcp_server import refresh_gemini_auth


@pytest.mark.asyncio
async def test_refresh_gemini_auth_success(mock_subprocess):
    """Test successful authentication refresh"""
    mock_process = AsyncMock()
    mock_process.communicate.return_value = (b"Success output", b"")
    mock_process.returncode = 0
    mock_subprocess.return_value = mock_process

    response = await refresh_gemini_auth()
    assert response.status == "success"
    assert "Success output" in response.message


@pytest.mark.asyncio
async def test_refresh_gemini_auth_failure(mock_subprocess):
    """Test failed authentication refresh"""
    mock_process = AsyncMock()
    mock_process.communicate.return_value = (b"Fail output", b"Error log")
    mock_process.returncode = 1
    mock_subprocess.return_value = mock_process

    response = await refresh_gemini_auth()
    assert response.status == "error"
    assert "Error log" in response.message
