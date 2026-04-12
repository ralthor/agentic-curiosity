from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import SimpleTestCase

from .agents import Agent


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
