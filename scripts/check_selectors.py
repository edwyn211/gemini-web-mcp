#!/usr/bin/env python3
import asyncio
import logging
import sys
import os
from pathlib import Path

# Add project root and src to path
project_root = Path(__file__).parent.parent
sys.path.append(str(project_root))
sys.path.append(str(project_root / "src"))

from mcp_controller.session_manager import SessionManager
from src.mcp_controller.selector_validator import SelectorValidator
from src.mcp_controller.selectors import selector_manager

# ANSI Colors for logs
RED = "\033[91m"
GREEN = "\033[92m"
YELLOW = "\033[93m"
RESET = "\033[0m"

# Configure Logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger("SelectorCheck")

async def main():
    logger.info(f"{YELLOW}Starting Daily Gemini Selector Verification...{RESET}")
    
    # Initialize Session Manager
    # This might require Redis env var to be set if running outside docker
    # But inside container it's fine.
    
    try:
        # Load selectors from Redis if available
        import redis.asyncio as redis
        import json
        
        redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
        try:
            r = redis.from_url(redis_url, decode_responses=True)
            stored = await r.get("gemini:selectors")
            if stored:
                logger.info("Loading selectors from Redis...")
                selector_manager.update_from_dict(json.loads(stored))
            else:
                logger.info("No selectors in Redis, using local config.")
        except Exception as e:
            logger.warning(f"Could not load from Redis (using local config): {e}")

        session_manager = SessionManager()
        validator = SelectorValidator(session_manager)
        
        report = await validator.validate_all()
        
        if report["status"] == "success":
            logger.info(f"{GREEN}✅ All critical selectors are working.{RESET}")
            # Optional: Report working selectors details
            # for item in report["working_selectors"]:
            #     print(f"  - {item['field']}: {item['selector']}")
        else:
            logger.error(f"{RED}❌ BROKEN SELECTORS DETECTED:{RESET}")
            for broken in report["broken_selectors"]:
                logger.error(f"{RED}  ! {broken}{RESET}")
            
            logger.info("Logs:")
            for log in report.get("logs", []):
                print(log)
            
            # Here we could send an alert (Slack, Email, etc.)
            sys.exit(1) # Exit with error code
            
    except Exception as e:
        logger.error(f"{RED}Critical Error during verification: {e}{RESET}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    asyncio.run(main())
