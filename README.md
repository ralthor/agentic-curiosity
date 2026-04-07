# Agentic Curiosity

Minimal Django project for experimenting with provider-neutral chat agents and persisted multi-agent conversations.

The repository currently contains:

- A reusable `ai_chat.Agent` base class with an OpenAI-style request contract.
- An `OpenAIAgent` adapter backed by the OpenAI Chat Completions API.
- A persisted `Chat` orchestration class that routes user messages, stores all turns, and compacts long-running context.
- A `chat_api` app with Django-authenticated token issuance plus session-based chat endpoints.
- A small Django app shell with a health-style home route and admin support for chat records.

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

The root page responds with `Agentic Curiosity is running.` and the Django admin is available at `/admin/`.

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
- `ai_chat.Chat`: orchestrates categorization, answering, persistence, and context management.
- `ai_chat.ChatPrompt`: prompt key/text pair accepted by `Chat`.

Persistent storage:

- `ChatSession`: logical user sessions.
- `ChatTurn`: immutable stored conversation turns with both user text and agent response.
- `ChatContext`: mutable per-session context state, including the compacted summary for that chat session.

## How `Chat` Works

For each incoming user message:

1. The chat loads the selected session's context from the database.
2. A categorizer agent sees numbered short descriptions of the available prompts and returns the best prompt number.
3. An answerer agent receives the selected prompt, the current context, and the latest user message.
4. The user message and the agent response are both stored as a `ChatTurn`.
5. If a briefer agent is configured and the context is too large, the chat can compact older context after responding.

Each session keeps its own isolated history and compacted context.
The `start_session` flag starts a fresh session for the current `Chat` instance.

Prompt keys stay internal. The categorizer only sees short prompt descriptions derived from each prompt's text, and `Chat` maps the returned number back to the stored key.

## Example Usage

Run this in a Django shell:

```bash
uv run python manage.py shell
```

```python
from ai_chat import Chat, OpenAIAgent

categorizer = OpenAIAgent(
    model="gpt-4.1-mini",
    system="Choose the best prompt number and return only that number.",
)

answerer = OpenAIAgent(
    model="gpt-4.1-mini",
    system="Answer clearly and directly.",
)

briefer = OpenAIAgent(
    model="gpt-4.1-mini",
    system="Condense old chat context while preserving important facts and recent intent.",
)

chat = Chat(
    user_id="user-123",
    prompts={
        "support": "Help the user with product and troubleshooting questions.",
        "sales": "Help the user with plans, pricing, and commercial questions.",
    },
    categorizer_agent=categorizer,
    answerer_agent=answerer,
    briefer_agent=briefer,
)

response = chat.reply("I need help resetting my account password.", start_session=True)
print(response)
print(chat.session_id)
```

## Chat API

The project includes a token-authenticated chat API at `/api/chat/`.

Available routes:

- `POST /api/chat/login/`: Django login with JSON credentials, returns the user's API token.
- `POST /api/chat/token/`: returns the current logged-in user's API token.
- `POST /api/chat/sessions/`: creates a new chat session for the token owner and returns `session_id`.
- `POST /api/chat/chat/`: accepts `session_id` and `text`, checks that the session belongs to the token owner, and returns the chat response.

The default API prompts are:

- `teacher`: teaches elementary math, introduces a topic when needed, and asks short check-for-understanding questions.
- `judge`: checks whether the student's answer is correct, explains mistakes, and asks whether the user understood.

Example flow:

```bash
curl -X POST http://127.0.0.1:8000/api/chat/login/ \
  -H "Content-Type: application/json" \
  -d '{"username":"alice","password":"wonderland"}'

curl -X POST http://127.0.0.1:8000/api/chat/sessions/ \
  -H "Authorization: Token <token>"

curl -X POST http://127.0.0.1:8000/api/chat/chat/ \
  -H "Authorization: Token <token>" \
  -H "Content-Type: application/json" \
  -d '{"session_id":1,"text":"2 + 2 = 4"}'
```

## Context Compaction

`Chat` keeps recent turns as structured conversation and can compress older context into a shorter summary.

Default behavior:

- Compaction threshold: `5120` bytes
- Recent turns kept verbatim: `10`

The compaction logic is designed to keep current-session continuity intact while shrinking older history.

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
chat_api/           Token-authenticated chat HTTP endpoints
core/               Minimal web app with the home route
manage.py           Django entry point
```
