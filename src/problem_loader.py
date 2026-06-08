"""Load problem JSON files into a typed object used by the pipeline."""

from __future__ import annotations
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

@dataclass(frozen=True)
class Problem:
    """Normalized representation of one programming task."""

    id: str
    title: str
    difficulty: str
    language: str
    function_name: str
    signature: str
    description: str
    tests: list[dict[str, Any]]
    constraints: list[str]
    tags: list[str]
    source: str
    source_url: str | None
    evaluation: dict[str, Any]
    code_template: str
    path: Path

def load_problem(path: str | Path) -> Problem:
    """Read and validate one problem JSON file."""
    problem_path = Path(path)
    data = json.loads(problem_path.read_text(encoding="utf-8"))

    required = [
        "id",
        "title",
        "difficulty",
        "language",
        "function_name",
        "signature",
        "description",
        "tests"
    ]
    missing = [key for key in required if key not in data]
    if missing:
        raise ValueError(f"{problem_path} is missing required fields: {', '.join(missing)}")

    return Problem(
        id=data["id"],
        title=data["title"],
        difficulty=data["difficulty"],
        language=data["language"],
        function_name=data["function_name"],
        signature=data["signature"],
        description=data["description"],
        tests=data["tests"],
        constraints=data.get("constraints", []),
        tags=data.get("tags", []),
        source=data.get("source", "custom"),
        source_url=data.get("source_url"),
        evaluation=data.get("evaluation", {}),
        code_template=data.get("code_template", ""),
        path=problem_path
    )

def load_problems(dataset: str | Path) -> list[Problem]:
    """Load every JSON problem in a dataset directory, or one JSON file."""
    dataset_path = Path(dataset)
    if dataset_path.is_file():
        return [load_problem(dataset_path)]

    problem_files = sorted(dataset_path.glob("*.json"))
    if not problem_files:
        raise ValueError(f"No JSON problem files found in {dataset_path}")

    return [load_problem(path) for path in problem_files]