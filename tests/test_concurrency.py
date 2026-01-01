import asyncio
import logging
import sys
import os

# Add src to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../src")))

from mcp_controller.session_manager import SessionManager

async def test_concurrency():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(message)s")
    logger = logging.getLogger("test_concurrency")
    
    manager = SessionManager()
    try:
        await manager.initialize()
        
        logger.info("1. Acquiring Session 1 (Worker)...")
        s1 = await manager.get_worker_session()
        logger.info(f"   Session 1 Page: {s1.page}")
        
        logger.info("2. Acquiring Session 2 (Worker)...")
        s2 = await manager.get_worker_session()
        logger.info(f"   Session 2 Page: {s2.page}")
        
        if s1.page == s2.page:
            logger.error("❌ FAILED: Worker sessions share the same page!")
            return
        else:
            logger.info("✅ SUCCESS: Worker sessions are distinct.")
        
        logger.info("3. Acquiring Main Session...")
        main = await manager.get_main_session()
        logger.info(f"   Main Session: {main.page}")
        
        if main.page == s1.page or main.page == s2.page:
             logger.error("❌ FAILED: Main session conflicts with active worker!")
             return
        else:
             logger.info("✅ SUCCESS: Main session is distinct from workers.")
        
        logger.info("4. Releasing Session 1...")
        await manager.release_session(s1)
        
        logger.info("5. Acquiring Session 3 (Should recycle Session 1)...")
        s3 = await manager.get_worker_session()
        logger.info(f"   Session 3 Page: {s3.page}")
        
        if s3.page == s1.page:
            logger.info("✅ SUCCESS: Session 1 recycled successfully.")
        else:
            logger.warning("⚠ WARNING: Session 1 was not recycled (maybe closed?). Got new page.")
            
        # Verify Context Scripts
        # Check if navigator.webdriver is undefined on s3
        is_headless = await s3.page.evaluate("navigator.webdriver")
        logger.info(f"   Navigator.webdriver on S3: {is_headless} (Should be undefined or null)")
        
    finally:
        logger.info("Closing all sessions...")
        await manager.close_all()

if __name__ == "__main__":
    asyncio.run(test_concurrency())
