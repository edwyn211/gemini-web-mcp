import asyncio
import logging
import os
import json
from pathlib import Path
from playwright.async_api import async_playwright

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Paths
BASE_DIR = Path("/home/user/Documentos/Github/gemini-web-mcp")
AUTH_STATE_FILE = BASE_DIR / "auth_state.json"
USER_DATA_DIR = BASE_DIR / "profiles/default"
SCREENSHOTS_DIR = BASE_DIR / "debug_output"
CONFIG_FILE = BASE_DIR / "config/selectors.json"

async def main():
    logging.info("Starting ALL TOOLS verification script...")
    
    # Ensure debug dir exists
    SCREENSHOTS_DIR.mkdir(parents=True, exist_ok=True)
    
    # Load selectors
    with open(CONFIG_FILE, 'r') as f:
        selectors_config = json.load(f)
    
    tools_button_selectors = selectors_config['tools_button']
    canvas_button_selectors = selectors_config['canvas_button']
    
    logging.info(f"Loaded selectors from {CONFIG_FILE}")

    async with async_playwright() as p:
        context = await p.chromium.launch_persistent_context(
            user_data_dir=USER_DATA_DIR,
            headless=True,
            channel="chrome",
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
                "--disable-infobars",
                "--disable-dev-shm-usage",
            ],
            viewport={'width': 1920, 'height': 1080}
        )
        
        page = context.pages[0] if context.pages else await context.new_page()
        
        try:
            logging.info("Navigating to Gemini...")
            await page.goto("https://gemini.google.com/", timeout=60000)
            
            # Check login
            try:
                await page.wait_for_selector("rich-textarea", timeout=10000)
                logging.info("✓ Logged in and chat interface visible.")
            except:
                logging.error("✗ Not logged in.")
                try:
                    await page.screenshot(path=str(SCREENSHOTS_DIR / "verify_all_login_fail.png"))
                except:
                    pass
                return

            await page.wait_for_timeout(3000)

            # Helper to click
            async def try_click(selectors_data, name):
                primary = selectors_data.get('primary')
                fallbacks = selectors_data.get('fallbacks', [])
                all_selectors = [primary] + fallbacks
                
                for i, sel in enumerate(all_selectors):
                    try:
                        logging.info(f"Trying {name} selector [{i}]: {sel}")
                        if await page.is_visible(sel):
                            logging.info(f"✓ Found visible {name}: {sel}")
                            # Highlight
                            await page.evaluate("(sel) => { const el = document.querySelector(sel); if(el) el.style.border = '5px solid blue'; }", sel)
                            await page.screenshot(path=str(SCREENSHOTS_DIR / f"verify_found_{name}_{i}.png"))
                            
                            await page.click(sel)
                            return True
                    except Exception as e:
                        logging.warning(f"Error with selector {sel}: {e}")
                return False

            # --- TEST 1: CANVAS TOOL ---
            logging.info("\n--- TEST 1: CHECKING CANVAS TOOL ---")
            
            # Open Tools Menu
            if await try_click(tools_button_selectors, "tools_button"):
                logging.info("✓ Clicked Tools button.")
                await page.wait_for_timeout(2000)
                
                # Click Canvas
                if await try_click(canvas_button_selectors, "canvas_button"):
                     logging.info("✓ Clicked Canvas button.")
                     await page.wait_for_timeout(2000)
                     await page.screenshot(path=str(SCREENSHOTS_DIR / "verify_test_1_canvas_selected.png"))
                else:
                    logging.error("✗ Failed to find/click Canvas button.")
            else:
                logging.error("✗ Failed to find/click Tools button.")

            # --- TEST 2: NO TOOL (DEFAULT) ---
            logging.info("\n--- TEST 2: CHECKING NO TOOL (DEFAULT) ---")
            
            # Refresh page to reset state
            await page.reload()
            await page.wait_for_timeout(3000)
            
            # Verify we are just in the chat input
            # In "No Tool" mode, we just expect the textarea to be available
            if await page.is_visible("rich-textarea"):
                 logging.info("✓ Standard chat interface visible (No Tool).")
                 await page.screenshot(path=str(SCREENSHOTS_DIR / "verify_test_2_no_tool.png"))
            else:
                 logging.error("✗ Standard chat interface NOT visible.")

            logging.info("\n✓ VERIFICATION COMPLETE")
            
        except Exception as e:
            logging.error(f"An error occurred: {e}")
            try:
                await page.screenshot(path=str(SCREENSHOTS_DIR / "verify_all_error.png"))
            except:
                pass
        finally:
            await context.close()

if __name__ == "__main__":
    asyncio.run(main())
