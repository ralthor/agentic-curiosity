# Agentic Curiosity

Minimal Django project for question-first tutoring with provider-neutral AI agents, stored course content, and persisted learner question state.

## Overview

The active runtime is centered on a question bank, not a free-form conversation planner.

- `Course` is the top-level teaching unit.
- `CourseTopic` groups questions for coverage and mastery reporting.
- `QuestionType` stores the reusable `hint_prompt` and `mark_prompt` for one question format within a course.
- `CourseQuestion` stores authored question text, `max_marks`, and optional `sample_answer` / `example_answer` / `marking_notes`.
- `ChatSession` tracks one learner's run through a course.
- `QuestionPresentation` stores the currently served question and how it was selected.
- `QuestionAttempt` stores each hint request, answer attempt, or skip action.
- `LearnerQuestionState` stores per-question progress, including Leitner-style scheduling fields.

The older full-session chat-context compaction and expectation-planner flow are no longer the active engine.

## Requirements

- Python 3.11+
- `uv`
- An OpenAI API key for real hint/mark model calls

## Configuration

Settings are loaded from environment variables and `.env`.

- `OPENAI_API_KEY`: required for the OpenAI-backed runtime
- `OPENAI_ORGANIZATION`: optional
- `OPENAI_PROJECT`: optional
- `OPENAI_BASE_URL`: optional custom OpenAI-compatible base URL
- `AI_CHAT_ANSWERER_MODEL`: optional model override used by hint and mark calls
- `AI_CHAT_MODEL`: fallback model when `AI_CHAT_ANSWERER_MODEL` is unset
- `AI_CHAT_LOG_LEVEL`: optional logger level for the `ai_chat` logger
- `LOGIN_RATE_LIMIT_ATTEMPTS`: optional failed-login threshold for `POST /api/chat/login/` before the endpoint returns `429` 
- `LOGIN_RATE_LIMIT_WINDOW_SECONDS`: optional sliding window for login throttling in seconds

If neither `AI_CHAT_ANSWERER_MODEL` nor `AI_CHAT_MODEL` is set, the tutoring runtime falls back to `gpt-5.4-mini`.

## Quick Start

```bash
uv sync
uv run python manage.py migrate
uv run python manage.py createsuperuser
uv run python manage.py runserver
```

The login and token endpoints expect an existing Django user, so create a user first with `createsuperuser` or through admin.

## Docker

Run the app with Docker Compose:

```bash
docker compose up --build
```

This uses [compose.yml](compose.yml) and stores the SQLite database on the host at `./docker-data/db.sqlite3` by bind-mounting `./docker-data` into the container as `/data`.

The local Compose file keeps the app on Django `runserver` and runs `python manage.py migrate` automatically before startup, so the mounted database is initialized on first boot.

If you want to run without Compose, mount a host directory and point Django at it explicitly:

```bash
docker build -t agentic-curiosity .
docker run --rm -it -p 8000:8000 --env-file .env -e DJANGO_DB_PATH=/data/db.sqlite3 -v ./docker-data:/data agentic-curiosity
```

The local Compose path still uses `runserver`, which is fine for simple testing and CI but is not a hardened production web stack.

### Server Deployment With Docker

If your GitHub workflow is publishing the image to Docker Hub, the simplest server deployment is to copy the deployment bootstrap script to the server, place a `.env` file next to it, and let the script generate the Compose and Nginx config for you.

Example server layout:

```text
/opt/agentic-curiosity/
  bootstrap.sh
  .env
  compose.yml
  nginx.conf
  docker-data/
  redis-data/
```

Copy these repo files to the server directory:

```bash
mkdir -p /opt/agentic-curiosity
cp deploy/bootstrap.sh deploy/.env.example /opt/agentic-curiosity/
cd /opt/agentic-curiosity
cp .env.example .env
```

Create `/opt/agentic-curiosity/.env` on the server with at least:

```env
APP_IMAGE=YOUR_DOCKERHUB_USERNAME/agentic-curiosity:latest

DJANGO_SECRET_KEY=replace-this-with-a-long-random-secret
DJANGO_DEBUG=False
DJANGO_ALLOWED_HOSTS=your-domain.example,www.your-domain.example,SERVER_PUBLIC_IP
DJANGO_CSRF_TRUSTED_ORIGINS=http://your-domain.example,https://your-domain.example,http://www.your-domain.example,https://www.your-domain.example

OPENAI_API_KEY=your-openai-api-key
AI_CHAT_ANSWERER_MODEL=gpt-5.4-mini
AI_CHAT_MODEL=gpt-5.4-mini
```

Notes on the server `.env`:

- `DJANGO_ALLOWED_HOSTS` must include every hostname and public IP you will use to access the app.
- If you are using a reverse proxy or a real domain, include the real public domain names there.
- Keep `.env` out of git and lock it down on the server with `chmod 600 /opt/agentic-curiosity/.env`.
- The SQLite database will be stored persistently on the host at `/opt/agentic-curiosity/docker-data/db.sqlite3`.
- `APP_IMAGE` should point to the published image tag you want the server to run.

