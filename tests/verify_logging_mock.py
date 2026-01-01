
import logging
import sys
import unittest
from unittest.mock import MagicMock, AsyncMock, patch

# Configure logging to stdout
logging.basicConfig(
    level=logging.INFO, 
    format="%(asctime)s - %(levelname)s - %(message)s",
    stream=sys.stdout
)

# We need to add src to path to import modules
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../src')))

from mcp_controller.actions import GeminiPageActions
# We don't import mcp_server directly to avoid starting the server/redis/etc, 
# but we might Mock it if needed or just use actions.py verification.

class TestLogging(unittest.IsolatedAsyncioTestCase):
    async def test_send_prompt_logging(self):
        print("\n--- Testing send_prompt logging ---")
        mock_page = MagicMock()
        mock_page.click = AsyncMock()
        mock_page.wait_for_selector = AsyncMock()
        mock_page.wait_for_timeout = AsyncMock()
        mock_page.locator = MagicMock()
        mock_page.locator.return_value.evaluate = AsyncMock()
        
        actions = GeminiPageActions(mock_page)
        
        # Mock internal helpers
        actions._try_selectors = AsyncMock()
        actions.validator = MagicMock()
        actions.validator.validate_response_ready = AsyncMock(return_value=(True, "ok"))
        
        await actions.send_prompt("Test Prompt 123")
        
    async def test_get_last_response_logging(self):
        print("\n--- Testing get_last_response logging ---")
        mock_page = MagicMock()
        actions = GeminiPageActions(mock_page)
        
        # Mock validation
        actions.validator = MagicMock()
        actions.validator.validate_generation_complete = AsyncMock(return_value=(True, "ok"))
        
        # Mock OpenAI-like response object or just the element finding
        # We need to mock query_selector_all and the element text
        mock_element = MagicMock()
        mock_element.inner_text = AsyncMock(return_value="This is a full response from Gemini that should not be truncated even if it is very long." * 10)
        
        actions.page.query_selector_all = AsyncMock(return_value=[mock_element])
        
        # Mocking gemini_selectors.get_all_selectors on the instance used by actions
        from mcp_controller.selectors import gemini_selectors
        # Since gemini_selectors is a Pydantic model, we can't easily patch it if it's frozen or restrictive.
        # But we can try to mock the method on the class if it were a normal class. 
        # Easier: just mock _try_selectors or the specific call if the logic allows.
        
        # Actually, let's just patch it where it is used in actions.py
        with patch('mcp_controller.actions.gemini_selectors') as mock_selectors:
            mock_selectors.get_all_selectors.return_value = ['.response']
            await actions.get_last_response()

if __name__ == '__main__':
    unittest.main()
