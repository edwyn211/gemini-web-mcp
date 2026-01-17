# trunk-ignore-all(black)
# trunk-ignore-all(isort)
import asyncio
import logging
import os
import argparse
from pathlib import Path
from playwright.async_api import async_playwright
from dotenv import load_dotenv

from datetime import datetime

# Load environment variables
load_dotenv()

def get_formatted_timestamp():
    """Generates a timestamp in the format: 4_de_enero_del_2026_18:34_hrs"""
    months = {
        1: "enero", 2: "febrero", 3: "marzo", 4: "abril", 5: "mayo", 6: "junio",
        7: "julio", 8: "agosto", 9: "septiembre", 10: "octubre", 11: "noviembre", 12: "diciembre"
    }
    now = datetime.now()
    return f"{now.day}_de_{months[now.month]}_del_{now.year}_{now.strftime('%H:%M')}_hrs"

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

USER_DATA_DIR = Path("profiles/default")
AUTH_STATE_FILE = Path("auth_state.json")

# Configurable Timeouts
TIMEOUT_SELECTOR = int(os.getenv("AUTH_TIMEOUT_SELECTOR", 30000)) # Default 30s
TIMEOUT_NAVIGATION = int(os.getenv("AUTH_TIMEOUT_NAVIGATION", 60000)) # Default 60s

async def login_if_needed(page, email, password):
    """
    Attempts to log in to Google if the login page is detected.
    """
    try:
         # Check if we are on a login page or if there is a "Sign in" button
        if "accounts.google.com" in page.url or await page.query_selector('a[href*="accounts.google.com"]'):
            logging.info("Login flow detected. Checking state...")

            # Case: "Choose an account" screen
            # Many times Google remembers the account but asks you to click it
            try:
                # Look for the email in the list of accounts
                if email:
                    account_selector = f"div[data-email='{email}']"
                    if await page.query_selector(account_selector):
                        logging.info(f"Found 'Choose an account' option for {email}. Clicking it...")
                        await page.click(account_selector)
                        await page.wait_for_load_state("networkidle")
                        # After clicking, we might be asked for password or it might just log in
            except Exception as e:
                logging.debug(f"Account selection click failed (non-fatal): {e}")
                # Continue to standard login checks

            
            if "accounts.google.com" not in page.url:
                 # Click sign in if we are on the landing page but not yet on the auth form
                 # Double check we didn't just log in via the click above
                 if not await page.query_selector('rich-textarea'):
                     if await page.query_selector('a[href*="accounts.google.com"]'):
                        await page.click('a[href*="accounts.google.com"]')
                        await page.wait_for_load_state("networkidle")

            # Standard Login Form
            if await page.query_selector('input[type="email"]'):
                if email:
                    logging.info(f"Entering email: {email}")
                    await page.fill('input[type="email"]', email)
                    await page.click('#identifierNext')
                    await page.wait_for_timeout(2000) # Wait for animation
                
                    if password:
                        logging.info("Entering password...")
                        try:
                            # Wait reasonably long for password field, but it might not show if
                            # we are redirected to passkey/2FA immediately
                            await page.wait_for_selector('input[type="password"]', state="visible", timeout=TIMEOUT_SELECTOR)
                            await page.fill('input[type="password"]', password)
                            await page.click('#passwordNext')
                        except Exception as e:
                            logging.warning(f"Password field not found (maybe 2FA/Passkey?): {e}")

                    logging.info("\nCurrent URL: " + page.url)
                    logging.info("Please complete 2FA or any other verification steps manually if asked.")
                else:
                    logging.warning("No credentials found in .env. Please login manually.")
            elif await page.query_selector('input[type="password"]'):
                 logging.info("Password field found (Saved Account flow). Entering password...")
                 if password:
                    try:
                        await page.wait_for_selector('input[type="password"]', state="visible", timeout=TIMEOUT_SELECTOR)
                        await page.fill('input[type="password"]', password)
                        await page.click('#passwordNext')
                        logging.info("\nCurrent URL: " + page.url)
                    except Exception as e:
                         logging.warning(f"Error filling password in saved account flow: {e}")
                 else:
                     logging.warning("Password field found but no password in env vars.")

            else:
                 logging.info("No standard email field found. Attempting to detect if already logged in...")

        else:
            logging.info("Already logged in or on the main page.")

    except Exception as e:
        logging.error(f"Auto-login attempt failed (non-fatal): {e}")
        logging.info("Please finish logging in manually.")

