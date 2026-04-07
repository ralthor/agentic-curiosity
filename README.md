# Agentic Curiosity

Minimal Django project for experimenting with provider-neutral chat agents and persisted chat sessions for tutoring workflows.

The repository currently contains:

- A reusable `ai_chat.Agent` base class with an OpenAI-style request contract.
- An `OpenAIAgent` adapter backed by the OpenAI Chat Completions API.
- A persisted `Chat` orchestration class that routes tutoring turns, tracks compact per-session course progress, stores all turns, and compacts long-running context.
- A `chat_api` app with Django-authenticated token issuance, course-topic management, and session-based chat endpoints.
- A `core` app with a browser chat console at `/` and a course-topic management page at `/course-topics/`.
- Admin support for chat sessions, turns, contexts, API tokens, and course topics.

## Requirements

- Python 3.11+
- `uv`
- An OpenAI API key if you want to use `OpenAIAgent`

## Quick Start

```bash
uv sync
uv run python manage.py migrate
uv run python manage.py runserver
```

The browser tools are available at:

- `/`: chat console for login, topic selection, session creation, and messaging
- `/course-topics/`: create and inspect reusable prompt sets
- `/admin/`: Django admin

## Environment

The project loads variables from a local `.env` file at the repository root.

Supported settings:

- `DJANGO_SECRET_KEY`
- `DJANGO_DEBUG`
- `DJANGO_ALLOWED_HOSTS`
- `OPENAI_API_KEY`
- `OPENAI_ORGANIZATION`
- `OPENAI_PROJECT`
- `OPENAI_BASE_URL`
- `AI_CHAT_MODEL`
- `AI_CHAT_ANSWERER_MODEL`
- `AI_CHAT_PLANNER_MODEL`
- `AI_CHAT_BRIEFER_MODEL`
- `AI_CHAT_CONTEXT_THRESHOLD_BYTES`
- `AI_CHAT_RECENT_TURNS_TO_KEEP`
- `AI_CHAT_MODEL_RECENT_TURNS`
- `AI_CHAT_LOG_LEVEL`

Minimal `.env` example:

```env
OPENAI_API_KEY=your-api-key
DJANGO_DEBUG=true
```

## Chat Architecture

`ai_chat` is intentionally kept as a reusable utility app rather than an HTTP API.

Core pieces:

- `ai_chat.Agent`: provider-neutral base class. `ask()` is text-in/text-out, `create()` preserves an OpenAI-shaped payload.
- `ai_chat.OpenAIAgent`: concrete provider adapter using the OpenAI SDK.
- `ai_chat.Chat`: orchestrates prompt routing, conditional planner updates, answering, persistence, and context management.
- `ai_chat.ChatPrompt`: prompt key/text pair accepted by `Chat`.

Persistent storage:

- `ChatSession`: logical user sessions, including the locked `course_topic` chosen at session creation time and the persisted `course_state` snapshot for that learner.
- `ChatTurn`: stored conversation turns with both user text and agent response.
- `ChatContext`: mutable per-session context state, including the compacted summary for that chat session.

Each of these records includes `created_at` and `updated_at` timestamps.

Prompt and progress storage:

- `chat_api.CourseTopic`: named bundle containing `teacher`, `judge`, `categorizer`, `answerer`, `planner`, and `briefer` prompts plus an ordered `expectations` list.
- `ChatSession.course_topic`: frozen topic selection for that session so later retrieval cannot silently change prompt behavior.
- `ChatSession.course_state`: compact internal session state containing per-expectation scores, active indexes, review indexes, recent evidence, and reply focus. API responses serialize that into a richer derived view.

## How `Chat` Works

For each incoming user message:

1. The chat loads the selected session's context from the database.
2. For the standard course flow with `teacher` and `judge` prompts, `Chat` routes locally: short answer attempts go to `judge`, while explanation or practice requests go to `teacher`.
3. If the prompt set is not the standard course pair, `Chat` can still use an optional categorizer agent to choose the prompt.
4. The planner runs only on assessment or transition turns. It receives a compact active-window payload and returns a JSON patch rather than rewriting the full course state.
5. The answerer receives the selected prompt, the compact planner note, the stored summary, and only the most recent turns instead of the full history.
6. The user message and the agent response are stored as a `ChatTurn`, and the updated `course_state` is persisted on the session.
7. Context compaction is available through `compact_context()` or the management command; it is not part of the normal reply hot path.

Each session keeps its own isolated history and compacted context.
The `start_session` flag starts a fresh session for the current `Chat` instance.

Prompt keys stay internal. When a categorizer is used, it only sees short prompt descriptions derived from each prompt's text, and `Chat` maps the returned number back to the stored key.

## Example Usage

Run this in a Django shell:

```bash
uv run python manage.py shell
```

```python
from ai_chat import Chat, OpenAIAgent

answerer = OpenAIAgent(
    model="gpt-4.1-mini",
    system="Tutor clearly and directly.",
)

planner = OpenAIAgent(
    model="gpt-4.1-mini",
    system="Update the compact course-state tracker with a JSON patch.",
)

briefer = OpenAIAgent(
    model="gpt-4.1-mini",
    system="Condense old chat context while preserving important facts and recent intent.",
)

chat = Chat(
    user_id="user-123",
    prompts={
        "teacher": "Teach one elementary math idea at a time.",
        "judge": "Judge the student's latest elementary math answer.",
    },
    answerer_agent=answerer,
    planner_agent=planner,
    briefer_agent=briefer,
    topic_name="Elementary Math",
    planner_prompt="Track progress through the elementary math expectations.",
    topic_expectations=[
        "Count forward and backward within 20.",
        "Add within 20 using objects, drawings, or equations.",
    ],
)

response = chat.reply("Can you show me how 2 + 3 works?", start_session=True)
print(response)
print(chat.session_id)
```

