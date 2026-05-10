from __future__ import annotations
import json
import logging
from typing import List, Optional, Callable, Any
from google import genai
from google.genai import types
from .state import TaskStep, AgentState
from .learning import LearningSystem
from .skills import SkillWorkshop, Skill
from scraper import Config as ScraperConfig
from scraper.engine import ScraperEngine

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
        Then tries Primary AI (Gemini).
        Finally falls back to Scraper-based secondary AI.
        """
        app = context.get("active_app") if context else None

        # 1. Skill Workshop (Memory Layer)
        if self.skill_workshop:
            learned = self.skill_workshop.find_skill(goal, app)
            if learned:
                log.info(f"Using learned skill for goal: {goal}")
                return [TaskStep(index=i, description=desc) for i, desc in enumerate(learned.steps)]

        log.info(f"Generating new plan for goal: {goal}")

        prompt = f"""
Decompose the following desktop task into a step-by-step plan.
Goal: {goal}
App Context: {app}
Running Apps: {context.get('running_apps', []) if context else []}

Return a JSON list of objects with "index" and "description" keys.
"""

        # 2. Primary AI (Gemini API)
        if self.client:
            try:
                response = self.client.models.generate_content(
                    model=self.model,
                    contents=prompt,
                    config=types.GenerateContentConfig(response_mime_type="application/json")
                )
                plan_data = json.loads(response.text)
                return [TaskStep(index=item["index"], description=item["description"]) for item in plan_data]
            except Exception as e:
                log.warning(f"Primary AI planning failed, falling back: {e}")

        # 3. Secondary AI Fallback (Scraper-based)
        log.info("Attempting fallback to Secondary AI (Scraper)")
        try:
            scraper_cfg = ScraperConfig(output_dir="data/scraper")
            async with ScraperEngine(scraper_cfg) as engine:
                tab = engine.create_tab("planner-fallback")
                # Wrap prompt to ensure JSON response from fallback
                fallback_prompt = prompt + "\nRespond ONLY with the raw JSON list."
                result = await tab.ask(fallback_prompt)

                if result.response:
                    # Try to extract JSON from markdown if needed
                    json_str = result.response
                    if "```json" in json_str:
                        json_str = json_str.split("```json")[1].split("```")[0].strip()
                    elif "```" in json_str:
                        json_str = json_str.split("```")[1].split("```")[0].strip()

                    plan_data = json.loads(json_str)
                    return [TaskStep(index=item["index"], description=item["description"]) for item in plan_data]
        except Exception as e:
            log.error(f"Fallback planning also failed: {e}")

        # 4. Final Safety Net (Basic Plan)
        return [
            TaskStep(index=0, description=f"Analyze current state for: {goal}"),
            TaskStep(index=1, description=f"Perform actions to achieve: {goal}"),
            TaskStep(index=2, description="Verify success")
        ]
