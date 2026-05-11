from __future__ import annotations

import httpx

from gateway.mmdev_gateway.schemas import ExecutorRunRequest, UsagePayload


class DeepSeekExecutor:
    def __init__(self, api_key: str, base_url: str, model: str) -> None:
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.model = model

    def run(self, request: ExecutorRunRequest, timeout_seconds: int) -> tuple[dict, UsagePayload]:
        response = httpx.post(
            f"{self.base_url}/chat/completions",
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": request.executor_model or self.model,
                "messages": [{"role": "user", "content": request.prompt}],
                "response_format": {"type": "json_object"},
            },
            timeout=timeout_seconds,
        )
        response.raise_for_status()
        payload = response.json()
        choices = payload.get("choices") or []
        if not choices:
            raise ValueError("DeepSeek response missing choices")
        content = choices[0].get("message", {}).get("content", "")
        data = httpx.Response(200, content=content.encode("utf-8")).json()
        usage = payload.get("usage") or {}
        return data, UsagePayload(
            input_tokens=usage.get("prompt_tokens") or 0,
            output_tokens=usage.get("completion_tokens") or 0,
        )

