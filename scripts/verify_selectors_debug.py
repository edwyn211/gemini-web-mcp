import asyncio
import logging
import json
import os
from pathlib import Path
from playwright.async_api import async_playwright

# Configuración de logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

BASE_DIR = Path(__file__).resolve().parent.parent
USER_DATA_DIR = BASE_DIR / "profiles/default"
DEBUG_DIR = BASE_DIR / "debug_output/debug_selectors"
CONFIG_FILE = BASE_DIR / "config/selectors.json"

async def debug_pill_presence(page, tool_name, validator_selector):
    logging.info(f"--- Debugging {tool_name} Pill ---")
    await page.wait_for_timeout(3000)
    
    # Intentar encontrar cualquier botón o elemento con el nombre de la herramienta dentro del prompt
    elements = await page.query_selector_all("rich-textarea button, rich-textarea .pill, .pill-container button")
    logging.info(f"Found {len(elements)} possible pill elements in textarea area.")
    
    for i, el in enumerate(elements):
        text = await el.inner_text()
        html = await el.evaluate("el => el.outerHTML")
        logging.info(f"Element [{i}] text: '{text}' | HTML: {html[:100]}...")
        if tool_name.lower() in text.lower():
            logging.info(f"MATCH FOUND: Element [{i}] matches {tool_name}")

    is_visible = await page.is_visible(validator_selector)
    logging.info(f"Validator '{validator_selector}' is_visible: {is_visible}")
    
    # Capturar HTML del prompt area
    try:
        prompt_html = await page.evaluate("() => document.querySelector('rich-textarea').parentElement.innerHTML")
        with open(DEBUG_DIR / f"prompt_area_{tool_name}.html", "w") as f:
            f.write(prompt_html)
    except Exception as e:
        logging.error(f"Could not dump prompt area HTML: {e}")

    await page.screenshot(path=str(DEBUG_DIR / f"debug_{tool_name}_pill.png"))

async def main():
    DEBUG_DIR.mkdir(parents=True, exist_ok=True)
    
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
            await page.wait_for_timeout(5000)

            # Helper para cliquear
            async def find_and_click(btn_config, name):
                primary = btn_config.get('primary')
                fallbacks = btn_config.get('fallbacks', [])
                all_sels = [primary] + fallbacks
                for sel in all_sels:
                    if await page.is_visible(sel):
                        logging.info(f"✓ Found {name}: {sel}")
                        await page.click(sel)
                        return True
                return False

            # TEST CANVAS
            logging.info("\n=== DEBUGGING CANVAS SELECTION ===")
            # New Chat
            await find_and_click(selectors['new_chat_button'], "new_chat_button")
            await page.wait_for_timeout(2000)
            
            if await find_and_click(selectors['tools_button'], "tools_button"):
                await page.wait_for_timeout(1000)
                if await find_and_click(selectors['canvas_button'], "canvas_button"):
                    await debug_pill_presence(page, "Canvas", selectors['canvas_button']['validator'])

            # TEST DEEP RESEARCH
            logging.info("\n=== DEBUGGING DEEP RESEARCH SELECTION ===")
            # New Chat
            await find_and_click(selectors['new_chat_button'], "new_chat_button")
            await page.wait_for_timeout(2000)
            
            if await find_and_click(selectors['tools_button'], "tools_button"):
                await page.wait_for_timeout(1000)
                if await find_and_click(selectors['deep_research_button'], "deep_research_button"):
                    await debug_pill_presence(page, "Deep Research", selectors['deep_research_button']['validator'])

        except Exception as e:
            logging.error(f"Error: {e}")
            await page.screenshot(path=str(DEBUG_DIR / "debug_error.png"))
        finally:
            await context.close()

if __name__ == "__main__":
    asyncio.run(main())
