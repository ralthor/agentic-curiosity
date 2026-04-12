---
name: agentic-curiosity-project
description: Project-specific guide for the `agentic-curiosity` Django repository. Use when working in this repo to understand the current structure, locate Django apps and routes, modify the question-first course engine, change the `ai_chat` abstraction or OpenAI adapter, add new Django apps, or run the correct `uv` and `manage.py` validation commands after changes.
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
- Keep the question-first tutoring runtime in `chat_api/services.py`. That module classifies interactions, builds hint/mark prompts, records attempts, updates learner state, and advances sessions to the next question.
- Treat `chat_api.Course` as the root content object. `CourseTopic` groups questions within a course, `QuestionType` owns the reusable hint/mark prompts for that course, and `CourseQuestion` stores the actual assessed question content.
- Preserve the session invariant: once a `ChatSession` is created, its `course`, selector overrides, and `active_presentation` drive later interactions. Do not silently swap the course or bypass `QuestionPresentation` / `QuestionAttempt` state.
- Keep question selection rules in `chat_api/question_selector.py` and progress aggregation in `chat_api/progress.py`; avoid duplicating those heuristics in views or templates.
- Re-export public agent classes from `ai_chat/__init__.py` if other modules should import them directly from `ai_chat`.
- Update tests whenever public `ai_chat` behavior changes.
- Register new Django apps in `agentic_curiosity/settings.py`, and only wire URLs when the app actually serves HTTP routes.
- `agentic_curiosity/settings.py` now contains console logging for the `ai_chat` logger. If you change chat logging behavior, keep `AI_CHAT_LOG_LEVEL` and the logger wiring coherent.

## Common Tasks

### Change AI Chat Behavior

1. Read `references/project-map.md` and confirm whether the change belongs in shared logic or a provider-specific adapter.
2. Change `chat_api/services.py` for interaction classification, hint/mark prompt construction, attempt recording, learner-state updates, or session advancement.
3. Change `ai_chat/agents.py` only for provider-agnostic behavior shared by multiple adapters.
4. Change `ai_chat/openai_agent.py` for OpenAI client wiring or Chat Completions payload behavior.
5. Keep provider-specific SDK calls in their own file.
6. Add or update tests in `ai_chat/tests.py` for the new behavior and in `chat_api/tests.py` if the HTTP/session workflow changed.
7. If you change exports or public behavior, update `ai_chat/__init__.py`.
8. Verify with the focused tests, then run the broader suite with `uv run python manage.py test` and `uv run python manage.py check`.

### Change Course Content Or Chat API Flow

1. Read `references/project-map.md` to confirm the current routes, templates, and models.
2. Change `chat_api/models.py` for `Course`, `CourseTopic`, `QuestionType`, `CourseQuestion`, or token-related data.
3. Change `chat_api/question_selector.py` when next-question selection rules change, and `chat_api/progress.py` when coverage/mastery reporting changes.
4. Change `ai_chat/models.py` only when persisted session or learner-tracking records such as `ChatSession`, `QuestionPresentation`, `QuestionAttempt`, or `LearnerQuestionState` need schema changes.
5. Change `chat_api/views.py` and `chat_api/urls.py` for token-authenticated JSON routes, payload shapes, or serialization.
6. Change `core/views.py`, `core/urls.py`, and the relevant `core/templates/core/*.html` page when the browser workflow changes.
7. Keep the course studio browser flow aligned with `/api/chat/courses/` and `/api/chat/courses/<course_id>/questions/import/`, and keep the home page aligned with `/api/chat/sessions/`, `/api/chat/sessions/<session_id>/`, and `/api/chat/chat/`.
8. If you add or alter models, run `uv run python manage.py makemigrations` and `uv run python manage.py migrate`.
9. Add or update tests in `chat_api/tests.py` and `core/tests.py`.
10. Verify with `uv run python manage.py test` and `uv run python manage.py check`.

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
- `uv run python manage.py test chat_api`
- `uv run python manage.py test ai_chat`
- `uv run python manage.py test core`
- `uv run python manage.py check`
- `uv run python manage.py runserver`
