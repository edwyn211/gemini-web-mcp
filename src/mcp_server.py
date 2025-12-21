import asyncio
import logging
from pathlib import Path
from typing import List, Dict, Any
from playwright.async_api import async_playwright, BrowserContext, Page, TimeoutError as PlaywrightTimeoutError
from fastmcp import FastMCP
from pydantic import BaseModel, Field
from starlette.responses import JSONResponse

from mcp_controller.actions import GeminiPageActions
from orchestrator.state import AgentState, Task
from orchestrator.graph import create_workflow
from utils.screenshot_manager import ScreenshotManager

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

AUTH_STATE_PATH = Path("auth_state.json")

# Initialize FastMCP server with HTTP transport
mcp = FastMCP("Gemini Web Agent")

# Global browser context (will be initialized on startup)
browser_context: BrowserContext = None
gemini_page: Page = None
gemini_actions: GeminiPageActions = None
screenshot_manager: ScreenshotManager = None


class TaskRequest(BaseModel):
    """Request model for task execution"""
    tasks: List[str] = Field(..., description="List of task descriptions to execute")
    tool: str | None = Field(None, description="Optional tool to use: 'canvas' or 'deep_research'")


class TaskResponse(BaseModel):
    """Response model for task execution"""
    status: str
    message: str
    tasks_completed: int
    results: List[Dict[str, Any]]


async def setup_browser_context(p) -> tuple[BrowserContext, Page]:
    """Sets up the Playwright browser context and page"""
    if not AUTH_STATE_PATH.exists():
         logging.warning(f"Auth file not found at {AUTH_STATE_PATH}. Attempting to run without auth (might fail).")

    logging.info("Launching browser...")
    # Use standard launch instead of persistent context for better Docker compatibility
    browser = await p.chromium.launch(
        headless=True,
        args=[
            "--disable-blink-features=AutomationControlled",
            "--no-sandbox",
            "--disable-infobars",
            "--disable-dev-shm-usage",
        ],
        ignore_default_args=["--enable-automation"]
    )
    
    # Create context with storage state if available
    context_args = {
        'viewport': {'width': 1920, 'height': 1080},
        'user_agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
    }
    
    if AUTH_STATE_PATH.exists():
        logging.info(f"Loading auth state from {AUTH_STATE_PATH}")
        context_args['storage_state'] = AUTH_STATE_PATH
        
    context = await browser.new_context(**context_args)
    page = await context.new_page()
    
    # Stealth scripts
    await page.add_init_script("""
        Object.defineProperty(navigator, 'webdriver', {
            get: () => undefined
        });
    """)
    
    # Navigate to Gemini
    logging.info("Navigating to Gemini...")
    try:
        await page.goto("https://gemini.google.com/")
        await page.wait_for_load_state("domcontentloaded", timeout=30000)
    except Exception as e:
        logging.warning(f"Warning: Page load issue: {e}")
    
    return context, page


