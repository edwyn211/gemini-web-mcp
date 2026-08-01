import asyncio
import logging
import os
import json
from pathlib import Path
from playwright.async_api import async_playwright

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Paths
BASE_DIR = Path(__file__).resolve().parent.parent
AUTH_STATE_FILE = BASE_DIR / "auth_state.json"
USER_DATA_DIR = BASE_DIR / "profiles/default"
SCREENSHOTS_DIR = BASE_DIR / "debug_output" # Use local dir to avoid permission issues
CONFIG_FILE = BASE_DIR / "config/selectors.json"

async def main():
    logging.info("Starting verification script...")
    
    # Load selectors
    with open(CONFIG_FILE, 'r') as f:
        selectors_config = json.load(f)
    
    tools_button_selectors = selectors_config['tools_button']
    deep_research_selectors = selectors_config['deep_research_button']
    
    logging.info(f"Loaded selectors from {CONFIG_FILE}")

    async with async_playwright() as p:
        # Launch persistent context to reuse auth
        context = await p.chromium.launch_persistent_context(
            user_data_dir=USER_DATA_DIR,
            headless=True, # Run headless
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
            # await page.wait_for_load_state("networkidle") # Flaky

            
            # Check if logged in (look for textarea)
            try:
                await page.wait_for_selector("rich-textarea", timeout=10000)
                logging.info("✓ Logged in and chat interface visible.")
            except:
                logging.error("✗ Not logged in or chat interface not found. Cannot proceed.")
                await page.screenshot(path=str(SCREENSHOTS_DIR / "verify_login_fail.png"))
                return

            await page.wait_for_timeout(3000)
            await page.screenshot(path=str(SCREENSHOTS_DIR / "verify_step_1_loaded.png"))

            # 1. Try to find and click Tools button
            logging.info("Attempting to find Tools button...")
            tools_clicked = False
            
            # Helper to try list of selectors
            async def try_click(selectors_data, name):
                primary = selectors_data.get('primary')
                fallbacks = selectors_data.get('fallbacks', [])
                all_selectors = [primary] + fallbacks
                
                for i, sel in enumerate(all_selectors):
                    try:
                        logging.info(f"Trying {name} selector [{i}]: {sel}")
                        if await page.is_visible(sel):
                            logging.info(f"✓ Found visible {name}: {sel}")
                            # Highlight it - safely
                            # await page.evaluate(f"document.querySelector('{sel}').style.border = '5px solid red'")
                            await page.evaluate("(sel) => { const el = document.querySelector(sel); if(el) el.style.border = '5px solid red'; }", sel)
                            await page.screenshot(path=str(SCREENSHOTS_DIR / f"verify_found_{name}_{i}.png"))
                            
                            # Click parent if icon
                            if "mat-icon" in sel:
                                await page.click(sel) # Playwright usually clicks center, works for icon
                            else:
                                await page.click(sel)
                                
                            return True
                        else:
                            logging.debug(f"Selector {sel} not visible.")
                    except Exception as e:
                        logging.warning(f"Error with selector {sel}: {e}")
                return False

            if await try_click(tools_button_selectors, "tools_button"):
                logging.info("✓ Clicked Tools button.")
                tools_clicked = True
                await page.wait_for_timeout(2000) # Wait for animation
                await page.screenshot(path=str(SCREENSHOTS_DIR / "verify_step_2_menu_open.png"))
            else:
                logging.error("✗ Failed to find/click Tools button.")
                return

            # 2. Try to find and click Deep Research
            if tools_clicked:
                logging.info("Attempting to find Deep Research button...")
                if await try_click(deep_research_selectors, "deep_research_button"):
                     logging.info("✓ Clicked Deep Research button.")
                     await page.wait_for_timeout(2000)
                     await page.screenshot(path=str(SCREENSHOTS_DIR / "verify_step_3_deep_selected.png"))
                else:
                    logging.error("✗ Failed to find/click Deep Research button.")
                    # Log page content for debugging
                    content = await page.content()
                    with open(SCREENSHOTS_DIR / "debug_page_source.html", "w") as f:
                        f.write(content)
                    logging.info("Saved page source to debug_page_source.html")
            
        except Exception as e:
            logging.error(f"An error occurred: {e}")
            try:
                await page.screenshot(path=str(SCREENSHOTS_DIR / "verify_error.png"))
            except Exception as e:
                logging.error(f"Failed to save error screenshot: {e}")
        finally:
            await context.close()

if __name__ == "__main__":
    asyncio.run(main())
