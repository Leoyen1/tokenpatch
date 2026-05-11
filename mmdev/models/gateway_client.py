from __future__ import annotations

import httpx

from mmdev.models.base import CompletionResult


class MMDevGatewayClient:
    def __init__(
        self,
        gateway_url: str,
        gateway_token: str,
        *,
        country: str | None = None,
        entity: str | None = None,
    ) -> None:
        self.gateway_url = gateway_url.rstrip("/")
        self.gateway_token = gateway_token
        self.country = country.strip() if country else None
        self.entity = entity.strip() if entity else None

    def complete(self, *, prompt: str, model: str, timeout_seconds: int) -> CompletionResult:
        headers = {
            "Authorization": f"Bearer {self.gateway_token}",
            "Content-Type": "application/json",
        }
        if self.country:
            headers["X-MMDEV-Country"] = self.country
        if self.entity:
            headers["X-MMDEV-Entity"] = self.entity
        response = httpx.post(
            f"{self.gateway_url}/v1/executor/run",
            headers=headers,
            json={
                "protocol": "mmdev.executor.v1",
                "executor_model": model,
                "prompt": prompt,
            },
            timeout=timeout_seconds,
        )
        response.raise_for_status()
        payload = response.json()
        patch = payload.get("patch")
        if not isinstance(patch, str) or not patch.strip():
            raise ValueError("gateway response missing patch")
        usage = payload.get("usage") or {}
        return CompletionResult(
            text=_gateway_payload_to_executor_json(payload),
            input_tokens=usage.get("input_tokens"),
            output_tokens=usage.get("output_tokens"),
            charged_credits=payload.get("charged_credits"),
            provider_cost=payload.get("provider_cost"),
        )


def _gateway_payload_to_executor_json(payload: dict) -> str:
    import json

    return json.dumps(
        {
            "patch": payload["patch"],
            "changed_files": payload.get("changed_files", []),
            "summary": payload.get("summary", ""),
            "risks": payload.get("risks", []),
            "verification_hint": payload.get("verification_hint", ""),
            "needs_human_input": payload.get("needs_human_input", False),
        },
        ensure_ascii=False,
    )
