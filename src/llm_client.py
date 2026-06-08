"""Minimal OpenAI API client for code generation.
The project avoids a hard dependency on the OpenAI Python SDK so the command-line
workflow stays lightweight. API credentials are read from `.env` or the process
environment."""

from __future__ import annotations
import json
import os
import socket
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

class LLMGenerationError(RuntimeError):
    """Raised when solution generation through the LLM API fails."""

    pass

@dataclass(frozen=True)
class GeneratedSolution:
    """Generated code plus model and raw provider response for debugging."""

    model: str
    code: str
    raw: dict[str, Any]

def generate_solution_with_openai(
    prompt: str,
    *,
    model: str = "gpt-5.2",
    env_path: str | Path = ".env",
    timeout_seconds: float = 180.0
) -> GeneratedSolution:
    """Send a prompt to the OpenAI Responses API and return cleaned code."""
    api_key = _load_openai_api_key(env_path)
    payload = {
        "model": model,
        "input": prompt
    }
    response = _post_json(
        "https://api.openai.com/v1/responses",
        payload,
        api_key=api_key,
        timeout_seconds=timeout_seconds
    )
    text = _extract_output_text(response)
    if not text.strip():
        raise LLMGenerationError("OpenAI returned an empty response.")
    return GeneratedSolution(
        model=model,
        code=clean_generated_code(text),
        raw=response
    )

def clean_generated_code(code: str) -> str:
    """Strip Markdown fences that models sometimes return despite instructions."""
    lines = code.strip().splitlines()
    if lines and lines[0].strip().startswith("```"):
        lines = lines[1:]
    if lines and lines[-1].strip().startswith("```"):
        lines = lines[:-1]
    if lines and lines[0].strip().lower() in {
        "c",
        "cpp",
        "c++",
        "java",
        "python",
        "python3",
        "py",
        "javascript",
        "typescript",
        "csharp",
        "c#",
        "go",
        "golang",
        "rust",
        "kotlin",
        "swift",
        "ruby",
        "scala",
        "php",
        "dart"
    }:
        lines = lines[1:]
    return "\n".join(lines).strip()

def _extract_output_text(response: dict[str, Any]) -> str:
    """Read text from both convenience and structured Responses API shapes."""
    if isinstance(response.get("output_text"), str):
        return response["output_text"]

    chunks: list[str] = []
    for item in response.get("output", []):
        for content in item.get("content", []):
            if content.get("type") in {"output_text", "text"} and isinstance(content.get("text"), str):
                chunks.append(content["text"])
    return "\n".join(chunks)

def _post_json(url: str, payload: dict[str, Any], *, api_key: str, timeout_seconds: float) -> dict[str, Any]:
    """POST a JSON request and surface provider errors as domain exceptions."""
    request = Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        },
        method="POST"
    )
    try:
        with urlopen(request, timeout=timeout_seconds) as response:
            return json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        details = exc.read().decode("utf-8", errors="replace")
        raise LLMGenerationError(f"OpenAI HTTP {exc.code}: {details}") from exc
    except (URLError, TimeoutError, socket.timeout) as exc:
        raise LLMGenerationError(f"Could not reach OpenAI API: {exc}") from exc

def _load_openai_api_key(env_path: str | Path) -> str:
    """Load OPENAI_API_KEY from `.env` first, falling back to environment vars."""
    values = dict(os.environ)
    path = Path(env_path)
    if path.exists():
        for raw_line in path.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            values[key.strip()] = value.strip().strip('"').strip("'")

    api_key = values.get("OPENAI_API_KEY")
    if not api_key:
        raise LLMGenerationError(f"Missing OPENAI_API_KEY. Add it to {env_path} or environment variables.")
    return api_key
