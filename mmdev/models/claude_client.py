from __future__ import annotations

import httpx

from mmdev.models.base import CompletionResult


class ClaudeMessagesClient:
    def __init__(self, api_key: str, base_url: str = "https://api.anthropic.com/v1") -> None:
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")

    def complete(self, *, prompt: str, model: str, timeout_seconds: int) -> CompletionResult:
        response = httpx.post(
            f"{self.base_url}/messages",
            headers={
                "x-api-key": self.api_key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json={
                "model": model,
                "max_tokens": 4096,
                "messages": [{"role": "user", "content": prompt}],
            },
            timeout=timeout_seconds,
        )
        response.raise_for_status()
        payload = response.json()
        usage = payload.get("usage") or {}
        return CompletionResult(
            text=_extract_message_text(payload),
            input_tokens=usage.get("input_tokens"),
            output_tokens=usage.get("output_tokens"),
        )


def _extract_message_text(payload: dict) -> str:
    parts: list[str] = []
    for item in payload.get("content", []):
        if isinstance(item, dict) and item.get("type") == "text":
            parts.append(str(item.get("text", "")))
    return "\n".join(part for part in parts if part).strip()

