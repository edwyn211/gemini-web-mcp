import logging

from langgraph.graph import END, StateGraph

from mcp_controller.actions import GeminiPageActions

from .state import AgentState

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)

# This is a simplified placeholder for the graph logic.
# In a real-world scenario, these nodes would be more complex,
# involving more sophisticated logic, error handling, and state management.


def execute_task_node(state: AgentState, actions: GeminiPageActions):
    """
    A node that executes the current task in the queue.
    """
    current_index = state.get("current_task_index", 0)
    tasks = state.get("tasks", [])

    if current_index >= len(tasks):
        return {"tasks": tasks, "current_task_index": current_index}

    task = tasks[current_index]
    if not task.completed:
        logging.info(f"Executing task: {task.description}")
        # In a real execution, we would call:
        # await actions.send_prompt(task.description)
        # last_response = await actions.get_last_response()
        last_response = f"Simulated response for: {task.description}"

        return {
            "tasks": tasks,
            "current_task_index": current_index,
            "last_response": last_response,
            "requires_human_approval": "deep research" in task.description.lower(),
        }

    return {"tasks": tasks, "current_task_index": current_index + 1}


def critic_node(state: AgentState):
    """
    Validates if the last response is sufficient.
    """
    last_response = state.get("last_response", "")
    if not last_response or len(last_response) < 20:
        return {"critic_feedback": "Response too short or empty. Retry."}
    return {"critic_feedback": None}


def human_approval_node(state: AgentState):
    """
    A node that represents a breakpoint for human approval.
    """
    # In LangGraph, we can use an interrupt here, but for this implementation
    # we just mark it as no longer needing approval once this node is visited.
    logging.info("Awaiting human approval for sensitive task...")
    return {"requires_human_approval": False}


def should_continue_node(state: AgentState):
    """
    Conditional logic to route the flow.
    """
    if state.get("requires_human_approval"):
        return "human_approval"

    if state.get("critic_feedback"):
        return "execute_task"  # Retry

    current_index = state.get("current_task_index", 0)
    tasks = state.get("tasks", [])

    if current_index >= len(tasks):
        return END

    # Check if current task just finished and needs validation
    if current_index < len(tasks) and not state.get("critic_feedback"):
        return "critic"

    return "execute_task"


def create_workflow(page_actions: GeminiPageActions):
    """
    Creates and configures the LangGraph StateGraph.
    """
    workflow = StateGraph(AgentState)

    bound_execute_task_node = lambda state: execute_task_node(state, page_actions)

    workflow.add_node("execute_task", bound_execute_task_node)
    workflow.add_node("critic", critic_node)
    workflow.add_node("human_approval", human_approval_node)

    workflow.add_conditional_edges(
        "execute_task",
        should_continue_node,
        {
            "human_approval": "human_approval",
            "critic": "critic",
            "execute_task": "execute_task",
            END: END,
        },
    )

    workflow.add_edge("human_approval", "critic")

    workflow.add_conditional_edges(
        "critic",
        lambda state: "execute_task" if state.get("critic_feedback") else "next_task",
        {
            "execute_task": "execute_task",
            "next_task": "execute_task",  # In this simple case, moves to next task via execute_task logic
        },
    )

    workflow.set_entry_point("execute_task")

    return workflow.compile()
