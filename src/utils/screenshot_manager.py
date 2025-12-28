"""
Screenshot manager for automatic capture on errors
Helps with debugging by saving visual evidence of failures
"""

import logging
from pathlib import Path
from datetime import datetime, timedelta
from typing import Optional, Dict, Any
from playwright.async_api import Page
import json

logger = logging.getLogger(__name__)


class ScreenshotManager:
    """
    Manages automatic screenshot capture for debugging purposes.
    Organizes screenshots by date and includes metadata.
    """
    
    def __init__(self, base_dir: str = "screenshots", retention_days: int = 7):
        """
        Initialize the screenshot manager
        
        Args:
            base_dir: Preferred base directory for storing screenshots
            retention_days: Number of days to keep screenshots before cleanup
        """
        self.retention_days = retention_days
        self.base_dir = self._find_writable_dir(base_dir)
        
        if self.base_dir:
            logger.info(f"✓ Screenshot manager initialized. Path: {self.base_dir}")
        else:
            logger.warning("⚠ No writable directory found for screenshots. Captures will be disabled.")

    def _find_writable_dir(self, preferred_path: str) -> Optional[Path]:
        """Find a writable directory from a list of candidates"""
        from os import getuid
        import os
        
        # List of candidate directories in order of preference
        candidates = [
            Path(preferred_path).resolve(),
            Path.home() / "gemini-mcp-screenshots",
            Path("/tmp/gemini-mcp-screenshots")
        ]
        
        for path in candidates:
            try:
                path.mkdir(parents=True, exist_ok=True)
                # Test writability
                test_file = path / f".write_test_{getuid()}"
                test_file.touch()
                test_file.unlink()
                return path
            except Exception as e:
                logger.debug(f"Candidate path {path} not writable: {e}")
                continue
                
        return None
        
    def _get_today_dir(self) -> Path:
        """Get the directory for today's screenshots"""
        today = datetime.now().strftime("%Y-%m-%d")
        today_dir = self.base_dir / today
        today_dir.mkdir(parents=True, exist_ok=True)
        return today_dir
        
    def _generate_filename(self, action: str, error_type: str = "error") -> str:
        """
        Generate a unique filename for a screenshot
        
        Args:
            action: The action that was being performed
            error_type: Type of error (default: "error")
            
        Returns:
            Filename string
        """
        timestamp = datetime.now().strftime("%H-%M-%S")
        # Sanitize action name for filename
        safe_action = "".join(c if c.isalnum() or c in "-_" else "_" for c in action)
        return f"{timestamp}_{error_type}_{safe_action}.png"
        
    async def capture_error(
        self,
        page: Page,
        action: str,
        error: Exception,
        selector: Optional[str] = None,
        additional_info: Optional[Dict[str, Any]] = None
    ) -> Optional[Path]:
        """
        Capture a screenshot when an error occurs
        
        Args:
            page: Playwright Page object
            action: Name of the action that failed
            error: The exception that was raised
            selector: The selector that was being used (if applicable)
            additional_info: Additional metadata to save
            
        Returns:
            Path to the saved screenshot, or None if capture failed
        """
        try:
            today_dir = self._get_today_dir()
            filename = self._generate_filename(action)
            screenshot_path = today_dir / filename
            
            # Capture the screenshot
            await page.screenshot(path=str(screenshot_path), full_page=True)
            
            # Save metadata
            metadata = {
                "timestamp": datetime.now().isoformat(),
                "action": action,
                "error_type": type(error).__name__,
                "error_message": str(error),
                "selector": selector,
                "url": page.url,
                "viewport": page.viewport_size,
            }
            
            if additional_info:
                metadata["additional_info"] = additional_info
            
            metadata_path = screenshot_path.with_suffix(".json")
            with open(metadata_path, 'w', encoding='utf-8') as f:
                json.dump(metadata, f, indent=2, ensure_ascii=False)
            
            logger.info(f"📸 Screenshot saved: {screenshot_path}")
            logger.info(f"📋 Metadata saved: {metadata_path}")
            
            return screenshot_path
            
        except Exception as e:
            logger.error(f"Failed to capture screenshot: {e}")
            return None
    
    async def capture_success(
        self,
        page: Page,
        action: str,
        additional_info: Optional[Dict[str, Any]] = None
    ) -> Optional[Path]:
        """
        Capture a screenshot of a successful action (for verification)
        
        Args:
            page: Playwright Page object
            action: Name of the action that succeeded
            additional_info: Additional metadata to save
            
        Returns:
            Path to the saved screenshot, or None if capture failed
        """
        try:
            today_dir = self._get_today_dir()
            filename = self._generate_filename(action, "success")
            screenshot_path = today_dir / filename
            
            # Capture the screenshot
            await page.screenshot(path=str(screenshot_path), full_page=True)
            
            # Save metadata
            metadata = {
                "timestamp": datetime.now().isoformat(),
                "action": action,
                "status": "success",
                "url": page.url,
                "viewport": page.viewport_size,
            }
            
            if additional_info:
                metadata["additional_info"] = additional_info
            
            metadata_path = screenshot_path.with_suffix(".json")
            with open(metadata_path, 'w', encoding='utf-8') as f:
                json.dump(metadata, f, indent=2, ensure_ascii=False)
            
            logger.debug(f"📸 Success screenshot saved: {screenshot_path}")
            
            return screenshot_path
            
        except Exception as e:
            logger.error(f"Failed to capture success screenshot: {e}")
            return None
    
    def cleanup_old_screenshots(self):
        """
        Remove screenshots older than retention_days
        """
        try:
            cutoff_date = datetime.now() - timedelta(days=self.retention_days)
            
            for date_dir in self.base_dir.iterdir():
                if not date_dir.is_dir():
                    continue
                    
                try:
                    # Parse directory name as date
                    dir_date = datetime.strptime(date_dir.name, "%Y-%m-%d")
                    
                    if dir_date < cutoff_date:
                        # Remove old directory
                        for file in date_dir.iterdir():
                            file.unlink()
                        date_dir.rmdir()
                        logger.info(f"🗑️ Cleaned up old screenshots from {date_dir.name}")
                        
                except ValueError:
                    # Not a valid date directory, skip
                    continue
                    
        except Exception as e:
            logger.error(f"Error during screenshot cleanup: {e}")
    
    def get_recent_screenshots(self, limit: int = 10) -> list[Path]:
        """
        Get the most recent screenshots
        
        Args:
            limit: Maximum number of screenshots to return
            
        Returns:
            List of screenshot paths, sorted by most recent first
        """
        screenshots = []
        
        for date_dir in sorted(self.base_dir.iterdir(), reverse=True):
            if not date_dir.is_dir():
                continue
                
            for screenshot in sorted(date_dir.glob("*.png"), reverse=True):
                screenshots.append(screenshot)
                if len(screenshots) >= limit:
                    return screenshots
        
        return screenshots
    
    def get_screenshot_metadata(self, screenshot_path: Path) -> Optional[Dict[str, Any]]:
        """
        Get metadata for a screenshot
        
        Args:
            screenshot_path: Path to the screenshot
            
        Returns:
            Metadata dictionary, or None if not found
        """
        metadata_path = screenshot_path.with_suffix(".json")
        
        if metadata_path.exists():
            try:
                with open(metadata_path, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception as e:
                logger.error(f"Error reading metadata: {e}")
        
        return None
