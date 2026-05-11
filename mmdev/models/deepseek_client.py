from __future__ import annotations

import httpx

from mmdev.models.base import CompletionResult


class DeepSeekChatClient:
    def __init__(self, api_key: str, base_url: str) -> None:
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")

    def complete(self, *, prompt: str, model: str, timeout_seconds: int) -> CompletionResult:
        response = httpx.post(
            f"{self.base_url}/chat/completions",
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": model,
                "messages": [{"role": "user", "content": prompt}],
                "response_format": {"type": "json_object"},
            },
            timeout=timeout_seconds,
        )
        response.raise_for_status()
        payload = response.json()
        choices = payload.get("choices") or []
        text = ""
        if choices:
            text = choices[0].get("message", {}).get("content", "")
        usage = payload.get("usage") or {}
        return CompletionResult(
            text=text,
            input_tokens=usage.get("prompt_tokens"),
            output_tokens=usage.get("completion_tokens"),
        )