Bring the app up with the bootstrap script:

```bash
cd /opt/agentic-curiosity
sh bootstrap.sh
```

The script writes `compose.yml` and `nginx.conf`, creates the `docker-data/` and `redis-data/` directories, validates the generated Compose file, and starts three services:

- `web`: your published app image, running Django migrations and Gunicorn
- `redis`: internal Redis service reserved for future cache or distributed rate-limit work
- `nginx`: the only public-facing container, proxying to `web`

If you only want the files without starting containers, run:

```bash
sh bootstrap.sh --write-only
```

On first boot, the web container runs `python manage.py migrate` automatically before starting Gunicorn, and it collects static files into `docker-data/static` for Nginx to serve.

Create the admin user once after the container is running:

```bash
cd /opt/agentic-curiosity
docker compose exec web uv run python manage.py createsuperuser
```

Updating the server later is the same pattern:

```bash
cd /opt/agentic-curiosity
docker compose pull
docker compose up -d
```

If the Docker Hub repository is private, log in on the server first:

```bash
docker login
```

Nginx is the only service that publishes a host port. By default the generated Compose file binds host port `80` to the Nginx container. If you need a different host port, set `NGINX_HTTP_PORT` in `.env` before running the bootstrap script.

For a minimal UFW setup with Nginx in front:

```bash
sudo ufw allow OpenSSH
sudo ufw allow 'Nginx Full'
sudo ufw enable
sudo ufw status
```

The local dev container still uses Django `runserver`. The deployment bootstrap path uses Gunicorn behind Nginx and keeps both `web` and `redis` off the public network surface.

GitHub Actions now includes [.github/workflows/docker-image.yml](.github/workflows/docker-image.yml), modeled on the other project:

- pull requests to `master` build the image only
- pushes to `master` build and push the image to Docker Hub
- pushes to `master` then SSH to the VPS and redeploy the `web` service from the latest image

To make the push step work:

1. Create a Docker Hub repository for the image first, for example `agentic-curiosity`.
2. Create a Docker Hub access token.
3. Add these GitHub repository secrets:
   - `DOCKERHUB_USERNAME`
   - `DOCKERHUB_TOKEN`
   - `VPS_HOST`
   - `VPS_USER`
   - `VPS_PASSWORD`
   - `VPS_DEPLOY_PATH`

You do not need to push a placeholder image first. Creating the Docker Hub repository and configuring the GitHub secrets is enough.

The deploy step assumes `VPS_DEPLOY_PATH` points at a directory that has already been bootstrapped using `deploy/bootstrap.sh`, so that directory already contains `.env`, `compose.yml`, and the persistent data folders. It connects over SSH, changes into `VPS_DEPLOY_PATH`, and runs `docker compose up -d --pull always web`. The server must have modern Docker Compose available as `docker compose`. The SSH user must either be able to run Docker directly, or have passwordless `sudo` for Docker commands. If your Docker Hub repository is private, make sure the server has already run `docker login` once.

Useful pages:

- `/`: browser session console for login, course selection, session creation, and question interaction
- `/course-topics/`: browser course studio for creating courses and importing questions with JSON payloads
- `/admin/`: Django admin for courses, questions, tokens, sessions, attempts, and learner state

## Runtime Flow

Each interaction is scoped to one active question.

1. The learner logs in and selects a stored course.
2. `POST /api/chat/sessions/` creates a `ChatSession`.
3. The selector chooses the first question in code and creates a `QuestionPresentation`.
4. The learner either asks for a hint, submits an answer, or skips.
5. The model sees only question-local context:
   - course name
   - topic name
   - question type name
   - question text
   - max marks
   - optional sample answer
   - optional marking notes
   - the latest three attempts on the same presented question
   - the latest learner message
6. The app stores a `QuestionAttempt`.
7. The app updates `LearnerQuestionState`.
8. If the question is completed or skipped, the selector assigns the next question without a separate model call.

The browser UI provides a `Full Answer` button for the active question. If `example_answer` is stored on the question, that authored answer is returned; otherwise the app asks the model for a full-mark answer using the question text, hint prompt, mark prompt, sample answer, marking notes, and recent attempts, then caches it back onto the question prefixed with `AI generated: `.

No full conversation transcript is sent back to the model.

## Selection And Scheduling

Question selection lives in `chat_api/question_selector.py`.

- An explicit `selector_override_question_id` wins first.
- Otherwise the selector may honor `selector_override_topic_id`.
- `selector_strategy_override: "same_topic"` biases toward the most recent topic when possible.
- Default selection prefers unseen questions, then due questions, then a fallback pool.
- The response exposes the selection source, such as `explicit_question`, `default_unseen`, `default_due`, or `default_fallback`.

Question types own both prompts:

- `hint_prompt`: used for hints and explanations
- `mark_prompt`: used for scoring and explanation

The marking prompt must return JSON:

```json
{
  "awarded_marks": 3,
  "explanation": "Good reasoning, but you missed the final justification."
}
```

