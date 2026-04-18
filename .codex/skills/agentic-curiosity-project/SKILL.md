---
name: agentic-curiosity-project
description: Project-specific guide for the `agentic-curiosity` Django repository. Use when working in this repo to understand the current structure, locate Django apps and routes, modify the question-first tutoring engine, change the `ai_chat` abstraction or OpenAI adapter, update the browser or JSON API flows, adjust environment or deployment wiring, add new Django apps, or run the correct `uv` and `manage.py` validation commands after changes.
---

# Agentic Curiosity Project

Read `references/project-map.md` before making non-trivial changes. It contains the current repo map, the key files, and the commands that already work in this project.
Read `README.md` as well when changing Docker, Nginx, bootstrap deployment, or API payload examples; those flows are documented there in more detail than the skill should duplicate.

## Work Rules

- Use `uv` for dependency management and for running Django commands.
- Keep edits small and explicit. This repo is still a minimal Django project, so avoid adding extra layers unless the user asks for them.
- When adding a new feature, add tests for that feature in the relevant test module.
- Before considering a feature complete, run the relevant new tests and the pre-existing test suite to confirm the change did not break current behavior.
- Treat `ai_chat` as reusable Python utilities plus persisted tutoring models, not a routed web app. `ai_chat/views.py` is intentionally empty. Keep provider-neutral behavior in `ai_chat/agents.py` and each concrete provider in its own module such as `ai_chat/openai_agent.py`.
- Preserve the current split in the chat API: `Agent.ask()` is the text-in/text-out helper, while `Agent.create()` preserves the OpenAI-style request shape for cross-provider compatibility.
- Keep the question-first tutoring runtime in `chat_api/services.py`. That module classifies interactions, builds hint/mark/full-answer prompts, records attempts, updates learner state, caches generated example answers, and advances sessions to the next question.
- Treat `chat_api.Course` as the root content object. `CourseTopic` groups questions within a course, `QuestionType` owns the reusable hint/mark prompts for that course, and `CourseQuestion` stores the actual assessed question content and optional authored example answer.
- Preserve the session invariant: once a `ChatSession` is created, its `course`, selector overrides, and `active_presentation` drive later interactions. Do not silently swap the course or bypass `QuestionPresentation` / `QuestionAttempt` state.
- Keep question selection rules in `chat_api/question_selector.py` and progress aggregation in `chat_api/progress.py`; avoid duplicating those heuristics in views or templates.
- Preserve current full-answer behavior: `/api/chat/chat/` with `action=full_answer` should return the stored `CourseQuestion.example_answer` first, and only call the model when that field is blank. Model-generated answers are cached back onto the question with the `AI generated: ` prefix.
- Keep token auth and login throttling coherent across `chat_api/views.py`, `chat_api/auth.py`, and `chat_api/rate_limits.py`.
- Keep the browser pages aligned with the JSON API. `core/templates/core/home.html` and `core/templates/core/course_topics.html` call the API directly and depend on current payload shapes and route names.
- Re-export public agent classes from `ai_chat/__init__.py` if other modules should import them directly from `ai_chat`.
- Update tests whenever public `ai_chat` behavior changes.
- Load configuration through `agentic_curiosity/settings.py` and `agentic_curiosity/env.py`; prefer environment variables over hardcoded secrets, hosts, or filesystem paths.
- Register new Django apps in `agentic_curiosity/settings.py`, and only wire URLs when the app actually serves HTTP routes.
- `agentic_curiosity/settings.py` contains console logging for the `ai_chat` logger plus env-driven database, proxy, and TLS settings. If you change logging or deployment behavior, keep the related settings coherent.
- `uv run python manage.py compact_chat_contexts` is intentionally deprecated in this engine and should keep raising unless the runtime is explicitly redesigned.

## Common Tasks

### Change AI Chat Behavior

