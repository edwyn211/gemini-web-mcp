"""Task execution service - handles the Gemini workflow logic."""

import asyncio
import logging
import uuid
from typing import Dict, List, Optional

from models.responses import TaskResponse, TaskResult
from mcp_controller.actions import GeminiPageActions
from mcp_controller.session_manager import SessionManager
from orchestrator.state import AgentState, Task
from services.redis_service import RedisService, get_redis_service

logger = logging.getLogger(__name__)

# Active task sessions tracking
active_task_sessions: Dict[str, GeminiPageActions] = {}


class TaskService:
    """Handles task execution workflow."""

    def __init__(self, session_manager: SessionManager):
        self.session_manager = session_manager
        self._redis: Optional[RedisService] = None

    async def get_redis(self) -> RedisService:
        """Get Redis service instance."""
        if self._redis is None:
            self._redis = await get_redis_service()
        return self._redis

    async def execute_tasks(
        self,
        task_descriptions: List[str],
        tool: Optional[str] = None,
        new_chat: bool = True,
        request_id: Optional[str] = None,
    ) -> TaskResponse:
        """
        Execute a list of tasks using the Gemini agent workflow.
        
        This is the main workflow orchestrator that:
        1. Acquires a browser session
        2. Checks/refreshes authentication
        3. Executes tasks sequentially
        4. Handles tool selection (Canvas, Deep Research)
        5. Stores results in Redis
        """
        global active_task_sessions

        if not request_id:
            request_id = str(uuid.uuid4())

        # Acquire session
        if new_chat:
            logger.info("🧠 CHAT MGMT: Acquiring new isolated WORKER session...")
            gemini_actions = await self.session_manager.get_worker_session()
        else:
            logger.info("🧠 CHAT MGMT: Acquiring shared MAIN session...")
            gemini_actions = await self.session_manager.get_main_session()

        logger.info(
            f"🧠 CHAT MGMT: Session acquired. Current URL: {gemini_actions.page.url if gemini_actions.page else 'N/A'}"
        )

        # Auto-auth check
        gemini_actions = await self._ensure_authenticated(gemini_actions, new_chat)

        screenshot_manager = gemini_actions.screenshot_manager

        # Register active session
        active_task_sessions[request_id] = gemini_actions

        # Use session lock for concurrent requests
        async with gemini_actions.execution_lock:
            try:
                tasks = [Task(description=desc, completed=False) for desc in task_descriptions]
                initial_state: AgentState = {"tasks": tasks, "current_task_index": 0}

                # Save initial processing state
                redis = await self.get_redis()
                initial_response = TaskResponse(
                    status="processing",
                    message=f"Starting processing of {len(tasks)} tasks.",
                    tasks_completed=0,
                    total_tasks=len(tasks),
                    results=[],
                    request_id=request_id,
                )
                await redis.save_task(request_id, initial_response)
                logger.info(f"✅ Task initialized in Redis with ID: {request_id}")

                # Execute workflow
                results = []

                logger.info(f"\n🧠 CHAT MGMT: Starting workflow with {len(tasks)} tasks...")
                if tool:
                    logger.info(f"🧠 CHAT MGMT: Using tool: {tool}")

                # Setup: new chat, reasoning mode, tool selection
                if new_chat:
                    await self._setup_new_chat(gemini_actions, tool, screenshot_manager)

                # Process tasks
                if tasks:
                    result = await self._process_task(
                        gemini_actions, tasks[0], 0, tool, new_chat, screenshot_manager
                    )
                    results.append(result)

                # Calculate final status
                completed_count = len([r for r in results if r.status == "completed"])
                overall_status = (
                    "success" if completed_count == len(tasks)
                    else "partial_success" if completed_count > 0
                    else "error"
                )

                current_url = gemini_actions.page.url if gemini_actions.page else None

                # Save final result
                final_response = TaskResponse(
                    status=overall_status,
                    message=f"Processed {len(results)} tasks. {completed_count}/{len(tasks)} successful.",
                    tasks_completed=completed_count,
                    total_tasks=len(tasks),
                    results=results,
                    chat_url=current_url,
                    request_id=request_id,
                )
                await redis.save_task(request_id, final_response)
                logger.info(f"✅ Final response saved to Redis with ID: {request_id}")

                return final_response

            except Exception as e:
                logger.error(f"Critical error in execute_tasks: {e}")
                error_response = TaskResponse(
                    status="error",
                    message=f"Critical workflow error: {str(e)}",
                    tasks_completed=0,
                    total_tasks=len(task_descriptions),
                    results=[],
                    request_id=request_id,
                )
                try:
                    redis = await self.get_redis()
                    await redis.save_task(request_id, error_response)
                except Exception:
                    pass
                return error_response

            finally:
                # Cleanup
                if request_id in active_task_sessions:
                    del active_task_sessions[request_id]

                if new_chat:
                    await self.session_manager.release_session(gemini_actions)

    async def _ensure_authenticated(
        self, gemini_actions: GeminiPageActions, new_chat: bool
    ) -> GeminiPageActions:
        """Check and refresh authentication if needed."""
        try:
            logger.info("Checking session authentication status...")
            auth_status = await gemini_actions.check_session_status()
            
            if not auth_status.get("authenticated", False):
                logger.warning("⚠️ Session unauthenticated or expired.")
                # Could trigger refresh here if implemented
                
        except Exception as e:
            logger.error(f"Error during auto-auth check: {e}")
        
        return gemini_actions

    async def _setup_new_chat(
        self, gemini_actions: GeminiPageActions, tool: Optional[str], screenshot_manager
    ):
        """Setup new chat with reasoning mode and tool selection."""
        try:
            await gemini_actions.start_new_chat()
            await asyncio.sleep(2)
        except Exception as e:
            logger.error(f"❌ Failed to start new chat: {e}")
            if screenshot_manager:
                await screenshot_manager.capture_error(
                    gemini_actions.page, "start_new_chat_workflow", e
                )

        try:
            await gemini_actions.ensure_reasoning_mode()
        except Exception as e:
            logger.error(f"❌ Failed to ensure Reasoning mode: {e}")
            if screenshot_manager:
                await screenshot_manager.capture_error(
                    gemini_actions.page, "ensure_reasoning_mode_workflow", e
                )

        if tool:
            try:
                await gemini_actions.select_tool(tool)
            except Exception as e:
                logger.error(f"❌ Failed to select tool '{tool}': {e}")
                if screenshot_manager:
                    await screenshot_manager.capture_error(
                        gemini_actions.page, f"select_tool_{tool}_workflow", e
                    )
                raise

    async def _process_task(
        self,
        gemini_actions: GeminiPageActions,
        task: Task,
        task_index: int,
        tool: Optional[str],
        new_chat: bool,
        screenshot_manager,
    ) -> TaskResult:
        """Process a single task."""
        logger.info(f"Processing task {task_index + 1}: {task.description}")

        try:
            skipped_prompt = False

            # Check for ongoing generation if continuing chat
            if not new_chat and await gemini_actions.is_generating():
                logger.info("⏳ Generation in progress. Waiting...")
                wait_timeout = 1800000 if tool and tool.lower() == "deep_research" else 300000
                success, details = await gemini_actions.validator.validate_generation_complete(
                    timeout=wait_timeout
                )
                if success:
                    logger.info("✓ Ongoing generation finished.")
                    skipped_prompt = True

            if not skipped_prompt:
                await gemini_actions.send_prompt(task.description)

            # Handle Deep Research plan confirmation
            if tool and tool.lower() == "deep_research" and not skipped_prompt:
                logger.info("🔍 Deep Research detected - waiting for plan...")
                try:
                    await gemini_actions.wait_for_deep_research_plan()
                    await gemini_actions.confirm_deep_research_plan()
                    logger.info("✅ Deep Research plan confirmed.")
                except Exception as dr_error:
                    logger.error(f"❌ Deep Research plan failed: {dr_error}")
                    return TaskResult(
                        task_index=task_index,
                        description=task.description,
                        status="error",
                        error=str(dr_error),
                        metadata={"tool": tool, "phase": "deep_research_plan"},
                    )

            # Get response
            response_timeout = (
                1800000 if (tool and tool.lower() == "deep_research") or skipped_prompt
                else 240000
            )
            response_text = await gemini_actions.get_last_response(
                timeout=response_timeout, tool=tool
            )

            logger.info(f"✅ TASK COMPLETED: {task.description}")

            return TaskResult(
                task_index=task_index,
                description=task.description,
                status="completed",
                result=response_text,
                metadata={"tool": tool, "skipped_prompt": skipped_prompt},
            )

        except Exception as e:
            logger.error(f"Error processing task: {e}")
            return TaskResult(
                task_index=task_index,
                description=task.description,
                status="error",
                error=str(e),
                metadata={"tool": tool},
            )

    async def get_task_status(
        self, request_id: str, offset: int = 0, max_chars: int = 100000
    ) -> Optional[TaskResponse]:
        """Get task status from Redis."""
        redis = await self.get_redis()
        return await redis.get_task(request_id)

    def is_task_generating(self, request_id: str) -> bool:
        """Check if a task is currently generating."""
        if request_id in active_task_sessions:
            try:
                # This is sync check, async check would need await
                return True  # If in active sessions, assume generating
            except Exception:
                pass
        return False
