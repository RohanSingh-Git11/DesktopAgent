from __future__ import annotations
import os
import json
import csv
from pathlib import Path
from .models import ScrapeResult

class JSONLWriter:
    def __init__(self, path: Path):
        self.path = path

    def write(self, result: ScrapeResult):
        with open(self.path, "a", encoding="utf-8") as f:
            f.write(json.dumps(result.to_dict()) + "\n")

class CSVWriter:
    def __init__(self, path: Path):
        self.path = path
        self.initialized = path.exists()

    def write(self, result: ScrapeResult):
        data = result.to_dict()
        fieldnames = list(data.keys())
        with open(self.path, "a", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            if not self.initialized:
                writer.writeheader()
                self.initialized = True
            writer.writerow(data)

class OutputManager:
    def __init__(self, output_dir: str, output_format: str, run_id: str):
        self.output_dir = Path(output_dir) / run_id
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.format = output_format
        self.results = []

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.finalise()

    def write(self, result: ScrapeResult):
        self.results.append(result)
        if self.format in ["jsonl", "both"]:
            JSONLWriter(self.output_dir / "results.jsonl").write(result)
        if self.format in ["csv", "both"]:
            CSVWriter(self.output_dir / "results.csv").write(result)

    def finalise(self):
        summary_path = self.output_dir / "summary.json"
        total = len(self.results)
        ok = sum(1 for r in self.results if r.ok)
        summary = {
            "total": total,
            "ok": ok,
            "errors": total - ok,
            "success_rate": (ok / total * 100.0) if total > 0 else 0.0
        }
        with open(summary_path, "w") as f:
            json.dump(summary, f, indent=2)
