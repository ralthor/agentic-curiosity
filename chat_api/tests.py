import json
from types import SimpleNamespace
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import SimpleTestCase, TestCase, override_settings

from ai_chat import Agent, Chat, ChatPrompt
from ai_chat.models import ChatContext, ChatSession, ChatTurn

from .models import ApiToken
from .services import build_chat


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

    def test_create_session_returns_a_session_id_for_the_authenticated_user(self):
        token = ApiToken.issue_for_user(self.user)

        response = self._post_json(
            "/api/chat/sessions/",
            {},
            **self._authorization_header(token),
        )

        self.assertEqual(response.status_code, 201)
        session = ChatSession.objects.get(pk=response.json()["session_id"])
        self.assertEqual(session.user_id, str(self.user.pk))
        self.assertTrue(ChatContext.objects.filter(session=session).exists())

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
        session = Chat.create_session(user_id=self.user.pk)

        def build_test_chat(*, user, session_id=None):
            self.assertEqual(user.pk, self.user.pk)
            self.assertEqual(session_id, session.pk)
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
            },
        )
        turn = ChatTurn.objects.get(session=session)
        self.assertEqual(turn.prompt_key, "judge")
        self.assertEqual(turn.user_text, "2 + 2 = 4")
        self.assertEqual(turn.agent_response, "Correct. 2 + 2 = 4. Did you understand?")


class ChatApiServiceTests(SimpleTestCase):
    @override_settings(
        AI_CHAT_MODEL=None,
        AI_CHAT_CATEGORIZER_MODEL=None,
        AI_CHAT_ANSWERER_MODEL=None,
        AI_CHAT_BRIEFER_MODEL=None,
    )
    def test_build_chat_uses_separate_default_models_per_agent(self):
        with patch("chat_api.services.OpenAIAgent") as openai_agent_class:
            openai_agent_class.side_effect = lambda **kwargs: kwargs

            chat = build_chat(user=SimpleNamespace(pk=7), session_id=12)

        self.assertEqual(chat.categorizer_agent["request_defaults"]["model"], "gpt-5-mini")
        self.assertEqual(chat.answerer_agent["request_defaults"]["model"], "gpt-5.4-mini")
        self.assertEqual(chat.briefer_agent["request_defaults"]["model"], "gpt-5-mini")
        self.assertNotIn("temperature", chat.categorizer_agent["request_defaults"])
        self.assertNotIn("temperature", chat.answerer_agent["request_defaults"])
        self.assertNotIn("temperature", chat.briefer_agent["request_defaults"])

    @override_settings(
        AI_CHAT_MODEL="shared-model",
        AI_CHAT_CATEGORIZER_MODEL="categorizer-model",
        AI_CHAT_ANSWERER_MODEL=None,
        AI_CHAT_BRIEFER_MODEL="briefer-model",
    )
    def test_build_chat_prefers_specific_model_settings_and_falls_back_to_shared_model(self):
        with patch("chat_api.services.OpenAIAgent") as openai_agent_class:
            openai_agent_class.side_effect = lambda **kwargs: kwargs

            chat = build_chat(user=SimpleNamespace(pk=7), session_id=12)

        self.assertEqual(chat.categorizer_agent["request_defaults"]["model"], "categorizer-model")
        self.assertEqual(chat.answerer_agent["request_defaults"]["model"], "shared-model")
        self.assertEqual(chat.briefer_agent["request_defaults"]["model"], "briefer-model")
        self.assertNotIn("temperature", chat.categorizer_agent["request_defaults"])
        self.assertNotIn("temperature", chat.answerer_agent["request_defaults"])
        self.assertNotIn("temperature", chat.briefer_agent["request_defaults"])
