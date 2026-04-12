# Agentic Curiosity

Minimal Django project for question-first tutoring with provider-neutral AI agents and persisted learner question state.

## What Changed

The app now uses a question-bank architecture:

- `Course` is the top-level teaching unit.
- `CourseTopic` organizes coverage and reporting inside a course.
- `QuestionType` stores the `hint_prompt` and `mark_prompt` for one reusable question format.
- `CourseQuestion` stores authored question text, marks, and optional marking guidance.
- `ChatSession` is now a lightweight runtime session tied to a course.
- `QuestionPresentation`, `QuestionAttempt`, and `LearnerQuestionState` are the primary runtime records.

The old expectation-index planner flow, full-session chat context, and prompt routing stack are no longer part of the active runtime.

## Requirements

- Python 3.11+
- `uv`
- An OpenAI API key if you want to use the OpenAI-backed model calls

## Quick Start

```bash
uv sync
uv run python manage.py migrate
uv run python manage.py runserver
```

Useful pages:

- `/`: session console for login, course selection, session creation, and question interaction
- `/course-topics/`: JSON import page for course/question-bank creation
- `/admin/`: Django admin for course and runtime records

## Runtime Model

Each active interaction is scoped to one served question:

1. The student creates a session for a selected course.
2. The selector module chooses the next question in code.
3. The app stores a `QuestionPresentation`.
4. The student either asks for a hint, submits an answer, or skips.
5. The model sees only:
   - the current question
   - question type
   - topic
   - max marks
   - optional sample answer / marking notes
   - the latest 3 attempts on the same question
   - the latest student message
6. The app stores a `QuestionAttempt` and updates `LearnerQuestionState`.
7. If the question closes, the selector picks the next question without a model call.

No full-conversation context is sent back to the model.

## Marking And Scheduling

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

- `POST /login/`: authenticate with Django username/password and return an API token
- `POST /token/`: return the current browser session's API token
- `GET /courses/`: list courses
- `POST /courses/`: create a course and optionally bulk import topics, question types, and questions
- `POST /sessions/`: create a session for a `course_id`
- `GET /sessions/<session_id>/`: return active question and derived progress
- `POST /chat/`: classify the message as hint, answer, or skip and return the updated active-question view

Example session creation:

```bash
curl -X POST http://127.0.0.1:8000/api/chat/sessions/ \
  -H "Authorization: Token <token>" \
  -H "Content-Type: application/json" \
  -d '{"course_id":1}'
```

Example interaction:

```bash
curl -X POST http://127.0.0.1:8000/api/chat/chat/ \
  -H "Authorization: Token <token>" \
  -H "Content-Type: application/json" \
  -d '{"session_id":1,"text":"Can I get a hint?"}'
```

## Course Import Payload

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
      "marking_notes": "Accept equivalent concise definitions."
    }
  ]
}
```

The import API resolves question references by topic/question-type id, import key, or name.

## Project Layout

```text
agentic_curiosity/  Django settings and root URLs
ai_chat/            Provider-neutral agents plus runtime session models
chat_api/           Course content models, selector, progress, and HTTP API
core/               Browser session console and course import page
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
