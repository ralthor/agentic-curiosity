import json
from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import SimpleTestCase, TestCase
from django.utils import timezone

from ai_chat.models import ChatSession, LearnerQuestionState, QuestionAttempt, QuestionPresentation

from .models import ApiToken, Course, CourseQuestion, CourseTopic, QuestionType
from .progress import build_course_progress, derive_leitner_score, schedule_due_at
from .question_selector import select_next_question
from .services import classify_interaction, create_session


class RecordingAgent:
    def __init__(self, *, response_text="ok", **kwargs):
        self.response_text = response_text
        self.kwargs = kwargs

    def ask(self, text=None, *, messages=None, system=None, model=None, **kwargs):
        return self.response_text


class ProgressTests(SimpleTestCase):
    def test_derive_leitner_score_uses_ratio_buckets(self):
        self.assertEqual(derive_leitner_score(awarded_marks=0, max_marks=4), 0)
        self.assertEqual(derive_leitner_score(awarded_marks=1, max_marks=4), 1)
        self.assertEqual(derive_leitner_score(awarded_marks=2, max_marks=4), 2)
        self.assertEqual(derive_leitner_score(awarded_marks=3, max_marks=4), 3)
        self.assertEqual(derive_leitner_score(awarded_marks=4, max_marks=4), 4)

    def test_schedule_due_at_uses_fixed_intervals(self):
        start = timezone.now()
        self.assertEqual(schedule_due_at(from_time=start, leitner_score=0), start)
        self.assertEqual(schedule_due_at(from_time=start, leitner_score=1), start + timedelta(days=1))
        self.assertEqual(schedule_due_at(from_time=start, leitner_score=2), start + timedelta(days=3))
        self.assertEqual(schedule_due_at(from_time=start, leitner_score=3), start + timedelta(days=7))
        self.assertEqual(schedule_due_at(from_time=start, leitner_score=4), start + timedelta(days=21))

    def test_classify_interaction_distinguishes_skip_hint_and_answer(self):
        self.assertEqual(classify_interaction("skip this question"), QuestionAttempt.InteractionType.SKIP)
        self.assertEqual(classify_interaction("Can you give me a hint?"), QuestionAttempt.InteractionType.HINT_REQUEST)
        self.assertEqual(classify_interaction("The answer is 5"), QuestionAttempt.InteractionType.ANSWER_ATTEMPT)


class CourseQuestionModelTests(TestCase):
    def setUp(self):
        self.course = Course.objects.create(name="Math")
        self.other_course = Course.objects.create(name="Science")
        self.topic = CourseTopic.objects.create(course=self.course, name="Addition")
        self.other_topic = CourseTopic.objects.create(course=self.other_course, name="Cells")
        self.question_type = QuestionType.objects.create(
            course=self.course,
            name="Short Answer",
            hint_prompt="Hint prompt",
            mark_prompt="Mark prompt",
        )
        self.other_question_type = QuestionType.objects.create(
            course=self.other_course,
            name="Science Short Answer",
            hint_prompt="Hint prompt",
            mark_prompt="Mark prompt",
        )

    def test_course_question_requires_positive_max_marks(self):
        question = CourseQuestion(
            course=self.course,
            topic=self.topic,
            question_type=self.question_type,
            question_text="What is 2 + 2?",
            max_marks=0,
        )
        with self.assertRaises(ValidationError):
            question.full_clean()

    def test_course_question_requires_matching_course_relations(self):
        question = CourseQuestion(
            course=self.course,
            topic=self.other_topic,
            question_type=self.other_question_type,
            question_text="Mismatch",
            max_marks=4,
        )
        with self.assertRaises(ValidationError):
            question.full_clean()


