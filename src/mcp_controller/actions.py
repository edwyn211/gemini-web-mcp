import logging
from playwright.async_api import Page, TimeoutError as PlaywrightTimeoutError
from mcp_controller.selectors import gemini_selectors
from utils.retry_handler import retry_async
from utils.state_validator import StateValidator
from utils.screenshot_manager import ScreenshotManager

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


class GeminiPageActions:
    """
    Page Object Model for interacting with the Gemini web interface.
    Enhanced with retry logic, state validation, and screenshot capture.
    """

    def __init__(self, page: Page):
        """
        Initializes the action class with a Playwright Page object.
        
        :param page: An authenticated Playwright Page object.
        """
        self.page = page
        self.validator = StateValidator(page, gemini_selectors)
        self.screenshot_manager = ScreenshotManager()
        
    async def _try_selectors(self, selector_field: str, action: str = "click", timeout: int = 10000, **kwargs):
        """
        Try multiple selectors in order until one works.
        
        Args:
            selector_field: Name of the selector field in gemini_selectors
            action: Action to perform ("click", "type", "wait", etc.)
            timeout: Timeout for each selector attempt
            **kwargs: Additional arguments for the action
            
        Returns:
            Result of the action, or raises exception if all selectors fail
        """
        selectors = gemini_selectors.get_all_selectors(selector_field)
        last_error = None
        
        for i, selector in enumerate(selectors):
            try:
                logger.debug(f"Trying selector {i+1}/{len(selectors)}: {selector}")
                
                if action == "click":
                    await self.page.click(selector, timeout=timeout, **kwargs)
                    return True
                elif action == "type":
                    text = kwargs.get("text", "")
                    await self.page.type(selector, text, timeout=timeout)
                    return True
                elif action == "wait":
                    state = kwargs.get("state", "attached")
                    await self.page.wait_for_selector(selector, state=state, timeout=timeout)
                    return True
                elif action == "get_element":
                    element = await self.page.query_selector(selector)
                    if element:
                        return element
                    raise Exception(f"Element not found: {selector}")
                else:
                    raise ValueError(f"Unknown action: {action}")
                    
            except Exception as e:
                last_error = e
                logger.debug(f"Selector {i+1} failed: {e}")
                continue
        
        # All selectors failed
        error_msg = f"All selectors failed for {selector_field}. Last error: {last_error}"
        logger.error(error_msg)
        await self.screenshot_manager.capture_error(
            self.page,
            f"try_selectors_{selector_field}",
            last_error,
            selector=selectors[0]
        )
        raise Exception(error_msg)

    @retry_async(max_attempts=3, initial_delay=2.0, exceptions=(PlaywrightTimeoutError, Exception))
    async def send_prompt(self, text: str):
        """
        Types a prompt into the text area and clicks the send button.
        Enhanced with retry logic and validation.
        
        :param text: The prompt text to send.
        """
        logger.info(f"Sending prompt: '{text}'")
        
        try:
            # Wait for the textarea to be available
            await self._try_selectors("prompt_textarea", action="wait", timeout=60000)
            logger.info("Textarea found, typing prompt...")
            
            # Click on the textarea first to focus it
            await self._try_selectors("prompt_textarea", action="click")
            await self.page.wait_for_timeout(2000)
            
            # Type the text
            textarea_selector = gemini_selectors.get_primary("prompt_textarea")
            await self.page.type(textarea_selector, text)
            await self.page.wait_for_timeout(3000)
            
            logger.info("Clicking send button...")
            await self._try_selectors("send_button", action="click")
            await self.page.wait_for_timeout(5000)
            
            # Validate response is ready
            success, details = await self.validator.validate_response_ready(timeout=60000)
            if success:
                logger.info("✓ Prompt sent and response validated")
            else:
                logger.warning(f"⚠ Response validation unclear: {details}")
            
        except Exception as e:
            logger.error(f"Error in send_prompt: {e}")
            await self.screenshot_manager.capture_error(self.page, "send_prompt", e)
            raise

    async def get_last_response(self) -> str:
        """
        Retrieves the text content of the last response from Gemini.
        
        :return: The text content of the last response.
        """
        logger.info("Retrieving last response...")
        
        try:
            # Try all response selectors
            response_selectors = gemini_selectors.get_all_selectors("last_response")
            
            for selector in response_selectors:
                try:
                    response_elements = await self.page.query_selector_all(selector)
                    if response_elements:
                        last_response_element = response_elements[-1]
                        response_text = await last_response_element.inner_text()
                        if response_text:
                            logger.info(f"Retrieved response: '{response_text[:100]}...'")
                            return response_text
                except Exception as e:
                    logger.debug(f"Selector {selector} failed: {e}")
                    continue
            
            logger.warning("No response elements found with any selector")
            return ""
            
        except Exception as e:
            logger.error(f"Error getting last response: {e}")
            return ""

    @retry_async(max_attempts=3, initial_delay=1.0, exceptions=(PlaywrightTimeoutError, Exception))
    async def start_new_chat(self):
        """
        Clicks the 'New chat' button to start a fresh conversation.
        Enhanced with retry logic and validation.
        """
        logger.info("Starting a new chat...")
        
        try:
            await self._try_selectors("new_chat_button", action="click", force=True)
            
            # Validate that new chat started
            success, details = await self.validator.validate_chat_started(timeout=5000)
            if success:
                logger.info("✓ New chat started and validated")
            else:
                logger.warning(f"⚠ New chat validation unclear: {details}")
                
        except Exception as e:
            logger.error(f"Error starting new chat: {e}")
            await self.screenshot_manager.capture_error(self.page, "start_new_chat", e)
            raise

    @retry_async(max_attempts=5, initial_delay=2.0, backoff_multiplier=1.5, exceptions=(PlaywrightTimeoutError, Exception))
    async def select_tool(self, tool_name: str):
        """
        Selects a tool (Canvas or Deep Research) before sending a prompt.
        Enhanced with retry logic and validation.
        
        :param tool_name: Either 'canvas' or 'deep_research'
        """
        logger.info(f"Selecting tool: {tool_name}")
        
        tool_field_map = {
            "canvas": "canvas_button",
            "deep_research": "deep_research_button"
        }
        
        tool_field = tool_field_map.get(tool_name.lower())
        if not tool_field:
            raise ValueError(f"Unknown tool: {tool_name}. Use 'canvas' or 'deep_research'")
        
        try:
            # 1. Click the Tools button to open the menu
            logger.info("Opening tools menu...")
            tools_button_selector = gemini_selectors.get_primary("tools_button")
            tools_icon = self.page.locator(tools_button_selector)
            await tools_icon.wait_for(state='attached', timeout=10000)
            await tools_icon.locator("..").click(force=True)
            await self.page.wait_for_timeout(1500)

            # 2. Wait for and click the specific tool
            logger.info(f"Clicking {tool_name} button...")
            await self._try_selectors(tool_field, action="wait", state='attached', timeout=10000)
            
            # Click the parent button of the tool icon
            tool_selector = gemini_selectors.get_primary(tool_field)
            tool_icon = self.page.locator(tool_selector)
            await tool_icon.locator("..").click(force=True)
            await self.page.wait_for_timeout(1500)
            
            # 3. Validate tool selection
            success, details = await self.validator.validate_tool_selected(tool_name, timeout=5000)
            if success:
                logger.info(f"✓ Tool '{tool_name}' selected and validated")
            else:
                logger.info(f"⚠ Tool selection validation not available: {details}")
                
        except Exception as e:
            logger.error(f"Error selecting tool '{tool_name}': {e}")
            await self.screenshot_manager.capture_error(self.page, f"select_tool_{tool_name}", e)
            raise

    @retry_async(max_attempts=3, initial_delay=5.0, max_delay=60.0, exceptions=(PlaywrightTimeoutError,))
    async def wait_for_deep_research_plan(self, timeout: int = 90000):
        """
        Waits for the Deep Research plan to be generated and displayed.
        Enhanced with retry logic and validation.
        
        :param timeout: Timeout in milliseconds
        """
        logger.info("Waiting for Deep Research plan to be generated...")
        
        try:
            # Try all selectors for the plan ready indicator
            await self._try_selectors("deep_research_plan_ready", action="wait", timeout=timeout)
            
            # Validate the plan is ready
            success, details = await self.validator.validate_deep_research_plan_ready(timeout=10000)
            if success:
                logger.info("✓ Deep Research plan is ready and validated")
            else:
                logger.warning(f"⚠ Deep Research plan validation unclear: {details}")
                
        except Exception as e:
            logger.error(f"Error waiting for Deep Research plan: {e}")
            await self.screenshot_manager.capture_error(self.page, "wait_for_deep_research_plan", e)
            raise

    @retry_async(max_attempts=3, initial_delay=2.0, exceptions=(PlaywrightTimeoutError, Exception))
    async def confirm_deep_research_plan(self):
        """
        Clicks the 'Confirm' button to proceed with the Deep Research plan.
        Enhanced with retry logic and validation.
        """
        logger.info("Confirming Deep Research plan...")
        
        try:
            await self._try_selectors("deep_research_confirm_button", action="click", force=True)
            await self.page.wait_for_timeout(2000)
            
            # Validate confirmation
            success, details = await self.validator.validate_deep_research_confirmed(timeout=5000)
            if success:
                logger.info("✓ Deep Research plan confirmed and validated")
            else:
                logger.info(f"⚠ Deep Research confirmation validation unclear: {details}")
                
        except Exception as e:
            logger.error(f"Error confirming Deep Research plan: {e}")
            await self.screenshot_manager.capture_error(self.page, "confirm_deep_research_plan", e)
            raise
    
    @retry_async(max_attempts=5, initial_delay=2.0, backoff_multiplier=1.5, exceptions=(PlaywrightTimeoutError, Exception))
    async def ensure_reasoning_mode(self):
        """
        Ensures that the 'Reasoning' (Razonamiento) model is selected.
        Enhanced with retry logic and validation.
        """
        logger.info("Verifying Reasoning mode...")
        
        try:
            # Wait for mode selector to be available
            await self._try_selectors("mode_selector", action="wait", state='attached', timeout=10000)
            
            # Check current mode
            mode_selector = gemini_selectors.get_primary("mode_selector")
            mode_element = await self.page.query_selector(mode_selector)
            
            if mode_element:
                current_mode = await mode_element.inner_text()
                
                if "Razonamiento" in current_mode:
                    logger.info("✓ Already in Reasoning mode")
                    return

                logger.info(f"Current mode is '{current_mode}', switching to Reasoning...")
                
                # Get the dropdown icon selector
                mode_config = getattr(gemini_selectors, "mode_selector")
                dropdown_icon = mode_config.dropdown_icon if hasattr(mode_config, 'dropdown_icon') else "mat-icon[data-mat-icon-name='keyboard_arrow_down']"
                
                # Click the dropdown icon to open menu
                await self.page.click(dropdown_icon, force=True)
                await self.page.wait_for_timeout(1500)
                
                # Select "Razonamiento" from the menu
                reasoning_option = mode_config.reasoning_option if hasattr(mode_config, 'reasoning_option') else "text=Razonamiento"
                await self.page.click(reasoning_option, force=True)
                await self.page.wait_for_timeout(2000)
                
                # Validate mode change
                success, details = await self.validator.validate_mode_changed("Razonamiento", timeout=5000)
                if success:
                    logger.info("✓ Switched to Reasoning mode and validated")
                else:
                    logger.warning(f"⚠ Mode change validation unclear: {details}")
            else:
                logger.warning("Mode selector element not found")
                
        except Exception as e:
            logger.error(f"Error ensuring Reasoning mode: {e}")
            await self.screenshot_manager.capture_error(self.page, "ensure_reasoning_mode", e)
            raise
