"""Integration tests for Redis service using testcontainers."""

import pytest
import sys
import os

# Add src to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../src")))

from models.responses import TaskResponse, TaskResult


# Skip if testcontainers not available
pytest.importorskip("testcontainers")

from testcontainers.redis import RedisContainer


@pytest.fixture(scope="module")
def redis_container():
    """Start a real Redis container for integration tests."""
    with RedisContainer("redis:7-alpine") as redis:
        yield redis


@pytest.fixture
async def redis_service(redis_container):
    """Create RedisService connected to test container."""
    from services.redis_service import RedisService
    
    host = redis_container.get_container_host_ip()
    port = redis_container.get_exposed_port(6379)
    redis_url = f"redis://{host}:{port}/0"
    
    service = RedisService(redis_url)
    yield service
    await service.close()


@pytest.mark.asyncio
async def test_save_and_get_task(redis_service):
    """Test saving and retrieving a task from Redis."""
    request_id = "test-123"
    
    response = TaskResponse(
        status="success",
        message="Test completed",
        tasks_completed=1,
        total_tasks=1,
        results=[
            TaskResult(
                task_index=0,
                description="Test task",
                status="completed",
                result="Test result",
            )
        ],
        request_id=request_id,
    )
    
    # Save
    await redis_service.save_task(request_id, response)
    
    # Retrieve
    retrieved = await redis_service.get_task(request_id)
    
    assert retrieved is not None
    assert retrieved.status == "success"
    assert retrieved.tasks_completed == 1
    assert len(retrieved.results) == 1
    assert retrieved.results[0].result == "Test result"


@pytest.mark.asyncio
async def test_task_not_found(redis_service):
    """Test retrieving non-existent task returns None."""
    result = await redis_service.get_task("nonexistent-id")
    assert result is None


@pytest.mark.asyncio
async def test_delete_task(redis_service):
    """Test deleting a task from Redis."""
    request_id = "delete-test"
    
    response = TaskResponse(
        status="processing",
        message="In progress",
        tasks_completed=0,
        total_tasks=1,
        results=[],
        request_id=request_id,
    )
    
    await redis_service.save_task(request_id, response)
    
    # Verify it exists
    assert await redis_service.get_task(request_id) is not None
    
    # Delete
    await redis_service.delete_task(request_id)
    
    # Verify deleted
    assert await redis_service.get_task(request_id) is None


@pytest.mark.asyncio
async def test_rate_limiting(redis_service):
    """Test rate limiting functionality."""
    key = "test-client"
    max_requests = 3
    window = 60
    
    # First 3 requests should be allowed
    for i in range(max_requests):
        allowed, remaining = await redis_service.check_rate_limit(key, max_requests, window)
        assert allowed is True
        assert remaining == max_requests - i - 1
    
    # 4th request should be blocked
    allowed, remaining = await redis_service.check_rate_limit(key, max_requests, window)
    assert allowed is False
    assert remaining == 0


@pytest.mark.asyncio
async def test_selectors_persistence(redis_service):
    """Test selector save and retrieval."""
    selectors = {
        "send_button": {"primary": "button.send", "fallbacks": []},
        "prompt_textarea": {"primary": "textarea.prompt", "fallbacks": []},
    }
    
    await redis_service.save_selectors(selectors)
    
    retrieved = await redis_service.get_selectors()
    
    assert retrieved is not None
    assert retrieved["send_button"]["primary"] == "button.send"
    assert "prompt_textarea" in retrieved


@pytest.mark.asyncio
async def test_task_ttl(redis_service):
    """Test that tasks expire after TTL."""
    import asyncio
    
    request_id = "ttl-test"
    
    response = TaskResponse(
        status="success",
        message="Short-lived",
        tasks_completed=1,
        total_tasks=1,
        results=[],
        request_id=request_id,
    )
    
    # Save with 1 second TTL
    await redis_service.save_task(request_id, response, ttl=1)
    
    # Should exist immediately
    assert await redis_service.get_task(request_id) is not None
    
    # Wait for expiration
    await asyncio.sleep(1.5)
    
    # Should be gone
    assert await redis_service.get_task(request_id) is None
