import json
from types import SimpleNamespace
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import SimpleTestCase, TestCase, override_settings

from ai_chat import Agent, Chat, ChatPrompt
from ai_chat.models import ChatContext, ChatSession, ChatTurn

from .course_state import build_initial_course_state, serialize_course_state
from .models import ApiToken, CourseTopic
from .services import build_chat, create_session as create_topic_session


class RecordingAgent(Agent):
    def __init__(self, *, response_text="ok", **kwargs):
        super().__init__(**kwargs)
        self.response_text = response_text

    def _create_completion(self, payload):
        return {"choices": [{"message": {"content": self.response_text}}]}


class ChatApiTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username="alice", password="wonderland")
        self.other_user = get_user_model().objects.create_user(username="bob", password="builder")
        self.course_topic = CourseTopic.objects.create(
            name="Test Topic",
            teacher_prompt="Teach one arithmetic idea at a time.",
            judge_prompt="Judge a student's arithmetic answer.",
            categorizer_prompt="Pick the best prompt number and return only the number.",
            answerer_prompt="Answer clearly for the selected arithmetic prompt.",
            planner_prompt="Plan the next arithmetic item and report covered versus remaining items.",
            briefer_prompt="Condense the arithmetic tutoring session.",
            expectations=[
                "Add within 20 using objects, drawings, or equations.",
                "Subtract within 20 using objects, drawings, or equations.",
            ],
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
        response = self._post_json(
            "/api/chat/login/",
            {"username": "alice", "password": "wonderland"},
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        token = ApiToken.objects.get(user=self.user)
        self.assertEqual(payload["token"], token.key)
        self.assertEqual(payload["user_id"], self.user.pk)
        self.assertEqual(self.client.session["_auth_user_id"], str(self.user.pk))

    def test_session_authenticated_token_endpoint_returns_existing_token(self):
        login_response = self._post_json(
            "/api/chat/login/",
            {"username": "alice", "password": "wonderland"},
        )
        issued_token = login_response.json()["token"]

        response = self._post_json("/api/chat/token/", {})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["token"], issued_token)

    def test_create_session_requires_a_token(self):
        response = self._post_json("/api/chat/sessions/", {})

        self.assertEqual(response.status_code, 401)
        self.assertEqual(
            response.json()["error"],
            "Authentication credentials were not provided or are invalid.",
        )

    def test_create_session_requires_a_course_topic_id(self):
        token = ApiToken.issue_for_user(self.user)

        response = self._post_json(
            "/api/chat/sessions/",
            {},
            **self._authorization_header(token),
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"], "course_topic_id must be a positive integer.")

    def test_create_session_returns_a_session_id_and_course_topic_for_the_authenticated_user(self):
        token = ApiToken.issue_for_user(self.user)

        response = self._post_json(
            "/api/chat/sessions/",
            {"course_topic_id": self.course_topic.pk},
            **self._authorization_header(token),
        )

        self.assertEqual(response.status_code, 201)
        session = ChatSession.objects.get(pk=response.json()["session_id"])
        self.assertEqual(session.user_id, str(self.user.pk))
        self.assertEqual(session.course_topic, self.course_topic)
        self.assertTrue(ChatContext.objects.filter(session=session).exists())
        self.assertEqual(
            serialize_course_state(session.course_state, expectations=self.course_topic.expectations)["overall_progress"],
            0,
        )
        self.assertEqual(
            response.json()["course_topic"],
            {"id": self.course_topic.pk, "name": self.course_topic.name},
        )
        self.assertEqual(
            response.json()["course_state"],
            serialize_course_state(
                build_initial_course_state(self.course_topic.expectations),
                expectations=self.course_topic.expectations,
            ),
        )

    def test_course_topics_endpoint_lists_existing_topics(self):
        token = ApiToken.issue_for_user(self.user)

        response = self.client.get(
            "/api/chat/course-topics/",
            **self._authorization_header(token),
        )

        self.assertEqual(response.status_code, 200)
        topic_payload = next(topic for topic in response.json()["topics"] if topic["id"] == self.course_topic.pk)
        self.assertEqual(topic_payload["name"], self.course_topic.name)
        self.assertEqual(topic_payload["planner_prompt"], self.course_topic.planner_prompt)
        self.assertEqual(topic_payload["expectations"], self.course_topic.expectations)

    def test_course_topics_endpoint_creates_a_topic(self):
        token = ApiToken.issue_for_user(self.user)

        response = self._post_json(
            "/api/chat/course-topics/",
            {
                "name": "Physics Intro",
                "teacher_prompt": "Teach one physics idea at a time.",
                "judge_prompt": "Judge a physics answer.",
                "categorizer_prompt": "Return the best prompt number.",
                "answerer_prompt": "Answer as a physics tutor.",
                "planner_prompt": "Plan the next physics item and report topic progress.",
                "briefer_prompt": "Condense the physics session.",
                "expectations": [
                    "Explain motion using speed, direction, and simple forces.",
                    "Relate pushes and pulls to changes in movement.",
                ],
            },
            **self._authorization_header(token),
        )

        self.assertEqual(response.status_code, 201)
        topic = CourseTopic.objects.get(name="Physics Intro")
        self.assertEqual(response.json()["topic"]["id"], topic.pk)
        self.assertEqual(topic.planner_prompt, "Plan the next physics item and report topic progress.")
        self.assertEqual(topic.expectations[0], "Explain motion using speed, direction, and simple forces.")

    def test_session_detail_returns_the_stored_course_topic(self):
        token = ApiToken.issue_for_user(self.user)
        session = create_topic_session(user=self.user, course_topic=self.course_topic)

        response = self.client.get(
            f"/api/chat/sessions/{session.pk}/",
            **self._authorization_header(token),
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json()["course_topic"],
            {"id": self.course_topic.pk, "name": self.course_topic.name},
        )
        self.assertEqual(
            response.json()["course_state"],
            serialize_course_state(
                build_initial_course_state(self.course_topic.expectations),
                expectations=self.course_topic.expectations,
            ),
        )

    def test_chat_rejects_sessions_owned_by_another_user(self):
        token = ApiToken.issue_for_user(self.user)
        other_session = Chat.create_session(user_id=self.other_user.pk)

        response = self._post_json(
            "/api/chat/chat/",
            {"session_id": other_session.pk, "text": "2 + 2 = 4"},
            **self._authorization_header(token),
        )

        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()["error"], "Session not found.")

    def test_chat_returns_a_response_and_persists_the_turn(self):
        token = ApiToken.issue_for_user(self.user)
        session = create_topic_session(user=self.user, course_topic=self.course_topic)

        def build_test_chat(*, user, session_id=None, session=None, course_topic=None):
            self.assertEqual(user.pk, self.user.pk)
            self.assertEqual(session_id, session.pk)
            self.assertEqual(course_topic, self.course_topic)
            return Chat(
                user_id=user.pk,
                session_id=session_id,
                prompts=[
                    ChatPrompt("teacher", "Teach elementary math and ask a short question."),
                    ChatPrompt("judge", "Check the user's answer and ask if they understood."),
                ],
                categorizer_agent=RecordingAgent(model="categorizer", response_text="2"),
                answerer_agent=RecordingAgent(
                    model="answerer",
                    response_text="Correct. 2 + 2 = 4. Did you understand?",
                ),
                course_state=session.course_state,
                topic_expectations=course_topic.expectations,
            )

        with patch("chat_api.views.build_chat", side_effect=build_test_chat):
            response = self._post_json(
                "/api/chat/chat/",
                {"session_id": session.pk, "text": "2 + 2 = 4"},
                **self._authorization_header(token),
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json(),
            {
                "session_id": session.pk,
                "response": "Correct. 2 + 2 = 4. Did you understand?",
                "course_state": serialize_course_state(
                    build_initial_course_state(self.course_topic.expectations),
                    expectations=self.course_topic.expectations,
                ),
            },
        )
        turn = ChatTurn.objects.get(session=session)
        self.assertEqual(turn.prompt_key, "judge")
        self.assertEqual(turn.user_text, "2 + 2 = 4")
        self.assertEqual(turn.agent_response, "Correct. 2 + 2 = 4. Did you understand?")


class ChatApiServiceTests(SimpleTestCase):
    @override_settings(
        AI_CHAT_MODEL=None,
        AI_CHAT_ANSWERER_MODEL=None,
        AI_CHAT_PLANNER_MODEL=None,
        AI_CHAT_BRIEFER_MODEL=None,
    )
    def test_build_chat_uses_separate_default_models_per_agent(self):
        with patch("chat_api.services.OpenAIAgent") as openai_agent_class:
            openai_agent_class.side_effect = lambda **kwargs: kwargs

            chat = build_chat(
                user=SimpleNamespace(pk=7),
                session_id=12,
                course_topic=SimpleNamespace(
                    teacher_prompt="Teach arithmetic.",
                    judge_prompt="Judge arithmetic answers.",
                    categorizer_prompt="Pick a prompt number.",
                    answerer_prompt="Answer arithmetic questions clearly.",
                    planner_prompt="Plan arithmetic progression.",
                    briefer_prompt="Condense arithmetic sessions.",
                    name="Arithmetic",
                    expectations=[
                        "Add within 20 using objects, drawings, or equations.",
                        "Subtract within 20 using objects, drawings, or equations.",
                    ],
                ),
            )

        self.assertIsNone(chat.categorizer_agent)
        self.assertEqual(chat.answerer_agent["request_defaults"]["model"], "gpt-5.4-mini")
        self.assertEqual(chat.planner_agent["request_defaults"]["model"], "gpt-5-mini")
        self.assertEqual(chat.briefer_agent["request_defaults"]["model"], "gpt-5-mini")
        self.assertNotIn("temperature", chat.answerer_agent["request_defaults"])
        self.assertNotIn("temperature", chat.planner_agent["request_defaults"])
        self.assertNotIn("temperature", chat.briefer_agent["request_defaults"])
        self.assertEqual(chat.prompts["teacher"], "Teach arithmetic.")
        self.assertEqual(chat.prompts["judge"], "Judge arithmetic answers.")
        self.assertNotIn("planner", chat.prompts)
        self.assertEqual(chat.planner_prompt, "Plan arithmetic progression.")
        self.assertEqual(chat.topic_name, "Arithmetic")
        self.assertEqual(
            serialize_course_state(chat.course_state, expectations=["Add within 20 using objects, drawings, or equations.", "Subtract within 20 using objects, drawings, or equations."])["overall_progress"],
            0,
        )
        self.assertEqual(len(chat.course_state["scores"]), 2)

    @override_settings(
        AI_CHAT_MODEL="shared-model",
        AI_CHAT_ANSWERER_MODEL=None,
        AI_CHAT_PLANNER_MODEL="planner-model",
        AI_CHAT_BRIEFER_MODEL="briefer-model",
    )
    def test_build_chat_prefers_specific_model_settings_and_falls_back_to_shared_model(self):
        with patch("chat_api.services.OpenAIAgent") as openai_agent_class:
            openai_agent_class.side_effect = lambda **kwargs: kwargs

            chat = build_chat(
                user=SimpleNamespace(pk=7),
                session_id=12,
                course_topic=SimpleNamespace(
                    teacher_prompt="Teach writing.",
                    judge_prompt="Judge writing answers.",
                    categorizer_prompt="Pick a writing prompt number.",
                    answerer_prompt="Answer writing questions clearly.",
                    planner_prompt="Plan writing progression.",
                    briefer_prompt="Condense writing sessions.",
                    name="Writing",
                    expectations=["Write simple sentences.", "Revise sentences for clarity."],
                ),
            )

        self.assertIsNone(chat.categorizer_agent)
        self.assertEqual(chat.answerer_agent["request_defaults"]["model"], "shared-model")
        self.assertEqual(chat.planner_agent["request_defaults"]["model"], "planner-model")
        self.assertEqual(chat.briefer_agent["request_defaults"]["model"], "briefer-model")
        self.assertNotIn("temperature", chat.answerer_agent["request_defaults"])
        self.assertNotIn("temperature", chat.planner_agent["request_defaults"])
        self.assertNotIn("temperature", chat.briefer_agent["request_defaults"])
        self.assertNotIn("planner", chat.prompts)
        self.assertEqual(chat.planner_prompt, "Plan writing progression.")
        self.assertEqual(
            serialize_course_state(chat.course_state, expectations=["Write simple sentences.", "Revise sentences for clarity."])["overall_progress"],
            0,
        )
