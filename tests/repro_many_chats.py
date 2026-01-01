import asyncio
import logging
import sys
import os

# Add src to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../src")))

from mcp_controller.session_manager import SessionManager

async def repro_many_chats():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(message)s")
    logger = logging.getLogger("repro_many_chats")
    
    manager = SessionManager()
    await manager.initialize()
    
    logger.info("--- Phase 1: Sequential Requests (Should reuse 1 tab) ---")
    
    # 1. Acquire and release 5 times sequentially
    for i in range(5):
        logger.info(f"Request {i+1}...")
        session = await manager.get_worker_session()
        logger.info(f"Got session page ID: {id(session.page)}")
        await manager.release_session(session)
        
    num_pages = len(manager.context.pages)
    logger.info(f"Total pages in context: {num_pages}")
    if num_pages > 2: # 1 worker + maybe 1 initial or main
         logger.warning(f"⚠ WARNING: High page count detected: {num_pages}")
    
    
    logger.info("--- Phase 2: Concurrent Requests (Should create multiple tabs) ---")
    
    sessions = []
    # Acquire 3 sessions without releasing
    for i in range(3):
        s = await manager.get_worker_session()
        sessions.append(s)
        logger.info(f"Acquired session {i+1}: {id(s.page)}")
        
    num_pages_conc = len(manager.context.pages)
    logger.info(f"Total pages in context during concurrency: {num_pages_conc}")
    
    # Release all
    for s in sessions:
        await manager.release_session(s)
        
    logger.info("--- Phase 3: Post-Concurrency Cleanup (Should reuse existing tabs) ---")
    
    # Acquire 1
    s_reuse = await manager.get_worker_session()
    logger.info(f"Acquired reuse session: {id(s_reuse.page)}")
    
    num_pages_final = len(manager.context.pages)
    logger.info(f"Total pages final: {num_pages_final}")
    
    await manager.close_all()

if __name__ == "__main__":
    asyncio.run(repro_many_chats())
