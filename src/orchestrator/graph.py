import logging
from langgraph.graph import END, StateGraph

from mcp_controller.actions import GeminiPageActions
from .state import AgentState

# Configure logging
logger = logging.getLogger(__name__)


async def execute_task_node(
    state: AgentState, actions: GeminiPageActions
) -> AgentState:
    """
    A node that executes the current task in the queue.
    """
    current_index = state.get("current_task_index", 0)
    tasks = state.get("tasks", [])
    tool = state.get("tool")

    if current_index >= len(tasks):
        logger.info("No more tasks to execute.")
        return state

    task = tasks[current_index]
    logger.info(
        f"🚀 Executing task {current_index + 1}/{len(tasks)}: {task.description}"
    )

    try:
        # 1. Send the prompt
        await actions.send_prompt(task.description)

        # 2. Handle Deep Research specific workflow if needed
        if tool and tool.lower() == "deep_research":
            logger.info("🔍 Deep Research phase: Waiting for plan...")
            await actions.wait_for_deep_research_plan()
            await actions.confirm_deep_research_plan()
            logger.info("✅ Deep Research plan confirmed.")

        # 3. Get response with appropriate timeout
        # Deep Research takes much longer (~30 mins)
        timeout = 1800000 if tool and tool.lower() == "deep_research" else 300000
        last_response = await actions.get_last_response(timeout=timeout, tool=tool)

        # Update task status
        task.completed = True
        tasks[current_index] = task

        return {
            **state,
            "tasks": tasks,
            "current_task_index": current_index,
            "last_response": last_response,
            "critic_feedback": None,  # Reset feedback
        }

    except Exception as e:
        logger.error(f"❌ Error in execute_task_node: {e}")
        return {
            **state,
            "critic_feedback": f"Execution failed: {str(e)}",
            "last_response": None,
        }


def critic_node(state: AgentState) -> AgentState:
    """
    Validates if the last response is sufficient.
    """
    last_response = state.get("last_response")
    feedback = None

    if not last_response:
        feedback = "Empty response received."
    elif len(last_response.strip()) < 10:
        feedback = "Response is too short, possibly blocked or failed to load."
    elif "No se puede acceder a esta función" in last_response:
        feedback = "Access blocked by Gemini (e.g. safety or regional restriction)."

    if feedback:
        logger.warning(f"⚖️ Critic Feedback: {feedback}")

    return {**state, "critic_feedback": feedback}


async def human_approval_node(state: AgentState) -> AgentState:
    """
    A node that represents a breakpoint for human approval (Stub for now).
    """
    logger.info("Awaiting human approval for sensitive task...")
    # In a real environment, this would wait for an external signal
    return {**state, "requires_human_approval": False}


def should_continue(state: AgentState) -> str:
    """
    Route based on state.
    """
    if state.get("requires_human_approval"):
        return "human_approval"

    if state.get("critic_feedback"):
        # If we have feedback, we might want to retry or end with error
        # For now, let's limit retries or just END if it's a hard error
        if "Execution failed" in state["critic_feedback"]:
            return END
        return "execute_task"

    current_index = state.get("current_task_index", 0)
    tasks = state.get("tasks", [])

    if current_index + 1 >= len(tasks):
        return END

    return "next_task"


def move_to_next_task(state: AgentState) -> AgentState:
    """Increments the task index."""
    return {**state, "current_task_index": state.get("current_task_index", 0) + 1}


def create_workflow(page_actions: GeminiPageActions):
    """
    Creates and configures the LangGraph StateGraph.
    """
    workflow = StateGraph(AgentState)

    # Bind actions to nodes that need them
    async def bound_execute_task(state):
        return await execute_task_node(state, page_actions)

    workflow.add_node("execute_task", bound_execute_task)
    workflow.add_node("critic", critic_node)
    workflow.add_node("human_approval", human_approval_node)
    workflow.add_node("next_task", move_to_next_task)

    workflow.set_entry_point("execute_task")

    workflow.add_edge("execute_task", "critic")

    workflow.add_conditional_edges(
        "critic",
        should_continue,
        {
            "human_approval": "human_approval",
            "execute_task": "execute_task",
            "next_task": "next_task",
            END: END,
        },
    )

    workflow.add_edge("human_approval", "execute_task")
    workflow.add_edge("next_task", "execute_task")

    return workflow.compile()
