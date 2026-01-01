import asyncio
import sys
import os
from unittest.mock import MagicMock, AsyncMock, patch

# Add src to path so imports work
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../src')))

from mcp_server import refresh_gemini_auth

async def test_refresh_gemini_auth():
    print("Testing refresh_gemini_auth...")
    
    with patch("asyncio.create_subprocess_exec", new_callable=AsyncMock) as mock_exec:
        # User Case 1: Success
        mock_process = AsyncMock()
        mock_process.communicate.return_value = (b"Success output", b"")
        mock_process.returncode = 0
        mock_exec.return_value = mock_process
        
        print("\nTest 1: Success scenario")
        response = await refresh_gemini_auth()
        print(f"Status: {response.status}")
        assert response.status == "success"
        
        # User Case 2: Failure
        mock_process_fail = AsyncMock()
        mock_process_fail.communicate.return_value = (b"Fail output", b"Error log")
        mock_process_fail.returncode = 1
        mock_exec.return_value = mock_process_fail
        
        print("\nTest 2: Failure scenario")
        response = await refresh_gemini_auth()
        print(f"Status: {response.status}")
        assert response.status == "error"
        assert "Error log" in response.message

if __name__ == "__main__":
    asyncio.run(test_refresh_gemini_auth())