async def main():
    """
    Launches a persistent browser context for Gemini.
    """
    parser = argparse.ArgumentParser(description="Authenticate with Gemini and save state.")
    parser.add_argument("--headless", action="store_true", help="Run browser in headless mode")
    args = parser.parse_args()

    # Ensure profile directory exists
    USER_DATA_DIR.mkdir(parents=True, exist_ok=True)
    
    email = os.getenv("GOOGLE_EMAIL")
    password = os.getenv("GOOGLE_PASSWORD")
    
    logging.info(f"Starting browser with profile at: {USER_DATA_DIR.absolute()}")
    
    # Check for display environment
    if not os.getenv("DISPLAY") and not args.headless:
        logging.warning("No X server or $DISPLAY detected. If not running headlessly, this will likely fail.")
        logging.warning("Consider using 'xvfb-run -a python auth_setup.py' or adding the '--headless' flag.")

    if args.headless:
        logging.info("Running in HEADLESS mode. Manual interaction will not be possible.")
        logging.info("Ensure GOOGLE_EMAIL and GOOGLE_PASSWORD are set in .env for auto-login.")
    
    async with async_playwright() as p:
        # Launch persistent context
        # We use a persistent context so the session is stored in the directory
        context = await p.chromium.launch_persistent_context(
            user_data_dir=USER_DATA_DIR,
            headless=args.headless,
            channel="chrome",  # Try to use system Chrome
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
                "--disable-infobars",
                "--disable-dev-shm-usage",
                "--disable-browser-side-navigation",
                "--disable-gpu",
            ],
            ignore_default_args=["--enable-automation"],
            viewport={'width': 1920, 'height': 1080}
        )
        
        # Determine if we should load auth state manually (backup to persistent context)
        if AUTH_STATE_FILE.exists():
            logging.info(f"Found {AUTH_STATE_FILE}, attempting to inject cookies...")
            try:
                # We can't use context.storage_state(path=...) to LOAD in persistent context easily
                # at launch args (it's for new_context).
                # But we can add cookies manually if needed.
                # However, persistent_context SHOULD have them if the profile dir is the same.
                # If the user deleted the profile dir but kept auth_state.json, we can restore cookies.
                import json
                with open(AUTH_STATE_FILE, 'r') as f:
                    state = json.load(f)
                    if 'cookies' in state:
                        await context.add_cookies(state['cookies'])
                        logging.info(f"Restored {len(state['cookies'])} cookies from auth_state.json")
            except Exception as e:
                logging.warning(f"Failed to load auth_state.json: {e}")

        page = context.pages[0] if context.pages else await context.new_page()
        
        # Stealth scripts
        await page.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', {
                get: () => undefined
            });
        """)

        logging.info("Navigating to Gemini...")
        
        # Periodic screenshot task removed as per user request.

        try:
            await page.goto("https://gemini.google.com/", timeout=TIMEOUT_NAVIGATION)
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
            # We wait for 'rich-textarea' which is the main input box
            # Added timeout of 180 seconds (3 minutes) as requested
            try:
                logging.info(f"Waiting for main chat interface (timeout: {int(TIMEOUT_NAVIGATION/1000)}s)...")
                await page.wait_for_selector('rich-textarea', state="visible", timeout=TIMEOUT_NAVIGATION * 3) # Wait longer for load
            except Exception as e:
                logging.error("Timeout waiting for chat interface! Login might have failed or 2FA took too long.")
                screenshot_dir = "screenshots_host_access" if os.path.exists("screenshots_host_access") else "screenshots"
                ts = get_formatted_timestamp()
                path = f"{screenshot_dir}/auth_timeout_{ts}.png"
                await page.screenshot(path=path)
                logging.error(f"Timeout screenshot saved: {path}")
                raise e

            # Wait a bit for UI to settle 
            await page.wait_for_timeout(3000)

            # Take a final success screenshot
            screenshot_dir = "screenshots_host_access" if os.path.exists("screenshots_host_access") else "screenshots"
            try:
                ts = get_formatted_timestamp()
                path = f"{screenshot_dir}/auth_success_{ts}.png"
                await page.screenshot(path=path)
                logging.info(f"Success screenshot saved: {path}")
            except Exception as e:
                logging.warning(f"Failed to take success screenshot: {e}")
            
            # Stop the screenshot task - removed
            # screenshot_task.cancel()
            
            logging.info("\n✅ LOGIN SUCCESSFUL! The chat interface is visible.")
            
            # Export session to JSON
            logging.info("Exporting session to 'auth_state.json' ...")
            await context.storage_state(path="auth_state.json")
            logging.info("Session exported successfully.")
            
        except Exception as e:
            # If we were taking screenshots, save the final state
            ts = get_formatted_timestamp()
            screenshot_path = f"screenshots_host_access/auth_last_error_{ts}.png"
            if not os.path.exists("screenshots_host_access"):
                screenshot_path = f"screenshots/auth_last_error_{ts}.png"
                os.makedirs("screenshots", exist_ok=True)
                
            try:
                await page.screenshot(path=screenshot_path)
                logging.error(f"Error during login. Last screen saved to {screenshot_path}")
            except:
                pass
            logging.warning(f"Browser closed or error before login confirmed: {e}")

        logging.info("----------------------------------------------------------------")
        logging.info("Closing browser and exiting...")
        logging.info("----------------------------------------------------------------")
        
        # Always close after attempt (Success or Error caught above)
        try:
            await context.close()
        except Exception as e:
            logging.debug(f"Error closing context: {e}")

if __name__ == "__main__":
    asyncio.run(main())
