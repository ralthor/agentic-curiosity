from io import StringIO
from types import SimpleNamespace
from unittest.mock import Mock, patch

from django.core.management import call_command
from django.test import SimpleTestCase, TestCase, override_settings

from .agents import Agent
from .chat import Chat, ChatPrompt
from .exceptions import AgentConfigurationError, AgentResponseError
from .models import ChatContext, ChatSession, ChatTurn
from .openai_agent import OpenAIAgent


class DummyAgent(Agent):
    def __init__(self, response, **kwargs):
        super().__init__(**kwargs)
        self.response = response
        self.last_payload = None

    def _create_completion(self, payload):
        self.last_payload = payload
        return self.response


class RecordingAgent(Agent):
    def __init__(self, *, response_text="ok", responder=None, **kwargs):
        super().__init__(**kwargs)
        self.response_text = response_text
        self.responder = responder
        self.payloads = []

    def _create_completion(self, payload):
        self.payloads.append(payload)
        if self.responder is None:
            content = self.response_text
        else:
            content = self.responder(payload)

        return {"choices": [{"message": {"content": content}}]}


class CommandBrieferAgent(Agent):
    payloads = []

    def _create_completion(self, payload):
        type(self).payloads.append(payload)
        return {"choices": [{"message": {"content": "Command summary"}}]}


class AgentTests(SimpleTestCase):
    def test_ask_builds_messages_from_text(self):
        agent = DummyAgent(
            {"choices": [{"message": {"content": "pong"}}]},
            model="dummy-model",
            system="Be brief.",
            temperature=0.3,
        )

        answer = agent.ask("Ping?")

        self.assertEqual(answer, "pong")
        self.assertEqual(
            agent.last_payload["messages"],
            [
                {"role": "system", "content": "Be brief."},
                {"role": "user", "content": "Ping?"},
            ],
        )
        self.assertEqual(agent.last_payload["model"], "dummy-model")
        self.assertEqual(agent.last_payload["temperature"], 0.3)

    def test_create_allows_call_time_overrides(self):
        agent = DummyAgent(
            {"choices": [{"message": {"content": "override works"}}]},
            model="default-model",
            temperature=0.1,
        )

        agent.create(
            messages=[{"role": "user", "content": "Hi"}],
            model="call-model",
            temperature=0.9,
            top_p=0.8,
        )

        self.assertEqual(agent.last_payload["model"], "call-model")
        self.assertEqual(agent.last_payload["temperature"], 0.9)
        self.assertEqual(agent.last_payload["top_p"], 0.8)

    def test_create_requires_a_model(self):
        agent = DummyAgent({"choices": [{"message": {"content": "missing model"}}]})

        with self.assertRaises(AgentConfigurationError):
            agent.create(messages=[{"role": "user", "content": "Hi"}])

    def test_ask_requires_text_or_messages(self):
        agent = DummyAgent({"choices": [{"message": {"content": "unused"}}]}, model="dummy")

        with self.assertRaises(ValueError):
            agent.ask()

    def test_ask_rejects_streaming(self):
        agent = DummyAgent({"choices": [{"message": {"content": "unused"}}]}, model="dummy")

        with self.assertRaises(ValueError):
            agent.ask("Hi", stream=True)

    def test_extract_text_raises_when_no_text_is_present(self):
        agent = DummyAgent({"choices": [{"message": {}}]}, model="dummy")

        with self.assertRaises(AgentResponseError):
            agent.ask("Hi")

    def test_init_accepts_model_and_system_inside_request_defaults(self):
        agent = DummyAgent(
            {"choices": [{"message": {"content": "pong"}}]},
            request_defaults={
                "model": "defaults-model",
                "system": "Defaults system prompt.",
                "temperature": 0.6,
            },
        )

        answer = agent.ask("Ping?")

        self.assertEqual(answer, "pong")
        self.assertEqual(agent.model, "defaults-model")
        self.assertEqual(agent.system, "Defaults system prompt.")
        self.assertEqual(
            agent.last_payload["messages"],
            [
                {"role": "system", "content": "Defaults system prompt."},
                {"role": "user", "content": "Ping?"},
            ],
        )
        self.assertEqual(agent.last_payload["model"], "defaults-model")
        self.assertEqual(agent.last_payload["temperature"], 0.6)