1. Read `references/project-map.md` and confirm whether the change belongs in shared logic, the tutoring runtime, or a provider-specific adapter.
2. Change `chat_api/services.py` for interaction classification, hint/mark/full-answer prompt construction, attempt recording, learner-state updates, example-answer caching, or session advancement.
3. Change `ai_chat/agents.py` only for provider-agnostic behavior shared by multiple adapters.
4. Change `ai_chat/openai_agent.py` for OpenAI client wiring or Chat Completions payload behavior.
5. Keep provider-specific SDK calls in their own file.
6. Add or update tests in `ai_chat/tests.py` for the new behavior and in `chat_api/tests.py` if the HTTP/session workflow changed.
7. If you change exports or public behavior, update `ai_chat/__init__.py`.
8. Verify with the focused tests, then run `uv run python manage.py test ai_chat`, `uv run python manage.py test chat_api`, `uv run python manage.py test`, and `uv run python manage.py check`.

### Change Course Content, Selection, Or Progress

1. Read `references/project-map.md` to confirm the current routes, templates, and models.
2. Change `chat_api/models.py` for `Course`, `CourseTopic`, `QuestionType`, `CourseQuestion`, `ApiToken`, or `LoginRateLimit`.
3. Change `ai_chat/models.py` when persisted session or learner-tracking records such as `ChatSession`, `QuestionPresentation`, `QuestionAttempt`, or `LearnerQuestionState` need schema changes.
4. Change `chat_api/question_selector.py` when next-question selection rules, selector overrides, or topic balancing change.
5. Change `chat_api/progress.py` when Leitner scoring, due scheduling, coverage/mastery reporting, or active-question serialization changes.
6. Keep selection and progress heuristics out of templates and views unless the user explicitly wants a different split.
7. If you add or alter models, run `uv run python manage.py makemigrations` and `uv run python manage.py migrate`.
8. Add or update tests in `chat_api/tests.py`, `ai_chat/tests.py`, and `core/tests.py` as needed.
9. Verify with the focused tests, then `uv run python manage.py test` and `uv run python manage.py check`.

### Change Auth, API, Or Browser Flow

1. Change `chat_api/views.py` for request parsing, payload validation, JSON responses, or `action` handling.
2. Change `chat_api/auth.py` for `Authorization` header parsing and `chat_api/rate_limits.py` for sliding-window login throttling.
3. Keep `chat_api/urls.py` aligned with the view names consumed by the templates.
4. Change `core/views.py` only for server-rendered page setup such as injecting route URLs into templates.
5. Change `core/templates/core/home.html` when the session console flow changes, including login, token use, active-question rendering, or the `Hint`, `Skip`, and `Full Answer` actions.
6. Change `core/templates/core/course_topics.html` when the course studio flow changes, especially `/api/chat/courses/` creation and `/api/chat/courses/<course_id>/questions/import/`.
7. Keep `core/tests.py` aligned with the routes, buttons, and template-visible strings that define the current browser workflow.
8. Verify with `uv run python manage.py test core`, `uv run python manage.py test chat_api`, `uv run python manage.py test`, and `uv run python manage.py check`.

### Change Environment Or Deployment

1. Change `agentic_curiosity/settings.py` and `agentic_curiosity/env.py` for env parsing, database path resolution, OpenAI settings, rate-limit settings, proxy headers, or TLS-related behavior.
2. Change `Dockerfile` and `docker-entrypoint.sh` for container build or startup behavior.
3. Change `compose.yml` and `nginx.conf` for the local Docker stack.
4. Change `deploy/bootstrap.sh` for generated deployment Compose or Nginx wiring.
5. Keep `DJANGO_DB_PATH`, `DJANGO_STATIC_ROOT`, `DJANGO_USE_X_FORWARDED_HOST`, and `DJANGO_TRUST_X_FORWARDED_PROTO` coherent across settings, entrypoint, Compose, and bootstrap.
6. Update `README.md` when deployment or container behavior changes, because that file documents the operational workflow in more detail than this skill.
7. Verify with `uv run python manage.py check`. If Docker tooling is part of the change and available, also run the relevant container validation such as `docker compose config`.

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
- `uv run python manage.py test agentic_curiosity`
- `uv run python manage.py test chat_api`
- `uv run python manage.py test ai_chat`
- `uv run python manage.py test core`
- `uv run python manage.py check`
- `uv run python manage.py migrate`
- `uv run python manage.py runserver`
