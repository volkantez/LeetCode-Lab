"""Submit saved solutions to LeetCode through HTTP endpoints.
This module uses direct requests with the user's personal LeetCode session
cookies. It is optional because it depends on LeetCode internals."""

from __future__ import annotations
import json
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen
from src.json_utils import write_compact_json
from src.llm_client import clean_generated_code
from src.problem_loader import Problem

class LeetCodeSubmissionError(RuntimeError):
    """Raised for authentication, networking, or judge-result failures."""

    pass

@dataclass(frozen=True)
class LeetCodeSubmissionResult:
    """Normalized LeetCode judge result plus the raw response payload."""

    problem_id: str
    title: str
    language: str
    solution_path: str
    status: str
    submission_id: int | None
    raw: dict[str, Any]

def submit_solution_to_leetcode(
    problem: Problem,
    solution_path: str | Path,
    *,
    env_path: str | Path = ".env",
    output_dir: str | Path,
    poll_interval_seconds: float = 2.0,
    timeout_seconds: float = 120.0
) -> LeetCodeSubmissionResult:
    """Submit a saved solution file and wait for the official judge result."""
    if not problem.source_url:
        raise LeetCodeSubmissionError(f"{problem.path} does not contain source_url.")
    source_url = _validated_leetcode_source_url(problem.source_url)

    solution_file = Path(solution_path)
    code = clean_generated_code(solution_file.read_text(encoding="utf-8"))
    language = problem.language.strip().lower()

    credentials = _load_leetcode_credentials(env_path)
    question_id = _fetch_leetcode_question_id(source_url, credentials)
    submit_payload = {"lang": language, "question_id": question_id, "typed_code": code}
    submit_url = f"{source_url.rstrip('/')}/submit/"
    submit_response = _request_json("POST", submit_url, credentials, source_url, submit_payload)
    submission_id = submit_response.get("submission_id")
    if not submission_id:
        raise LeetCodeSubmissionError(f"LeetCode did not return a submission_id: {submit_response}")

    raw_status = _poll_submission_status(
        int(submission_id),
        credentials,
        source_url,
        poll_interval_seconds=poll_interval_seconds,
        timeout_seconds=timeout_seconds
    )
    status = str(raw_status.get("status_msg") or raw_status.get("state") or "unknown")
    result = LeetCodeSubmissionResult(
        problem_id=problem.id,
        title=problem.title,
        language=language,
        solution_path=str(solution_file),
        status=status,
        submission_id=int(submission_id),
        raw=raw_status
    )

    output_path = Path(output_dir) / f"{problem.id}_{submission_id}.json"
    write_compact_json(output_path, {
        "problem_id": result.problem_id,
        "title": result.title,
        "language": result.language,
        "solution_path": result.solution_path,
        "status": result.status,
        "submission_id": result.submission_id,
        "raw": result.raw
    })
    return result

def _poll_submission_status(
    submission_id: int,
    credentials: dict[str, str],
    referer: str,
    *,
    poll_interval_seconds: float,
    timeout_seconds: float
) -> dict[str, Any]:
    """Poll LeetCode until the submission leaves PENDING/STARTED state."""
    status_url = f"https://leetcode.com/submissions/detail/{submission_id}/check/"
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        time.sleep(poll_interval_seconds)
        payload = _request_json("GET", status_url, credentials, referer)
        if payload.get("state") not in {"PENDING", "STARTED"}:
            return payload
    raise LeetCodeSubmissionError(f"Timed out waiting for LeetCode submission {submission_id}.")

def _fetch_leetcode_question_id(source_url: str, credentials: dict[str, str]) -> str:
    """Resolve LeetCode's internal questionId from the public problem slug."""
    slug = _slug_from_source_url(source_url)
    payload = {
        "operationName": "questionData",
        "variables": {"titleSlug": slug},
        "query": (
            "query questionData($titleSlug: String!) { "
            "question(titleSlug: $titleSlug) { questionId questionFrontendId titleSlug } "
            "}"
        )
    }
    data = _request_json("POST", "https://leetcode.com/graphql/", credentials, source_url, payload)
    question = data.get("data", {}).get("question")
    if not question or not question.get("questionId"):
        raise LeetCodeSubmissionError(f"Could not resolve LeetCode questionId for {slug}: {data}")
    return str(question["questionId"])

