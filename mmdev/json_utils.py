from __future__ import annotations

import json
import re
from typing import TypeVar

from pydantic import BaseModel, ValidationError


T = TypeVar("T", bound=BaseModel)


class ModelJSONError(ValueError):
    pass


def extract_json_object(text: str) -> str:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
        cleaned = re.sub(r"\s*```$", "", cleaned)
    if cleaned.startswith("{"):
        return cleaned
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise ModelJSONError("model response did not contain a JSON object")
    return cleaned[start : end + 1]


def parse_model_json(text: str, model_type: type[T]) -> T:
    try:
        payload = json.loads(extract_json_object(text))
    except json.JSONDecodeError as exc:
        raise ModelJSONError(f"model response was not valid JSON: {exc}") from exc
    try:
        return model_type.model_validate(payload)
    except ValidationError as exc:
        raise ModelJSONError(f"model response did not match schema: {exc}") from exc

