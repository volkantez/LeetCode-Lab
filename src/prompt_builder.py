"""Build deterministic LLM prompts from stored problem JSON data."""

from __future__ import annotations
from pathlib import Path
import json
from src.problem_loader import Problem

def build_prompt(problem: Problem, template_path: str | Path = "default_prompt.txt") -> str:
    """Render one problem into the configured prompt template."""
    template = Path(template_path).read_text(encoding="utf-8")
    constraints = "\n".join(f"- {item}" for item in problem.constraints) or "- Not specified"
    tests = _format_tests(problem)
    interface = (problem.code_template or "").strip()
    if not interface:
        raise ValueError(f"{problem.id} is missing code_template.")

    return template.format(
        language=problem.language,
        signature=problem.signature,
        interface=interface,
        description=problem.description,
        constraints=constraints,
        tests=tests,
        title=problem.title,
        tags=", ".join(problem.tags)
    )

def _format_tests(problem: Problem) -> str:
    """Render public sample tests into a compact prompt section."""
    if not problem.tests:
        return "- No public sample tests available"

    lines = []
    for test in problem.tests:
        lines.append(f"- {test.get('name', 'test')}:")
        lines.append(f"  input = {json.dumps(test['input'], ensure_ascii=False)}")
        lines.append(f"  expected = {json.dumps(test['expected'], ensure_ascii=False)}")
    return "\n".join(lines)