class QuestionSelectorTests(TestCase):
    def setUp(self):
        self.course = Course.objects.create(name="Math")
        self.addition = CourseTopic.objects.create(course=self.course, name="Addition")
        self.subtraction = CourseTopic.objects.create(course=self.course, name="Subtraction")
        self.question_type = QuestionType.objects.create(
            course=self.course,
            name="Short Answer",
            hint_prompt="Hint prompt",
            mark_prompt="Mark prompt",
        )
        self.q1 = CourseQuestion.objects.create(
            course=self.course,
            topic=self.addition,
            question_type=self.question_type,
            question_text="1 + 1 = ?",
            max_marks=4,
        )
        self.q2 = CourseQuestion.objects.create(
            course=self.course,
            topic=self.addition,
            question_type=self.question_type,
            question_text="2 + 2 = ?",
            max_marks=4,
        )
        self.q3 = CourseQuestion.objects.create(
            course=self.course,
            topic=self.subtraction,
            question_type=self.question_type,
            question_text="4 - 1 = ?",
            max_marks=4,
        )
        self.session = ChatSession.objects.create(user_id="1", course=self.course)

    def test_selector_honors_explicit_question_override(self):
        self.session.selector_override_question = self.q3
        self.session.save(update_fields=["selector_override_question", "updated_at"])

        selection = select_next_question(user_id="1", course=self.course, session=self.session)

        self.assertIsNotNone(selection)
        self.assertEqual(selection.question, self.q3)
        self.assertEqual(selection.source, "explicit_question")

    def test_selector_prefers_unseen_question_from_less_recent_topic(self):
        first_presentation = QuestionPresentation.objects.create(
            session=self.session,
            question=self.q1,
            status=QuestionPresentation.Status.COMPLETED,
        )
        self.session.active_presentation = first_presentation
        self.session.save(update_fields=["active_presentation", "updated_at"])
        LearnerQuestionState.objects.create(
            user_id="1",
            course=self.course,
            question=self.q1,
            latest_leitner_score=3,
            best_leitner_score=3,
            due_at=timezone.now() + timedelta(days=7),
            times_seen=1,
            times_answered=1,
            last_presented_at=timezone.now(),
            last_completed_at=timezone.now(),
        )

        selection = select_next_question(user_id="1", course=self.course, session=self.session)

        self.assertIsNotNone(selection)
        self.assertEqual(selection.question, self.q3)
        self.assertEqual(selection.source, "default_unseen")


class ChatApiTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username="alice", password="wonderland")
        self.other_user = get_user_model().objects.create_user(username="bob", password="builder")
        self.course = Course.objects.create(name="Arithmetic")
        self.addition = CourseTopic.objects.create(course=self.course, name="Addition", import_key="addition")
        self.subtraction = CourseTopic.objects.create(course=self.course, name="Subtraction", import_key="subtraction")
        self.question_type = QuestionType.objects.create(
            course=self.course,
            name="Worked Answer",
            import_key="worked",
            hint_prompt="Give a short hint.",
            mark_prompt="Return JSON with awarded_marks and explanation.",
        )
        self.q1 = CourseQuestion.objects.create(
            course=self.course,
            topic=self.addition,
            question_type=self.question_type,
            question_text="What is 2 + 3?",
            max_marks=4,
            sample_answer="5",
            example_answer="A full-mark answer is 5.",
            marking_notes="Award full marks for 5.",
        )
        self.q2 = CourseQuestion.objects.create(
            course=self.course,
            topic=self.subtraction,
            question_type=self.question_type,
            question_text="What is 5 - 2?",
            max_marks=4,
            sample_answer="3",
            example_answer="",
            marking_notes="Award full marks for 3.",
        )

    def _post_json(self, path, payload, **extra):
        return self.client.post(
            path,
            data=json.dumps(payload),
            content_type="application/json",
            **extra,
        )

    def _authorization_header(self, token: ApiToken) -> dict[str, str]:
        return {"HTTP_AUTHORIZATION": f"Token {token.key}"}

    def test_login_returns_token_and_logs_the_user_in(self):
        response = self._post_json("/api/chat/login/", {"username": "alice", "password": "wonderland"})

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        token = ApiToken.objects.get(user=self.user)
        self.assertEqual(payload["token"], token.key)
        self.assertEqual(payload["user_id"], self.user.pk)
        self.assertEqual(self.client.session["_auth_user_id"], str(self.user.pk))

    def test_courses_endpoint_creates_nested_course_content(self):
        token = ApiToken.issue_for_user(self.user)

        response = self._post_json(
            "/api/chat/courses/",
            {
                "name": "Physics Intro",
                "topics": [{"name": "Motion", "import_key": "motion"}],
                "question_types": [
                    {
                        "name": "Short Answer",
                        "import_key": "short",
                        "hint_prompt": "Give a short hint.",
                        "mark_prompt": "Return JSON with awarded_marks and explanation.",
                    }
                ],
                "questions": [
                    {
                        "topic_import_key": "motion",
                        "question_type_import_key": "short",
                        "question_text": "Define speed.",
                        "max_marks": 4,
                        "example_answer": "Speed is the distance travelled per unit time.",
                    }
                ],
            },
            **self._authorization_header(token),
        )

        self.assertEqual(response.status_code, 201)
        course = Course.objects.get(name="Physics Intro")
        self.assertEqual(course.topics.count(), 1)
        self.assertEqual(course.question_types.count(), 1)
        self.assertEqual(course.questions.count(), 1)
        self.assertEqual(
            course.questions.get(question_text="Define speed.").example_answer,
            "Speed is the distance travelled per unit time.",
        )

    def test_course_question_import_endpoint_adds_questions_to_existing_course(self):
        token = ApiToken.issue_for_user(self.user)

        response = self._post_json(
            f"/api/chat/courses/{self.course.pk}/questions/import/",
            {
                "questions": [
                    {
                        "topic_import_key": "addition",
                        "question_type_import_key": "worked",
                        "question_text": "What is 7 + 1?",
                        "max_marks": 4,
                        "sample_answer": "8",
                        "example_answer": "A full-mark answer is 8.",
                        "marking_notes": "Award full marks for 8.",
                    },
                    {
                        "topic_name": "Subtraction",
                        "question_type_name": "Worked Answer",
                        "question_text": "What is 9 - 4?",
                        "max_marks": 4,
                        "sample_answer": "5",
                    },
                ]
            },
            **self._authorization_header(token),
        )

        self.assertEqual(response.status_code, 201)
        self.course.refresh_from_db()
        self.assertEqual(response.json()["imported_question_count"], 2)
        self.assertEqual(self.course.questions.count(), 4)
        self.assertTrue(self.course.questions.filter(question_text="What is 7 + 1?").exists())
        self.assertTrue(self.course.questions.filter(question_text="What is 9 - 4?").exists())
        self.assertEqual(
            self.course.questions.get(question_text="What is 7 + 1?").example_answer,
            "A full-mark answer is 8.",
        )

    def test_course_question_import_endpoint_requires_at_least_one_question(self):
        token = ApiToken.issue_for_user(self.user)

        response = self._post_json(
            f"/api/chat/courses/{self.course.pk}/questions/import/",
            {"questions": []},
            **self._authorization_header(token),
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"], "questions must contain at least one item.")

    def test_create_session_requires_course_id(self):
        token = ApiToken.issue_for_user(self.user)

        response = self._post_json("/api/chat/sessions/", {}, **self._authorization_header(token))

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"], "course_id must be a positive integer.")

    def test_create_session_assigns_the_first_question(self):
        token = ApiToken.issue_for_user(self.user)

        response = self._post_json(
            "/api/chat/sessions/",
            {"course_id": self.course.pk},
            **self._authorization_header(token),
        )

        self.assertEqual(response.status_code, 201)
        session = ChatSession.objects.get(pk=response.json()["session_id"])
        self.assertEqual(session.course, self.course)
        self.assertIsNotNone(session.active_presentation)
        self.assertEqual(session.active_presentation.question, self.q1)
        self.assertEqual(response.json()["active_question"]["question_text"], self.q1.question_text)
        state = LearnerQuestionState.objects.get(user_id=str(self.user.pk), course=self.course, question=self.q1)
        self.assertEqual(state.times_seen, 1)

    def test_session_detail_returns_course_progress_and_active_question(self):
        token = ApiToken.issue_for_user(self.user)
        session = create_session(user=self.user, course=self.course)

        response = self.client.get(
            f"/api/chat/sessions/{session.pk}/",
            **self._authorization_header(token),
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["course"]["name"], self.course.name)
        self.assertEqual(response.json()["active_question"]["question_text"], self.q1.question_text)
        self.assertEqual(response.json()["course_progress"]["coverage_pct"], 50)

    def test_hint_request_uses_one_model_call_and_does_not_increment_answer_count(self):
        token = ApiToken.issue_for_user(self.user)
        session = create_session(user=self.user, course=self.course)

        with patch("chat_api.services.OpenAIAgent") as agent_class:
            agent_class.side_effect = lambda **kwargs: RecordingAgent(response_text="Try combining two groups.")

            response = self._post_json(
                "/api/chat/chat/",
                {"session_id": session.pk, "text": "Can I get a hint?"},
                **self._authorization_header(token),
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["interaction_type"], "hint_request")
        self.assertEqual(response.json()["message"], "Try combining two groups.")
        self.assertIsNone(response.json()["awarded_marks"])
        self.assertFalse(response.json()["completed_presentation"])
        self.assertEqual(agent_class.call_count, 1)
        attempt = QuestionAttempt.objects.get(presentation=session.active_presentation)
        self.assertEqual(attempt.interaction_type, QuestionAttempt.InteractionType.HINT_REQUEST)
        state = LearnerQuestionState.objects.get(user_id=str(self.user.pk), course=self.course, question=self.q1)
        self.assertEqual(state.times_answered, 0)

    def test_partial_credit_answer_keeps_same_question_active(self):
        token = ApiToken.issue_for_user(self.user)
        session = create_session(user=self.user, course=self.course)

        with patch("chat_api.services.OpenAIAgent") as agent_class:
            agent_class.side_effect = lambda **kwargs: RecordingAgent(
                response_text='{"awarded_marks": 2, "explanation": "You added correctly but did not explain."}'
            )

            response = self._post_json(
                "/api/chat/chat/",
                {"session_id": session.pk, "text": "It is 5"},
                **self._authorization_header(token),
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["interaction_type"], "answer_attempt")
        self.assertEqual(response.json()["awarded_marks"], 2)
        self.assertEqual(response.json()["derived_leitner_score"], 2)
        self.assertFalse(response.json()["completed_presentation"])
        session.refresh_from_db()
        self.assertEqual(session.active_presentation.question, self.q1)
        state = LearnerQuestionState.objects.get(user_id=str(self.user.pk), course=self.course, question=self.q1)
        self.assertEqual(state.latest_leitner_score, 2)
        self.assertEqual(state.times_answered, 1)

    def test_full_answer_uses_stored_example_answer_and_logs_attempt(self):
        token = ApiToken.issue_for_user(self.user)
        session = create_session(user=self.user, course=self.course)

        with patch("chat_api.services.OpenAIAgent") as agent_class:
            response = self._post_json(
                "/api/chat/chat/",
                {"session_id": session.pk, "action": "full_answer"},
                **self._authorization_header(token),
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["interaction_type"], "full_answer_request")
        self.assertEqual(response.json()["message"], "A full-mark answer is 5.")
        self.assertFalse(response.json()["completed_presentation"])
        self.assertEqual(agent_class.call_count, 0)
        attempt = QuestionAttempt.objects.get(presentation=session.active_presentation)
        self.assertEqual(attempt.interaction_type, QuestionAttempt.InteractionType.FULL_ANSWER_REQUEST)
        self.assertEqual(attempt.model_response_text, "A full-mark answer is 5.")
        state = LearnerQuestionState.objects.get(user_id=str(self.user.pk), course=self.course, question=self.q1)
        self.assertEqual(state.times_answered, 0)

    def test_full_answer_uses_ai_when_stored_example_answer_is_blank(self):
        token = ApiToken.issue_for_user(self.user)
        session = create_session(user=self.user, course=self.course)

        with patch("chat_api.services.OpenAIAgent") as agent_class:
            agent_class.side_effect = [
                RecordingAgent(response_text='{"awarded_marks": 4, "explanation": "Correct."}'),
                RecordingAgent(response_text="A full-mark answer is 3."),
            ]

            answer_response = self._post_json(
                "/api/chat/chat/",
                {"session_id": session.pk, "text": "5"},
                **self._authorization_header(token),
            )
            response = self._post_json(
                "/api/chat/chat/",
                {"session_id": session.pk, "action": "full_answer"},
                **self._authorization_header(token),
            )
            cached_response = self._post_json(
                "/api/chat/chat/",
                {"session_id": session.pk, "action": "full_answer"},
                **self._authorization_header(token),
            )

        self.assertEqual(answer_response.status_code, 200)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(cached_response.status_code, 200)
        self.assertEqual(response.json()["interaction_type"], "full_answer_request")
        self.assertEqual(response.json()["message"], "AI generated: A full-mark answer is 3.")
        self.assertEqual(cached_response.json()["message"], "AI generated: A full-mark answer is 3.")
        self.assertEqual(agent_class.call_count, 2)
        session.refresh_from_db()
        self.q2.refresh_from_db()
        self.assertEqual(self.q2.example_answer, "AI generated: A full-mark answer is 3.")
        latest_attempt = QuestionAttempt.objects.filter(presentation=session.active_presentation).latest("created_at", "id")
        self.assertEqual(latest_attempt.interaction_type, QuestionAttempt.InteractionType.FULL_ANSWER_REQUEST)
        self.assertEqual(latest_attempt.model_response_text, "AI generated: A full-mark answer is 3.")

    def test_full_mark_answer_closes_question_and_advances(self):
        token = ApiToken.issue_for_user(self.user)
        session = create_session(user=self.user, course=self.course)
        first_presentation_id = session.active_presentation_id

        with patch("chat_api.services.OpenAIAgent") as agent_class:
            agent_class.side_effect = lambda **kwargs: RecordingAgent(
                response_text='{"awarded_marks": 4, "explanation": "Correct."}'
            )

            response = self._post_json(
                "/api/chat/chat/",
                {"session_id": session.pk, "text": "5"},
                **self._authorization_header(token),
            )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["completed_presentation"])
        self.assertEqual(response.json()["active_question"]["question_text"], self.q2.question_text)
        first_presentation = QuestionPresentation.objects.get(pk=first_presentation_id)
        self.assertEqual(first_presentation.status, QuestionPresentation.Status.COMPLETED)
        session.refresh_from_db()
        self.assertEqual(session.active_presentation.question, self.q2)
        state = LearnerQuestionState.objects.get(user_id=str(self.user.pk), course=self.course, question=self.q1)
        self.assertEqual(state.latest_leitner_score, 4)
        self.assertEqual(state.best_leitner_score, 4)

    def test_skip_closes_current_question_without_model_call(self):
        token = ApiToken.issue_for_user(self.user)
        session = create_session(user=self.user, course=self.course)
        first_presentation_id = session.active_presentation_id

        with patch("chat_api.services.OpenAIAgent") as agent_class:
            response = self._post_json(
                "/api/chat/chat/",
                {"session_id": session.pk, "text": "skip this question"},
                **self._authorization_header(token),
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["interaction_type"], "skip")
        self.assertTrue(response.json()["completed_presentation"])
        self.assertEqual(agent_class.call_count, 0)
        first_presentation = QuestionPresentation.objects.get(pk=first_presentation_id)
        self.assertEqual(first_presentation.status, QuestionPresentation.Status.SKIPPED)
        session.refresh_from_db()
        self.assertEqual(session.active_presentation.question, self.q2)

    def test_repeated_attempts_are_preserved_in_order(self):
        token = ApiToken.issue_for_user(self.user)
        session = create_session(user=self.user, course=self.course)

        with patch("chat_api.services.OpenAIAgent") as agent_class:
            agent_class.side_effect = [
                RecordingAgent(response_text="Try making the groups equal."),
                RecordingAgent(response_text='{"awarded_marks": 1, "explanation": "You need the final number."}'),
                RecordingAgent(response_text='{"awarded_marks": 4, "explanation": "Correct."}'),
            ]

            self._post_json(
                "/api/chat/chat/",
                {"session_id": session.pk, "text": "Can I get a hint?"},
                **self._authorization_header(token),
            )
            self._post_json(
                "/api/chat/chat/",
                {"session_id": session.pk, "text": "Maybe 4"},
                **self._authorization_header(token),
            )
            self._post_json(
                "/api/chat/chat/",
                {"session_id": session.pk, "text": "5"},
                **self._authorization_header(token),
            )

        attempts = list(
            QuestionAttempt.objects.filter(presentation_id=session.presentations.order_by("opened_at", "id").first().id)
            .order_by("created_at", "id")
        )
        self.assertEqual(
            [attempt.interaction_type for attempt in attempts],
            [
                QuestionAttempt.InteractionType.HINT_REQUEST,
                QuestionAttempt.InteractionType.ANSWER_ATTEMPT,
                QuestionAttempt.InteractionType.ANSWER_ATTEMPT,
            ],
        )

    def test_invalid_marking_output_falls_back_to_zero_marks(self):
        token = ApiToken.issue_for_user(self.user)
        session = create_session(user=self.user, course=self.course)

        with patch("chat_api.services.OpenAIAgent") as agent_class:
            agent_class.side_effect = lambda **kwargs: RecordingAgent(response_text="not json")

            response = self._post_json(
                "/api/chat/chat/",
                {"session_id": session.pk, "text": "5"},
                **self._authorization_header(token),
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["awarded_marks"], 0)
        self.assertEqual(response.json()["derived_leitner_score"], 0)
        self.assertFalse(response.json()["completed_presentation"])
        session.refresh_from_db()
        self.assertEqual(session.active_presentation.question, self.q1)

    def test_build_course_progress_aggregates_question_state(self):
        create_session(user=self.user, course=self.course)
        LearnerQuestionState.objects.filter(user_id=str(self.user.pk), course=self.course, question=self.q1).update(
            latest_leitner_score=4,
            best_leitner_score=4,
        )

        progress = build_course_progress(course=self.course, user_id=self.user.pk)

        self.assertEqual(progress["coverage_pct"], 50)
        self.assertEqual(progress["mastery_pct"], 50)
