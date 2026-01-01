import asyncio
import logging
import sys
import os
import time

# Add src to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../src")))

from mcp_controller.session_manager import SessionManager

async def test_locking():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(message)s")
    logger = logging.getLogger("test_locking")
    
    manager = SessionManager()
    await manager.initialize()
    
    logger.info("--- Phase 1: Main Session locking (Should be Sequential) ---")
    
    # Get main session twice (simulating two requests to same session)
    main1 = await manager.get_main_session()
    main2 = await manager.get_main_session()
    
    async def task_on_main(name, delay):
        logger.info(f"[{name}] Starting (acquiring lock)...")
        # Simulate the lock usage in mcp_server.py
        async with main1.execution_lock:
             logger.info(f"[{name}] Acquired lock! Sleeping {delay}s...")
             await asyncio.sleep(delay)
             logger.info(f"[{name}] Done.")
             return time.time()
             
    start_time = time.time()
    # Launch two tasks on main session simultaneously
    t1 = asyncio.create_task(task_on_main("SEQ-1", 2))
    t2 = asyncio.create_task(task_on_main("SEQ-2", 2))
    
    await asyncio.gather(t1, t2)
    end_time = time.time()
    duration = end_time - start_time
    
    logger.info(f"Sequential Duration: {duration:.2f}s")
    
    if duration >= 4.0:
        logger.info("✅ SUCCESS: Main session tasks ran sequentially (2s + 2s).")
    else:
        logger.error(f"❌ FAILED: Main session tasks ran too fast ({duration:.2f}s)! Locking failed.")

    logger.info("--- Phase 2: Worker Session Parallelism (Should be Concurrent) ---")
    
    w1 = await manager.get_worker_session()
    w2 = await manager.get_worker_session()
    
    async def task_on_worker(session, name, delay):
        logger.info(f"[{name}] Starting (acquiring lock)...")
        async with session.execution_lock:
             logger.info(f"[{name}] Acquired lock! Sleeping {delay}s...")
             await asyncio.sleep(delay)
             logger.info(f"[{name}] Done.")
             return time.time()
             
    start_time_par = time.time()
    t3 = asyncio.create_task(task_on_worker(w1, "PAR-1", 2))
    t4 = asyncio.create_task(task_on_worker(w2, "PAR-2", 2))
    
    await asyncio.gather(t3, t4)
    end_time_par = time.time()
    duration_par = end_time_par - start_time_par
    
    logger.info(f"Parallel Duration: {duration_par:.2f}s")
    
    # Should take roughly 2 seconds (max of 2, 2)
    if duration_par < 3.0: 
        logger.info("✅ SUCCESS: Worker tasks ran in parallel (~2s).")
    else:
        logger.error(f"❌ FAILED: Worker tasks ran too slow ({duration_par:.2f}s)!")
        
    await manager.close_all()

if __name__ == "__main__":
    asyncio.run(test_locking())
