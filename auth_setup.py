import asyncio
import logging
from playwright.async_api import async_playwright

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

async def main():
    """
    This script launches a browser in headed mode, allowing the user to manually
    log in to the Gemini website. After successful login, it saves the
    authentication state (cookies, local storage) to 'auth_state.json'.
    This state can then be used by the main agent to run in a headless browser
    without needing to log in again.
    """
    async with async_playwright() as p:
        # Launch with arguments to try and bypass automation detection
        browser = await p.chromium.launch(
            headless=False,
            channel="chrome", # Try to use system Chrome if available
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
                "--disable-infobars",
            ],
            ignore_default_args=["--enable-automation"]
        )
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        page = await context.new_page()
        
        # Stealth scripts to hide webdriver property
        await page.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', {
                get: () => undefined
            });
        """)

        logging.info("Please log in to the Gemini website manually.")
        logging.info("Navigating to Gemini...")
        await page.goto("https://gemini.google.com/")

        logging.info("\nWaiting for you to complete the login process...")
        logging.info("Once you are logged in and on the main chat page, this script will save the authentication state.")
        
        # A simple way to wait for the user to be done.
        # We'll just wait until the user closes the browser window.
        await page.wait_for_event("close")

        logging.info("Saving authentication state to 'auth_state.json'...")
        await context.storage_state(path="auth_state.json")
        logging.info("Authentication state saved successfully.")

        await browser.close()

if __name__ == "__main__":
    asyncio.run(main())
