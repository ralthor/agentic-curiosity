from __future__ import annotations

from collections.abc import Mapping
from typing import Any
from urllib.parse import urlparse

from django.conf import settings as django_settings
from django.core.exceptions import ImproperlyConfigured
from openai import OpenAI

from .agents import Agent
from .exceptions import AgentConfigurationError


def _get_django_setting(name: str) -> Any | None:
    try:
        return getattr(django_settings, name, None)
    except ImproperlyConfigured:
        return None


def _normalize_optional_value(value: Any | None) -> Any | None:
    if isinstance(value, str):
        stripped = value.strip()
        return stripped or None
    return value


def _normalize_base_url(value: str | None) -> str | None:
    normalized = _normalize_optional_value(value)
    if normalized is None:
        return None

    parsed = urlparse(normalized)
    if parsed.scheme not in {"http", "https"}:
        raise AgentConfigurationError("OPENAI_BASE_URL must start with http:// or https://.")

    return normalized


class OpenAIAgent(Agent):
    """OpenAI-backed agent using the Chat Completions API."""

    def __init__(
        self,
        *,
        client: Any | None = None,
        api_key: str | None = None,
        organization: str | None = None,
        project: str | None = None,
        base_url: str | None = None,
        timeout: Any = None,
        max_retries: int = 2,
        default_headers: Mapping[str, str] | None = None,
        default_query: Mapping[str, object] | None = None,
        http_client: Any = None,
        model: str | None = None,
        system: str | None = None,
        **request_defaults: Any,
    ) -> None:
        super().__init__(model=model, system=system, **request_defaults)
        resolved_api_key = _normalize_optional_value(
            api_key if api_key is not None else _get_django_setting('OPENAI_API_KEY')
        )
        resolved_organization = _normalize_optional_value(
            organization if organization is not None else _get_django_setting('OPENAI_ORGANIZATION')
        )
        resolved_project = _normalize_optional_value(
            project if project is not None else _get_django_setting('OPENAI_PROJECT')
        )
        resolved_base_url = _normalize_base_url(
            base_url if base_url is not None else _get_django_setting('OPENAI_BASE_URL')
        )
        self.client = client or OpenAI(
            api_key=resolved_api_key,
            organization=resolved_organization,
            project=resolved_project,
            base_url=resolved_base_url,
            timeout=timeout,
            max_retries=max_retries,
            default_headers=default_headers,
            default_query=default_query,
            http_client=http_client,
        )

    def _create_completion(self, payload: dict[str, Any]) -> Any:
        return self.client.chat.completions.create(**payload)
