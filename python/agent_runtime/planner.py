from __future__ import annotations
import json
import logging
from typing import List, Optional, Callable, Any
from google import genai
from google.genai import types
from .state import TaskStep, AgentState
from .learning import LearningSystem
from .skills import SkillWorkshop, Skill

log = logging.getLogger(__name__)

class Planner:
    def __init__(self, api_key: str, skill_workshop: Optional[SkillWorkshop] = None, model: str = "gemini-2.0-flash"):
        self.client = None
        if api_key and api_key != "mock-key":
            self.client = genai.Client(api_key=api_key)
        self.skill_workshop = skill_workshop
        self.model = model

    async def decompose_task(self, goal: str, context: Optional[dict] = None) -> List[TaskStep]:
        """
        Takes a goal and returns a list of TaskSteps.
        First checks the Skill Workshop for a known successful skill.
        """
        app = context.get("active_app") if context else None

        if self.skill_workshop:
            learned = self.skill_workshop.find_skill(goal, app)
            if learned:
                log.info(f"Using learned skill for goal: {goal}")
                return [TaskStep(index=i, description=desc) for i, desc in enumerate(learned.steps)]

        log.info(f"Generating new plan for goal: {goal}")

        # If no client, return mock steps
        if not self.client:
             return [
                 TaskStep(index=0, description=f"Analyze current window for '{goal}'"),
                 TaskStep(index=1, description=f"Execute interaction on target elements"),
                 TaskStep(index=2, description="Verify goal accomplishment")
             ]

        prompt = f"""
Decompose the following desktop task into a step-by-step plan.
Goal: {goal}
App Context: {app}

Return a JSON list of objects with "index" and "description" keys.
"""
        try:
            response = self.client.models.generate_content(
                model=self.model,
                contents=prompt,
                config=types.GenerateContentConfig(response_mime_type="application/json")
            )
            plan_data = json.loads(response.text)
            return [TaskStep(index=item["index"], description=item["description"]) for item in plan_data]
        except Exception as e:
            log.error(f"Planning failed: {e}")
            return [TaskStep(index=0, description=f"Execute: {goal}")]
