"""Security tests for input validation and rate limiting."""

import os
import sys

import pytest
from pydantic import ValidationError

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../src")))

from models.requests import TaskRequest, StatusRequest


class TestTaskRequestValidation:
    """Tests for TaskRequest input validation."""

    def test_valid_request(self):
        """Test valid request passes validation."""
        request = TaskRequest(
            tasks=["Summarize the news"],
            tool="canvas",
            new_chat=True,
        )
        assert len(request.tasks) == 1
        assert request.tool == "canvas"

    def test_empty_tasks_rejected(self):
        """Test empty tasks list is rejected."""
        with pytest.raises(ValidationError) as exc:
            TaskRequest(tasks=[])
        
        assert "at least 1" in str(exc.value).lower() or "min_length" in str(exc.value).lower()

    def test_too_many_tasks_rejected(self):
        """Test more than 10 tasks is rejected."""
        with pytest.raises(ValidationError):
            TaskRequest(tasks=["task"] * 11)

    def test_max_tasks_allowed(self):
        """Test exactly 10 tasks is allowed."""
        request = TaskRequest(tasks=["task"] * 10)
        assert len(request.tasks) == 10

    def test_empty_task_string_rejected(self):
        """Test empty string task is rejected."""
        with pytest.raises(ValidationError) as exc:
            TaskRequest(tasks=["valid task", ""])
        
        assert "empty" in str(exc.value).lower()

    def test_whitespace_only_task_rejected(self):
        """Test whitespace-only task is rejected."""
        with pytest.raises(ValidationError) as exc:
            TaskRequest(tasks=["   \n\t  "])
        
        assert "empty" in str(exc.value).lower()

    def test_task_too_long_rejected(self):
        """Test task exceeding 50000 chars is rejected."""
        long_task = "x" * 50001
        with pytest.raises(ValidationError) as exc:
            TaskRequest(tasks=[long_task])
        
        assert "50000" in str(exc.value)

    def test_max_length_task_allowed(self):
        """Test task at exactly 50000 chars is allowed."""
        long_task = "x" * 50000
        request = TaskRequest(tasks=[long_task])
        assert len(request.tasks[0]) == 50000

    def test_tasks_are_stripped(self):
        """Test whitespace is stripped from tasks."""
        request = TaskRequest(tasks=["  hello world  "])
        assert request.tasks[0] == "hello world"

    def test_invalid_tool_rejected(self):
        """Test invalid tool name is rejected."""
        with pytest.raises(ValidationError) as exc:
            TaskRequest(tasks=["task"], tool="invalid_tool")
        
        assert "invalid tool" in str(exc.value).lower()

    def test_valid_tools_accepted(self):
        """Test all valid tools are accepted."""
        for tool in ["canvas", "deep_research", "CANVAS", "Deep_Research"]:
            request = TaskRequest(tasks=["task"], tool=tool)
            assert request.tool in ["canvas", "deep_research"]

    def test_tool_normalized_to_lowercase(self):
        """Test tool names are normalized to lowercase."""
        request = TaskRequest(tasks=["task"], tool="DEEP_RESEARCH")
        assert request.tool == "deep_research"

    def test_none_tool_allowed(self):
        """Test None tool is allowed."""
        request = TaskRequest(tasks=["task"], tool=None)
        assert request.tool is None

    def test_xss_payload_in_task(self):
        """Test XSS-like payloads are passed through (sanitization is frontend's job)."""
        xss_payload = "<script>alert('xss')</script>"
        request = TaskRequest(tasks=[xss_payload])
        # Should pass - it's just text to send to Gemini
        assert xss_payload.strip() in request.tasks[0]

    def test_sql_injection_payload_in_task(self):
        """Test SQL injection payloads are passed through (no SQL in this system)."""
        sql_payload = "'; DROP TABLE users; --"
        request = TaskRequest(tasks=[sql_payload])
        assert sql_payload in request.tasks[0]


class TestStatusRequestValidation:
    """Tests for StatusRequest input validation."""

    def test_valid_request(self):
        """Test valid status request."""
        request = StatusRequest(
            request_id="abc-123",
            offset=0,
            max_chars=1000,
        )
        assert request.request_id == "abc-123"

    def test_empty_request_id_rejected(self):
        """Test empty request_id is rejected."""
        with pytest.raises(ValidationError):
            StatusRequest(request_id="")

    def test_too_long_request_id_rejected(self):
        """Test request_id over 100 chars is rejected."""
        with pytest.raises(ValidationError):
            StatusRequest(request_id="x" * 101)

    def test_negative_offset_rejected(self):
        """Test negative offset is rejected."""
        with pytest.raises(ValidationError):
            StatusRequest(request_id="abc", offset=-1)

    def test_zero_offset_allowed(self):
        """Test zero offset is allowed."""
        request = StatusRequest(request_id="abc", offset=0)
        assert request.offset == 0

    def test_zero_max_chars_rejected(self):
        """Test zero max_chars is rejected."""
        with pytest.raises(ValidationError):
            StatusRequest(request_id="abc", max_chars=0)

    def test_too_large_max_chars_rejected(self):
        """Test max_chars over 1000000 is rejected."""
        with pytest.raises(ValidationError):
            StatusRequest(request_id="abc", max_chars=1000001)

    def test_max_max_chars_allowed(self):
        """Test max_chars at exactly 1000000 is allowed."""
        request = StatusRequest(request_id="abc", max_chars=1000000)
        assert request.max_chars == 1000000


class TestPathTraversalPrevention:
    """Tests for path traversal attack prevention."""

    def test_path_traversal_in_task(self):
        """Test path traversal in task is just passed as text."""
        payload = "../../../etc/passwd"
        request = TaskRequest(tasks=[payload])
        # This is fine - it's just text for Gemini
        assert payload in request.tasks[0]

    def test_null_byte_injection(self):
        """Test null byte in task is handled."""
        payload = "normal task\x00malicious"
        # Python strings can contain null bytes, should work
        request = TaskRequest(tasks=[payload])
        assert "\x00" in request.tasks[0] or "malicious" in request.tasks[0]


class TestUnicodeHandling:
    """Tests for proper Unicode handling."""

    def test_unicode_task(self):
        """Test Unicode characters in tasks."""
        request = TaskRequest(tasks=["Résumé des actualités 日本語 🚀"])
        assert "Résumé" in request.tasks[0]
        assert "日本語" in request.tasks[0]
        assert "🚀" in request.tasks[0]

    def test_rtl_text(self):
        """Test right-to-left text handling."""
        arabic = "مرحبا بالعالم"
        request = TaskRequest(tasks=[arabic])
        assert arabic in request.tasks[0]

    def test_mixed_scripts(self):
        """Test mixed script content."""
        mixed = "Hello مرحبا 你好 🌍"
        request = TaskRequest(tasks=[mixed])
        assert mixed.strip() == request.tasks[0]
