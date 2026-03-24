"""
Digest analysis and generation for Jarvis v2 Core.

This module will:
- Take cleaned, deduplicated, and ranked messages
- Use prompts and the local LLM (Ollama) to build a daily digest
"""

from __future__ import annotations

from pathlib import Path
from typing import List

from .ollama_client import OllamaClient
from ..core.logger import get_logger
from ..core.utils import get_project_root


logger = get_logger(__name__)


class DigestAnalyzer:
    """
    High-level interface for turning messages into a digest using Ollama.
    """

    def __init__(self) -> None:
        self.client = OllamaClient()

    def _load_prompt(self, filename: str) -> str:
        """
        Load a prompt template from the `prompts` directory.
        """
        project_root = get_project_root()
        prompt_path = project_root / "prompts" / filename
        if not prompt_path.exists():
            raise FileNotFoundError(
                f"Prompt file not found: {prompt_path}. "
                "Please create it before running the analyzer."
            )
        return prompt_path.read_text(encoding="utf-8")

    def build_digest(self, messages: List[str]) -> str:
        """
        Build a daily digest from a list of message texts.

        For now, this is a very simple stub that just calls the model
        with a basic prompt template and inserts the messages.
        """
        logger.info("Building digest from %d messages (placeholder).", len(messages))

        template = self._load_prompt("digest_prompt.txt")
        joined_messages = "\n\n".join(messages)
        prompt = template.replace("{{MESSAGES}}", joined_messages)

        # TODO: Refine the prompt structure and parsing of the response.
        return self.client.generate(prompt)

