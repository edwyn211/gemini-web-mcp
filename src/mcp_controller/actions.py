import asyncio
import logging
from pathlib import Path
from typing import Dict, List

from playwright.async_api import Page
from playwright.async_api import TimeoutError as PlaywrightTimeoutError

from mcp_controller.selectors import selector_manager
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
        self.validator = StateValidator(page, selector_manager.current)
        self.screenshot_manager = ScreenshotManager()
        self.execution_lock = asyncio.Lock()

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
        selectors = selector_manager.current.get_all_selectors(selector_field)
        last_error = None

        for i, selector in enumerate(selectors):
            try:
                logger.debug(f"Trying selector {i + 1}/{len(selectors)}: {selector}")

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
                logger.debug(f"Selector {i + 1} failed: {e}")
                continue

        # All selectors failed
        error_msg = (
            f"All selectors failed for {selector_field}. Last error: {last_error}"
        )

        # Check for specific "Session Ended" overlay which often intercepts clicks
        try:
            # Common selector for the session ended dialog title
            session_ended = await self.page.query_selector("h1.mat-mdc-dialog-title")
            if session_ended:
                text = await session_ended.inner_text()
                if (
                    "cerrado tu sesión" in text
                    or "signed out" in text
                    or "session expired" in text
                ):
                    error_msg = "CRITICAL: Session expired (Se ha cerrado tu sesión). Please refresh auth_state.json"
                    logger.critical(error_msg)
        except Exception:
            pass

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
        current_url = self.page.url
        logger.info(f"🧠 CHAT MGMT: 👤 SENDING PROMPT in {current_url}: '{text[:100]}...'")

        try:
            # Wait for the textarea to be available
            await self._try_selectors("prompt_textarea", action="wait", timeout=60000)
            logger.info("Textarea found, typing prompt...")

            # Click on the textarea first to focus it
            await self._try_selectors("prompt_textarea", action="click")
            await self.page.wait_for_timeout(2000)

            # Type the text - OPTIMIZED: Use evaluate for instant insertion to avoid timeouts with large prompts
            textarea_selector = selector_manager.current.get_primary("prompt_textarea")

            # Use locator.evaluate to handle the DOM element directly, avoiding selector parsing issues in JS
            # This simulates a "paste" operation by setting innerText and triggering multiple events
            locator = self.page.locator(textarea_selector)
            await locator.evaluate(
                """(el, text) => { 
                    el.innerText = text; 
                    el.dispatchEvent(new Event('input', { bubbles: true }));
                    el.dispatchEvent(new Event('change', { bubbles: true }));
                    el.dispatchEvent(new KeyboardEvent('keydown', { key: ' ', bubbles: true }));
                    el.dispatchEvent(new KeyboardEvent('keyup', { key: ' ', bubbles: true }));
                }""",
                text,
            )

            # waiting for valid state after "paste" and for UI to update (mic -> send)
            await self.page.wait_for_timeout(1500)
            
            # Wait specifically for the send button to become visible
            logger.info("Waiting for send button to appear...")
            try:
                send_selectors = selector_manager.current.get_all_selectors("send_button")
                primary_send = send_selectors[0]
                await self.page.wait_for_selector(primary_send, state="visible", timeout=5000)
            except Exception:
                logger.warning("Send button not visible after typing, attempting to click anyway...")

            logger.info("Clicking send button...")
            await self._try_selectors("send_button", action="click")
            await self.page.wait_for_timeout(3000)

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
            stop_selectors = selector_manager.current.get_all_selectors("stop_button")
            for selector in stop_selectors:
                if await self.page.is_visible(selector):
                    logger.info("Generation in progress: Stop button is visible")
                    return True

            # 2. Check for Mic button (only visible when idle and textarea empty)
            mic_selectors = selector_manager.current.get_all_selectors("mic_button")
            for selector in mic_selectors:
                if await self.page.is_visible(selector):
                    logger.info("Not generating: Mic button is visible")
                    return False

            # 3. Check if Send button is visible
            send_selectors = selector_manager.current.get_all_selectors("send_button")
            for selector in send_selectors:
                if await self.page.is_visible(selector):
                    logger.info("Not generating: Send button is visible")
                    return False

            # 4. If neither Stop, Send, nor Mic is visible, it might be busy or in an unusual state
            # but usually it's considered "generating" if Send/Mic are missing
            # logger.info("Neither Stop, Send, nor Mic visible - checking for progress indicators...")
            
            # Additional check for generic progress/busy indicators if available
            busy_indicators = [
                "mat-progress-bar",
                ".typing-indicator",
                "div[role='progressbar']"
            ]
            for selector in busy_indicators:
                try:
                    if await self.page.is_visible(selector, timeout=500):
                        logger.info(f"Generation in progress: Busy indicator '{selector}' visible")
                        return True
                except Exception:
                    continue

            logger.info("Neither Stop, Send, nor Mic visible - likely in progress or transitioning")
            return True
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
            canvas_selectors = selector_manager.current.get_all_selectors("canvas_content")

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
            research_selectors = selector_manager.current.get_all_selectors(
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
        self, timeout: int = 240000, tool: str | None = None
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

            # Check for "Show more" buttons before grabbing text
            try:
                # Check for explicit "Show more" buttons
                show_more_selectors = selector_manager.current.get_all_selectors("show_more")
                for selector in show_more_selectors:
                    try:
                        show_more_btn = await self.page.query_selector(selector)
                        if show_more_btn and await show_more_btn.is_visible():
                            logger.info("Found 'Show more' button, clicking...")
                            await show_more_btn.click()
                            await self.page.wait_for_timeout(2000)  # Wait for expansion
                    except Exception:
                        pass
            except Exception as e:
                logger.debug(f"Error checking show more buttons: {e}")

            # Probar selectores de respuesta normales
            response_selectors = selector_manager.current.get_all_selectors("last_response")

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
                    # Try to get inner_text
                    try:
                        text = await element.inner_text()
                    except Exception:
                        continue

                    if not text:
                        continue

                    # Filter out known status messages if necessary
                    if "Has parado esta respuesta" in text and len(text) < 50:
                        logger.warning("Skipping 'Stopped response' status message")
                        continue

                    # If response is very short, maybe it's not the real one, check previous
                    if len(text.strip()) < 5:
                        continue

                    valid_response = text

                    # Clean up UI artifacts
                    if "Ver razonamiento" in valid_response:
                        valid_response = valid_response.replace(
                            "Ver razonamiento", ""
                        ).strip()
                    if "Mostrar borradores" in valid_response:
                        valid_response = valid_response.replace(
                            "Mostrar borradores", ""
                        ).strip()

                    logger.info(f"🤖 GEMINI RESPONSE:\n{valid_response}")
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
        logger.info("🧠 CHAT MGMT: Starting a new chat...")

        try:
            await self._try_selectors("new_chat_button", action="click", force=True)

            # Validate that new chat started
            success, details = await self.validator.validate_chat_started(timeout=5000)
            if success:
                logger.info(f"🧠 CHAT MGMT: ✓ New chat started and validated. URL: {self.page.url}")
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
            # Direct click works for both icons and buttons
            await self._try_selectors("tools_button", action="click", force=True)

            await self.page.wait_for_timeout(1500)

            # 2. Wait for and click the specific tool
            logger.info(f"Clicking {tool_name} button...")
            
            # Direct click works for both icons and buttons
            await self._try_selectors(tool_field, action="click", force=True)

            await self.page.wait_for_timeout(1500)

            # 3. Validate tool selection
            success, details = await self.validator.validate_tool_selected(
                tool_name, timeout=5000
            )
            if success:
                logger.info(f"✓ Tool '{tool_name}' selected and validated")
            else:
                error_msg = f"Tool selection validation failed for '{tool_name}': {details}"
                logger.error(f"✗ {error_msg}")
                raise Exception(error_msg)

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
            mode_selector = selector_manager.current.get_primary("mode_selector")
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
                mode_config = selector_manager.current.mode_selector
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

    async def take_screenshot(self, name: str = "manual_capture") -> str:
        """
        Captures a screenshot of the current page.
        
        :param name: Base name for the screenshot file
        :return: Absolute path to the saved screenshot
        """
        logger.info(f"Capturing screenshot: {name}")
        path = await self.screenshot_manager.capture_success(self.page, name)
        if path:
            return str(path.resolve())
        raise Exception("Failed to capture screenshot")

    async def check_session_status(self) -> dict:
        """
        Checks if the current session is valid and authenticated.
        
        :return: Dictionary with status information
        """
        logger.info("Checking session status...")
        
        status = {
            "authenticated": False,
            "page_loaded": False,
            "url": self.page.url,
            "details": ""
        }
        
        try:
            # Check for specific elements similar to diagnostic script
            # 1. Check for prompt textarea (definitive test for "can I chat?")
            textarea = await self.page.query_selector("div[contenteditable='true']") or \
                       await self.page.query_selector("rich-textarea")
            
            if textarea and await textarea.is_visible():
                status["authenticated"] = True
                status["page_loaded"] = True
                status["details"] = "Session active: Prompt input area visible."
            else:
                 # Check for "Se ha cerrado tu sesión" or similar
                session_ended = await self.page.query_selector("h1.mat-mdc-dialog-title")
                if session_ended:
                    text = await session_ended.inner_text()
                    status["details"] = f"Session ended dialog detected: {text}"
                else:
                    status["details"] = "Textarea not visible. "

            # 2. Check for User Avatar (Account Verification)
            if status["authenticated"]:
                account_btn = await self.page.query_selector("div[aria-label*='cuenta' i]") or \
                              await self.page.query_selector("div[aria-label*='Google Account' i]") or \
                              await self.page.query_selector("img[src*='googleusercontent.com']") or \
                              await self.page.query_selector("a[href*='accounts.google.com']")
                
                if account_btn:
                     status["details"] += " Account verified (Avatar found)."
                else:
                     status["details"] += " WARNING: Account avatar not found (but chat is visible)."

            # 3. Check for specific URL pattern
            if "/app" in self.page.url:
                 # Standard Gemini App URL
                 pass
            elif "accounts.google.com" in self.page.url:
                 status["authenticated"] = False
                 status["page_loaded"] = False
                 status["details"] = "Redirected to login page."

            return status
        except Exception as e:
            logger.error(f"Error checking session status: {e}")
            status["details"] = f"Error: {str(e)}"
            return status

    async def upload_file(self, file_path: str):
        """
        Uploads a file to the Gemini prompt.
        
        :param file_path: Path to the file to upload
        """
        logger.info(f"Uploading file: {file_path}")
        
        if not Path(file_path).exists():
            raise FileNotFoundError(f"File not found: {file_path}")
            
        try:
            # Try to find the file input
            # Playwright's set_input_files works on hidden inputs as well
            file_input_selectors = [
                "input[type='file']",
                "input[accept*='image']",
                "input[accept*='pdf']"
            ]
            
            success = False
            for selector in file_input_selectors:
                try:
                    # Check if it exists
                    await self.page.wait_for_selector(selector, timeout=5000)
                    await self.page.set_input_files(selector, file_path)
                    success = True
                    logger.info(f"✓ File uploaded using selector: {selector}")
                    break
                except Exception:
                    continue
            
            if not success:
                # Try clicking the plus/attach button first if it exists
                attach_selectors = [
                    "button[aria-label*='Attach' i]",
                    "button[aria-label*='Adjuntar' i]",
                    "mat-icon[data-mat-icon-name='add_circle']",
                    "mat-icon[data-mat-icon-name='add']"
                ]
                
                for selector in attach_selectors:
                    try:
                        btn = await self.page.query_selector(selector)
                        if btn and await btn.is_visible():
                            await btn.click()
                            await self.page.wait_for_timeout(1000)
                            # Try input again after clicking
                            await self.page.set_input_files("input[type='file']", file_path)
                            success = True
                            logger.info(f"✓ File uploaded after clicking attach button: {selector}")
                            break
                    except Exception:
                        continue
            
            if not success:
                raise Exception("Could not find file input for uploading.")
                
            # Wait for upload to process
            await self.page.wait_for_timeout(3000)
            
        except Exception as e:
            logger.error(f"Error uploading file: {e}")
            await self.screenshot_manager.capture_error(self.page, "upload_file", e)
            raise

    async def list_chats(self) -> List[Dict[str, str]]:
        """
        Lists recent chats from the sidebar.
        
        :return: List of dictionaries with 'title' and 'url' (if available)
        """
        logger.info("Listing recent chats...")
        
        chats = []
        history_selectors = [
            "a[href*='/app/']",  # Gemini chat links usually have /app/ in URL
            ".history-item",
            "div[role='link']",
            "li.conversation-list-item"
        ]
        
        for selector in history_selectors:
            try:
                elements = await self.page.query_selector_all(selector)
                for el in elements:
                    text = await el.inner_text()
                    href = await el.get_attribute("href")
                    
                    if text and len(text.strip()) > 1:
                        # Clean up text (often has icons/newlines)
                        clean_title = text.split('\n')[0].strip()
                        if clean_title and clean_title not in [c["title"] for c in chats]:
                            chats.append({
                                "title": clean_title,
                                "url": href if href else ""
                            })
                
                if chats:
                    break
            except Exception:
                continue
                
        return chats[:15]  # Limit to 15 recent chats

    async def switch_chat(self, chat_title: str) -> bool:
        """
        Switches to a chat with the given title.
        
        :param chat_title: The title of the chat to switch to
        :return: True if successful
        """
        logger.info(f"🧠 CHAT MGMT: Switching to chat: {chat_title}")
        
        # Try finding the chat item in the sidebar
        try:
            # Use text selector for the chat title
            chat_selector = f"text='{chat_title}'"
            chat_item = await self.page.query_selector(chat_selector)
            
            if chat_item:
                await chat_item.click()
                await self.page.wait_for_load_state("domcontentloaded")
                await self.page.wait_for_timeout(2000)
                logger.info(f"🧠 CHAT MGMT: ✓ Switched to chat: {chat_title}. URL: {self.page.url}")
                return True
            
            # Try partial match if exact match fails
            chat_selector = f"xpath=//div[contains(text(), '{chat_title}')] | //a[contains(text(), '{chat_title}')]"
            chat_item = await self.page.query_selector(chat_selector)
            if chat_item:
                await chat_item.click()
                await self.page.wait_for_load_state("domcontentloaded")
                await self.page.wait_for_timeout(2000)
                logger.info(f"🧠 CHAT MGMT: ✓ Switched to chat (partial match): {chat_title}. URL: {self.page.url}")
                return True
                
            logger.warning(f"Chat '{chat_title}' not found in the list.")
            return False
            
        except Exception as e:
            logger.error(f"Error switching chat: {e}")
            await self.screenshot_manager.capture_error(self.page, "switch_chat", e)
            return False
