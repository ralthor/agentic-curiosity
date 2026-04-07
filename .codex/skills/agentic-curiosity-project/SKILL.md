---
name: agentic-curiosity-project
description: Project-specific guide for the `agentic-curiosity` Django repository. Use when working in this repo to understand the current structure, locate Django apps and routes, modify the `ai_chat` abstraction, add new provider adapters, add new Django apps, or run the correct `uv` and `manage.py` validation commands after changes.
---

# Agentic Curiosity Project

Read `references/project-map.md` before making non-trivial changes. It contains the current repo map, the key files, and the commands that already work in this project.

## Work Rules

- Use `uv` for dependency management and for running Django commands.
- Keep edits small and explicit. This repo is still a minimal Django project, so avoid adding extra layers unless the user asks for them.
- When adding a new feature, add tests for that feature in the relevant test module.
- Before considering a feature complete, run the relevant new tests and the pre-existing test suite to confirm the change did not break current behavior.
- Treat `ai_chat` as a reusable Python utility app, not a web app. Keep provider-neutral behavior in `ai_chat/agents.py` and each concrete provider in its own module such as `ai_chat/openai_agent.py`.
- Preserve the current split in the chat API: `Agent.ask()` is the text-in/text-out helper, while `Agent.create()` preserves the OpenAI-style request shape for cross-provider compatibility.
- Keep persisted chat orchestration and prompt routing in `ai_chat/chat.py`. The categorizer currently sees numbered short prompt descriptions and should return only the selected prompt number.
- Re-export public agent classes from `ai_chat/__init__.py` if other modules should import them directly from `ai_chat`.
- Update tests whenever public `ai_chat` behavior changes.
- Register new Django apps in `agentic_curiosity/settings.py`, and only wire URLs when the app actually serves HTTP routes.

## Common Tasks

### Change AI Chat Behavior

1. Read `references/project-map.md` and confirm whether the change belongs in shared logic or a provider-specific adapter.
2. Change `ai_chat/chat.py` for persisted chat orchestration, prompt routing, or context-compaction behavior.
3. Change `ai_chat/agents.py` only for provider-agnostic behavior shared by multiple adapters.
4. Keep provider-specific SDK calls in their own file.
5. Add or update tests in `ai_chat/tests.py` for the new behavior.
6. If you change exports or public behavior, update `ai_chat/__init__.py`.
7. Verify with the focused tests, then run the broader suite with `uv run python manage.py test` and `uv run python manage.py check`.

### Add A New AI Provider

1. Add a new module under `ai_chat/`, for example `gemini_agent.py` or `ollama_agent.py`.
2. Inherit from `Agent` and implement `_create_completion()`.
3. Keep constructor options provider-specific, but preserve the OpenAI-shaped request contract exposed by `create()`.
4. Re-export the new class from `ai_chat/__init__.py` if it should be part of the public API.
5. Add or extend tests in `ai_chat/tests.py`.
6. Run the new provider tests, then `uv run python manage.py test` and `uv run python manage.py check`.

### Add A New Django App

1. Run `uv run python manage.py startapp <app_name>`.
2. Add the app config to `INSTALLED_APPS` in `agentic_curiosity/settings.py`.
3. Add URLs only if the app serves routes.
4. Add tests for the new app behavior in the appropriate test module.
5. If you add models, run `uv run python manage.py makemigrations` and `uv run python manage.py migrate`.
6. Run the new tests and then `uv run python manage.py test` and `uv run python manage.py check`.

## Validation

- For feature work, run the targeted tests you added or changed first.
- `uv run python manage.py test`
- `uv run python manage.py test ai_chat`
- `uv run python manage.py check`
- `uv run python manage.py runserver`
