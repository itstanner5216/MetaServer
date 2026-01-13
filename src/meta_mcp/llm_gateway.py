"""Canonical LLM gateway for model invocations."""

import logging
from typing import Any, Dict, List

logger = logging.getLogger(__name__)


def call_model(
    model: str,
    messages: List[Dict[str, str]],
    temperature: float,
    client: Any,
) -> str:
    """Call the LLM client with standard logging and error handling."""
    try:
        kwargs = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
        }

        if "gpt" in model.lower() or "o1" in model.lower():
            kwargs["response_format"] = {"type": "json_object"}

        response = client.completion(**kwargs)
        return response.choices[0].message.content
    except Exception as exc:
        logger.error("LLM call failed: %s", exc)
        raise RuntimeError(f"LLM call failed: {exc}") from exc
