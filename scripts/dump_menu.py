import asyncio
import logging
from pathlib import Path
from playwright.async_api import async_playwright

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

BASE_DIR = Path(__file__).resolve().parent.parent
USER_DATA_DIR = BASE_DIR / "profiles/default"
DEBUG_DIR = BASE_DIR / "debug_output"

async def main():
    try:
        async with async_playwright() as p:
            context = await p.chromium.launch_persistent_context(
                user_data_dir=USER_DATA_DIR,
                headless=True,
                args=["--no-sandbox", "--disable-dev-shm-usage"],
                viewport={'width': 1920, 'height': 1080}
            )
            page = context.pages[0] if context.pages else await context.new_page()
            
            logging.info("Navigating...")
            await page.goto("https://gemini.google.com/", timeout=60000)
            await page.wait_for_timeout(2000)

            # Open tools menu
            logging.info("Opening tools menu...")
            # Use the known good selector from previous step
            # selector: [aria-label*='Abrir menú de subida' i] OR button:has(mat-icon[data-mat-icon-name='add_2'])
            # Let's try to query generic add button first
            
            tools_btn = await page.query_selector("button:has(mat-icon[data-mat-icon-name='add_2'])")
            if not tools_btn:
                 tools_btn = await page.query_selector("[aria-label*='Abrir menú de subida' i]")
            
            if tools_btn:
                await tools_btn.click()
                await page.wait_for_timeout(2000)
                
                canvas_btn = await page.query_selector("button.toolbox-drawer-item-list-button mat-icon[data-mat-icon-name='note_stack_add']")
                if canvas_btn:
                    await canvas_btn.click()
                    await page.wait_for_timeout(3000)
                    logging.info("Canvas selected.")
                    
                    # Find pills
                    pills = await page.evaluate("""() => {
                        return Array.from(document.querySelectorAll('rich-textarea button, rich-textarea [role="button"]')).map(el => ({
                            text: el.innerText.trim(),
                            classes: el.className,
                            aria: el.getAttribute('aria-label')
                        }));
                    }""")
                    logging.info(f"Pills found: {pills}")
                
                content = await page.content()
                output_path = DEBUG_DIR / "canvas_selected_source.html"
                with open(output_path, "w", encoding="utf-8") as f:
                    f.write(content)
                logging.info(f"Saved HTML to {output_path}")
            else:
                logging.error("Could not find tools button to open menu.")
            
            await context.close()
    except Exception as e:
        logging.error(f"Error: {e}")

if __name__ == "__main__":
    asyncio.run(main())
