from __future__ import annotations
import asyncio
import logging
import sys
from pathlib import Path
from typing import Callable, Dict, Any, List, Optional

from .models.settings import AgentSettings
from .state import StateCore, TaskStep
from .memory import GlobalMemory, MemoryEntry
from .learning import LearningSystem, FailurePattern
from .vision import VisionSystem
from .planner import Planner
from .windows import WindowManager
from .executor import Executor
from .verifier import Verifier
from .recovery import RecoverySystem
from .finalizer import Finalizer
from .skills import SkillWorkshop, Skill
from .browser import BrowserEngine

log = logging.getLogger(__name__)

class AgentRuntime:
    def __init__(
        self,
        settings: AgentSettings,
        llm_caller: Optional[Callable[[str], Any]] = None,
        state_dir: Path = Path("data")
    ):
        self.settings = settings
        self.llm_caller = llm_caller
        self.state_dir = state_dir

        # Initialize sub-systems
        self.state = StateCore(state_dir / "state")
        self.memory = GlobalMemory(state_dir / "memory")
        self.learning = LearningSystem(state_dir / "learning")
        self.workshop = SkillWorkshop(state_dir / "state") # Shared DB
        self.vision = VisionSystem(state_dir / "vision")
        self.windows = WindowManager()
        self.browser = BrowserEngine()
        self.planner = Planner(api_key=settings.api_key, skill_workshop=self.workshop)
        self.executor = Executor(self.state, self.vision)
        self.verifier = Verifier(self.state, self.vision)
        self.recovery = RecoverySystem(self.state)
        self.finalizer = Finalizer(self.state, state_dir / "logs")

    def update_settings(self, settings: AgentSettings):
        self.settings = settings
        self.planner = Planner(api_key=settings.api_key, skill_workshop=self.workshop)

    async def run(self, goal: str, emit: Callable[[str, Any], None], request_id: str):
        self.state.reset()
        self.state.update(task_id=request_id, goal=goal)

        res = emit("agent_task_started", {"goal": goal})
        if asyncio.iscoroutine(res): await res

        # 1. Full Task Decomposition (Requirement 2)
        try:
            steps = await self.planner.decompose_task(goal)
            self.state.update(steps=steps)
            res = emit("agent_plan_generated", {"steps": [s.model_dump() for s in steps]})
            if asyncio.iscoroutine(res): await res
        except Exception as e:
            res = emit("error", {"message": f"Planning failed: {e}"})
            if asyncio.iscoroutine(res): await res
            return

        # 2. Execution Loop
        for i in range(len(self.state.current.steps)):
            self.state.update(current_step_index=i)
            self.state.set_step_status(i, "running")

            step = self.state.current.steps[i]
            res = emit("agent_step_update", {
                "index": i,
                "status": "running",
                "all_steps": [s.model_dump() for s in self.state.current.steps]
            })
            if asyncio.iscoroutine(res): await res

            success = False
            retries = 0
            max_retries = 2

            while not success and retries <= max_retries:
                try:
                    # Deterministic Interaction Detection
                    desc = step.description.lower()
                    if "browser" in desc or "http" in desc or "www" in desc:
                         # Use AI-Native Browser Logic
                         if not self.browser.browser: await self.browser.start(headless=True)
                         if "open" in desc or "navigate" in desc:
                              url = "https://" + desc.split("to")[-1].strip() if "to" in desc else "https://google.com"
                              await self.browser.navigate(url)

                         snapshot = await self.browser.get_ai_snapshot()
                         res = emit("agent_observation", {"type": "browser", "snapshot": snapshot})
                         if asyncio.iscoroutine(res): await res

                    # Native OS Execution
                    await self.executor.execute_step(step.description)

                    # Strict Verification
                    if self.verifier.verify_step(step.description):
                        success = True
                        self.state.set_step_status(i, "done")
                    else:
                        raise Exception("UI verification failed")

                except Exception as e:
                    retries += 1
                    decision = self.recovery.handle_failure(e)
                    res = emit("agent_recovery", {"index": i, "decision": decision, "attempt": retries})
                    if asyncio.iscoroutine(res): await res

                    if decision == "RETRY_STEP":
                        continue
                    else:
                        self.state.set_step_status(i, "failed")
                        break

            res = emit("agent_step_update", {
                "index": i,
                "status": self.state.current.steps[i].status,
                "all_steps": [s.model_dump() for s in self.state.current.steps]
            })
            if asyncio.iscoroutine(res): await res

        # 3. Final Output & Skill Recording
        result = self.finalizer.finalize_task()
        if result["success"]:
            # Requirement 13: Self-Learning (Autonomous Skill Workshop)
            self.workshop.save_skill(Skill(
                name=goal,
                description=f"Automated workflow for: {goal}",
                steps=[s.description for s in self.state.current.steps],
                app_context=self.state.current.active_app
            ))

        res = emit("agent_task_finished", {"result": result})
        if asyncio.iscoroutine(res): await res
        if self.browser.browser: await self.browser.stop()
