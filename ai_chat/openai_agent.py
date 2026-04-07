from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from django.conf import settings as django_settings
from django.core.exceptions import ImproperlyConfigured
from openai import OpenAI

from .agents import Agent


def _get_django_setting(name: str) -> Any | None:
    try:
        return getattr(django_settings, name, None)
    except ImproperlyConfigured:
        return None


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
        resolved_api_key = api_key if api_key is not None else _get_django_setting('OPENAI_API_KEY')
        resolved_organization = (
            organization if organization is not None else _get_django_setting('OPENAI_ORGANIZATION')
        )
        resolved_project = project if project is not None else _get_django_setting('OPENAI_PROJECT')
        resolved_base_url = base_url if base_url is not None else _get_django_setting('OPENAI_BASE_URL')
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
