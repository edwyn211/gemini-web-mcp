import asyncio
import os
import redis.asyncio as redis
import json
import uuid
from datetime import datetime

# Set env for local redis (from docker-compose)
os.environ["REDIS_URL"] = "redis://localhost:6379/0"


async def test_redis_logic():
    print("Testing Redis Persistence...")
    try:
        # 1. Connect to Redis
        r = redis.from_url(os.environ["REDIS_URL"], decode_responses=True)
        await r.ping()
        print("✅ Redis connection successful")

        # 2. Simulate saving a response (mimicking mcp_server.py logic)
        request_id = str(uuid.uuid4())
        mock_response = {
            "status": "success",
            "message": "Test message",
            "tasks_completed": 1,
            "total_tasks": 1,
            "results": [
                {
                    "task_index": 0,
                    "status": "completed",
                    "result": "This is a test response",
                }
            ],
            "chat_url": "https://gemini.google.com/app/test",
            "request_id": request_id,
        }

        # Save
        await r.setex(f"gemini:response:{request_id}", 86400, json.dumps(mock_response))
        print(f"✅ Saved mock response with ID: {request_id}")

        # 3. Retrieve
        saved_data = await r.get(f"gemini:response:{request_id}")
        if saved_data:
            parsed = json.loads(saved_data)
            if parsed["request_id"] == request_id:
                print("✅ Retrieved data matches saved data")
            else:
                print("❌ Retrieved data ID mismatch")
        else:
            print("❌ Failed to retrieve data")

    except Exception as e:
        print(f"❌ Test Failed: {e}")


if __name__ == "__main__":
    asyncio.run(test_redis_logic())
