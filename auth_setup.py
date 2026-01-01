# trunk-ignore-all(black)
# trunk-ignore-all(isort)
import asyncio
import logging
import os
import argparse
from pathlib import Path
from playwright.async_api import async_playwright
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

USER_DATA_DIR = Path("profiles/default")
AUTH_STATE_FILE = Path("auth_state.json")

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
                            await page.wait_for_selector('input[type="password"]', state="visible", timeout=5000)
                            await page.fill('input[type="password"]', password)
                            await page.click('#passwordNext')
                        except Exception as e:
                            logging.warning(f"Password field not found (maybe 2FA/Passkey?): {e}")

                    logging.info("\nCurrent URL: " + page.url)
                    logging.info("Please complete 2FA or any other verification steps manually if asked.")
                else:
                    logging.warning("No credentials found in .env. Please login manually.")
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
            # Task to take periodic screenshots for remote debugging
            async def periodic_screenshot():
                screenshot_dir = "screenshots_host_access" if os.path.exists("screenshots_host_access") else "screenshots"
                os.makedirs(screenshot_dir, exist_ok=True)
                count = 0
                while True:
                    try:
                        await page.screenshot(path=f"{screenshot_dir}/auth_step_{count}.png")
                        logging.info(f"Screenshot saved: {screenshot_dir}/auth_step_{count}.png")
                        count += 1
                        # Rotate screenshots (keep last 5)
                        if count > 5:
                            oldest = f"{screenshot_dir}/auth_step_{count-6}.png"
                            if os.path.exists(oldest):
                                os.remove(oldest)
                    except Exception as e:
                        logging.debug(f"Screenshot failed: {e}")
                        break
                    await asyncio.sleep(5)

            screenshot_task = asyncio.create_task(periodic_screenshot())

            # We wait for 'rich-textarea' which is the main input box
            await page.wait_for_selector('rich-textarea', state="visible", timeout=0)

            # Wait a bit for UI to settle (user request: wait long enough to take screenshot)
            await page.wait_for_timeout(3000)

            # Take a final success screenshot
            screenshot_dir = "screenshots_host_access" if os.path.exists("screenshots_host_access") else "screenshots"
            try:
                await page.screenshot(path=f"{screenshot_dir}/auth_success.png")
                logging.info(f"Success screenshot saved: {screenshot_dir}/auth_success.png")
            except Exception as e:
                logging.warning(f"Failed to take success screenshot: {e}")
            
            # Stop the screenshot task
            screenshot_task.cancel()
            
            logging.info("\n✅ LOGIN SUCCESSFUL! The chat interface is visible.")
            
            # Export session to JSON for Docker compatibility
            # (Windows User Data Dir is not compatible with Linux)
            logging.info("Exporting session to 'auth_state.json' for Docker...")
            await context.storage_state(path="auth_state.json")
            logging.info("Session exported successfully.")
            
        except Exception as e:
            # Should not happen with timeout=0 unless browser is closed
            # If we were taking screenshots, save the final state
            screenshot_path = "screenshots/auth_last_error.png"
            os.makedirs("screenshots", exist_ok=True)
            try:
                await page.screenshot(path=screenshot_path)
                logging.error(f"Error during login. Last screen saved to {screenshot_path}")
            except:
                pass
            logging.warning(f"Browser closed or error before login confirmed: {e}")

        logging.info("----------------------------------------------------------------")
        if not args.headless:
            logging.info("YOU MAY NOW CLOSE THE BROWSER WINDOW TO EXIT.")
        else:
            logging.info("HEADLESS MODE: Process will exit automatically once login is detected.")
            logging.info("If it hangs, check if 2FA is required.")
        logging.info("----------------------------------------------------------------")
        
        # Wait for the user to close the page/browser or for periodic checks if headless
        try:
            # Loop until the page is closed
            while context.pages:
                if args.headless:
                    # If headless and we reached here, it means we found 'rich-textarea'
                    # and exported the state. We can probably exit.
                    logging.info("Login confirmed and state exported. Exiting...")
                    break
                await asyncio.sleep(1)
        except Exception as e:
            logging.debug(f"Loop check exited (browser closed?): {e}")

        logging.info("Browser closed. Profile updated.")
        try:
            await context.close()
        except Exception as e:
            logging.debug(f"Error checking/closing context: {e}")

if __name__ == "__main__":
    asyncio.run(main())
