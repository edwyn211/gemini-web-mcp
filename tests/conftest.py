import pytest
import sys
import os
from unittest.mock import AsyncMock, patch

# Add src to path so imports work
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../src")))


@pytest.fixture
def mock_redis():
    """Fixture to mock Redis client"""
    with patch("mcp_server.get_redis", new_callable=AsyncMock) as mock:
        yield mock


@pytest.fixture
def mock_subprocess():
    """Fixture to mock asyncio subprocess execution"""
    with patch("asyncio.create_subprocess_exec", new_callable=AsyncMock) as mock:
        yield mock


@pytest.fixture
def mock_session_manager():
    """Fixture to mock SessionManager"""
    with patch("mcp_server.session_manager", new_callable=AsyncMock) as mock:
        yield mock
