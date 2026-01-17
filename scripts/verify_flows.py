import asyncio
import logging
import json
import os
from pathlib import Path
from playwright.async_api import async_playwright

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

BASE_DIR = Path("/home/user/Documentos/Github/gemini-web-mcp")
USER_DATA_DIR = BASE_DIR / "profiles/default"
SCREENSHOTS_DIR = BASE_DIR / "debug_output"
CONFIG_FILE = BASE_DIR / "config/selectors.json"

async def main():
    logging.info("Starting FLOW VERIFICATION script...")
    SCREENSHOTS_DIR.mkdir(parents=True, exist_ok=True)
    
    with open(CONFIG_FILE, 'r') as f:
        selectors = json.load(f)
        
    async with async_playwright() as p:
        context = await p.chromium.launch_persistent_context(
            user_data_dir=USER_DATA_DIR,
            headless=True,
            channel="chrome",
            args=["--no-sandbox", "--disable-blink-features=AutomationControlled"],
            viewport={'width': 1920, 'height': 1080}
        )
        page = context.pages[0] if context.pages else await context.new_page()
        
        try:
            logging.info("Navigating to Gemini...")
            await page.goto("https://gemini.google.com/", timeout=60000)
            
            # Check Login using prompt_textarea selectors
            await page.wait_for_timeout(5000)
            is_logged_in = False
            for _ in range(3): # Retry 3 times
                for sel in [selectors['prompt_textarea'].get('primary')] + selectors['prompt_textarea'].get('fallbacks', []):
                    if await page.is_visible(sel):
                        is_logged_in = True
                        logging.info(f"✓ Logged in (found chat box via {sel}).")
                        break
                if is_logged_in: break
                logging.info("  Waiting more for chat box...")
                await page.wait_for_timeout(3000)
            
            if not is_logged_in:
                logging.error("✗ Not logged in or chat interface NOT fully loaded.")
                await page.screenshot(path=str(SCREENSHOTS_DIR / "flow_login_fail.png"))
                return

            # Helper for selector matching
            async def find_and_click(btn_config, name):
                primary = btn_config.get('primary')
                fallbacks = btn_config.get('fallbacks', [])
                all_sels = [primary] + fallbacks
                
                for sel in all_sels:
                    if await page.is_visible(sel):
                        logging.info(f"  ✓ Found {name}: {sel}")
                        # Skip highlight if not simple CSS
                        # await page.evaluate("(s) => { const e = document.querySelector(s); if(e) e.style.border='3px solid magenta'; }", sel)
                        logging.info(f"  Clicking {sel}...")
                        await page.click(sel)
                        return True
                logging.warning(f"  ✗ Could not find {name}")
                return False

            # Helper to start new chat
            async def start_new_chat():
                btn_config = selectors['new_chat_button']
                logging.info("Starting a new chat...")
                if await find_and_click(btn_config, "new_chat_button"):
                    await page.wait_for_timeout(2000)
                    return True
                # Fallback: go to base URL
                await page.goto("https://gemini.google.com/", timeout=60000)
                await page.wait_for_timeout(3000)
                return True

            # Helper to send prompt
            async def send_prompt(text):
                textarea_sel = selectors['prompt_textarea'].get('primary')
                logging.info(f"  Sending prompt: {text}")
                await page.fill(textarea_sel, text)
                await page.press(textarea_sel, "Enter")
                await page.wait_for_timeout(3000) # Wait for UI update
                
                # Wait for response to be complete (stop button disappears OR send button is visible again)
                # We'll use a simple wait for now to avoid complexity in this test script
                logging.info("  Waiting for response...")
                await page.wait_for_timeout(20000)
                logging.info("  Response wait complete.")

            # --- FLOW 1: DEEP RESEARCH ---
            logging.info("\n=== FLOW 1: DEEP RESEARCH ===")
            await start_new_chat()
            
            if await find_and_click(selectors['tools_button'], "tools_button"):
                await page.wait_for_timeout(1500)
                if await find_and_click(selectors['deep_research_button'], "deep_research_button"):
                    logging.info("  ✓ Clicked Deep Research")
                    await page.wait_for_timeout(3000)
                    
                    # Validate
                    validator = selectors['deep_research_button'].get("validator")
                    logging.info(f"  Validating with: {validator}")
                    if await page.is_visible(validator):
                        logging.info("  ✓ Validation PASSED")
                        await send_prompt("Investiga sobre la misión Artemis 3 de la NASA.")
                        await page.screenshot(path=str(SCREENSHOTS_DIR / "flow_1_deep_prompt.png"))
                    else:
                        logging.error("  ✗ Validation FAILED")
                else:
                    logging.error("  ✗ Deep Research button NOT found")
            
            # --- FLOW 2: CANVAS ---
            logging.info("\n=== FLOW 2: CANVAS ===")
            await start_new_chat()
            
            if await find_and_click(selectors['tools_button'], "tools_button"):
                await page.wait_for_timeout(1500)
                if await find_and_click(selectors['canvas_button'], "canvas_button"):
                    logging.info("  ✓ Clicked Canvas")
                    
                    # Wait for pill to appear (more robust than just visible check)
                    pill_sel = selectors['canvas_button'].get("validator")
                    try:
                        await page.wait_for_selector(pill_sel, timeout=10000)
                        logging.info("  ✓ Pill found (Validation PASSED)")
                        await send_prompt("Escribe un poema sobre el espacio en modo Canvas.")
                        await page.screenshot(path=str(SCREENSHOTS_DIR / "flow_2_canvas_prompt.png"))
                    except Exception:
                        logging.error("  ✗ Pill NOT found after timeout")
                        await page.screenshot(path=str(SCREENSHOTS_DIR / "flow_2_canvas_fail_pill.png"))

            # --- FLOW 3: NO TOOL (DEFAULT) ---
            logging.info("\n=== FLOW 3: NO TOOL ===")
            await start_new_chat()
            
            if await page.is_visible(selectors['prompt_textarea'].get('primary')):
                logging.info("  ✓ Chat box visible (Default mode active)")
                await send_prompt("Hola, ¿cómo estás?")
                await page.screenshot(path=str(SCREENSHOTS_DIR / "flow_3_default_prompt.png"))
            else:
                logging.error("  ✗ Chat box NOT visible")

        except Exception as e:
            logging.error(f"Error: {e}")
            await page.screenshot(path=str(SCREENSHOTS_DIR / "flow_error.png"))
        finally:
            await context.close()

import sys
if __name__ == "__main__":
    asyncio.run(main())
