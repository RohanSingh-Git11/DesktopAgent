from __future__ import annotations
import asyncio
import logging
import sys
import re
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
        self.workshop = SkillWorkshop(state_dir / "state")
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

        # 1. Full Task Decomposition
        try:
            steps = await self.planner.decompose_task(goal)
            task_steps = []
            for i, s in enumerate(steps):
                if isinstance(s, str):
                    task_steps.append(TaskStep(index=i, description=s))
                elif isinstance(s, TaskStep):
                    task_steps.append(s)
                else:
                    task_steps.append(TaskStep(index=i, description=str(s)))

            self.state.update(steps=task_steps)
            res = emit("agent_plan_generated", {"steps": [s.model_dump() for s in self.state.current.steps]})
            if asyncio.iscoroutine(res): await res
        except Exception as e:
            log.error(f"Planning failed: {e}")
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
                    # Deterministic Environment Detection
                    desc = step.description.lower()

                    # A. Browser Context
                    if any(x in desc for x in ["browser", "http", "www", "site", "web"]):
                         if not self.browser.context: await self.browser.start(headless=False)
                         if any(x in desc for x in ["open", "navigate", "go to"]):
                              url_match = re.search(r'https?://[^\s]+', desc)
                              url = url_match.group(0) if url_match else "https://google.com"
                              await self.browser.navigate(url)

                         snapshot = await self.browser.get_ai_snapshot()
                         res = emit("agent_observation", {"type": "browser", "snapshot": snapshot})
                         if asyncio.iscoroutine(res): await res

                    # B. Desktop Context
                    elif any(x in desc for x in ["window", "app", "desktop", "excel", "powerpoint", "word", "notepad"]):
                         # Extract app name from description
                         app_match = re.search(r'(excel|powerpoint|word|notepad|chrome|slack|discord)', desc)
                         if app_match:
                             self.windows.bind_to_window(app_match.group(0))
                             snapshot = self.windows.get_desktop_snapshot()
                             res = emit("agent_observation", {"type": "desktop", "snapshot": snapshot})
                             if asyncio.iscoroutine(res): await res

                    # Native OS Execution
                    await self.executor.execute_step(step.description)

                    # Strict Verification
                    if self.verifier.verify_step(step.description):
                        success = True
                        self.state.set_step_status(i, "done")
                    else:
                        raise Exception("UI verification failed - state did not reach expected target")

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

            if self.state.current.steps[i].status == "failed":
                break

        # 3. Final Output & Skill Recording
        result = self.finalizer.finalize_task()
        if result["success"]:
            # Record successful workflow as a Skill
            self.workshop.save_skill(Skill(
                name=goal,
                description=f"High-fidelity workflow for: {goal}",
                steps=[s.description for s in self.state.current.steps],
                app_context=self.state.current.active_app
            ))

        res = emit("agent_task_finished", {"result": result})
        if asyncio.iscoroutine(res): await res
        if self.browser.context: await self.browser.stop()
