"""Import LeetCode problems through LeetCode GraphQL and build problem JSON."""

from __future__ import annotations
import ast
import html
import json
import re
import socket
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen
from src.dataset_paths import VALID_LANGUAGE_SLUGS

GRAPHQL_URL = "https://leetcode.com/graphql/"

@dataclass(frozen=True)
class GraphQLImportResult:
    """Imported problem payload plus warnings that need user attention."""

    data: dict[str, Any]
    warnings: list[str]

@dataclass(frozen=True)
class ProblemListItem:
    """Small LeetCode problem-list entry used for configured batch imports."""

    frontend_id: int
    title: str
    slug: str
    difficulty: str
    is_paid_only: bool

@dataclass(frozen=True)
class ProblemImportPlan:
    """Configured problem selection plus items skipped before the limit was met."""

    selected: list[ProblemListItem]
    skipped_paid: list[ProblemListItem]

def load_import_config(path: str | Path = "LeetCodeConfig.json") -> dict[str, Any]:
    """Load the fixed LeetCode import configuration."""
    config_path = Path(path)
    if not config_path.exists():
        raise RuntimeError(f"Import config not found: {config_path}")
    return json.loads(config_path.read_text(encoding="utf-8"))

def plan_problems_from_config(config: dict[str, Any]) -> ProblemImportPlan:
    """Select importable problems and record paid-only problems that are skipped."""
    start_id = config.get("start_id")
    end_id = config.get("end_id")
    problems = _fetch_problem_list(max_frontend_id=int(end_id) if end_id is not None else None)
    difficulties = {str(item).lower() for item in config.get("difficulties", []) if item}
    exclude_paid = bool(config.get("exclude_paid", True))
    limit = config.get("limit")

    selected: list[ProblemListItem] = []
    skipped_paid: list[ProblemListItem] = []
    for problem in problems:
        if start_id is not None and problem.frontend_id < int(start_id):
            continue
        if end_id is not None and problem.frontend_id > int(end_id):
            continue
        if difficulties and problem.difficulty.lower() not in difficulties:
            continue
        if exclude_paid and problem.is_paid_only:
            skipped_paid.append(problem)
            continue
        selected.append(problem)
        if limit is not None and len(selected) >= int(limit):
            break
    return ProblemImportPlan(selected=selected, skipped_paid=skipped_paid)

def import_leetcode_problem(*, slug: str, output_language: str | None = None) -> GraphQLImportResult:
    """Import one LeetCode problem through GraphQL by title slug."""
    problem = _fetch_problem_data(slug)
    language = (output_language or str(problem.get("codeSnippets", [{}])[0].get("langSlug") or "unknown")).strip().lower()
    if output_language and language not in VALID_LANGUAGE_SLUGS:
        allowed = ", ".join(sorted(VALID_LANGUAGE_SLUGS))
        raise RuntimeError(
            f"Unsupported import language {output_language!r}. "
            f"Use canonical LeetCode language slugs: {allowed}."
        )
    code_template = _code_template_for_language(problem.get("codeSnippets", []), language)
    function_name, signature, signature_warning = _signature_from_template(code_template, language)
    try:
        source_id = int(problem.get("questionFrontendId") or problem.get("questionId"))
    except Exception:
        source_id = None

    data = _build_problem_data(
        slug=slug,
        title=problem.get("title") or slug,
        difficulty=problem.get("difficulty") or "Unknown",
        source_id=source_id,
        language=language,
        function_name=function_name,
        signature=signature,
        description_text=_html_to_text_preserving_sup(problem.get("content") or ""),
    )
    data["source"] = "leetcode-graphql-import"
    data["tags"] = [tag.get("name") for tag in problem.get("topicTags", []) if tag.get("name")]
    if code_template:
        data["code_template"] = code_template

    warnings = data.pop("_warnings")
    if signature_warning:
        warnings.append(signature_warning)
    return GraphQLImportResult(data=data, warnings=warnings)

