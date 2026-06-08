"""JSON formatting helpers for human-readable problem files.
The standard `json.dumps(..., indent=2)` makes small matrix inputs very tall.
These helpers keep short scalar lists compact while still formatting large
objects across multiple lines."""

from __future__ import annotations
import json
from pathlib import Path
from typing import Any

def write_compact_json(path: str | Path, data: dict[str, Any]) -> None:
    """Write JSON with the project's compact formatting rules."""
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(format_compact_json(data) + "\n", encoding="utf-8")

def format_compact_json(data: dict[str, Any]) -> str:
    """Return a formatted JSON string optimized for LeetCode examples."""
    lines = ["{"]
    items = list(data.items())
    for index, (key, value) in enumerate(items):
        comma = "," if index < len(items) - 1 else ""
        rendered = _render_value(value, indent=2)
        if "\n" in rendered:
            lines.append(f'  {json.dumps(key, ensure_ascii=False)}: {rendered}{comma}')
        else:
            lines.append(f'  {json.dumps(key, ensure_ascii=False)}: {rendered}{comma}')
    lines.append("}")
    return "\n".join(lines)

def _render_value(value: Any, indent: int) -> str:
    """Render a JSON value while preserving compact short lists."""
    if _is_scalar(value):
        return json.dumps(value, ensure_ascii=False)

    if _is_compact_list(value):
        return json.dumps(value, ensure_ascii=False, separators=(", ", ": "))

    if isinstance(value, list):
        if not value:
            return "[]"
        lines = ["["]
        for index, item in enumerate(value):
            comma = "," if index < len(value) - 1 else ""
            rendered = _render_value(item, indent + 2)
            prefix = " " * (indent + 2)
            if "\n" in rendered:
                lines.append(f"{prefix}{rendered}{comma}")
            else:
                lines.append(f"{prefix}{rendered}{comma}")
        lines.append(" " * indent + "]")
        return "\n".join(lines)

    if isinstance(value, dict):
        if not value:
            return "{}"
        lines = ["{"]
        items = list(value.items())
        for index, (key, item) in enumerate(items):
            comma = "," if index < len(items) - 1 else ""
            rendered = _render_value(item, indent + 2)
            lines.append(f'{" " * (indent + 2)}{json.dumps(key, ensure_ascii=False)}: {rendered}{comma}')
        lines.append(" " * indent + "}")
        return "\n".join(lines)

    return json.dumps(value, ensure_ascii=False)

def _is_scalar(value: Any) -> bool:
    """Return whether a value can be printed on one JSON line."""
    return value is None or isinstance(value, (str, int, float, bool))

def _is_compact_list(value: Any) -> bool:
    """Return whether a list is short and simple enough for one line."""
    if not isinstance(value, list):
        return False
    rendered = json.dumps(value, ensure_ascii=False, separators=(", ", ": "))
    if len(rendered) > 120:
        return False
    return _list_depth(value) <= 2 and _contains_only_scalars_or_lists(value)

def _list_depth(value: Any) -> int:
    """Measure nested list depth for compact rendering decisions."""
    if not isinstance(value, list) or not value:
        return 0
    return 1 + max(_list_depth(item) for item in value)

def _contains_only_scalars_or_lists(value: Any) -> bool:
    """Reject dictionaries inside compact lists to keep JSON readable."""
    if _is_scalar(value):
        return True
    if isinstance(value, list):
        return all(_contains_only_scalars_or_lists(item) for item in value)
    return False