class OpenAIAgentTests(SimpleTestCase):
    def test_openai_agent_forwards_payload_to_sdk_client(self):
        response = SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content="Hello from OpenAI", refusal=None))]
        )
        create = Mock(return_value=response)
        client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
        agent = OpenAIAgent(client=client, model="gpt-4.1-mini", temperature=0.2)

        answer = agent.ask("Say hello", user="integration-test")

        self.assertEqual(answer, "Hello from OpenAI")
        create.assert_called_once_with(
            messages=[{"role": "user", "content": "Say hello"}],
            model="gpt-4.1-mini",
            temperature=0.2,
            user="integration-test",
        )

    @override_settings(
        OPENAI_API_KEY='settings-api-key',
        OPENAI_ORGANIZATION='settings-org',
        OPENAI_PROJECT='settings-project',
        OPENAI_BASE_URL='https://example.test/v1',
    )
    def test_openai_agent_uses_django_settings_when_explicit_values_are_missing(self):
        with patch('ai_chat.openai_agent.OpenAI') as openai_class:
            OpenAIAgent(model='gpt-4.1-mini')

        openai_class.assert_called_once_with(
            api_key='settings-api-key',
            organization='settings-org',
            project='settings-project',
            base_url='https://example.test/v1',
            timeout=None,
            max_retries=2,
            default_headers=None,
            default_query=None,
            http_client=None,
        )


