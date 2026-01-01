
import asyncio
from playwright.async_api import async_playwright
import logging
from pathlib import Path

# Configure logging
logging.basicConfig(level=logging.INFO)

async def check_auth():
    async with async_playwright() as p:
        logging.info("Launching browser...")
        browser = await p.chromium.launch(
            headless=True,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
            ]
        )
        
        context_args = {
            "viewport": {"width": 1920, "height": 1080},
            "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        }
        
        auth_path = Path("auth_state.json")
        if auth_path.exists():
            logging.info(f"Loading auth state from {auth_path}")
            context_args["storage_state"] = auth_path
        else:
            logging.warning("No auth_state.json found!")

        context = await browser.new_context(**context_args)
        page = await context.new_page()
        
        # Add stealth
        await page.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', {
                get: () => undefined
            });
        """)

        logging.info("Navigating to Gemini...")
        await page.goto("https://gemini.google.com/")
        
        try:
            await page.wait_for_load_state("networkidle", timeout=10000)
        except Exception:
            pass

        logging.info(f"Current URL: {page.url}")
        
        # Take screenshot
        screenshot_path = Path("debug_auth_screenshot.png").resolve()
        await page.screenshot(path=str(screenshot_path))
        logging.info(f"Screenshot saved to {screenshot_path}")
        
        # Check for specific elements
        try:
            # Check for avatar/account button
            account_btn = await page.query_selector("div[aria-label*='cuenta' i]") or \
                          await page.query_selector("div[aria-label*='Google Account' i]") or \
                          await page.query_selector("img[src*='googleusercontent.com']") or \
                          await page.query_selector("a[href*='accounts.google.com']")
            
            if account_btn:
                logging.info(f"✅ Found potential account element: {await account_btn.get_attribute('aria-label') or 'Image'}")
            else:
                logging.warning("⚠️ No account element found.")
                
            # Check for 'Sign in' button specifically
            sign_in_link = await page.query_selector("a[aria-label*='Sign in' i]") or \
                           await page.query_selector("a[href*='accounts.google.com/ServiceLogin']")
            
            if sign_in_link:
                 if await sign_in_link.is_visible():
                     logging.warning("⚠️ Visible 'Sign in' link found!")
                 else:
                     logging.info("ℹ️ 'Sign in' link present but hidden (common in some apps).")
            
        except Exception as e:
            logging.error(f"Error checking elements: {e}")

        content = await page.content()
        if "Inicia sesión" in content:
             logging.warning("⚠️ 'Inicia sesión' text detected.")

        # Check for textarea - definitive test for "can I chat?"
        textarea = await page.query_selector("div[contenteditable='true']") or \
                   await page.query_selector("rich-textarea")
        if textarea and await textarea.is_visible():
            logging.info("✅ Prompt input area found and visible. The bot SHOULD be able to work.")
        else:
            logging.error("❌ Prompt input area NOT found or not visible.")

        await browser.close()

if __name__ == "__main__":
    asyncio.run(check_auth())
