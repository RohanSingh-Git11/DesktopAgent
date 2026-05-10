import logging
import os
from pathlib import Path
import sys

from .config import Config
from .models import ScrapeResult, Status
from .output import OutputManager

def get_logger(name: str):
    return logging.getLogger(name)

def configure_logging(level: str = "INFO", log_dir: str = "logs", console_stream = sys.stdout):
    Path(log_dir).mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=getattr(logging, level),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        handlers=[
            logging.StreamHandler(console_stream),
            logging.FileHandler(Path(log_dir) / "app.log")
        ]
    )

def print_banner(prompt_count: int, concurrency: int, run_id: str):
    print(f"--- Scraper Run {run_id} ---")
    print(f"Prompts: {prompt_count}, Concurrency: {concurrency}")

def print_result(prompt, response, status, attempt, duration, index, total):
    print(f"[{index}/{total}] {status.upper()}: {prompt[:30]}... ({duration:.2f}s)")

def print_summary(ok, errors, total_s, output_dir, run_id):
    print(f"--- Summary ---")
    print(f"OK: {ok}, Errors: {errors}, Total Time: {total_s:.2f}s")
    print(f"Results in: {output_dir}/{run_id}")

# PDF stubs
def extract_pdf_pages(path): return []
def build_page_chunks(pages, pages_per_prompt): return []
def merge_scan_results(results): return {}
def write_scan_artifacts(output_dir, pdf_path, report): return {}
