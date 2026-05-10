from __future__ import annotations
import asyncio
import logging
from pathlib import Path
from typing import Dict, Any, List, Optional
from playwright.async_api import async_playwright, Page, BrowserContext

log = logging.getLogger(__name__)

class BrowserEngine:
    def __init__(self):
        self.playwright = None
        self.browser = None
        self.context = None
        self.page = None
        self.refs: Dict[str, Any] = {}

    async def start(self, headless: bool = False):
        self.playwright = await async_playwright().start()
        self.browser = await self.playwright.chromium.launch(headless=headless)
        self.context = await self.browser.new_context(viewport={'width': 1280, 'height': 720})
        self.page = await self.context.new_page()

    async def stop(self):
        if self.browser:
            await self.browser.close()
        if self.playwright:
            await self.playwright.stop()
        # Reset state to allow re-initialization
        self.browser = None
        self.playwright = None
        self.context = None
        self.page = None

    async def navigate(self, url: str):
        if not self.page: await self.start()
        await self.page.goto(url, wait_until="networkidle")

    async def get_ai_snapshot(self) -> str:
        if not self.page: return "No page active"

        script = """
        () => {
            const items = [];
            const interactive = document.querySelectorAll('button, a, input, select, textarea, [role="button"], [role="link"], [onclick]');
            interactive.forEach((el, index) => {
                const rect = el.getBoundingClientRect();
                if (rect.width > 0 && rect.height > 0) {
                    const refId = `e${index}`;
                    el.setAttribute('data-agent-ref', refId);
                    items.push({
                        ref: refId,
                        tag: el.tagName.toLowerCase(),
                        text: el.innerText || el.placeholder || el.getAttribute('aria-label') || '',
                        role: el.getAttribute('role') || el.type || ''
                    });
                }
            });
            return items;
        }
        """
        elements = await self.page.evaluate(script)

        snapshot_lines = []
        self.refs = {el['ref']: el for el in elements}

        for el in elements:
            snapshot_lines.append(f"[{el['ref']}] {el['tag']}({el['role']}): \"{el['text'][:50]}\"")

        return "\\n".join(snapshot_lines)

    async def click(self, ref_id: str):
        if not self.page: return
        selector = f'[data-agent-ref="{ref_id}"]'
        await self.page.click(selector)

    async def type(self, ref_id: str, text: str, submit: bool = False):
        if not self.page: return
        selector = f'[data-agent-ref="{ref_id}"]'
        await self.page.fill(selector, text)
        if submit:
            await self.page.press(selector, "Enter")

    async def screenshot(self, path: Path):
        if self.page:
            await self.page.screenshot(path=str(path))
