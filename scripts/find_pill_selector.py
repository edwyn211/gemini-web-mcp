import asyncio
import logging
import json
import os
from pathlib import Path
from playwright.async_api import async_playwright

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

BASE_DIR = Path("/home/user/Documentos/Github/gemini-web-mcp")
USER_DATA_DIR = BASE_DIR / "profiles/default"
CONFIG_FILE = BASE_DIR / "config/selectors.json"

async def main():
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
            await page.goto("https://gemini.google.com/", timeout=60000)
            await page.wait_for_timeout(5000)

            # Activate Canvas
            logging.info("Activating Canvas...")
            await page.click(selectors['new_chat_button']['primary'])
            await page.wait_for_timeout(1000)
            await page.click(selectors['tools_button']['primary'])
            await page.wait_for_timeout(1000)
            await page.click(selectors['canvas_button']['primary'])
            await page.wait_for_timeout(3000)

            # Find the pill
            logging.info("Searching for Canvas pill...")
            # Search for any element containing 'Canvas' text
            elements = await page.query_selector_all("button:has-text('Canvas'), div:has-text('Canvas'), span:has-text('Canvas')")
            for i, el in enumerate(elements):
                visible = await el.is_visible()
                if visible:
                    selector = await el.evaluate("el => { \
                        let path = ''; \
                        let cur = el; \
                        while (cur && cur.nodeType === 1) { \
                            let name = cur.nodeName.toLowerCase(); \
                            if (cur.id) { path = '#' + cur.id + (path ? ' > ' + path : ''); break; } \
                            let sub = ''; \
                            if (cur.className) sub = '.' + cur.className.split(' ').join('.'); \
                            path = name + sub + (path ? ' > ' + path : ''); \
                            cur = cur.parentNode; \
                        } \
                        return path; \
                    }")
                    text = await el.inner_text()
                    logging.info(f"Found visible element [{i}]: Text='{text}', Selector='{selector}'")

            # Try to find specifically the one with the 'x' (close button)
            close_buttons = await page.query_selector_all("button:has(mat-icon[data-mat-icon-name='close'])")
            logging.info(f"Found {len(close_buttons)} buttons with close icon.")
            for i, btn in enumerate(close_buttons):
                parent_text = await btn.evaluate("el => el.parentElement.innerText")
                logging.info(f"Close button [{i}] parent text: '{parent_text}'")

        finally:
            await context.close()

if __name__ == "__main__":
    asyncio.run(main())