def _fetch_problem_list(max_frontend_id: int | None = None) -> list[ProblemListItem]:
    """Fetch the LeetCode problem list used for configured imports."""
    problems: list[ProblemListItem] = []
    page_size = 100
    skip = 0
    while True:
        payload = {
            "operationName": "problemsetQuestionListV2",
            "variables": {
                "categorySlug": "algorithms",
                "skip": skip,
                "limit": page_size,
                "searchKeyword": "",
            },
            "query": (
                "query problemsetQuestionListV2($limit: Int, $searchKeyword: String, $skip: Int, "
                "$categorySlug: String) { "
                "problemsetQuestionListV2(limit: $limit, searchKeyword: $searchKeyword, "
                "skip: $skip, categorySlug: $categorySlug) { "
                "questions { questionFrontendId title titleSlug difficulty paidOnly } "
                "} "
                "}"
            ),
        }
        questions = _post_graphql(payload).get("data", {}).get("problemsetQuestionListV2", {}).get("questions", [])
        if not questions:
            break

        for question in questions:
            slug = question.get("titleSlug")
            if not slug:
                continue
            try:
                frontend_id = int(question.get("questionFrontendId"))
            except Exception:
                continue
            problems.append(
                ProblemListItem(
                    frontend_id=frontend_id,
                    title=question.get("title") or slug,
                    slug=slug,
                    difficulty=question.get("difficulty") or "Unknown",
                    is_paid_only=bool(question.get("paidOnly")),
                )
            )

        if max_frontend_id is not None and any(problem.frontend_id >= max_frontend_id for problem in problems):
            break
        if len(questions) < page_size:
            break
        skip += page_size

    problems.sort(key=lambda item: item.frontend_id)
    return problems

def _fetch_problem_data(slug: str) -> dict[str, Any]:
    """Fetch one LeetCode problem payload from GraphQL by title slug."""
    payload = {
        "operationName": "questionData",
        "variables": {"titleSlug": slug},
        "query": (
            "query questionData($titleSlug: String!) { "
            "question(titleSlug: $titleSlug) { "
            "questionId questionFrontendId title titleSlug difficulty content "
            "topicTags { name slug } "
            "codeSnippets { lang langSlug code } "
            "} "
            "}"
        ),
    }
    question = _post_graphql(payload).get("data", {}).get("question")
    if not question:
        raise RuntimeError(f"LeetCode GraphQL did not return problem data for slug {slug!r}.")
    return question

def _post_graphql(payload: dict[str, Any]) -> dict[str, Any]:
    """Send a GraphQL request to LeetCode and parse the JSON response."""
    request = Request(
        GRAPHQL_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Accept": "application/json",
            "Content-Type": "application/json",
            "Origin": "https://leetcode.com",
            "Referer": "https://leetcode.com/problemset/",
            "User-Agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/125.0.0.0 Safari/537.36"
            ),
        },
        method="POST",
    )
    try:
        with urlopen(request, timeout=20) as response:
            return json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        details = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"LeetCode GraphQL HTTP {exc.code}: {details}") from exc
    except (URLError, TimeoutError, socket.timeout) as exc:
        raise RuntimeError(f"Could not reach LeetCode GraphQL: {exc}") from exc

def _code_template_for_language(code_snippets: list[dict[str, Any]], language: str) -> str:
    """Return the LeetCode code template for the selected language."""
    snippet = next((item for item in code_snippets if item.get("langSlug") == language), None)
    if snippet:
        return snippet.get("code") or ""
    available = ", ".join(
        sorted({str(item.get("langSlug")).strip() for item in code_snippets if item.get("langSlug")})
    )
    raise RuntimeError(
        f"LeetCode did not provide a code template for language {language!r}. "
        f"Available templates: {available or 'none'}."
    )

def _html_to_text_preserving_sup(raw_html: str) -> str:
    """Convert HTML to text without losing `<sup>` exponent information."""
    text = re.sub(
        r"<sup[^>]*>\s*([^<]+?)\s*</sup>",
        lambda match: "^" + html.unescape(match.group(1).strip()),
        raw_html,
        flags=re.IGNORECASE,
    )
    text = re.sub(r"<br\s*/?>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"</(?:p|div|li|pre|h\d)>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"<[^>]+>", "", text)
    lines = [line.strip() for line in html.unescape(text).splitlines()]
    return "\n".join(line for line in lines if line).strip()

