from __future__ import annotations

import httpx

from mmdev.models.base import CompletionResult


class OpenAIResponsesClient:
    def __init__(self, api_key: str, base_url: str = "https://api.openai.com/v1") -> None:
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")

    def complete(self, *, prompt: str, model: str, timeout_seconds: int) -> CompletionResult:
        response = httpx.post(
            f"{self.base_url}/responses",
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": model,
                "input": prompt,
                "text": {"format": {"type": "json_object"}},
            },
            timeout=timeout_seconds,
        )
        response.raise_for_status()
        payload = response.json()
        text = _extract_response_text(payload)
        usage = payload.get("usage") or {}
        return CompletionResult(
            text=text,
            input_tokens=usage.get("input_tokens"),
            output_tokens=usage.get("output_tokens"),
        )


class OpenAIChatCompletionsClient:
    def __init__(self, api_key: str, base_url: str = "https://api.openai.com/v1") -> None:
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
        text = _extract_chat_completion_text(payload)
        usage = payload.get("usage") or {}
        return CompletionResult(
            text=text,
            input_tokens=usage.get("prompt_tokens"),
            output_tokens=usage.get("completion_tokens"),
        )


def _extract_response_text(payload: dict) -> str:
    if isinstance(payload.get("output_text"), str):
        return payload["output_text"]
    parts: list[str] = []
    for item in payload.get("output", []):
        for content in item.get("content", []):
            if isinstance(content, dict) and content.get("type") == "output_text":
                parts.append(str(content.get("text", "")))
    return "\n".join(part for part in parts if part).strip()


def _extract_chat_completion_text(payload: dict) -> str:
    choices = payload.get("choices") or []
    if not choices:
        return ""
    message = choices[0].get("message") or {}
    content = message.get("content")
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        parts = []
        for item in content:
            if isinstance(item, dict) and isinstance(item.get("text"), str):
                parts.append(item["text"])
        return "\n".join(parts).strip()
    return ""
