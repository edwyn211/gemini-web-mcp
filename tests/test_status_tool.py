import asyncio
import json
import uuid
import sys
import os
from pathlib import Path

# Add src to path
sys.path.append(str(Path(__file__).parent.parent / "src"))

from mcp_server import execute_tasks_workflow, execute_get_gemini_task_status, StatusResponse, TaskResponse

async def test_status_logic():
    print("🚀 Starting Verification Test for Task Status Tool...")

    # 1. Test execute_tasks_workflow generates ID and saves to Redis
    print("\n--- 1. Testing workflow initialization ---")
    # We use a simple task so it finishes quickly, but we want to see it in Redis
    task_desc = ["Calculate 123 + 456"]
    
    # We can't easily intercept the 'processing' state in a single-threaded test without complex mocking,
    # but we can verify it exists and is updated.
    
    response = await execute_tasks_workflow(task_desc)
    request_id = response.request_id
    print(f"✅ Workflow started/finished. Request ID: {request_id}")
    print(f"✅ Initial Status: {response.status}")

    # 2. Test get_gemini_task_status (Success case)
    print("\n--- 2. Testing get_gemini_task_status (Success) ---")
    status_resp = await execute_get_gemini_task_status(request_id)
    print(f"✅ Status Response: {status_resp.status}")
    print(f"✅ Result content (first 50 chars): {status_resp.results[0].result[:50]}")
    assert status_resp.status == "success"
    assert "579" in status_resp.results[0].result

    # 3. Test get_gemini_task_status (Pagination/Truncation)
    print("\n--- 3. Testing Pagination/Truncation ---")
    full_text = status_resp.results[0].result
    max_chars = 10
    trunc_resp = await execute_get_gemini_task_status(request_id, offset=0, max_chars=max_chars)
    print(f"✅ Truncated Result (max {max_chars}): '{trunc_resp.results[0].result}'")
    assert len(trunc_resp.results[0].result) <= max_chars
    assert trunc_resp.results[0].metadata["truncated"] == (len(full_text) > max_chars)

    # 4. Test Offset
    print("\n--- 4. Testing Offset ---")
    offset = 5
    offset_resp = await execute_get_gemini_task_status(request_id, offset=offset, max_chars=10)
    print(f"✅ Offset Result (offset {offset}): '{offset_resp.results[0].result}'")
    assert offset_resp.results[0].result == full_text[offset:offset+10]

    # 5. Test Not Found
    print("\n--- 5. Testing Not Found ---")
    fake_id = str(uuid.uuid4())
    nf_resp = await execute_get_gemini_task_status(fake_id)
    print(f"✅ Not Found Status: {nf_resp.status}")
    assert nf_resp.status == "not_found"

    print("\n✨ All tests passed!")

if __name__ == "__main__":
    asyncio.run(test_status_logic())
