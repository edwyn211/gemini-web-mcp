import logging
import asyncio
from typing import Dict, List, Any
from playwright.async_api import Page
from mcp_controller.selectors import selector_manager
from mcp_controller.session_manager import SessionManager

logger = logging.getLogger(__name__)

class SelectorValidator:
    """
    Validates the current selectors against a live Gemini session.
    """

    def __init__(self, session_manager: SessionManager):
        self.session_manager = session_manager

    async def validate_all(self) -> Dict[str, Any]:
        """
        Checks all critical selectors and returns a report.
        
        Returns:
            Dict containing status, broken_selectors, and details.
        """
        logger.info("Starting selector validation...")
        
        # Get a worker session (fresh or reused)
        session_actions = await self.session_manager.get_worker_session()
        page = session_actions.page
        
        report = {
            "status": "success",
            "timestamp": "",
            "broken_selectors": [],
            "working_selectors": [],
            "logs": []
        }
        
        # Ensure we are on the page
        if "gemini.google.com" not in page.url:
             await page.goto("https://gemini.google.com/")
        
        # Always wait a bit for dynamic elements
        await page.wait_for_timeout(5000)

        selectors = selector_manager.current
        
        # List of critical selectors to check
        # format: (field_name, expected_visible)
        to_check = [
            ("new_chat_button", True),
            ("prompt_textarea", True),
            ("tools_button", True),
            ("mic_button", False), # Might be visible or not depending on state
            ("send_button", False), # Usually hidden until typing
            ("mode_selector", False) # Sometimes inside menu
        ]
        
        for field, should_be_visible in to_check:
            log_msg = f"Checking {field}..."
            report["logs"].append(log_msg)
            logger.info(log_msg)
            
            try:
                # Get all fallback options
                options = selectors.get_all_selectors(field)
                found = False
                working_option = None
                
                for sel in options:
                    try:
                        # Log what we are checking
                        # logger.debug(f"  - Trying {sel}")
                        count = await page.locator(sel).count()
                        if count > 0:
                            # If strict visibility is required
                            if should_be_visible:
                                if await page.locator(sel).first.is_visible():
                                    found = True
                                    working_option = sel
                                    break
                            else:
                                # Just existing in DOM is enough for some elements that might be hidden
                                found = True
                                working_option = sel
                                break
                    except Exception:
                        continue
                
                if found:
                    report["working_selectors"].append({
                        "field": field,
                        "selector": working_option
                    })
                else:
                    report["broken_selectors"].append(field)
                    report["status"] = "failed"
                    msg = f"❌ Failed to find any working selector for {field}"
                    report["logs"].append(msg)
                    logger.error(msg)
                    
                    # Capture debug screenshot
                    try:
                        path = f"debug_validator_error_{field}.png"
                        await page.screenshot(path=path)
                        logger.info(f"Saved debug screenshot to {path}")
                    except Exception as scr_err:
                        logger.error(f"Failed to capture screenshot: {scr_err}")

            except Exception as e:
                report["logs"].append(f"Error checking {field}: {str(e)}")
        
        # Release session
        await self.session_manager.release_session(session_actions)
        
        return report
