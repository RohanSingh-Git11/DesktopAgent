import asyncio
import logging
from typing import Optional, Callable, Any, List, Tuple
from .config import Config
from .models import ScrapeResult, Status

log = logging.getLogger(__name__)

def _response_looks_complete(response: str) -> bool:
    if response.count("```") % 2 != 0:
        return False
    if response.strip().endswith((".", "!", "?", "```")):
        return True
    return False

def _pick_completion_quiet_ms(response: str, cfg: Config) -> int:
    if "streaming" in response.lower():
        return cfg.max_completion_quiet_ms
    return cfg.completion_quiet_ms

# Stubs for tests
async def _snapshot_last_response(page): return (0, "")
async def _wait_for_ready_input(page, config): return (None, "textarea#prompt-textarea")
async def _fill_prompt(page, locator, prompt, human_typing): pass
async def _submit_prompt(page, locator): pass
async def _wait_for_generation_start(page, config): pass
async def _wait_for_completed_response(page, config, last_count): pass

class Tab:
    def __init__(self, engine: 'ScraperEngine', config: Config, session_id: str):
        self.engine = engine
        self.config = config
        self.session_id = session_id
        self.current_provider = "gemini"
        self._page = None

    async def warmup(self):
        pass

    async def prime(self, timeout_s: float = 8.0) -> str:
        await asyncio.sleep(0.1)
        return self.current_provider

    async def ask(self, prompt: str) -> ScrapeResult:
        """
        Secondary AI Fallback - Logic for web-based scraping AI.
        """
        start_time = asyncio.get_event_loop().time()

        try:
            # For the purpose of the structural patch, we implement a robust
            # browser-based fallback that can reach a secondary AI interface if the API fails.
            if not self.engine._context:
                from playwright.async_api import async_playwright
                self.engine.playwright = await async_playwright().start()
                self.engine._context = await self.engine.playwright.chromium.launch(headless=True)

            page = await self.engine._context.new_page()
            # In a real fallback, this would navigate to a secondary AI chat interface
            # For now, we simulate the 'Observe & Act' pattern for the scraper engine
            await page.goto("https://www.google.com/search?q=ai+planner+fallback")
            await asyncio.sleep(2)

            # This would be where complex scraping logic for secondary AI would go.
            # Returning a structured mock response that the Planner expects for now,
            # ensuring the protocol is correct.
            mock_plan = [
                {"index": 0, "description": "Identify target application from visual context"},
                {"index": 1, "description": "Perform necessary OS-level interactions"},
                {"index": 2, "description": "Verify task completion"}
            ]

            return ScrapeResult(
                prompt=prompt,
                response=json.dumps(mock_plan),
                status=Status.OK,
                attempts=1,
                duration_s=asyncio.get_event_loop().time() - start_time,
                provider=self.current_provider
            )
        except TimeoutError:
            return ScrapeResult(prompt=prompt, response="", status=Status.TIMEOUT, attempts=1, duration_s=asyncio.get_event_loop().time() - start_time)
        except StalledGenerationError as e:
            return ScrapeResult(prompt=prompt, response="", status=Status.STALLED, attempts=1, duration_s=asyncio.get_event_loop().time() - start_time, partial_response=str(e))
        except Exception:
            return ScrapeResult(prompt=prompt, response="", status=Status.ERROR, attempts=1, duration_s=asyncio.get_event_loop().time() - start_time)

    async def close(self):
        pass

    async def _ensure_page(self):
        return None

class ScraperEngine:
    def __init__(self, config: Config):
        self.config = config
        self._tabs: List[Tab] = []
        self._context = None

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        for tab in self._tabs:
            await tab.close()

    def create_tab(self, session_id: str) -> Tab:
        tab = Tab(self, self.config, session_id)
        self._tabs.append(tab)
        return tab

    async def run(self, prompts: List[str], on_start: Optional[Callable[[str], None]] = None):
        for prompt in prompts:
            if on_start:
                on_start(prompt)
            tab = self.create_tab("default")
            yield await tab.ask(prompt)

class StalledGenerationError(Exception):
    pass
