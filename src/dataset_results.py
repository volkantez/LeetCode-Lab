"""Helpers for dataset resume state and submission status formatting."""

from __future__ import annotations

import csv
import re
from pathlib import Path

def classify_submit_failure(message: str) -> str:
    """Convert low-level submission errors into spreadsheet-friendly statuses."""
    lowered = message.lower()
    if "rate limit" in lowered or "http 429" in lowered:
        return "Rate Limited"
    if "cloudflare" in lowered or "just a moment" in lowered or "__cf_chl" in lowered:
        return "Blocked by Cloudflare"
    if "not authenticated" in lowered or "user is not authenticated" in lowered:
        return "Not Authenticated"
    if "missing" in lowered and ("leetcode_session" in lowered or "csrf_token" in lowered):
        return "Missing Credentials"
    if "timed out" in lowered:
        return "Submission Timeout"
    if "permissions" in lowered:
        return "Permission Denied"
    return "Submission Failed"

def format_passed_tests(result) -> str:
    """Format LeetCode's passed/total test counters for spreadsheet output."""
    total_correct = result.raw.get("total_correct")
    total_tests = result.raw.get("total_testcases")
    if total_correct is None or total_tests is None:
        return ""
    return f"{total_correct}/{total_tests}"

def load_solved_problem_ids(path: str | Path, language: str) -> set[str]:
    """Return dataset problem ids already accepted for one language."""
    csv_path = Path(path)
    if not csv_path.exists():
        return set()

    target_language = language.strip().lower()
    solved_ids: set[str] = set()
    with csv_path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle, delimiter=";")
        for row in reader:
            row_language = str(row.get("Sprache", "")).strip().lower()
            row_status = str(row.get("Test", "")).strip().lower()
            if row_language != target_language or row_status != "passed":
                continue
            problem_id = str(row.get("ID", "")).strip()
            if problem_id:
                solved_ids.add(problem_id)
    return solved_ids

def display_problem_id(problem_id: str) -> str:
    """Normalize `[2370]_slug` ids to the spreadsheet id `2370`."""
    match = re.match(r"^\[(\d+)\]_", problem_id)
    return match.group(1) if match else problem_id