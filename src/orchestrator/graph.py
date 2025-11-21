import logging
from langgraph.graph import StateGraph, END
from .state import AgentState, Task
from mcp_controller.actions import GeminiPageActions

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# This is a simplified placeholder for the graph logic.
# In a real-world scenario, these nodes would be more complex,
# involving more sophisticated logic, error handling, and state management.

def execute_task_node(state: AgentState, actions: GeminiPageActions):
    """
    A node that executes the current task in the queue.
    For this example, it just sends the task description as a prompt.
    """
    current_index = state.get("current_task_index", 0)
    tasks = state.get("tasks", [])
    
    if current_index >= len(tasks):
        logging.info("All tasks completed.")
        return {"tasks": tasks, "current_task_index": current_index}

    task = tasks[current_index]
    if not task.completed:
        logging.info(f"Executing task: {task.description}")
        # This is where the agent would use the page actions
        # For simplicity, we'll just pretend to run it.
        # await actions.send_prompt(task.description)
        # response = await actions.get_last_response()
        # logging.info(f"Got response: {response}")
        
        # Mark task as completed
        task.completed = True
        tasks[current_index] = task

    return {"tasks": tasks, "current_task_index": current_index + 1}

def should_continue_node(state: AgentState):
    """
    A conditional node that determines whether to continue to the next task
    or end the execution.
    """
    current_index = state.get("current_task_index", 0)
    tasks = state.get("tasks", [])
    
    if current_index >= len(tasks):
        return END
    return "execute_task"

def create_workflow(page_actions: GeminiPageActions):
    """
    Creates and configures the LangGraph StateGraph.
    """
    workflow = StateGraph(AgentState)

    # Bind the execute_task_node with the page_actions instance
    # LangGraph doesn't directly support passing extra args to nodes in this way,
    # so we use a lambda to create a closure.
    bound_execute_task_node = lambda state: execute_task_node(state, page_actions)

    workflow.add_node("execute_task", bound_execute_task_node)
    workflow.add_conditional_edges(
        "execute_task",
        should_continue_node,
        {
            "continue": "execute_task",
            END: END
        }
    )
    
    workflow.set_entry_point("execute_task")
    
    return workflow.compile()
