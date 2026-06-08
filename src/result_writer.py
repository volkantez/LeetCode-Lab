"""Append LeetCode submission summaries to CSV files."""

from __future__ import annotations
import csv
from datetime import datetime
from pathlib import Path
from typing import Any
from src.dataset_results import display_problem_id

LEETCODE_FIELDNAMES = [
    "problem_id",
    "title",
    "difficulty",
    "language",
    "status",
    "model",
    "runtime",
    "leetcode_status",
    "memory",
    "passed_tests",
    "submission_id",
    "solution_path",
    "source_url",
    "timestamp"
]

LEETCODE_DISPLAY_HEADER = [
    "ID",
    "Titel",
    "Schwierigkeit",
    "Sprache",
    "Test",
    "Model",
    "Laufzeit",
    "LeetCode Status",
    "Speicher",
    "Bestandene Tests",
    "Submission ID",
    "Solution Pfad",
    "Source URL",
    "Zeitpunkt"
]

def append_leetcode_result(path: str | Path, row: dict[str, Any]) -> None:
    """Append one compact LeetCode submission row for spreadsheet analysis."""
    _append_csv_row(
        path,
        LEETCODE_FIELDNAMES,
        _normalize_result_row(row),
        delimiter=";",
        header=LEETCODE_DISPLAY_HEADER
    )

def append_leetcode_success(
    path: str | Path,
    *,
    problem,
    result,
    solution_path: str | Path,
    model: str,
    passed_tests: str
) -> None:
    """Append one successful or evaluated LeetCode submission result row."""
    append_leetcode_result(path, {
        "problem_id": problem.id,
        "title": problem.title,
        "difficulty": problem.difficulty,
        "language": result.language,
        "status": "Passed" if result.status == "Accepted" else "Failed",
        "model": model,
        "runtime": result.raw.get("status_runtime", ""),
        "leetcode_status": result.status,
        "memory": result.raw.get("status_memory", ""),
        "passed_tests": passed_tests,
        "submission_id": result.submission_id or "",
        "solution_path": str(solution_path),
        "source_url": problem.source_url or "",
        "timestamp": datetime.now().isoformat(timespec="seconds")
    })

def append_leetcode_failure(
    path: str | Path,
    *,
    problem,
    solution_path: str | Path,
    model: str,
    leetcode_status: str
) -> None:
    """Append one failed LeetCode submission attempt to the result CSV."""
    append_leetcode_result(path, {
        "problem_id": problem.id,
        "title": problem.title,
        "difficulty": problem.difficulty,
        "language": problem.language,
        "status": "Failed",
        "model": model,
        "runtime": "",
        "leetcode_status": leetcode_status,
        "memory": "",
        "passed_tests": "",
        "submission_id": "",
        "solution_path": str(solution_path),
        "source_url": problem.source_url or "",
        "timestamp": datetime.now().isoformat(timespec="seconds")
    })

def _normalize_result_row(row: dict[str, Any]) -> dict[str, Any]:
    """Normalize shared result fields before they are written to CSV."""
    normalized = dict(row)
    normalized["problem_id"] = display_problem_id(str(normalized.get("problem_id", "")))
    return normalized

def _append_csv_row(
    path: str | Path,
    fieldnames: list[str],
    row: dict[str, Any],
    delimiter: str = ",",
    header: list[str] | None = None
) -> None:
    """Append one CSV row, creating parent folders and a header if needed."""
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    should_write_header = not output_path.exists() or output_path.stat().st_size == 0
    if output_path.exists() and output_path.stat().st_size > 0:
        _ensure_trailing_newline(output_path)

    with output_path.open("a", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, delimiter=delimiter)
        if should_write_header:
            if header:
                csv.writer(handle, delimiter=delimiter).writerow(header)
            else:
                writer.writeheader()
        writer.writerow({field: row.get(field, "") for field in fieldnames})

def _ensure_trailing_newline(path: Path) -> None:
    """Ensure appending starts on a fresh row even after manual Excel edits."""
    with path.open("rb+") as handle:
        handle.seek(0, 2)
        if handle.tell() == 0:
            return
        handle.seek(-1, 2)
        if handle.read(1) not in {b"\n", b"\r"}:
            handle.write(b"\n")
