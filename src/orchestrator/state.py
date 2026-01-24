from typing import List, TypedDict
from pydantic import BaseModel, Field


class Task(BaseModel):
    """
    Represents a single task to be executed by the agent.
    """

    description: str = Field(
        ..., description="The detailed description of the task to perform."
    )
    completed: bool = Field(False, description="Whether the task has been completed.")


class AgentState(TypedDict):
    """
    Represents the state of the agent, including the queue of tasks.
    This uses TypedDict as required by LangGraph for state management.
    """

    tasks: List[Task]
    current_task_index: int
    critic_feedback: str | None
    requires_human_approval: bool
    last_response: str | None
    tool: str | None  # Added: Tool to use (canvas, deep_research)
    request_id: str | None  # Added: ID for persistence
