from __future__ import annotations
import asyncio
import time
import logging
from typing import List, Callable, Any, Dict
from pydantic import BaseModel

log = logging.getLogger(__name__)

class BackgroundJob(BaseModel):
    id: str
    goal: str
    interval_seconds: float
    last_run: float = 0
    active: bool = True

class ProactiveScheduler:
    def __init__(self, run_callback: Callable[[str], Any]):
        self.jobs: List[BackgroundJob] = []
        self.run_callback = run_callback
        self._running = False

    def add_job(self, job_id: str, goal: str, interval: float):
        self.jobs.append(BackgroundJob(id=job_id, goal=goal, interval_seconds=interval))
        log.info(f"Added proactive job: {job_id} ({goal}) every {interval}s")

    async def start(self):
        self._running = True
        log.info("Proactive Scheduler started")
        while self._running:
            now = time.time()
            for job in self.jobs:
                if job.active and (now - job.last_run) >= job.interval_seconds:
                    log.info(f"Triggering background job: {job.id}")
                    job.last_run = now
                    try:
                        if asyncio.iscoroutinefunction(self.run_callback):
                            await self.run_callback(job.goal)
                        else:
                            self.run_callback(job.goal)
                    except Exception as e:
                        log.error(f"Job {job.id} failed: {e}")

            await asyncio.sleep(0.1)

    def stop(self):
        self._running = False
