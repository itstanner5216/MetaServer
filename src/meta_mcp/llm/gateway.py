"""LLM gateway utilities."""

from typing import Any, Dict, List, Optional

try:
    import litellm
except ImportError:
    litellm = None


def model_call(model: str, messages: List[Dict[str, str]], **kwargs: Any) -> Any:
    """
    Forward an LLM completion call through the configured client.

    Args:
        model: Model identifier.
        messages: Chat messages for the completion.
        **kwargs: Additional parameters, including optional llm_client.

    Returns:
        LLM response object.
    """
    llm_client = kwargs.pop("llm_client", None) or litellm
    if llm_client is None:
        raise RuntimeError("LLM client is not available")

    return llm_client.completion(model=model, messages=messages, **kwargs)
