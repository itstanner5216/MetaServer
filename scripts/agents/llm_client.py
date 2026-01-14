"""
Unified LLM client that handles multiple providers.
Supports: Azure OpenAI, OpenAI, Anthropic, GitHub Models, Moonshot, OpenRouter, Ollama
"""

import asyncio
from dataclasses import dataclass
from typing import Optional

try:
    import httpx
except ImportError:
    # Fallback for environments without httpx
    httpx = None

from .llm_config import AgentRole, get_config, ModelConfig, ProviderConfig


@dataclass
class ChatMessage:
    """A single chat message."""
    role: str  # "system", "user", "assistant"
    content: str


@dataclass
class ChatResponse:
    """Response from LLM."""
    content: str
    model: str
    usage: dict
    raw_response: dict


class LLMClient:
    """
    Unified client for multiple LLM providers.
    Configuration is loaded from config/models.yaml.
    """
    
    def __init__(self, role: AgentRole):
        """
        Initialize client for a specific agent role.
        
        Args:
            role: Agent role (determines which model to use from config)
        """
        if httpx is None:
            raise ImportError(
                "httpx is required for LLM client. "
                "Install it with: pip install httpx"
            )
        
        self.role = role
        self.config = get_config()
        self.model_config = self.config.get_model_config(role)
        self.provider_config = self.config.get_provider_config(
            self.model_config.provider
        )
        self.defaults = self.config.get_defaults()
    
    def _build_headers(self) -> dict:
        """Build request headers based on provider configuration."""
        headers = {
            "Content-Type": "application/json",
        }
        
        # Add authentication header
        if self.provider_config.auth_header:
            api_key = self.model_config.get_api_key()
            auth_value = f"{self.provider_config.auth_prefix}{api_key}"
            headers[self.provider_config.auth_header] = auth_value
        
        # Add any extra headers from provider config
        headers.update(self.provider_config.extra_headers)
        
        return headers
    
    def _build_payload(
        self,
        messages: list[ChatMessage],
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
    ) -> dict:
        """Build request payload."""
        return {
            "model": self.model_config.model,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
            "temperature": temperature or self.model_config.temperature,
            "max_tokens": max_tokens or self.model_config.max_tokens,
        }
    
    def _parse_response(self, data: dict) -> ChatResponse:
        """Parse response from various providers."""
        # Handle Anthropic's different response format
        if self.model_config.provider == "anthropic":
            content = data.get("content", [{}])[0].get("text", "")
        else:
            # Standard OpenAI-compatible format
            content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
        
        return ChatResponse(
            content=content,
            model=data.get("model", self.model_config.model),
            usage=data.get("usage", {}),
            raw_response=data,
        )
    
    async def chat(
        self,
        messages: list[ChatMessage],
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
    ) -> ChatResponse:
        """
        Send chat completion request.
        
        Args:
            messages: List of chat messages
            temperature: Override default temperature
            max_tokens: Override default max tokens
            
        Returns:
            ChatResponse with model output
        """
        headers = self._build_headers()
        payload = self._build_payload(messages, temperature, max_tokens)
        
        timeout = httpx.Timeout(self.model_config.timeout, connect=10.0)
        
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.post(
                self.model_config.endpoint,
                headers=headers,
                json=payload,
            )
            response.raise_for_status()
            data = response.json()
        
        return self._parse_response(data)
    
    async def chat_with_retry(
        self,
        messages: list[ChatMessage],
        max_retries: Optional[int] = None,
        retry_delay: Optional[float] = None,
    ) -> ChatResponse:
        """
        Send chat request with automatic retry on failure.
        
        Args:
            messages: List of chat messages
            max_retries: Maximum retry attempts (default from config)
            retry_delay: Delay between retries in seconds (default from config)
            
        Returns:
            ChatResponse with model output
        """
        max_retries = max_retries or self.defaults.get("max_retries", 3)
        retry_delay = retry_delay or self.defaults.get("retry_delay", 2.0)
        
        last_error = None
        
        for attempt in range(max_retries):
            try:
                return await self.chat(messages)
            except httpx.HTTPStatusError as e:
                last_error = e
                if e.response.status_code == 429:  # Rate limited
                    await asyncio.sleep(retry_delay * (attempt + 1))
                elif e.response.status_code >= 500:  # Server error
                    await asyncio.sleep(retry_delay)
                else:
                    raise
            except httpx.TimeoutException as e:
                last_error = e
                await asyncio.sleep(retry_delay)
            except Exception as e:
                last_error = e
                if attempt < max_retries - 1:
                    await asyncio.sleep(retry_delay)
        
        raise last_error or Exception("Max retries exceeded")
