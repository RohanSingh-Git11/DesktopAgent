from __future__ import annotations
import asyncio
import logging
from pathlib import Path
from typing import Callable, Dict, Any, List

from .models.settings import AgentSettings
from .state import StateCore, TaskStep
from .memory import GlobalMemory, MemoryEntry
from .learning import LearningSystem
from .vision import VisionSystem
from .planner import Planner
from .windows import WindowManager
from .executor import Executor
from .verifier import Verifier
from .recovery import RecoverySystem
from .finalizer import Finalizer

log = logging.getLogger(__name__)

class AgentRuntime:
    def __init__(
        self,
        settings: AgentSettings,
        llm_caller: Callable[[str], Any],
        approval_requester: Optional[Callable[[Any], Any]] = None,
        state_dir: Path = Path("data")
    ):
        self.settings = settings
        self.llm_caller = llm_caller
        self.approval_requester = approval_requester

        # Initialize sub-systems
        self.state = StateCore(state_dir / "state")
        self.memory = GlobalMemory(state_dir / "memory")
        self.learning = LearningSystem(state_dir / "learning")
        self.vision = VisionSystem(state_dir / "vision")
        self.windows = WindowManager()
        self.planner = Planner(llm_caller)
        self.executor = Executor(self.state, self.vision)
        self.verifier = Verifier(self.state, self.vision)
        self.recovery = RecoverySystem(self.state)
        self.finalizer = Finalizer(self.state, state_dir / "logs")

    def update_settings(self, settings: AgentSettings):
        self.settings = settings

    def quota_status(self) -> Dict[str, Any]:
        return self.settings.quota_status()

    async def run(self, goal: str, emit: Callable[[str, Any], None], request_id: str):
        self.state.reset()
        self.state.update(task_id=request_id, goal=goal)

        emit("agent_task_started", {"goal": goal})

        # 1. Planning Layer (Requirement 2)
        try:
            steps = await self.planner.decompose_task(goal)
            self.state.update(steps=steps)
            emit("agent_plan_generated", {"steps": [s.model_dump() for s in steps]})
        except Exception as e:
            emit("error", {"message": f"Planning failed: {e}"})
            return

        # 2. Execution Loop
        for i, step in enumerate(self.state.current.steps):
            self.state.update(current_step_index=i)
            self.state.set_step_status(i, "running")
            emit("agent_step_update", {
                "index": i,
                "status": "running",
                "all_steps": [s.model_dump() for s in self.state.current.steps]
            })

            success = False
            retries = 0
            max_retries = 2

            while not success and retries <= max_retries:
                try:
                    # Bind state before action (Requirement 12)
                    # For now, we assume binding happens during first execution or is pre-bound

                    # Execute
                    await self.executor.execute_step(step.description)

                    # Verify (Requirement 10)
                    if self.verifier.verify_step(step.description):
                        success = True
                        self.state.set_step_status(i, "done")
                    else:
                        raise Exception("Verification failed")

                except Exception as e:
                    retries += 1
                    decision = self.recovery.handle_failure(e)
                    emit("agent_recovery", {"index": i, "decision": decision, "attempt": retries})

                    if decision == "RETRY_STEP":
                        continue
                    else:
                        self.state.set_step_status(i, "failed")
                        break

            # Update UI with final step status
            emit("agent_step_update", {
                "index": i,
                "status": self.state.current.steps[i].status,
                "all_steps": [s.model_dump() for s in self.state.current.steps]
            })

            # Confidence update
            conf = self.vision.calculate_confidence(
                state_binding=self.state.current.is_bound,
                ui_stability=True,
                visual_clarity=1.0
            )
            self.state.update(confidence_score=conf)
            emit("agent_state_update", {
                "active_app": self.state.current.active_app,
                "confidence": conf
            })

            if self.state.current.steps[i].status == "failed":
                break

        # 3. Finalization (Requirement 8)
        result = self.finalizer.finalize_task()
        self.memory.record_task(MemoryEntry(
            task_id=request_id,
            goal=goal,
            steps=[s.model_dump() for s in self.state.current.steps],
            success=result["success"],
            final_output=result
        ))
        emit("agent_task_finished", {"result": result})
