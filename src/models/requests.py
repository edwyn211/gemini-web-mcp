"""Request models for the Gemini Web MCP server."""

from typing import List
from pydantic import BaseModel, Field, field_validator


class TaskRequest(BaseModel):
    """Request model for task execution."""

    tasks: List[str] = Field(
        ...,
        min_length=1,
        max_length=10,
        description="List of task descriptions to execute sequentially. Each task is processed after the previous one completes.",
        examples=[["Summarize the latest AI news", "Draft a LinkedIn post about it"]],
    )
    tool: str | None = Field(
        None,
        description="Optional tool to use for the tasks. Use 'canvas' for content creation/writing, or 'deep_research' for complex multi-step investigations.",
        examples=["canvas", "deep_research"],
    )
    new_chat: bool = Field(
        True,
        description="Whether to start a new chat session. Set to False to continue/monitor an existing session (e.g., waiting for Deep Research to finish).",
    )

    @field_validator('tasks')
    @classmethod
    def validate_tasks(cls, v: List[str]) -> List[str]:
        """Validate each task is not empty and within size limits."""
        validated = []
        for i, task in enumerate(v):
            task = task.strip()
            if not task:
                raise ValueError(f"Task {i} is empty")
            if len(task) > 50000:
                raise ValueError(f"Task {i} exceeds maximum length of 50000 characters")
            validated.append(task)
        return validated

    @field_validator('tool')
    @classmethod
    def validate_tool(cls, v: str | None) -> str | None:
        """Validate tool is one of the allowed values."""
        if v is None:
            return v
        allowed_tools = {'canvas', 'deep_research'}
        v_lower = v.lower()
        if v_lower not in allowed_tools:
            raise ValueError(f"Invalid tool '{v}'. Allowed: {allowed_tools}")
        return v_lower


class StatusRequest(BaseModel):
    """Request model for checking task status."""

    request_id: str = Field(
        ..., 
        min_length=1,
        max_length=100,
        description="The unique ID of the task request to check."
    )
    offset: int = Field(
        0, 
        ge=0,
        description="Character offset for the result text (useful for pagination)."
    )
    max_chars: int = Field(
        100000, 
        ge=1,
        le=1000000,
        description="Maximum number of characters to return in each result."
    )
