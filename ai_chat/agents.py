from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Mapping, Sequence
from typing import Any

from .exceptions import AgentConfigurationError, AgentResponseError

ChatMessage = Mapping[str, Any]


class Agent(ABC):
    """Provider-agnostic chat agent with an OpenAI-style request contract."""

    _reserved_request_defaults = {"messages", "model"}

    def __init__(
        self,
        *,
        model: str | None = None,
        system: str | None = None,
        **request_defaults: Any,
    ) -> None:
        reserved_keys = self._reserved_request_defaults.intersection(request_defaults)
        if reserved_keys:
            reserved_list = ", ".join(sorted(reserved_keys))
            raise ValueError(f"Reserved request defaults cannot be provided: {reserved_list}.")

        self.model = model
        self.system = system
        self.request_defaults = dict(request_defaults)

    def ask(
        self,
        text: str | None = None,
        *,
        messages: Sequence[ChatMessage] | None = None,
        system: str | None = None,
        model: str | None = None,
        **kwargs: Any,
    ) -> str:
        """
        Send a prompt and return plain text.

        For simple cases, pass ``text`` directly. For full control, pass
        OpenAI-style ``messages`` instead.
        """
        if kwargs.get("stream"):
            raise ValueError("ask() does not support stream=True. Use create() for raw streaming responses.")

        completion = self.create(
            messages=self._coerce_messages(text=text, messages=messages, system=system),
            model=model,
            **kwargs,
        )
        return self.extract_text(completion)

    def create(
        self,
        *,
        messages: Sequence[ChatMessage],
        model: str | None = None,
        frequency_penalty: float | None = None,
        max_completion_tokens: int | None = None,
        max_tokens: int | None = None,
        metadata: Mapping[str, Any] | None = None,
        n: int | None = None,
        presence_penalty: float | None = None,
        response_format: Mapping[str, Any] | None = None,
        seed: int | None = None,
        stop: str | Sequence[str] | None = None,
        stream: bool | None = None,
        temperature: float | None = None,
        tool_choice: Any = None,
        tools: Sequence[Mapping[str, Any]] | None = None,
        top_p: float | None = None,
        user: str | None = None,
        extra_headers: Mapping[str, str] | None = None,
        extra_query: Mapping[str, object] | None = None,
        extra_body: Mapping[str, Any] | None = None,
        timeout: Any = None,
        **kwargs: Any,
    ) -> Any:
        """
        Execute a raw provider call with an OpenAI-compatible chat payload.

        Subclasses may accept additional OpenAI-style kwargs through ``**kwargs``.
        """
        request_model = model or self.model
        if request_model is None:
            raise AgentConfigurationError("A model is required. Set one on the agent or pass model=...")

        payload = {
            **self.request_defaults,
            "messages": list(messages),
            "model": request_model,
        }
        payload.update(
            self._drop_none(
                {
                    "frequency_penalty": frequency_penalty,
                    "max_completion_tokens": max_completion_tokens,
                    "max_tokens": max_tokens,
                    "metadata": dict(metadata) if metadata is not None else None,
                    "n": n,
                    "presence_penalty": presence_penalty,
                    "response_format": dict(response_format) if response_format is not None else None,
                    "seed": seed,
                    "stop": stop,
                    "stream": stream,
                    "temperature": temperature,
                    "tool_choice": tool_choice,
                    "tools": list(tools) if tools is not None else None,
                    "top_p": top_p,
                    "user": user,
                    "extra_headers": dict(extra_headers) if extra_headers is not None else None,
                    "extra_query": dict(extra_query) if extra_query is not None else None,
                    "extra_body": dict(extra_body) if extra_body is not None else None,
                    "timeout": timeout,
                    **kwargs,
                }
            )
        )
        return self._create_completion(payload)

    def extract_text(self, completion: Any) -> str:
        """Extract plain text from an OpenAI-compatible completion response."""
        choices = self._read_value(completion, "choices") or []
        chunks: list[str] = []

        for choice in choices:
            message = self._read_value(choice, "message")
            if message is None:
                continue

            chunks.extend(self._extract_message_text(message))

        text = "\n\n".join(chunk for chunk in (item.strip() for item in chunks) if chunk)
        if text:
            return text

        raise AgentResponseError("The provider response did not contain any text content.")

    def _coerce_messages(
        self,
        *,
        text: str | None,
        messages: Sequence[ChatMessage] | None,
        system: str | None,
    ) -> list[ChatMessage]:
        if text is None and messages is None:
            raise ValueError("Either text or messages must be provided.")
        if text is not None and messages is not None:
            raise ValueError("Pass either text or messages, not both.")

        if messages is not None:
            return list(messages)

        prompt_messages: list[ChatMessage] = []
        system_prompt = self.system if system is None else system
        if system_prompt:
            prompt_messages.append({"role": "system", "content": system_prompt})

        prompt_messages.append({"role": "user", "content": text})
        return prompt_messages

    def _extract_message_text(self, message: Any) -> list[str]:
        content = self._read_value(message, "content")
        refusal = self._read_value(message, "refusal")
        chunks = self._coerce_content_to_text(content)

        if isinstance(refusal, str) and refusal.strip():
            chunks.append(refusal)

        return chunks

    def _coerce_content_to_text(self, content: Any) -> list[str]:
        if isinstance(content, str):
            return [content]

        if isinstance(content, Sequence) and not isinstance(content, (str, bytes, bytearray)):
            chunks: list[str] = []
            for item in content:
                text = self._read_value(item, "text")
                if isinstance(text, str):
                    chunks.append(text)
            return chunks

        return []

    def _read_value(self, item: Any, key: str) -> Any:
        if isinstance(item, Mapping):
            return item.get(key)
        return getattr(item, key, None)

    def _drop_none(self, payload: dict[str, Any]) -> dict[str, Any]:
        return {key: value for key, value in payload.items() if value is not None}

    @abstractmethod
    def _create_completion(self, payload: dict[str, Any]) -> Any:
        """Run a provider-specific chat completion request."""
