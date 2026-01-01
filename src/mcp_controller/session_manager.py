import asyncio
import logging
from pathlib import Path
from typing import List, Optional, Set

from playwright.async_api import Browser, BrowserContext, Page, async_playwright

from mcp_controller.actions import GeminiPageActions

# Constants
AUTH_STATE_PATH = Path("auth_state.json")

logger = logging.getLogger(__name__)

class SessionManager:
    """
    Manages Browser Context and a pool of Gemini interaction sessions (Pages).
    Ensures safe concurrency by providing isolated sessions for parallel tasks.
    """

    def __init__(self):
        self.playwright = None
        self.browser: Optional[Browser] = None
        self.context: Optional[BrowserContext] = None
        
        # The primary session used for stateful operations (upload, continue chat)
        self.main_session: Optional[GeminiPageActions] = None
        
        # Pool for concurrent tasks
        self.active_workers: Set[GeminiPageActions] = set()
        self.idle_workers: List[GeminiPageActions] = []
        
        self.lock = asyncio.Lock()

    async def initialize(self):
        """Initializes the browser and context if not already done."""
        if self.context:
            return

        logger.info("Initializing SessionManager and Browser...")
        self.playwright = await async_playwright().start()
        
        # Launch browser
        # Use standard launch instead of persistent context for better Docker compatibility
        self.browser = await self.playwright.chromium.launch(
            headless=True,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
                "--disable-infobars",
                "--disable-dev-shm-usage",
            ],
            ignore_default_args=["--enable-automation"],
        )

        # Create context with storage state if available
        context_args = {
            "viewport": {"width": 1920, "height": 1080},
            "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        }

        if AUTH_STATE_PATH.exists():
            logger.info(f"Loading auth state from {AUTH_STATE_PATH}")
            context_args["storage_state"] = AUTH_STATE_PATH

        self.context = await self.browser.new_context(**context_args)
        
        # Stealth scripts
        await self.context.add_init_script(
            """
            Object.defineProperty(navigator, 'webdriver', {
                get: () => undefined
            });
            """
        )
        logger.info("Browser Context initialized.")

    async def _create_session(self) -> GeminiPageActions:
        """Helper to create a fresh session."""
        if not self.context:
             await self.initialize()
             
        page = await self.context.new_page()
        # Initial navigation
        try:
            await page.goto("https://gemini.google.com/")
            # We don't block heavily here, let the actions handle specific waits
        except Exception as e:
             logger.warning(f"New page navigation warning: {e}")
             
        return GeminiPageActions(page)

    async def get_main_session(self) -> GeminiPageActions:
        """
        Returns the main shared session. Initializes if necessary.
        Use this for operations that require continuity or state (uploads, recursive calls).
        """
        async with self.lock:
             if self.main_session and self.main_session.page.is_closed():
                 logger.warning("Main session page was closed, recreating.")
                 self.main_session = None

             if not self.main_session:
                 self.main_session = await self._create_session()
                 
             return self.main_session

    async def get_worker_session(self) -> GeminiPageActions:
        """
        Returns an isolated session for concurrent tasks.
        Reuses idle sessions if available, or creates new one.
        """
        async with self.lock:
            # Clean up closed idle sessions
            self.idle_workers = [s for s in self.idle_workers if not s.page.is_closed()]
            
            if self.idle_workers:
                session = self.idle_workers.pop(0)
                self.active_workers.add(session)
                logger.info(f"Reusing idle worker session. (Active: {len(self.active_workers)})")
                return session
            
            # Create new
            session = await self._create_session()
            self.active_workers.add(session)
            logger.info(f"Created new worker session. (Active: {len(self.active_workers)})")
            return session

    async def release_session(self, session: GeminiPageActions):
        """
        Releases a worker session back to the pool.
        Does NOT affect main_session.
        """
        async with self.lock:
            if session == self.main_session:
                return # Do nothing for main session
            
            if session in self.active_workers:
                self.active_workers.remove(session)
                if not session.page.is_closed():
                    self.idle_workers.append(session)
                    logger.info(f"Worker session returned to pool. (Idle: {len(self.idle_workers)})")

    async def close_all(self):
        """Closes all sessions and browser."""
        logger.info("Closing all browser sessions...")
        if self.context:
            await self.context.close()
            self.context = None
        if self.playwright:
            await self.playwright.stop()
            self.playwright = None
        self.main_session = None
        self.active_workers.clear()
        self.idle_workers.clear()
            
    async def reload_auth(self):
        """Reloads the context to refresh auth state."""
        logger.info("Reloading auth state (restarting browser context)...")
        await self.close_all()
        # Initialize will called on next get_session