For non-course prompt bundles such as `support` and `sales`, pass a `categorizer_agent` if you want the model to choose among more than the standard `teacher` and `judge` routes.

## Chat API

The project includes a token-authenticated chat API at `/api/chat/`.

Available routes:

- `POST /api/chat/login/`: Django login with JSON credentials, returns the user's API token.
- `POST /api/chat/token/`: returns the current logged-in user's API token.
- `GET /api/chat/course-topics/`: lists available course topics.
- `POST /api/chat/course-topics/`: creates a new course topic with six prompts and an `expectations` list.
- `POST /api/chat/sessions/`: creates a new chat session for the token owner, requires `course_topic_id`, and initializes the session `course_state`.
- `GET /api/chat/sessions/<session_id>/`: returns session metadata, including the stored topic and current `course_state`.
- `POST /api/chat/chat/`: accepts `session_id` and `text`, checks that the session belongs to the token owner, and returns the chat response plus the updated `course_state`.

New sessions always use the selected `CourseTopic`, and that topic stays fixed for the life of the session.
The seeded default topic is `Elementary Math`, including an expectation list that the planner scores from `0` to `4` per item.
The `categorizer_prompt` field is still stored on `CourseTopic` for compatibility and custom prompt bundles, but the standard `teacher`/`judge` course flow routes locally without a categorizer model call.

Example flow:

```bash
curl -X POST http://127.0.0.1:8000/api/chat/login/ \
  -H "Content-Type: application/json" \
  -d '{"username":"alice","password":"wonderland"}'

curl http://127.0.0.1:8000/api/chat/course-topics/ \
  -H "Authorization: Token <token>"

curl -X POST http://127.0.0.1:8000/api/chat/sessions/ \
  -H "Authorization: Token <token>" \
  -H "Content-Type: application/json" \
  -d '{"course_topic_id":1}'

curl -X POST http://127.0.0.1:8000/api/chat/chat/ \
  -H "Authorization: Token <token>" \
  -H "Content-Type: application/json" \
  -d '{"session_id":1,"text":"2 + 2 = 4"}'

curl http://127.0.0.1:8000/api/chat/sessions/1/ \
  -H "Authorization: Token <token>"
```

Course topic creation example:

The payload below is a concrete `Elementary Math` example you can insert through the API or use as the equivalent data for the `chat_api_coursetopic` table:

```bash
curl -X POST http://127.0.0.1:8000/api/chat/course-topics/ \
  -H "Authorization: Token <token>" \
  -H "Content-Type: application/json" \
  -d '{
    "name":"Elementary Math",
    "teacher_prompt":"You are a patient elementary math teacher. Teach one small idea at a time in simple language, use short worked examples, and end most teaching turns with a quick check for understanding.",
    "judge_prompt":"You are checking a student'\''s elementary math answer. Say whether it is correct, explain the reasoning simply, and point out the next correction or reinforcement step.",
    "categorizer_prompt":"Choose the best prompt number for the next reply when this topic is used with non-standard prompt bundles. Return only the number.",
    "answerer_prompt":"You are an elementary math tutor. Follow the selected prompt exactly, stay inside the current course topic, and keep the language concise, clear, and age-appropriate.",
    "planner_prompt":"You are the internal course planner for elementary math. Update only the compact active-window course state, keep scores from 0 to 4, and return a JSON patch for the current item, next item, evidence summary, and reply focus.",
    "briefer_prompt":"Condense the elementary math tutoring session. Keep the concepts covered, the student'\''s mistakes, evidence that affects expectation scores, and the next teaching step.",
    "expectations":[
      "Count forward and backward within 20.",
      "Add within 20 using objects, drawings, or equations.",
      "Subtract within 20 using objects, drawings, or equations.",
      "Recall addition and subtraction facts within 10 with fluency.",
      "Solve one-step word problems within 20 using addition or subtraction.",
      "Understand two-digit numbers as tens and ones."
    ]
  }'
```

## Context Compaction

`Chat` keeps recent turns as structured conversation and can compress older context into a shorter summary.
Model calls only receive the stored summary plus the most recent turns.

Default behavior:

- Compaction threshold: `5120` bytes
- Recent turns kept verbatim: `10`
- Recent turns sent to the model: `4`

The compaction logic is designed to keep current-session continuity intact while shrinking older history, and it runs outside the normal reply path unless you call it explicitly.

You can trigger compaction from code:

```python
chat.compact_context(force=True)
```

Or from cron with the management command:

```bash
uv run python manage.py compact_chat_contexts \
  --agent-class ai_chat.OpenAIAgent \
  --model gpt-4.1-mini \
  --system "Condense old conversation context and preserve important facts."
```

## Logging

`ai_chat.chat` now logs its main lifecycle events to the console during development, including:

- session creation
- prompt selection
- turn persistence
- context compaction

Control the log level with `AI_CHAT_LOG_LEVEL`. The default is `INFO`.

## Development Commands

```bash
uv run python manage.py test
uv run python manage.py test ai_chat
uv run python manage.py check
uv run python manage.py migrate
uv run python manage.py runserver
```

## Project Layout

```text
agentic_curiosity/  Django project settings and root URLs
ai_chat/            Reusable agent and persisted chat utilities
chat_api/           Token-authenticated chat HTTP endpoints and course topics
core/               Browser chat console and topic-management pages
manage.py           Django entry point
```