def _request_json(
    method: str,
    url: str,
    credentials: dict[str, str],
    referer: str,
    payload: dict[str, Any] | None = None
) -> dict[str, Any]:
    """Send an authenticated JSON request to LeetCode and parse the response."""
    _assert_safe_leetcode_url(url)
    body = None
    cookie_header = _build_cookie_header(credentials)
    headers = {
        "Accept": "application/json, text/javascript, */*; q=0.01",
        "Accept-Language": "en-US,en;q=0.9",
        "Content-Type": "application/json",
        "Cookie": cookie_header,
        "Origin": "https://leetcode.com",
        "Referer": referer,
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/125.0.0.0 Safari/537.36"
        ),
        "X-CSRFToken": credentials["CSRF_TOKEN"],
        "X-Requested-With": "XMLHttpRequest"
    }
    if payload is not None:
        body = json.dumps(payload).encode("utf-8")

    request = Request(url, data=body, headers=headers, method=method)
    try:
        with urlopen(request, timeout=20) as response:
            content = response.read().decode("utf-8")
            if _looks_like_cloudflare_challenge(content):
                raise LeetCodeSubmissionError(_cloudflare_message(url))
            return json.loads(content)
    except HTTPError as exc:
        details = exc.read().decode("utf-8", errors="replace")
        if exc.code == 429:
            raise LeetCodeSubmissionError(
                f"LeetCode rate limit exceeded for {url} (HTTP 429). Wait before retrying."
            ) from exc
        if _looks_like_cloudflare_challenge(details):
            raise LeetCodeSubmissionError(_cloudflare_message(url)) from exc
        raise LeetCodeSubmissionError(f"LeetCode HTTP {exc.code} for {url}: {details}") from exc
    except (URLError, TimeoutError) as exc:
        raise LeetCodeSubmissionError(f"Could not reach LeetCode: {exc}") from exc

def _validated_leetcode_source_url(source_url: str) -> str:
    """Accept only canonical https://leetcode.com problem URLs before sending cookies."""
    parsed = urlparse(source_url)
    if parsed.scheme != "https" or parsed.netloc != "leetcode.com":
        raise LeetCodeSubmissionError(
            f"Refusing to use non-LeetCode source_url for authenticated requests: {source_url}"
        )

    parts = [part for part in parsed.path.split("/") if part]
    if len(parts) < 2 or parts[0] != "problems":
        raise LeetCodeSubmissionError(f"Invalid LeetCode problem source_url: {source_url}")
    return f"https://leetcode.com/problems/{parts[1]}/"

def _assert_safe_leetcode_url(url: str) -> None:
    """Prevent authenticated requests from sending LeetCode cookies to other hosts."""
    parsed = urlparse(url)
    if parsed.scheme != "https" or parsed.netloc != "leetcode.com":
        raise LeetCodeSubmissionError(
            f"Refusing to send authenticated request to non-LeetCode URL: {url}"
        )

def _load_leetcode_credentials(env_path: str | Path) -> dict[str, str]:
    """Load the required LeetCode submission cookies from `.env` or environment."""
    values = dict(os.environ)
    path = Path(env_path)
    if path.exists():
        for raw_line in path.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            values[key.strip()] = value.strip().strip('"').strip("'")

    missing = [key for key in ("LEETCODE_SESSION", "CSRF_TOKEN") if not values.get(key)]
    if missing:
        joined = ", ".join(missing)
        raise LeetCodeSubmissionError(f"Missing {joined}. Add them to {env_path} or environment variables.")
    return {
        "LEETCODE_SESSION": values["LEETCODE_SESSION"],
        "CSRF_TOKEN": values["CSRF_TOKEN"],
    }

def _build_cookie_header(credentials: dict[str, str]) -> str:
    """Build the Cookie header from the required LeetCode credentials."""
    cookies = [
        f"csrftoken={credentials['CSRF_TOKEN']}",
        f"LEETCODE_SESSION={credentials['LEETCODE_SESSION']}"
    ]
    return "; ".join(cookies)

def _looks_like_cloudflare_challenge(content: str) -> bool:
    """Detect Cloudflare challenge pages returned instead of JSON."""
    lowered = content.lower()
    return any(marker in lowered for marker in (
        "challenges.cloudflare.com",
        "just a moment",
        "enable javascript and cookies",
        "__cf_chl",
    ))

def _cloudflare_message(url: str) -> str:
    """Explain Cloudflare blocks without dumping the full HTML challenge."""
    return (
        "LeetCode/Cloudflare blocked the direct HTTP request for "
        f"{url}. Refresh your LeetCode browser session, update the LeetCode "
        "cookies in `.env`, and retry. If Cloudflare continues to challenge the request, official "
        "submission is temporarily unavailable through direct HTTP requests."
    )

def _slug_from_source_url(source_url: str) -> str:
    """Extract the problem slug from a canonical LeetCode problem URL."""
    parsed = urlparse(source_url)
    parts = [part for part in parsed.path.split("/") if part]
    try:
        problem_index = parts.index("problems")
    except ValueError as exc:
        raise LeetCodeSubmissionError(f"Could not derive problem slug from source_url: {source_url}") from exc

    if problem_index + 1 >= len(parts):
        raise LeetCodeSubmissionError(f"Could not derive problem slug from source_url: {source_url}")
    return parts[problem_index + 1]