If the model returns invalid JSON, the app falls back to `0` marks with a generic retry message.

Python then derives the internal Leitner score:

- `0% -> 0`
- `>0% and <50% -> 1`
- `50%-74% -> 2`
- `75%-99% -> 3`
- `100% -> 4`

Scheduling intervals:

- `0 => immediate`
- `1 => 1 day`
- `2 => 3 days`
- `3 => 7 days`
- `4 => 21 days`

## API

Base path: `/api/chat/`

### Authentication

- `POST /login/`: authenticate with Django username/password, create a browser session, and return an API token; repeated failed attempts for the same username and client are throttled with `429`
- `POST /token/`: return the current browser session's token; this requires an already-authenticated Django session

### Courses

- `GET /courses/`: list courses with topics, question types, and counts
- `POST /courses/`: create a course and optionally bulk import topics, question types, and questions
- `POST /courses/<course_id>/questions/import/`: append new questions to an existing course

### Sessions

- `POST /sessions/`: create a session for a `course_id`
- `GET /sessions/<session_id>/`: return session state, active question, coverage, mastery, and topic progress
- `POST /chat/`: classify the learner message as hint, answer, or skip and return the updated session view

Session creation accepts these fields:

- `course_id`: required
- `selector_override_topic_id`: optional; must point at a topic in the selected course
- `selector_override_question_id`: optional; must point at a question in the selected course
- `selector_strategy_override`: optional string such as `"same_topic"`

Example session creation:

```bash
curl -X POST http://127.0.0.1:8000/api/chat/sessions/ \
  -H "Authorization: Token <token>" \
  -H "Content-Type: application/json" \
  -d '{
    "course_id": 1,
    "selector_override_topic_id": 2,
    "selector_strategy_override": "same_topic"
  }'
```

Example interaction:

```bash
curl -X POST http://127.0.0.1:8000/api/chat/chat/ \
  -H "Authorization: Token <token>" \
  -H "Content-Type: application/json" \
  -d '{"session_id":1,"text":"Can I get a hint?"}'
```

## Course Creation Payload

`POST /api/chat/courses/` accepts a nested payload:

```json
{
  "name": "Physics Intro",
  "topics": [
    {"name": "Motion", "import_key": "motion"},
    {"name": "Forces", "import_key": "forces"}
  ],
  "question_types": [
    {
      "name": "Short Answer",
      "import_key": "short",
      "hint_prompt": "Give a concise hint for this question only.",
      "mark_prompt": "Mark the answer and return JSON with awarded_marks and explanation."
    }
  ],
  "questions": [
    {
      "topic_import_key": "motion",
      "question_type_import_key": "short",
      "question_text": "Define speed in one sentence.",
      "max_marks": 4,
      "sample_answer": "Speed is distance travelled per unit time.",
      "example_answer": "Speed is the distance travelled per unit time.",
      "marking_notes": "Accept equivalent concise definitions."
    }
  ]
}
```

The import logic resolves question references by topic or question-type id, import key, or name.

## Questions-Only Import Payload

`POST /api/chat/courses/<course_id>/questions/import/` accepts a questions-only payload for an existing course:

```json
{
  "questions": [
    {
      "topic_import_key": "motion",
      "question_type_import_key": "short",
      "question_text": "What unit is speed usually measured in?",
      "max_marks": 4,
      "sample_answer": "Metres per second (m/s).",
      "example_answer": "A full-mark answer would be: speed is usually measured in metres per second, written as m/s.",
      "marking_notes": "Accept metres per second or m s^-1."
    }
  ]
}
```

Topics and question types must already exist on the target course. They can be referenced by id, import key, or name.

## Browser Pages

The browser UI is intentionally thin and calls the JSON API directly.

- The home page stores the token, selected course, and session id in `localStorage`.
- The home page shows the current active question, attempt count, selection source, and topic progress.
- The home page provides dedicated `Hint`, `Skip`, and `Full Answer` buttons.
- Clicking `Full Answer` logs a question attempt and either returns the stored `example_answer` or generates a full-mark answer with the model when the field is blank.
- AI-generated full answers are cached onto `CourseQuestion.example_answer` with the prefix `AI generated: ` so later requests reuse the stored answer.
- The course studio can either use a token from the JSON login flow or call `/api/chat/token/` when the browser already has an authenticated Django session.
- The course studio lists stored courses and their topic/question-type import keys to make follow-up question imports easier.

## Project Layout

```text
agentic_curiosity/  Django settings and root URLs
ai_chat/            Provider-neutral agents and persisted tutoring runtime models
chat_api/           Course content models, question selection, progress, and HTTP API
core/               Browser session console and course studio pages
manage.py           Django entry point
```

## Development Commands

```bash
uv run python manage.py test
uv run python manage.py test chat_api
uv run python manage.py test ai_chat
uv run python manage.py test core
uv run python manage.py check
uv run python manage.py migrate
uv run python manage.py runserver
```

`uv run python manage.py compact_chat_contexts` is still present as a command name, but it is deprecated and intentionally raises an error in the question-first engine.
