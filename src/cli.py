"""Minimal command-line interface for configured LeetCode batch runs."""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

from src.dataset_paths import (
    configured_dataset_name,
    configured_languages,
    language_problem_dir,
    language_solutions_dir,
    language_submission_dir,
    results_csv_path,
    solution_extension,
)
from src.dataset_results import (
    classify_submit_failure,
    display_problem_id,
    format_passed_tests,
    load_solved_problem_ids,
)
from src.json_utils import write_compact_json
from src.leetcode_graphql_importer import import_leetcode_problem, load_import_config, plan_problems_from_config
from src.leetcode_submitter import LeetCodeSubmissionError, submit_solution_to_leetcode
from src.llm_client import LLMGenerationError, generate_solution_with_openai
from src.problem_loader import load_problems
from src.prompt_builder import build_prompt
from src.result_writer import append_leetcode_failure, append_leetcode_success

def main() -> None:
    """Parse the two supported public workflow commands."""
    parser = argparse.ArgumentParser(description="Import configured LeetCode problems and submit the dataset.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser(
        "import.dataset",
        help="Import LeetCode problems selected in LeetCodeConfig.json."
    )
    subparsers.add_parser(
        "submit.dataset",
        help="Generate and submit every imported problem from the configured dataset."
    )

    args = parser.parse_args()

    if args.command == "import.dataset":
        _import_configured_dataset()
        return

    if args.command == "submit.dataset":
        _submit_configured_dataset()
        return

def _import_configured_dataset() -> None:
    """Import all LeetCode problems selected by the project config."""
    config = load_import_config()
    dataset_name = configured_dataset_name(config)
    languages = configured_languages(config)
    plan = plan_problems_from_config(config)
    for problem in plan.skipped_paid:
        print(f"Skipping [{problem.frontend_id}] {problem.title}: paid-only LeetCode problem.")

    total_imported = 0
    for language in languages:
        print()
        print(f"=== Importing dataset '{dataset_name}' in {language} ===")
        output_dir = language_problem_dir(config, language)
        imported_count = 0
        for problem in plan.selected:
            result = import_leetcode_problem(slug=problem.slug, output_language=language)
            output_path = output_dir / f"{result.data['id']}.json"
            write_compact_json(output_path, result.data)
            imported_count += 1
            total_imported += 1
            print(f"Problem JSON written to {output_path}")
            for warning in result.warnings:
                print(f"WARNING: {warning}")
        print(f"Imported {imported_count} problem(s) for {language}.")
    print(f"Imported {total_imported} language-specific problem file(s).")

def _submit_configured_dataset() -> None:
    """Generate and submit solutions for every configured dataset language."""
    config = load_import_config()
    dataset_name = configured_dataset_name(config)
    for language in configured_languages(config):
        dataset = language_problem_dir(config, language)
        runtime = _resolve_runtime(config, language)
        print()
        print(f"=== Submitting dataset '{dataset_name}' in {language} ===")
        problems = load_problems(dataset)
        solved_problem_ids = load_solved_problem_ids(runtime["leetcode_results"], language)
        pending_problems = [
            problem for problem in problems if display_problem_id(problem.id) not in solved_problem_ids
        ]
        skipped_as_solved = len(problems) - len(pending_problems)
        if skipped_as_solved:
            print(f"Skipping {skipped_as_solved} already solved problem(s) for {language}.")
        if not pending_problems:
            print(f"No pending problems for {language}.")
            continue
        _solve_and_submit_batch(pending_problems, runtime)

def _resolve_runtime(config: dict, language: str) -> dict[str, str | float | Path]:
    """Resolve concrete runtime values for one dataset language."""
    return {
        "template": config.get("template", "default_prompt.txt"),
        "solutions_dir": language_solutions_dir(config, language),
        "env": config.get("env", ".env"),
        "model": config.get("model", "gpt-5.2"),
        "api_timeout": float(config.get("api_timeout", 180.0)),
        "submission_output_dir": language_submission_dir(config, language),
        "leetcode_results": results_csv_path(config),
        "submission_delay": float(config.get("submission_delay", 10.0)),
    }

