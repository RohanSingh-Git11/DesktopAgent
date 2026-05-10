from __future__ import annotations
import asyncio
import logging
import json
import os
from pathlib import Path
from typing import Dict, Any, List, Optional
from playwright.async_api import async_playwright, Page, BrowserContext

log = logging.getLogger(__name__)

class BrowserEngine:
    def __init__(self):
        self.playwright = None
        self.browser = None
        self.context = None
        self.pages: List[Page] = []
        self.active_page: Optional[Page] = None
        self.refs: Dict[str, Any] = {}

    async def start(self, headless: bool = False, session_path: Optional[Path] = None):
        self.playwright = await async_playwright().start()

        if session_path:
            self.context = await self.playwright.chromium.launch_persistent_context(
                user_data_dir=str(session_path),
                headless=headless,
                viewport={'width': 1280, 'height': 720},
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                accept_downloads=True
            )
        else:
            self.browser = await self.playwright.chromium.launch(headless=headless)
            self.context = await self.browser.new_context(
                viewport={'width': 1280, 'height': 720},
                accept_downloads=True
            )

        self.active_page = await self.context.new_page()
        self.pages.append(self.active_page)

    async def stop(self):
        if self.browser:
            await self.browser.close()
        elif self.context:
            await self.context.close()

        if self.playwright:
            await self.playwright.stop()

        self.browser = None
        self.playwright = None
        self.context = None
        self.active_page = None
        self.pages = []

    async def new_tab(self, url: Optional[str] = None):
        if not self.context: await self.start()
        page = await self.context.new_page()
        self.pages.append(page)
        self.active_page = page
        if url:
            await page.goto(url, wait_until="networkidle")
        return page

    async def switch_tab(self, index: int):
        if 0 <= index < len(self.pages):
            self.active_page = self.pages[index]
            await self.active_page.bring_to_front()

    async def navigate(self, url: str):
        if not self.active_page: await self.start()
        try:
            await self.active_page.goto(url, wait_until="networkidle", timeout=60000)
        except Exception as e:
            log.warning(f"Navigation to {url} timed out or failed: {e}")

    async def get_ai_snapshot(self, format: str = "ai") -> str:
        if not self.active_page: return "No active page"

        script = """
        (snapshotFormat) => {
            const items = [];
            const interactive = document.querySelectorAll('button, a, input, select, textarea, [role="button"], [role="link"], [role="checkbox"], [role="menuitem"], [role="tab"], [onclick]');

            interactive.forEach((el, index) => {
                const rect = el.getBoundingClientRect();
                const style = window.getComputedStyle(el);

                if (rect.width > 0 && rect.height > 0 && style.visibility !== 'hidden' && style.display !== 'none' && rect.top >= 0 && rect.left >= 0) {
                    const refId = snapshotFormat === 'aria' ? `ax${index}` : `e${index}`;
                    el.setAttribute('data-agent-ref', refId);

                    items.push({
                        ref: refId,
                        tag: el.tagName.toLowerCase(),
                        text: (el.innerText || el.value || el.placeholder || el.getAttribute('aria-label') || '').trim().substring(0, 150),
                        role: el.getAttribute('role') || el.type || el.tagName.toLowerCase(),
                        url: el.tagName === 'A' ? el.href : null,
                        checked: el.checked || el.getAttribute('aria-checked') === 'true',
                        disabled: el.disabled || el.getAttribute('aria-disabled') === 'true'
                    });
                }
            });
            return items;
        }
        """
        elements = await self.active_page.evaluate(script, format)

        snapshot_lines = []
        self.refs = {el['ref']: el for el in elements}

        for el in elements:
            state = []
            if el['checked']: state.append("CHECKED")
            if el['disabled']: state.append("DISABLED")
            state_str = f" [{', '.join(state)}]" if state else ""

            url_info = f" (URL: {el['url']})" if el['url'] and len(el['url']) < 100 else ""
            snapshot_lines.append(f"[{el['ref']}] {el['tag']}({el['role']}): \"{el['text']}\"{state_str}{url_info}")

        return "\\n".join(snapshot_lines)

    async def act(self, action: str, ref_id: str, payload: Optional[str] = None):
        if not self.active_page: return False
        selector = f'[data-agent-ref="{ref_id}"]'

        try:
            if action == "click":
                await self.active_page.click(selector, timeout=10000)
            elif action == "double_click":
                await self.active_page.dblclick(selector, timeout=10000)
            elif action == "right_click":
                await self.active_page.click(selector, button="right", timeout=10000)
            elif action == "type":
                await self.active_page.fill(selector, payload or "", timeout=10000)
            elif action == "press":
                await self.active_page.press(selector, payload or "Enter", timeout=10000)
            elif action == "hover":
                await self.active_page.hover(selector, timeout=10000)
            elif action == "scroll":
                await self.active_page.locator(selector).scroll_into_view_if_needed()
            elif action == "select":
                await self.active_page.select_option(selector, payload)
            return True
        except Exception as e:
            log.warning(f"Browser action {action} failed on {ref_id}: {e}")
            return False

    async def wait_for(self, state: str = "networkidle", timeout: int = 30000):
        if self.active_page:
            await self.active_page.wait_for_load_state(state, timeout=timeout)