class ChatTests(TestCase):
    def build_chat(
        self,
        *,
        user_id="user-1",
        session_id=None,
        categorizer_agent=None,
        answerer_agent=None,
        briefer_agent=None,
        context_threshold_bytes=5_120,
        recent_turns_to_keep=10,
    ):
        categorizer = categorizer_agent or RecordingAgent(model="categorizer", response_text="1")
        answerer = answerer_agent or RecordingAgent(model="answerer", response_text="agent reply")
        return Chat(
            user_id=user_id,
            session_id=session_id,
            prompts=[ChatPrompt("support", "Help the user solve support issues.")],
            categorizer_agent=categorizer,
            answerer_agent=answerer,
            briefer_agent=briefer_agent,
            context_threshold_bytes=context_threshold_bytes,
            recent_turns_to_keep=recent_turns_to_keep,
        )

    def test_create_session_initializes_a_context(self):
        session = Chat.create_session(user_id="user-1")
        context = ChatContext.objects.get(session=session)

        self.assertEqual(session.user_id, "user-1")
        self.assertTrue(ChatContext.objects.filter(session=session).exists())
        self.assertIsNotNone(session.created_at)
        self.assertIsNotNone(session.updated_at)
        self.assertIsNotNone(context.created_at)
        self.assertIsNotNone(context.updated_at)

    def test_reply_selects_prompt_persists_turn_and_uses_context(self):
        categorizer = RecordingAgent(model="categorizer", response_text="1", system="Pick a route.")
        answerer = RecordingAgent(model="answerer", response_text="Here is the answer.", system="Answer clearly.")
        chat = self.build_chat(categorizer_agent=categorizer, answerer_agent=answerer)

        reply = chat.reply("I need support", start_session=True)

        self.assertEqual(reply, "Here is the answer.")
        turn = ChatTurn.objects.get()
        context = ChatContext.objects.get(session=turn.session)
        self.assertEqual(turn.prompt_key, "support")
        self.assertEqual(turn.user_text, "I need support")
        self.assertEqual(turn.agent_response, "Here is the answer.")
        self.assertEqual(chat.session_id, turn.session_id)
        self.assertEqual(context.session_id, turn.session_id)
        self.assertIsNotNone(turn.created_at)
        self.assertIsNotNone(turn.updated_at)

        categorizer_payload = categorizer.payloads[-1]
        self.assertEqual(categorizer_payload["messages"][0]["content"], "Pick a route.")
        self.assertIn("Return only the prompt number and nothing else.", categorizer_payload["messages"][1]["content"])
        self.assertIn("1. Help the user solve support issues.", categorizer_payload["messages"][1]["content"])

        answerer_payload = answerer.payloads[-1]
        self.assertEqual(answerer_payload["messages"][0]["content"], "Answer clearly.")
        self.assertIn("Selected prompt (support):", answerer_payload["messages"][1]["content"])
        self.assertEqual(answerer_payload["messages"][-1], {"role": "user", "content": "I need support"})

    def test_reply_logs_session_prompt_and_turn_details(self):
        chat = self.build_chat()

        with self.assertLogs("ai_chat.chat", level="INFO") as captured:
            chat.reply("I need support", start_session=True)

        joined_logs = "\n".join(captured.output)
        self.assertIn("Processing chat reply for user user-1", joined_logs)
        self.assertIn("Started new chat session", joined_logs)
        self.assertIn("Selected prompt support", joined_logs)
        self.assertIn("Stored chat turn", joined_logs)

    def test_reply_maps_numbered_prompt_selection_to_key(self):
        categorizer = RecordingAgent(model="categorizer", response_text="2")
        answerer = RecordingAgent(model="answerer", response_text="Sales answer.")
        chat = Chat(
            user_id="user-2",
            prompts=[
                ChatPrompt("support", "Help the user solve support issues."),
                ChatPrompt("sales", "Answer pre-sales and pricing questions."),
            ],
            categorizer_agent=categorizer,
            answerer_agent=answerer,
        )

        reply = chat.reply("How much does the paid plan cost?", start_session=True)

        self.assertEqual(reply, "Sales answer.")
        self.assertEqual(ChatTurn.objects.get(session__user_id="user-2").prompt_key, "sales")
        self.assertIn("Selected prompt (sales):", answerer.payloads[-1]["messages"][0]["content"])

    def test_start_session_rotates_to_a_new_isolated_session(self):
        answerer = RecordingAgent(model="answerer", response_text="agent reply")
        chat = self.build_chat(answerer_agent=answerer)

        chat.reply("First question", start_session=True)
        first_session_id = chat.session_id
        first_payload = answerer.payloads[-1]["messages"]
        self.assertEqual(first_payload[-1], {"role": "user", "content": "First question"})

        chat.reply("Second question", start_session=True)

        second_payload = answerer.payloads[-1]["messages"]
        self.assertEqual(ChatSession.objects.filter(user_id="user-1").count(), 2)
        self.assertEqual(ChatContext.objects.count(), 2)
        self.assertNotEqual(chat.session_id, first_session_id)
        self.assertEqual(second_payload[-1], {"role": "user", "content": "Second question"})
        self.assertNotIn({"role": "user", "content": "First question"}, second_payload)
        self.assertNotIn({"role": "assistant", "content": "agent reply"}, second_payload[:-1])

    def test_reply_reuses_only_the_selected_session_history(self):
        answerer = RecordingAgent(model="answerer", response_text="agent reply")
        chat = self.build_chat(answerer_agent=answerer)

        chat.reply("Session one", start_session=True)
        first_session_id = chat.session_id
        chat.reply("Session one follow-up")

        second_session = Chat.create_session(user_id="user-1")
        another_chat = self.build_chat(session_id=second_session.pk, answerer_agent=answerer)
        another_chat.reply("Session two question")

        self.assertEqual(first_session_id, ChatTurn.objects.order_by("id").first().session_id)
        second_payload = answerer.payloads[-1]["messages"]
        self.assertEqual(second_payload[-1], {"role": "user", "content": "Session two question"})
        self.assertNotIn({"role": "user", "content": "Session one"}, second_payload)
        self.assertNotIn({"role": "user", "content": "Session one follow-up"}, second_payload)

    def test_compact_context_summarizes_older_turns_and_keeps_recent_turns(self):
        briefer = RecordingAgent(model="briefer", response_text="Condensed summary")
        answerer = RecordingAgent(
            model="answerer",
            responder=lambda payload: f"reply {len(payload['messages'])}",
        )
        chat = self.build_chat(
            answerer_agent=answerer,
            briefer_agent=briefer,
            context_threshold_bytes=100_000,
            recent_turns_to_keep=10,
        )

        for index in range(12):
            chat.reply(f"user turn {index}", start_session=index == 0)

        compacted = chat.compact_context(force=True)

        self.assertTrue(compacted)
        context = ChatContext.objects.get(session_id=chat.session_id)
        remaining_turns = list(ChatTurn.objects.filter(session_id=chat.session_id, id__gt=context.compacted_through_turn_id))
        self.assertEqual(context.summary, "Condensed summary")
        self.assertEqual(context.compacted_through_turn.user_text, "user turn 1")
        self.assertEqual(len(remaining_turns), 10)
        self.assertEqual(remaining_turns[0].user_text, "user turn 2")
        self.assertIn("Turns to condense:", briefer.payloads[-1]["messages"][-1]["content"])

    def test_compact_context_logs_decision_and_result(self):
        chat = self.build_chat(
            briefer_agent=RecordingAgent(model="briefer", response_text="Condensed summary"),
            context_threshold_bytes=100_000,
            recent_turns_to_keep=1,
        )
        for index in range(3):
            chat.reply(f"user turn {index}", start_session=index == 0)

        with self.assertLogs("ai_chat.chat", level="INFO") as captured:
            compacted = chat.compact_context(force=True)

        self.assertTrue(compacted)
        joined_logs = "\n".join(captured.output)
        self.assertIn("Compacting chat context for user user-1 session", joined_logs)
        self.assertIn("Compacted chat context for user user-1 session", joined_logs)

    def test_reply_does_not_fail_when_auto_compaction_raises(self):
        def raise_on_brief(_payload):
            raise RuntimeError("briefing failed")

        chat = self.build_chat(
            briefer_agent=RecordingAgent(model="briefer", responder=raise_on_brief),
            context_threshold_bytes=1,
            recent_turns_to_keep=1,
        )

        chat.reply("first message", start_session=True)
        with self.assertLogs("ai_chat.chat", level="ERROR"):
            reply = chat.reply("second message")

        self.assertEqual(reply, "agent reply")
        self.assertEqual(ChatTurn.objects.filter(session_id=chat.session_id).count(), 2)


class CompactChatContextsCommandTests(TestCase):
    def setUp(self):
        CommandBrieferAgent.payloads = []

    def test_command_compacts_oversized_contexts(self):
        chat = Chat(
            user_id="command-user",
            prompts={"support": "Help with support."},
            categorizer_agent=RecordingAgent(model="categorizer", response_text="1"),
            answerer_agent=RecordingAgent(model="answerer", response_text="brief response"),
            context_threshold_bytes=100_000,
            recent_turns_to_keep=2,
        )
        for index in range(4):
            chat.reply("x" * 80 + str(index), start_session=index == 0)

        stdout = StringIO()
        call_command(
            "compact_chat_contexts",
            "--agent-class",
            "ai_chat.tests.CommandBrieferAgent",
            "--model",
            "brief-model",
            "--threshold-bytes",
            "1",
            "--recent-turns",
            "2",
            stdout=stdout,
        )

        context = ChatContext.objects.get(session_id=chat.session_id)
        self.assertEqual(context.summary, "Command summary")
        self.assertIn("Compacted 1 chat context(s).", stdout.getvalue())
        self.assertTrue(CommandBrieferAgent.payloads)