def _signature_from_template(code_template: str, language: str) -> tuple[str | None, str | None, str | None]:
    """Extract the callable name and signature from the LeetCode template."""
    if not code_template:
        return None, None, "Code template not found. Edit function_name and signature manually."

    if language in {"python", "python3"}:
        match = _find_python_solution_method(code_template)
        if match:
            signature = _drop_self_from_python_signature(match.group(0))
            return match.group(1), signature, None
        return None, None, "Python signature not found in code template."

    class_match = re.search(r"\bclass\s+([A-Za-z_][A-Za-z0-9_]*)", code_template)
    function_match = re.search(r"\b([A-Za-z_][A-Za-z0-9_]*)\s*\([^;{}]*\)\s*(?:\{|;)", code_template)
    name = class_match.group(1) if class_match else function_match.group(1) if function_match else None
    signature = next(
        (
            line.strip()
            for line in code_template.splitlines()
            if line.strip() and not line.strip().startswith("//") and not line.strip().startswith("#")
        ),
        None,
    )
    if name and signature:
        return name, signature, None
    if name:
        return name, code_template.strip(), None
    return "solution", code_template.strip(), None

def _find_python_solution_method(code_template: str) -> re.Match[str] | None:
    """Find the method declared inside LeetCode's `class Solution` template."""
    def_pattern = re.compile(
        r"^\s*def\s+([a-zA-Z_][a-zA-Z0-9_]*)\s*\([^)]*\)\s*(?:->\s*[^:]+)?\s*:",
        re.MULTILINE,
    )
    uncommented = "\n".join(line for line in code_template.splitlines() if not line.lstrip().startswith("#"))
    solution_match = re.search(r"^\s*class\s+Solution\b.*:", uncommented, flags=re.MULTILINE)
    if solution_match:
        method_match = def_pattern.search(uncommented, solution_match.end())
        if method_match:
            return method_match
    return def_pattern.search(uncommented)

def _drop_self_from_python_signature(signature: str) -> str:
    """Convert LeetCode's method signature to the prompt function signature."""
    match = re.match(r"\s*def\s+([a-zA-Z_][a-zA-Z0-9_]*)\s*\((.*)\)\s*(->\s*[^:]+)?\s*:", signature)
    if not match:
        return signature
    name, params, return_type = match.groups()
    parts = [part.strip() for part in params.split(",") if part.strip()]
    if parts and parts[0] == "self":
        parts = parts[1:]
    suffix = f" {return_type}" if return_type else ""
    return f"def {name}({', '.join(parts)}){suffix}:"

def _build_problem_data(
    *,
    slug: str,
    title: str,
    difficulty: str,
    source_id: int | None,
    language: str,
    function_name: str | None,
    signature: str | None,
    description_text: str,
) -> dict[str, Any]:
    """Build the repository's JSON problem structure from imported data."""
    warnings: list[str] = []
    if signature is None:
        signature = "def solution(...):"
        warnings.append("No Python signature found. Edit signature and function_name before evaluation.")
    if function_name is None:
        function_name = "solution"
        warnings.append("No function name found. Edit function_name before evaluation.")
    if "..." in signature:
        warnings.append("Placeholder signature detected. Edit the generated JSON before evaluation.")

    tests, warnings = _extract_examples(description_text)
    return {
        "id": _problem_id(slug, source_id),
        "title": title,
        "difficulty": difficulty or "Unknown",
        "source": "leetcode-assisted-import",
        "source_id": source_id,
        "source_url": f"https://leetcode.com/problems/{slug}/",
        "tags": [],
        "language": language,
        "function_name": function_name,
        "signature": signature,
        "description": _compact_description(description_text, title),
        "constraints": _dedupe_constraints(_extract_constraints(description_text)),
        "tests": tests,
        "evaluation": {"comparison": "exact", "timeout_ms": 2000},
        "_warnings": warnings,
    }

def _problem_id(slug: str, source_id: int | None) -> str:
    """Build the public problem id used as filename stem."""
    base = slug.replace("-", "_")
    return f"[{source_id}]_{base}" if source_id is not None else base

def _compact_description(text: str, title: str | None = None) -> str:
    """Keep only the prose problem statement before examples and metadata."""
    before_examples = re.split(r"\bExample\s+\d+\s*:", text, maxsplit=1, flags=re.IGNORECASE)[0]
    skip = {"Easy", "Medium", "Hard", "Topics", "Companies", "Hint", "premium lock icon"}
    lines = [
        line
        for raw_line in before_examples.splitlines()
        if (line := raw_line.strip())
        and line not in skip
        and (not title or line != title)
        and not re.match(r"^\d+\.\s+", line)
    ]
    return " ".join(lines)

