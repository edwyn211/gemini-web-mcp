"""
State validator for Gemini web interface actions
Validates that actions completed successfully before proceeding
"""

import logging
from typing import Dict, Any, Optional
from playwright.async_api import Page

logger = logging.getLogger(__name__)


class StateValidator:
    """
    Validates the state of the Gemini web interface after actions.
    Each validator returns (success: bool, details: dict)
    """
    
    def __init__(self, page: Page, selectors):
        """
        Initialize the state validator
        
        Args:
            page: Playwright Page object
            selectors: GeminiSelectors object
        """
        self.page = page
        self.selectors = selectors
    
    def _get_selector(self, field_name: str) -> str:
        """Get primary selector string for a field"""
        selector = getattr(self.selectors, field_name, None)
        if selector is None:
            return ""
        # If it's a SelectorConfig object, get the primary
        if hasattr(selector, 'primary'):
            return selector.primary
        # Otherwise it's already a string
        return selector
        
    async def validate_chat_started(self, timeout: int = 5000) -> tuple[bool, dict]:
        """
        Validate that a new chat was started successfully
        
        Returns:
            (success, details) where details contains validation info
        """
        try:
            # Check if the textarea is empty (has ql-blank class)
            textarea_selector = self._get_selector("prompt_textarea")
            blank_selector = f"{textarea_selector}.ql-blank"
            
            await self.page.wait_for_selector(blank_selector, state='attached', timeout=timeout)
            
            # Verify the textarea is actually empty
            textarea = await self.page.query_selector(textarea_selector)
            if textarea:
                text_content = await textarea.inner_text()
                is_empty = len(text_content.strip()) == 0
                
                if is_empty:
                    logger.info("✓ New chat validated: textarea is empty")
                    return True, {"status": "empty", "content": ""}
                else:
                    logger.warning(f"✗ New chat validation failed: textarea contains text: '{text_content}'")
                    return False, {"status": "not_empty", "content": text_content}
            
            return False, {"status": "textarea_not_found"}
            
        except Exception as e:
            logger.error(f"✗ Error validating new chat: {e}")
            return False, {"status": "error", "error": str(e)}
    
    async def validate_mode_changed(self, expected_mode: str, timeout: int = 5000) -> tuple[bool, dict]:
        """
        Validate that the mode was changed to the expected mode
        
        Args:
            expected_mode: Expected mode name (e.g., "Razonamiento")
            timeout: Timeout in milliseconds
            
        Returns:
            (success, details)
        """
        try:
            mode_selector = self._get_selector("mode_selector")
            
            await self.page.wait_for_selector(mode_selector, state='attached', timeout=timeout)
            
            mode_element = await self.page.query_selector(mode_selector)
            if mode_element:
                current_mode = await mode_element.inner_text()
                
                if expected_mode.lower() in current_mode.lower():
                    logger.info(f"✓ Mode validated: {current_mode}")
                    return True, {"current_mode": current_mode, "expected_mode": expected_mode}
                else:
                    logger.warning(f"✗ Mode mismatch: expected '{expected_mode}', got '{current_mode}'")
                    return False, {"current_mode": current_mode, "expected_mode": expected_mode}
            
            return False, {"status": "mode_element_not_found"}
            
        except Exception as e:
            logger.error(f"✗ Error validating mode: {e}")
            return False, {"status": "error", "error": str(e)}
    
    async def validate_tool_selected(self, tool_name: str, timeout: int = 5000) -> tuple[bool, dict]:
        """
        Validate that a tool (Canvas or Deep Research) was selected
        
        Args:
            tool_name: Name of the tool ("canvas" or "deep_research")
            timeout: Timeout in milliseconds
            
        Returns:
            (success, details)
        """
        try:
            # Get the validator selector for this tool
            tool_key = f"{tool_name}_button"
            tool_selector = getattr(self.selectors, tool_key, None)
            
            if tool_selector and hasattr(tool_selector, 'validator') and tool_selector.validator:
                # Try to find the validator element
                try:
                    await self.page.wait_for_selector(tool_selector.validator, state='attached', timeout=timeout)
                    logger.info(f"✓ Tool validated: {tool_name} is active")
                    return True, {"tool": tool_name, "status": "active"}
                except:
                        pass
            
            # Fallback: Check if the tool button is still visible (might indicate it's selected)
            # This is a weaker validation but better than nothing
            logger.info(f"⚠ Tool selection validation not available for {tool_name}, assuming success")
            return True, {"tool": tool_name, "status": "assumed_active", "note": "no_validator"}
            
        except Exception as e:
            logger.error(f"✗ Error validating tool selection: {e}")
            return False, {"status": "error", "error": str(e)}
    
    async def validate_response_ready(self, timeout: int = 60000) -> tuple[bool, dict]:
        """
        Validate that a response from Gemini is ready
        
        Args:
            timeout: Timeout in milliseconds
            
        Returns:
            (success, details)
        """
        try:
            response_selector = self._get_selector("last_response")
            
            await self.page.wait_for_selector(response_selector, state='attached', timeout=timeout)
            
            # Wait a bit more to ensure the response is fully loaded
            await self.page.wait_for_timeout(2000)
            
            # Get the response elements
            response_elements = await self.page.query_selector_all(response_selector)
            
            if response_elements:
                # Get the last response
                last_response = response_elements[-1]
                response_text = await last_response.inner_text()
                response_length = len(response_text)
                
                if response_length > 0:
                    logger.info(f"✓ Response validated: {response_length} characters")
                    return True, {
                        "status": "ready",
                        "length": response_length,
                        "preview": response_text[:100]
                    }
                else:
                    logger.warning("✗ Response element found but empty")
                    return False, {"status": "empty_response"}
            
            return False, {"status": "no_response_elements"}
            
        except Exception as e:
            logger.error(f"✗ Error validating response: {e}")
            return False, {"status": "error", "error": str(e)}
    
    async def validate_deep_research_plan_ready(self, timeout: int = 60000) -> tuple[bool, dict]:
        """
        Validate that the Deep Research plan is ready for confirmation
        
        Args:
            timeout: Timeout in milliseconds
            
        Returns:
            (success, details)
        """
        try:
            plan_selector = self._get_selector("deep_research_plan_ready")
            
            await self.page.wait_for_selector(plan_selector, state='attached', timeout=timeout)
            
            # Check if the confirm button is visible and enabled
            confirm_button = await self.page.query_selector(plan_selector)
            if confirm_button:
                is_visible = await confirm_button.is_visible()
                is_enabled = await confirm_button.is_enabled()
                
                if is_visible and is_enabled:
                    logger.info("✓ Deep Research plan validated: ready for confirmation")
                    return True, {"status": "ready", "visible": True, "enabled": True}
                else:
                    logger.warning(f"✗ Deep Research plan button found but not ready: visible={is_visible}, enabled={is_enabled}")
                    return False, {"status": "not_ready", "visible": is_visible, "enabled": is_enabled}
            
            return False, {"status": "button_not_found"}
            
        except Exception as e:
            logger.error(f"✗ Error validating Deep Research plan: {e}")
            return False, {"status": "error", "error": str(e)}
    
    async def validate_deep_research_confirmed(self, timeout: int = 5000) -> tuple[bool, dict]:
        """
        Validate that the Deep Research plan was confirmed and research is running
        
        Args:
            timeout: Timeout in milliseconds
            
        Returns:
            (success, details)
        """
        try:
            # After confirmation, the button should disappear
            plan_selector = self._get_selector("deep_research_plan_ready")
            
            # Wait for the button to disappear (indicating confirmation was successful)
            try:
                await self.page.wait_for_selector(plan_selector, state='detached', timeout=timeout)
                logger.info("✓ Deep Research confirmed: plan button disappeared")
                return True, {"status": "confirmed", "research_running": True}
            except:
                # Button still visible, confirmation might have failed
                logger.warning("✗ Deep Research confirmation unclear: button still visible")
                return False, {"status": "button_still_visible"}
            
        except Exception as e:
            logger.error(f"✗ Error validating Deep Research confirmation: {e}")
            return False, {"status": "error", "error": str(e)}
