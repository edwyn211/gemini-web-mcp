import pytest
from unittest.mock import AsyncMock, MagicMock
from orchestrator.graph import execute_task_node, critic_node, should_continue
from orchestrator.state import Task, AgentState
from langgraph.graph import END


@pytest.fixture
def mock_actions():
    actions = MagicMock()
    actions.send_prompt = AsyncMock()
    actions.get_last_response = AsyncMock(return_value="Detailed research response")
    actions.wait_for_deep_research_plan = AsyncMock()
    actions.confirm_deep_research_plan = AsyncMock()
    return actions


@pytest.mark.asyncio
async def test_execute_task_node_success(mock_actions):
    tasks = [Task(description="Research BTC", completed=False)]
    state: AgentState = {
        "tasks": tasks,
        "current_task_index": 0,
        "tool": None,
        "critic_feedback": None,
        "requires_human_approval": False,
        "last_response": None,
        "request_id": "test-id",
    }

    new_state = await execute_task_node(state, mock_actions)

    assert new_state["tasks"][0].completed is True
    assert new_state["last_response"] == "Detailed research response"
    mock_actions.send_prompt.assert_called_once_with("Research BTC")


def test_critic_node_validation():
    # Case 1: Success
    state = {"last_response": "This is a long enough response to be valid."}
    result = critic_node(state)
    assert result["critic_feedback"] is None

    # Case 2: Too short
    state = {"last_response": "Short"}
    result = critic_node(state)
    assert "too short" in result["critic_feedback"].lower()


def test_should_continue_logic():
    # Case 1: More tasks
    state = {
        "current_task_index": 0,
        "tasks": [Task(description="T1"), Task(description="T2")],
        "critic_feedback": None,
    }
    assert should_continue(state) == "next_task"

    # Case 2: Last task
    state = {
        "current_task_index": 1,
        "tasks": [Task(description="T1"), Task(description="T2")],
        "critic_feedback": None,
    }
    assert should_continue(state) == END

    # Case 3: Error
    state = {"critic_feedback": "Execution failed: Something went wrong"}
    assert should_continue(state) == END