def _solve_and_submit_batch(problems, runtime: dict[str, str | float | Path]) -> None:
    """Solve and submit all supported problems in sequence."""
    generated_count = 0
    failed_count = 0
    skipped_count = 0
    for index, problem in enumerate(problems, start=1):
        if index > 1:
            print()
        print(f"=== {index}/{len(problems)} {problem.id} ===")

        # Skip tasks where the stored interface gives us no callable target to generate.
        data = json.loads(Path(problem.path).read_text(encoding="utf-8"))
        code_template = data.get("code_template") or ""
        if "class " not in code_template and data.get("function_name") in {"", None, "__init__"}:
            skipped_count += 1
            print(f"Skipping {problem.id}: unsupported Python LeetCode template.")
            continue

        try:
            solution_path = _generate_and_save_solution(problem, runtime)
        except LLMGenerationError as exc:
            failed_count += 1
            print(f"API solution generation failed for {problem.id}: {exc}")
            continue

        generated_count += 1
        print(f"Solution written to {solution_path}")
        submit_status = _submit_and_print(problem, solution_path, runtime)
        if submit_status in {"Rate Limited", "Not Authenticated"}:
            print(f"Stopping batch because LeetCode submission is not currently available: {submit_status}.")
            break
        if submit_status == "Blocked by Cloudflare":
            print("Skipping this problem because LeetCode/Cloudflare blocked the submission.")
        time.sleep(float(runtime["submission_delay"]))

    print(
        f"Batch finished: total={len(problems)}, generated={generated_count}, "
        f"skipped={skipped_count}, failed_generation={failed_count}."
    )

def _generate_and_save_solution(problem, runtime: dict[str, str | float | Path]) -> Path:
    """Generate code through the API and save it to the solutions directory."""
    prompt = build_prompt(problem, str(runtime["template"]))
    generated = generate_solution_with_openai(
        prompt,
        model=str(runtime["model"]),
        env_path=str(runtime["env"]),
        timeout_seconds=float(runtime["api_timeout"])
    )

    solution_path = Path(runtime["solutions_dir"]) / f"{problem.id}{solution_extension(problem.language)}"
    solution_path.parent.mkdir(parents=True, exist_ok=True)
    solution_path.write_text(generated.code + "\n", encoding="utf-8")
    return solution_path

def _submit_and_print(problem, solution_path: Path, runtime: dict[str, str | float | Path]) -> str:
    """Submit a generated solution to LeetCode and print the official result."""
    try:
        result = submit_solution_to_leetcode(
            problem,
            solution_path,
            env_path=str(runtime["env"]),
            output_dir=str(runtime["submission_output_dir"]),
            poll_interval_seconds=2.0,
            timeout_seconds=120.0
        )
    except LeetCodeSubmissionError as exc:
        status = classify_submit_failure(str(exc))
        print(f"LeetCode submission failed: {status}")
        print(str(exc))
        append_leetcode_failure(
            runtime["leetcode_results"],
            problem=problem,
            solution_path=solution_path,
            model=str(runtime["model"]),
            leetcode_status=status
        )
        print(f"LeetCode failure appended to {runtime['leetcode_results']}")
        return status

    print(f"{result.status}: {result.problem_id} (submission_id={result.submission_id})")
    if result.raw.get("total_correct") is not None and result.raw.get("total_testcases") is not None:
        print(f"Passed: {result.raw.get('total_correct')}/{result.raw.get('total_testcases')}")
    if result.raw.get("status_runtime"):
        print(f"Runtime: {result.raw.get('status_runtime')}")
    if result.raw.get("status_memory"):
        print(f"Memory: {result.raw.get('status_memory')}")
    if result.raw.get("full_compile_error"):
        print(result.raw.get("full_compile_error"))
    elif result.raw.get("full_runtime_error"):
        print(result.raw.get("full_runtime_error"))
    elif result.raw.get("last_testcase") and result.status != "Accepted":
        print(f"Last testcase: {result.raw.get('last_testcase')}")
        print(f"Output: {result.raw.get('code_output')}")
        print(f"Expected: {result.raw.get('expected_output')}")

    append_leetcode_success(
        runtime["leetcode_results"],
        problem=problem,
        result=result,
        solution_path=solution_path,
        model=str(runtime["model"]),
        passed_tests=format_passed_tests(result)
    )
    print(f"LeetCode result appended to {runtime['leetcode_results']}")
    return "Accepted" if result.status == "Accepted" else "Submitted"

if __name__ == "__main__":
    main()
