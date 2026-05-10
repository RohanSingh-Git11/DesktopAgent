from __future__ import annotations
import json
import logging
from typing import List, Optional, Callable, Any
from google import genai
from google.genai import types
from .state import TaskStep, AgentState
from .learning import LearningSystem

log = logging.getLogger(__name__)

class Planner:
    def __init__(self, api_key: str, learning_system: Optional[LearningSystem] = None, model: str = "gemini-2.0-flash"):
        self.client = genai.Client(api_key=api_key)
        self.learning_system = learning_system
        self.model = model

    async def decompose_task(self, goal: str, context: Optional[dict] = None) -> List[TaskStep]:
        """
        Takes a goal and returns a list of TaskSteps.
        First checks the Learning System for a known successful plan.
        """
        app = context.get("active_app") if context else None

        if self.learning_system:
            learned = self.learning_system.find_matching_procedure(goal, app)
            if learned:
                log.info(f"Using learned procedure for goal: {goal}")
                return [TaskStep(index=i, description=desc) for i, desc in enumerate(learned.steps)]

        log.info(f"Generating new plan for goal: {goal}")
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
