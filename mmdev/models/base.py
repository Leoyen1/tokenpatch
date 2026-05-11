from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class CompletionResult:
    text: str
    input_tokens: int | None = None
    output_tokens: int | None = None
    charged_credits: float | None = None
    provider_cost: float | None = None


class CompletionClient(Protocol):
    def complete(self, *, prompt: str, model: str, timeout_seconds: int) -> CompletionResult:
        ...
