"""Wrapper utilities for LLM tool invocation."""

import logging
from typing import Any

logger = logging.getLogger(__name__)


def _supports_json_format(model: str) -> bool:
    model_lower = model.lower()
    return "gpt" in model_lower or "o1" in model_lower


def invoke_tool(
    llm_client: Any,
    model: str,
    system_prompt: str,
    user_prompt: str,
    temperature: float,
) -> str:
    """
    Invoke the LLM tool with standardized prompt formatting.

    Args:
        llm_client: LLM client (litellm or compatible).
        model: Model identifier for LLM calls.
        system_prompt: System prompt text.
        user_prompt: User prompt text.
        temperature: Sampling temperature.

    Returns:
        LLM response content.
    """
    try:
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]

        kwargs = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
        }

        if _supports_json_format(model):
            kwargs["response_format"] = {"type": "json_object"}

        response = llm_client.completion(**kwargs)
        return response.choices[0].message.content

    except Exception as e:
        logger.error(f"LLM call failed: {e}")
        raise RuntimeError(f"LLM call failed: {e}") from e
