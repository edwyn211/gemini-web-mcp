
import sys
import unittest
from unittest.mock import MagicMock
from typing import List, Dict, Any

# Mock dependencies before importing local modules
sys.modules["fastmcp"] = MagicMock()
sys.modules["playwright.async_api"] = MagicMock()
sys.modules["mcp_controller"] = MagicMock()
sys.modules["mcp_controller.actions"] = MagicMock()
sys.modules["orchestrator"] = MagicMock()
sys.modules["orchestrator.state"] = MagicMock()
sys.modules["orchestrator.graph"] = MagicMock()
sys.modules["utils"] = MagicMock()
sys.modules["utils.screenshot_manager"] = MagicMock()
sys.modules["starlette"] = MagicMock()
sys.modules["starlette.responses"] = MagicMock()

# Import the module to test
# We need to make sure src is in path
import os
sys.path.append(os.path.join(os.getcwd(), "src"))

try:
    from mcp_server import TaskRequest, TaskResponse, TaskResult
    print("✅ Successfully imported mcp_server models")
except ImportError as e:
    print(f"❌ Failed to import mcp_server: {e}")
    sys.exit(1)
except Exception as e:
    print(f"❌ Error during import: {e}")
    sys.exit(1)

from pydantic import ValidationError

class TestModels(unittest.TestCase):
    def test_task_request_valid(self):
        """Test valid TaskRequest"""
        req = TaskRequest(tasks=["Do something"], tool="canvas")
        self.assertEqual(req.tasks, ["Do something"])
        self.assertEqual(req.tool, "canvas")
        print("✅ TaskRequest valid test passed")

    def test_task_request_invalid(self):
        """Test invalid TaskRequest"""
        with self.assertRaises(ValidationError):
            TaskRequest(tool="canvas") # Missing tasks
        print("✅ TaskRequest validation test passed")

    def test_task_result_valid(self):
        """Test valid TaskResult"""
        res = TaskResult(
            task_index=0, 
            description="test", 
            status="success", 
            result="done",
            metadata={"time": 1.0}
        )
        self.assertEqual(res.status, "success")
        print("✅ TaskResult valid test passed")

    def test_task_response_valid(self):
        """Test valid TaskResponse"""
        result = TaskResult(
            task_index=0, 
            description="test", 
            status="completed", 
            result="done"
        )
        res = TaskResponse(
            status="success",
            message="All good",
            tasks_completed=1,
            total_tasks=1,
            results=[result],
            chat_url="https://gemini.google.com/app/123"
        )
        self.assertEqual(res.status, "success")
        self.assertEqual(res.chat_url, "https://gemini.google.com/app/123")
        self.assertEqual(len(res.results), 1)
        print("✅ TaskResponse valid test passed")

if __name__ == '__main__':
    unittest.main(verbosity=2)
