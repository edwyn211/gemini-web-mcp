import logging

from playwright.async_api import Page
from playwright.async_api import TimeoutError as PlaywrightTimeoutError

from mcp_controller.selectors import gemini_selectors
from utils.retry_handler import retry_async
from utils.screenshot_manager import ScreenshotManager
from utils.state_validator import StateValidator

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
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

    async def _try_selectors(
        self, selector_field: str, action: str = "click", timeout: int = 10000, **kwargs
    ):
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
                    await self.page.wait_for_selector(
                        selector, state=state, timeout=timeout
                    )
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
        error_msg = (
            f"All selectors failed for {selector_field}. Last error: {last_error}"
        )
        logger.error(error_msg)
        await self.screenshot_manager.capture_error(
            self.page,
            f"try_selectors_{selector_field}",
            last_error,
            selector=selectors[0],
        )
        raise Exception(error_msg)

    @retry_async(
        max_attempts=3,
        initial_delay=2.0,
        exceptions=(PlaywrightTimeoutError, Exception),
    )
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
            success, details = await self.validator.validate_response_ready(
                timeout=60000
            )
            if success:
                logger.info("✓ Prompt sent and response validated")
            else:
                logger.warning(f"⚠ Response validation unclear: {details}")

        except Exception as e:
            logger.error(f"Error in send_prompt: {e}")
            await self.screenshot_manager.capture_error(self.page, "send_prompt", e)
            raise

    async def is_generating(self) -> bool:
        """
        Checks if Gemini is currently generating a response (busy state).
        Returns True if the Stop button is visible or if the Send button is hidden/disabled.
        """
        try:
            # 1. Check for Stop button
            stop_selectors = gemini_selectors.get_all_selectors("stop_button")
            for selector in stop_selectors:
                if await self.page.is_visible(selector):
                    logger.info("Generation in progress: Stop button is visible")
                    return True

            # 2. Check if Send button is hidden (often replaced by Stop button)
            # This is a secondary check, might be less reliable if UI changes
            send_selectors = gemini_selectors.get_all_selectors("send_button")
            primary_send = send_selectors[0]
            if not await self.page.is_visible(primary_send):
                logger.info("Generation in progress: Send button is not visible")
                return True

            return False
        except Exception as e:
            logger.warning(f"Error checking generation status: {e}")
            return False

    async def get_canvas_content(self) -> str | None:
        """
        Attempts to retrieve content from the Canvas editor.
        Returns None if Canvas is not visible or empty.
        """
        logger.info("Checking for Canvas content...")
        try:
            # Check if we have a canvas content selector
            canvas_selectors = gemini_selectors.get_all_selectors("canvas_content")

            for selector in canvas_selectors:
                elements = await self.page.query_selector_all(selector)
                for element in elements:
                    if await element.is_visible():
                        content = await element.inner_text()
                        if content and len(content.strip()) > 10:
                            logger.info(
                                f"✓ Found Canvas content ({len(content)} chars)"
                            )
                            return content
            return None
        except Exception as e:
            logger.debug(f"Error checking canvas: {e}")
            return None

    async def get_deep_research_content(self) -> str | None:
        """
        Intenta recuperar el contenido del informe de Deep Research.
        Retorna None si Deep Research no es visible o está vacío.
        """
        logger.info("Verificando si hay contenido del informe de Deep Research...")
        try:
            # Obtener selectores para el contenido de investigación profunda
            research_selectors = gemini_selectors.get_all_selectors(
                "deep_research_content"
            )

            for selector in research_selectors:
                elements = await self.page.query_selector_all(selector)
                for element in elements:
                    if await element.is_visible():
                        content = await element.inner_text()
                        if content and len(content.strip()) > 10:
                            logger.info(
                                f"✓ Se encontró un informe de Investigación Profunda ({len(content)} caracteres)"
                            )
                            return content
            return None
        except Exception as e:
            logger.debug(
                f"Error al verificar el contenido de investigación profunda: {e}"
            )
            return None

    async def get_last_response(
        self, timeout: int = 120000, tool: str | None = None
    ) -> str:
        """
        Recupera el contenido de texto de la última respuesta de Gemini.
        Prioriza el contenido según la herramienta utilizada (Deep Research, Canvas),
        luego intenta con el chat principal.

        :param timeout: Tiempo máximo de espera para que la generación finalice (ms).
        :param tool: Herramienta utilizada ('deep_research', 'canvas', etc.)
        :return: El contenido de texto de la última respuesta.
        """
        logger.info(
            f"Recuperando la última respuesta (timeout: {timeout}ms, herramienta: {tool})..."
        )

        try:
            # Esperar a que la generación se complete
            success, details = await self.validator.validate_generation_complete(
                timeout=timeout
            )
            if not success:
                logger.warning(
                    f"⚠ La validación de finalización de generación falló o expiró: {details.get('error', 'error desconocido')}"
                )

            # 1. Prioridad según la herramienta
            if tool and tool.lower() == "deep_research":
                research_text = await self.get_deep_research_content()
                if research_text:
                    logger.info(
                        "Retornando el informe de Deep Research como respuesta."
                    )
                    return research_text

            if tool and tool.lower() == "canvas":
                canvas_text = await self.get_canvas_content()
                if canvas_text:
                    logger.info("Retornando el contenido de Canvas como respuesta.")
                    return canvas_text

            # 2. Si no es herramienta específica o no se encontró contenido, buscar en el chat normal
            # Pero también probar Deep Research y Canvas como respaldo si fallan los selectores normales

            # Probar selectores de respuesta normales
            response_selectors = gemini_selectors.get_all_selectors("last_response")

            # Get all potential response elements first
            candidates = []
            for selector in response_selectors:
                try:
                    elements = await self.page.query_selector_all(selector)
                    candidates.extend(elements)
                except Exception as e:
                    # Ignorar errores de selectores individuales y continuar con el siguiente
                    logger.debug(f"Error al buscar selector {selector}: {e}")
                    continue

            # Filter and sort (assuming document order is roughly chronological)
            # We want the last non-empty one that isn't just a status message

            valid_response = ""

            if candidates:
                # Iterate backwards
                for element in reversed(candidates):
                    text = await element.inner_text()
                    if not text:
                        continue

                    # Filter out known status messages if necessary
                    if "Has parado esta respuesta" in text and len(text) < 50:
                        logger.warning("Skipping 'Stopped response' status message")
                        continue

                    valid_response = text
                    logger.info(f"Retrieved response: '{valid_response[:100]}...'")
                    break

            if valid_response:
                return valid_response

            logger.warning("No valid response elements found")
            return ""

        except Exception as e:
            logger.error(f"Error getting last response: {e}")
            return ""

    @retry_async(
        max_attempts=3,
        initial_delay=1.0,
        exceptions=(PlaywrightTimeoutError, Exception),
    )
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

    @retry_async(
        max_attempts=5,
        initial_delay=2.0,
        backoff_multiplier=1.5,
        exceptions=(PlaywrightTimeoutError, Exception),
    )
    async def select_tool(self, tool_name: str):
        """
        Selects a tool (Canvas or Deep Research) before sending a prompt.
        Enhanced with retry logic and validation.

        :param tool_name: Either 'canvas' or 'deep_research'
        """
        logger.info(f"Selecting tool: {tool_name}")

        tool_field_map = {
            "canvas": "canvas_button",
            "deep_research": "deep_research_button",
        }

        tool_field = tool_field_map.get(tool_name.lower())
        if not tool_field:
            raise ValueError(
                f"Unknown tool: {tool_name}. Use 'canvas' or 'deep_research'"
            )

        try:
            # 1. Click the Tools button to open the menu
            logger.info("Opening tools menu...")
            await self._try_selectors(
                "tools_button", action="wait", state="attached", timeout=10000
            )

            # Since we need to click the icon's parent, we find the element first
            tools_icon = await self._try_selectors("tools_button", action="get_element")
            if tools_icon:
                await tools_icon.locator("..").click(force=True)
            else:
                # Fallback to direct click if get_element failed but _try_selectors wait passed
                # (though this branch is unlikely given _try_selectors logic)
                await self._try_selectors("tools_button", action="click", force=True)
                
            await self.page.wait_for_timeout(1500)

            # 2. Wait for and click the specific tool
            logger.info(f"Clicking {tool_name} button...")
            await self._try_selectors(
                tool_field, action="wait", state="attached", timeout=10000
            )

            # Click the parent button of the tool icon
            tool_icon = await self._try_selectors(tool_field, action="get_element")
            if tool_icon:
                await tool_icon.locator("..").click(force=True)
            else:
                await self._try_selectors(tool_field, action="click", force=True)
                
            await self.page.wait_for_timeout(1500)

            # 3. Validate tool selection
            success, details = await self.validator.validate_tool_selected(
                tool_name, timeout=5000
            )
            if success:
                logger.info(f"✓ Tool '{tool_name}' selected and validated")
            else:
                logger.info(f"⚠ Tool selection validation not available: {details}")

        except Exception as e:
            logger.error(f"Error selecting tool '{tool_name}': {e}")
            await self.screenshot_manager.capture_error(
                self.page, f"select_tool_{tool_name}", e
            )
            raise

    @retry_async(
        max_attempts=3,
        initial_delay=5.0,
        max_delay=60.0,
        exceptions=(PlaywrightTimeoutError,),
    )
    async def wait_for_deep_research_plan(self, timeout: int = 90000):
        """
        Waits for the Deep Research plan to be generated and displayed.
        Enhanced with retry logic and validation.

        :param timeout: Timeout in milliseconds
        """
        logger.info("Waiting for Deep Research plan to be generated...")

        try:
            # Try all selectors for the plan ready indicator
            await self._try_selectors(
                "deep_research_plan_ready", action="wait", timeout=timeout
            )

            # Validate the plan is ready
            success, details = await self.validator.validate_deep_research_plan_ready(
                timeout=10000
            )
            if success:
                logger.info("✓ Deep Research plan is ready and validated")
            else:
                logger.warning(f"⚠ Deep Research plan validation unclear: {details}")

        except Exception as e:
            logger.error(f"Error waiting for Deep Research plan: {e}")
            await self.screenshot_manager.capture_error(
                self.page, "wait_for_deep_research_plan", e
            )
            raise

    @retry_async(
        max_attempts=3,
        initial_delay=2.0,
        exceptions=(PlaywrightTimeoutError, Exception),
    )
    async def confirm_deep_research_plan(self):
        """
        Clicks the 'Confirm' button to proceed with the Deep Research plan.
        Enhanced with retry logic and validation.
        """
        logger.info("Confirming Deep Research plan...")

        try:
            await self._try_selectors(
                "deep_research_confirm_button", action="click", force=True
            )
            await self.page.wait_for_timeout(2000)

            # Validate confirmation
            success, details = await self.validator.validate_deep_research_confirmed(
                timeout=5000
            )
            if success:
                logger.info("✓ Deep Research plan confirmed and validated")
            else:
                logger.info(
                    f"⚠ Deep Research confirmation validation unclear: {details}"
                )

        except Exception as e:
            logger.error(f"Error confirming Deep Research plan: {e}")
            await self.screenshot_manager.capture_error(
                self.page, "confirm_deep_research_plan", e
            )
            raise

    @retry_async(
        max_attempts=5,
        initial_delay=2.0,
        backoff_multiplier=1.5,
        exceptions=(PlaywrightTimeoutError, Exception),
    )
    async def ensure_reasoning_mode(self):
        """
        Ensures that the 'Reasoning' (Razonamiento) model is selected.
        Enhanced with retry logic and validation.
        """
        logger.info("Verifying Reasoning mode...")

        try:
            # Wait for mode selector to be available
            await self._try_selectors(
                "mode_selector", action="wait", state="attached", timeout=10000
            )

            # Check current mode
            mode_selector = gemini_selectors.get_primary("mode_selector")
            mode_element = await self.page.query_selector(mode_selector)

            if mode_element:
                current_mode = await mode_element.inner_text()

                if "Razonamiento" in current_mode:
                    logger.info("✓ Already in Reasoning mode")
                    return

                logger.info(
                    f"Current mode is '{current_mode}', switching to Reasoning..."
                )

                # Obtener la configuración del selector de modo
                mode_config = gemini_selectors.mode_selector
                dropdown_icon = (
                    mode_config.dropdown_icon
                    if hasattr(mode_config, "dropdown_icon")
                    and mode_config.dropdown_icon
                    else "mat-icon[data-mat-icon-name='keyboard_arrow_down']"
                )

                # Click the dropdown icon to open menu
                await self.page.click(dropdown_icon, force=True)
                await self.page.wait_for_timeout(1500)

                # Seleccionar "Razonamiento" del menú
                reasoning_option = (
                    mode_config.reasoning_option
                    if hasattr(mode_config, "reasoning_option")
                    and mode_config.reasoning_option
                    else "text=Razonamiento"
                )
                await self.page.click(reasoning_option, force=True)
                await self.page.wait_for_timeout(2000)

                # Validate mode change
                success, details = await self.validator.validate_mode_changed(
                    "Razonamiento", timeout=5000
                )
                if success:
                    logger.info("✓ Switched to Reasoning mode and validated")
                else:
                    logger.warning(f"⚠ Mode change validation unclear: {details}")
            else:
                logger.warning("Mode selector element not found")

        except Exception as e:
            logger.error(f"Error ensuring Reasoning mode: {e}")
            await self.screenshot_manager.capture_error(
                self.page, "ensure_reasoning_mode", e
            )
            raise
