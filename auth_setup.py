import asyncio
import logging
import os
import time
from pathlib import Path
from playwright.async_api import async_playwright
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

USER_DATA_DIR = Path("profiles/default")

async def login_if_needed(page, email, password):
    """
    Attempts to log in to Google if the login page is detected.
    """
    try:
        # Check if we are on a login page or if there is a "Sign in" button
        if "accounts.google.com" in page.url or await page.query_selector('a[href*="accounts.google.com"]'):
            logging.info("Login required. Attempting to auto-login...")
            
            if "accounts.google.com" not in page.url:
                 # Click sign in if we are on the landing page but not yet on the auth form
                 await page.click('a[href*="accounts.google.com"]')
                 await page.wait_for_load_state("networkidle")

            if email:
                logging.info(f"Entering email: {email}")
                await page.fill('input[type="email"]', email)
                await page.click('#identifierNext')
                await page.wait_for_timeout(2000) # Wait for animation
                
                if password:
                    logging.info("Entering password...")
                    try:
                        await page.wait_for_selector('input[type="password"]', state="visible", timeout=10000)
                        await page.fill('input[type="password"]', password)
                        await page.click('#passwordNext')
                    except Exception as e:
                         logging.warning(f"Could not find password field (maybe 2FA or Passkey triggered first?): {e}")

                logging.info("\nCurrent URL: " + page.url)
                logging.info("Please complete 2FA or any other verification steps manually if asked.")
            else:
                logging.warning("No credentials found in .env. Please login manually.")
        else:
            logging.info("Already logged in or on the main page.")

    except Exception as e:
        logging.error(f"Auto-login attempt failed: {e}")
        logging.info("Please finish logging in manually.")

async def main():
    """
    Launches a persistent browser context for Gemini.
    """
    # Ensure profile directory exists
    USER_DATA_DIR.mkdir(parents=True, exist_ok=True)
    
    email = os.getenv("GOOGLE_EMAIL")
    password = os.getenv("GOOGLE_PASSWORD")
    
    logging.info(f"Starting browser with profile at: {USER_DATA_DIR.absolute()}")
    
    async with async_playwright() as p:
        # Launch persistent context
        # We use a persistent context so the session is stored in the directory
        context = await p.chromium.launch_persistent_context(
            user_data_dir=USER_DATA_DIR,
            headless=False,
            channel="chrome",  # Try to use system Chrome
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
                "--disable-infobars",
            ],
            ignore_default_args=["--enable-automation"],
            viewport={'width': 1920, 'height': 1080}
        )
        
        page = context.pages[0] if context.pages else await context.new_page()
        
        # Stealth scripts
        await page.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', {
                get: () => undefined
            });
        """)

        logging.info("Navigating to Gemini...")
        try:
            await page.goto("https://gemini.google.com/", timeout=60000)
        except Exception as e:
            logging.warning(f"Navigation timeout/error: {e}")

        # Attempt auto-login
        await login_if_needed(page, email, password)

        logging.info("----------------------------------------------------------------")
        logging.info("WAITING FOR LOGIN SUCCESS...")
        logging.info("If you have 2FA, please approve it now.")
        logging.info("The script is monitoring for the chat interface to appear.")
        logging.info("----------------------------------------------------------------")

        # Wait indefinitely for the main chat element to verify login success
        try:
            await page.wait_for_selector('rich-textarea', state="visible", timeout=0)
            logging.info("\n✅ LOGIN SUCCESSFUL! The chat interface is visible.")
            
            # Export session to JSON for Docker compatibility
            # (Windows User Data Dir is not compatible with Linux)
            logging.info("Exporting session to 'auth_state.json' for Docker...")
            await context.storage_state(path="auth_state.json")
            logging.info("Session exported successfully.")
            
        except Exception as e:
            # Should not happen with timeout=0 unless browser is closed
            logging.warning(f"Browser closed or error before login confirmed: {e}")

        logging.info("----------------------------------------------------------------")
        logging.info("YOU MAY NOW CLOSE THE BROWSER WINDOW TO EXIT.")
        logging.info("----------------------------------------------------------------")
        
        # Wait for the user to close the page/browser
        try:
             # Loop until the page is closed
            while context.pages:
                await asyncio.sleep(1)
        except Exception:
            pass

        logging.info("Browser closed. Profile updated.")
        await context.close()

if __name__ == "__main__":
    asyncio.run(main())