def _extract_constraints(text: str) -> list[str]:
    """Extract the Constraints block from LeetCode description text."""
    match = re.search(
        r"Constraints\s*:?\s*(.*?)(?=\n\s*(?:Seen this question|Accepted|Acceptance Rate|Topics|Companies|Hint|Similar Questions|Discussion|Copyright)\b|\s*$)",
        text,
        re.IGNORECASE | re.DOTALL,
    )
    if not match:
        return []
    return [
        line
        for raw_line in match.group(1).splitlines()
        if (line := raw_line.strip().lstrip("-•* ").strip())
    ]

def _dedupe_constraints(constraints: list[str]) -> list[str]:
    """Remove repeated constraints while preserving original order."""
    result, seen = [], set()
    for constraint in constraints:
        if constraint.lower() != "constraints:" and constraint not in seen:
            seen.add(constraint)
            result.append(constraint)
    return result

def _extract_examples(text: str) -> tuple[list[dict[str, Any]], list[str]]:
    """Extract public sample tests from Example blocks."""
    warnings: list[str] = []
    examples: list[dict[str, Any]] = []
    pattern = re.compile(
        r"Example\s+(\d+)\s*:\s*(.*?)(?=Example\s+\d+\s*:|Constraints\s*:|$)",
        re.IGNORECASE | re.DOTALL,
    )
    for match in pattern.finditer(text):
        number = match.group(1)
        body = match.group(2)
        input_match = re.search(r"Input\s*:\s*(.*?)(?=\n\s*Output\s*:)", body, re.IGNORECASE | re.DOTALL)
        output_match = re.search(
            r"Output\s*:\s*(.*?)(?=\n\s*Explanation\s*:|\n\s*Constraints\s*:|$)",
            body,
            re.IGNORECASE | re.DOTALL,
        )
        if not input_match or not output_match:
            warnings.append(f"Example {number}: input/output could not be parsed")
            continue
        try:
            test_input = _parse_input(input_match.group(1).strip())
            expected = _parse_value(output_match.group(1).strip())
        except ValueError as exc:
            warnings.append(f"Example {number}: {exc}")
            continue
        examples.append({"name": f"example_{number}", "input": test_input, "expected": expected})
    if not examples:
        warnings.append("No examples were extracted. Review the generated JSON before generation.")
    return examples, warnings

def _parse_input(raw: str) -> dict[str, Any]:
    """Parse LeetCode's named input format into keyword arguments."""
    raw = _one_line(raw)
    if "=" not in raw:
        raise ValueError("input does not contain named arguments")

    result: dict[str, Any] = {}
    for part in _split_top_level(raw):
        if "=" not in part:
            raise ValueError(f"could not parse input part: {part}")
        key, value = part.split("=", 1)
        result[key.strip()] = _parse_value(value.strip())
    return result


def _parse_value(raw: str) -> Any:
    """Parse one LeetCode literal into a Python value."""
    normalized = _one_line(raw)
    normalized = re.sub(r"\btrue\b", "True", normalized, flags=re.IGNORECASE)
    normalized = re.sub(r"\bfalse\b", "False", normalized, flags=re.IGNORECASE)
    normalized = re.sub(r"\bnull\b", "None", normalized, flags=re.IGNORECASE)
    try:
        return ast.literal_eval(normalized)
    except Exception as exc:
        raise ValueError(f"could not parse value '{raw}'") from exc

def _one_line(text: str) -> str:
    """Collapse multiline snippets so regex and literal parsing are simpler."""
    return " ".join(line.strip() for line in text.strip().splitlines()).strip()

def _split_top_level(raw: str) -> list[str]:
    """Split comma-separated input assignments without breaking nested lists."""
    parts: list[str] = []
    start = 0
    depth = 0
    quote: str | None = None
    escape = False

    for index, char in enumerate(raw):
        if quote:
            if escape:
                escape = False
            elif char == "\\":
                escape = True
            elif char == quote:
                quote = None
            continue

        if char in ("'", '"'):
            quote = char
        elif char in "[({":
            depth += 1
        elif char in "])}":
            depth -= 1
        elif char == "," and depth == 0:
            parts.append(raw[start:index].strip())
            start = index + 1

    parts.append(raw[start:].strip())
    return [part for part in parts if part]
