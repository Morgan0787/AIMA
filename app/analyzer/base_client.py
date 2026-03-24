from __future__ import annotations


class BaseAIClient:
    def generate(self, prompt: str, timeout: int = 60) -> str | None:
        raise NotImplementedError