async def execute_tasks_workflow(task_descriptions: List[str], tool: str | None = None) -> TaskResponse:
    """Execute a list of tasks using the Gemini agent workflow"""
    global gemini_actions, browser_context, gemini_page, screenshot_manager
    
    # Lazy initialization of browser
    if not gemini_actions:
        logging.info("Initializing browser on first request...")
        playwright = await async_playwright().start()
        browser_context, gemini_page = await setup_browser_context(playwright)
        gemini_actions = GeminiPageActions(gemini_page)
        screenshot_manager = ScreenshotManager()
        logging.info("Browser initialized successfully.")

    
    # Create tasks from descriptions
    tasks = [Task(description=desc, completed=False) for desc in task_descriptions]
    
    initial_state: AgentState = {
        "tasks": tasks,
        "current_task_index": 0
    }
    
    # Create workflow
    app = create_workflow(gemini_actions)
    
    # Execute workflow
    results = []
    current_state = initial_state
    
    logging.info(f"\nStarting workflow with {len(tasks)} tasks...")
    if tool:
        logging.info(f"Using tool: {tool}")
    
    # Step -1: Start new chat (with retries built-in)
    try:
        await gemini_actions.start_new_chat()
        await asyncio.sleep(2) # Wait for new chat to load
    except Exception as e:
        logging.error(f"❌ Failed to start new chat after retries: {e}")
        if screenshot_manager:
            await screenshot_manager.capture_error(gemini_page, "start_new_chat_workflow", e)
        # Continue anyway, might still work

    # Step 0: Ensure Reasoning mode is active (with retries built-in)
    try:
        await gemini_actions.ensure_reasoning_mode()
    except Exception as e:
        logging.error(f"❌ Failed to ensure Reasoning mode after retries: {e}")
        if screenshot_manager:
            await screenshot_manager.capture_error(gemini_page, "ensure_reasoning_mode_workflow", e)
        # Continue anyway, might still work in current mode

    
    # Step 1: Select tool if specified (with retries built-in)
    if tool:
        try:
            await gemini_actions.select_tool(tool)
        except Exception as e:
            logging.error(f"❌ Failed to select tool '{tool}' after retries: {e}")
            if screenshot_manager:
                await screenshot_manager.capture_error(gemini_page, f"select_tool_{tool}_workflow", e)
            # This is critical, return error
            return TaskResponse(
                status="error",
                message=f"Failed to select tool '{tool}': {str(e)}",
                tasks_completed=0,
                results=[{
                    "task_index": 0,
                    "description": "Tool selection",
                    "status": "error",
                    "response": str(e)
                }]
            )
    
    # Step 2: Process first task (send the query)
    if len(tasks) > 0:
        task_index = 0
        task = current_state["tasks"][task_index]
        
        logging.info(f"Processing task {task_index + 1}/{len(tasks)}: {task.description}")
        
        try:
            # Send the prompt
            await gemini_actions.send_prompt(task.description)
            
            # Step 3: If Deep Research, wait for plan and confirm (with retries built-in)
            if tool and tool.lower() == "deep_research":
                logging.info("🔍 Deep Research detected - waiting for plan...")
                try:
                    # Increased timeout for Deep Research plan generation
                    await gemini_actions.wait_for_deep_research_plan()
                    await gemini_actions.confirm_deep_research_plan()
                    logging.info("✅ Deep Research plan confirmed. Research is now running.")
                except Exception as dr_error:
                    logging.error(f"❌ Deep Research plan confirmation failed: {dr_error}")
                    if screenshot_manager:
                        await screenshot_manager.capture_error(gemini_page, "deep_research_plan_workflow", dr_error)
                    # Return error for Deep Research failures
                    return TaskResponse(
                        status="error",
                        message=f"Deep Research plan failed: {str(dr_error)}",
                        tasks_completed=0,
                        results=[{
                            "task_index": task_index,
                            "description": task.description,
                            "status": "error",
                            "response": f"Deep Research plan failed: {str(dr_error)}"
                        }]
                    )
            
            # Get response
            response_text = await gemini_actions.get_last_response()
            
            task.completed = True
            results.append({
                "task_index": task_index,
                "description": task.description,
                "status": "completed",
                "response": response_text
            })
            
            current_state["tasks"][task_index] = task
            current_state["current_task_index"] += 1
            
        except Exception as e:
            logging.error(f"Error processing task: {e}")
            results.append({
                "task_index": task_index,
                "description": task.description,
                "status": "error",
                "response": str(e)
            })
    
    logging.info("Workflow completed successfully.")
    
    return TaskResponse(
        status="success",
        message=f"Successfully processed {len(results)} tasks",
        tasks_completed=len([r for r in results if r["status"] == "completed"]),
        results=results
    )


@mcp.tool()
async def execute_gemini_tasks(tasks: List[str], tool: str | None = None) -> TaskResponse:
    """
    Execute a list of tasks or queries on the Gemini web interface. This tool can be used for internet searches,
    current news, or any general query you might have for Gemini.
    
    Args:
        tasks: List of task descriptions or queries to execute sequentially.
        tool: Optional tool to use.
              - 'canvas': Activates the Gemini Canvas tool for creative tasks.
              - 'deep_research': Activates the Gemini Deep Research tool for in-depth investigations.
              If no tool is specified, Gemini will respond based on the query, potentially using its general knowledge or web search capabilities.
        
    Returns:
        Dictionary containing execution status and results
    """
    try:
        return await execute_tasks_workflow(tasks, tool)
    except Exception as e:
        logging.exception("An error occurred in execute_gemini_tasks")
        return TaskResponse(
            status="error",
            message=str(e),
            tasks_completed=0,
            results=[]
        )


@mcp.custom_route("/tasks", methods=["POST"])
async def create_tasks_endpoint(request):
    """
    HTTP endpoint to execute Gemini tasks.
    
    POST /tasks
    {
        "tasks": ["task 1 description", "task 2 description"],
        "tool": "canvas" | "deep_research" | null  (optional)
    }
    """
    try:
        # Parse JSON body manually
        import json
        body = await request.body()
        data = json.loads(body)
        tasks = data.get("tasks", [])
        tool = data.get("tool", None)
        
        response = await execute_tasks_workflow(tasks, tool)
        return JSONResponse(response.model_dump())
    except Exception as e:
        logging.exception("An error occurred in the /tasks endpoint")
        return JSONResponse({
            "status": "error",
            "message": str(e),
            "tasks_completed": 0,
            "results": []
        }, status_code=500)


@mcp.custom_route("/health", methods=["GET"])
async def health_check(request):
    """Health check endpoint"""
    return JSONResponse({
        "status": "healthy",
        "browser_initialized": gemini_actions is not None,
        "auth_file_exists": AUTH_STATE_PATH.exists()
    })





if __name__ == "__main__":
    # Note: Browser will be initialized lazily on first request
    # to avoid blocking server startup
    logging.info("Starting MCP server...")
    logging.info("Browser will initialize on first task request")
    
    # Run the MCP server with HTTP transport
    mcp.run()
