from __future__ import annotations

import re
from datetime import date
from typing import Any


class InputValidationError(ValueError):
    """Raised when report input has an invalid shape or date value."""


_DATE_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_LIST_FIELDS = ("git_records", "news_records", "historical_reports")


def validate_date(value: str, field_name: str = "current_date") -> str:
    """Validate an exact ``YYYY-MM-DD`` date and return it unchanged."""
    if not isinstance(value, str) or not _DATE_PATTERN.fullmatch(value):
        raise InputValidationError(f"{field_name} 必须使用 YYYY-MM-DD 格式")
    try:
        date.fromisoformat(value)
    except ValueError as exc:
        raise InputValidationError(f"{field_name} 不是有效日期：{value}") from exc
    return value


def validate_input_data(data: Any) -> None:
    """Reject malformed top-level fields before analysis starts.

    Record contents remain intentionally permissive so older exports with
    optional fields can still be analyzed, but containers and records must
    have the documented shapes.
    """
    if not isinstance(data, dict):
        raise InputValidationError("输入 JSON 顶层必须是对象")

    current_date = data.get("current_date")
    if current_date is not None:
        validate_date(current_date)

    team_config = data.get("team_config")
    if team_config is not None and not isinstance(team_config, dict):
        raise InputValidationError("team_config 必须是对象")

    for field_name in _LIST_FIELDS:
        value = data.get(field_name)
        if value is None:
            continue
        if not isinstance(value, list):
            raise InputValidationError(f"{field_name} 必须是数组")
        for index, item in enumerate(value):
            if not isinstance(item, dict):
                raise InputValidationError(
                    f"{field_name}[{index}] 必须是对象"
                )
