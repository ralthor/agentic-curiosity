from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import SimpleTestCase, TestCase

from .agents import Agent
from .models import AnswerPhotoUpload, ChatSession, QuestionAttempt, QuestionPresentation
from chat_api.models import Course, CourseQuestion, CourseTopic, QuestionType


class RecordingAgent(Agent):
    def __init__(self, *, response_text="ok", **kwargs):
        super().__init__(**kwargs)
        self.response_text = response_text
        self.payloads = []

    def _create_completion(self, payload):
        self.payloads.append(payload)
        return {"choices": [{"message": {"content": self.response_text}}]}


class AgentTests(SimpleTestCase):
    def test_ask_builds_messages_from_text_and_system(self):
        agent = RecordingAgent(model="demo-model", system="Be concise.")

        response = agent.ask("Hello")

        self.assertEqual(response, "ok")
        self.assertEqual(
            agent.payloads[-1]["messages"],
            [
                {"role": "system", "content": "Be concise."},
                {"role": "user", "content": "Hello"},
            ],
        )

    def test_ask_accepts_explicit_messages(self):
        agent = RecordingAgent(model="demo-model", response_text="done")

        response = agent.ask(messages=[{"role": "user", "content": "Hi"}])

        self.assertEqual(response, "done")
        self.assertEqual(agent.payloads[-1]["messages"], [{"role": "user", "content": "Hi"}])

    def test_create_requires_a_model(self):
        agent = RecordingAgent()

        with self.assertRaises(ValueError):
            agent.create(messages=[{"role": "user", "content": "Hi"}])


class CompactChatContextsCommandTests(SimpleTestCase):
    def test_command_raises_deprecation_error(self):
        with self.assertRaises(CommandError):
            call_command("compact_chat_contexts")


class AnswerPhotoUploadModelTests(TestCase):
    def setUp(self):
        self.course = Course.objects.create(name="Model Test Course")
        self.topic = CourseTopic.objects.create(course=self.course, name="Model Test Topic")
        self.question_type = QuestionType.objects.create(
            course=self.course,
            name="Short Answer",
            hint_prompt="Hint prompt",
            mark_prompt="Mark prompt",
        )
        self.question = CourseQuestion.objects.create(
            course=self.course,
            topic=self.topic,
            question_type=self.question_type,
            question_text="What is 2 + 2?",
            max_marks=4,
        )
        self.session = ChatSession.objects.create(user_id="student-1", course=self.course)
        self.presentation = QuestionPresentation.objects.create(session=self.session, question=self.question)

    def test_answer_photo_upload_orders_within_a_presentation(self):
        first = AnswerPhotoUpload.objects.create(
            session=self.session,
            presentation=self.presentation,
            storage_key="answer-photos/one.jpg",
            filename="one.jpg",
            content_type="image/jpeg",
            byte_size=10,
            display_order=2,
        )
        second = AnswerPhotoUpload.objects.create(
            session=self.session,
            presentation=self.presentation,
            storage_key="answer-photos/two.jpg",
            filename="two.jpg",
            content_type="image/jpeg",
            byte_size=12,
            display_order=1,
        )

        uploads = list(AnswerPhotoUpload.objects.all())

        self.assertEqual([upload.pk for upload in uploads], [second.pk, first.pk])

    def test_answer_photo_upload_can_attach_to_one_attempt(self):
        attempt = QuestionAttempt.objects.create(
            presentation=self.presentation,
            interaction_type=QuestionAttempt.InteractionType.ANSWER_ATTEMPT,
            student_message="Photo 1 OCR:\n4",
            model_response_text="Correct.",
            awarded_marks=4,
            derived_leitner_score=4,
            completed_presentation=True,
        )
        upload = AnswerPhotoUpload.objects.create(
            session=self.session,
            presentation=self.presentation,
            storage_key="answer-photos/answer.jpg",
            filename="answer.jpg",
            content_type="image/jpeg",
            byte_size=20,
            display_order=1,
        )

        upload.attempt = attempt
        upload.extracted_text = "4"
        upload.save(update_fields=["attempt", "extracted_text", "updated_at"])
        upload.refresh_from_db()

        self.assertEqual(upload.attempt, attempt)
        self.assertEqual(upload.extracted_text, "4")
