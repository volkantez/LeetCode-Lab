"""Helpers for dataset- and language-specific pipeline paths."""

from __future__ import annotations
from pathlib import Path

VALID_LANGUAGE_SLUGS = {
    "c",
    "cpp",
    "java",
    "python",
    "python3",
    "javascript",
    "typescript",
    "csharp",
    "golang",
    "rust",
    "kotlin",
    "swift",
    "ruby",
    "scala",
    "php",
    "dart",
}

def configured_dataset_name(config: dict) -> str:
    """Return the configured dataset name used for derived data paths."""
    return str(config.get("dataset", "default")).strip() or "default"

def configured_languages(config: dict) -> list[str]:
    """Return configured language names from the required `languages` list."""
    languages = config.get("languages")
    if languages is None:
        raise ValueError("Missing required config field: languages")
    if isinstance(languages, str):
        languages = [languages]
    result = [str(language).strip().lower() for language in languages if str(language).strip()]
    if not result:
        raise ValueError("Config field 'languages' must contain at least one language.")
    invalid = [language for language in result if language not in VALID_LANGUAGE_SLUGS]
    if invalid:
        joined = ", ".join(invalid)
        allowed = ", ".join(sorted(VALID_LANGUAGE_SLUGS))
        raise ValueError(
            f"Unsupported language value(s) in config: {joined}. "
            f"Use canonical LeetCode language slugs: {allowed}."
        )
    return result

def dataset_root(config: dict) -> Path:
    """Return the root directory for one named dataset."""
    base_dir = Path(config.get("data_dir", "datasets"))
    return base_dir / configured_dataset_name(config)

def language_problem_dir(config: dict, language: str) -> Path:
    """Return where imported problem JSON files are stored for one language."""
    return dataset_root(config) / "problems" / language

def language_solutions_dir(config: dict, language: str) -> Path:
    """Return where generated solution files are stored for one language."""
    return dataset_root(config) / "solutions" / language

def language_submission_dir(config: dict, language: str) -> Path:
    """Return where detailed LeetCode submission payloads are stored."""
    return dataset_root(config) / "results" / "leetcode_submissions" / language

def results_csv_path(config: dict) -> Path:
    """Return the compact CSV result path shared by all languages of a dataset."""
    return dataset_root(config) / "results" / "leetcode_results.csv"

def solution_extension(language: str) -> str:
    """Return a readable file extension for generated solution files."""
    extensions = {
        "c": ".c",
        "cpp": ".cpp",
        "java": ".java",
        "python": ".py",
        "python3": ".py",
        "javascript": ".js",
        "typescript": ".ts",
        "csharp": ".cs",
        "golang": ".go",
        "rust": ".rs",
        "kotlin": ".kt",
        "swift": ".swift",
        "ruby": ".rb",
        "scala": ".scala",
        "php": ".php",
        "dart": ".dart",
    }
    return extensions.get(language.strip().lower(), ".txt")
