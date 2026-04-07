from .agents import Agent
from .exceptions import AgentConfigurationError, AgentResponseError
from .openai_agent import OpenAIAgent

__all__ = [
    "Agent",
    "Chat",
    "ChatPrompt",
    "OpenAIAgent",
    "AgentConfigurationError",
    "AgentResponseError",
]


def __getattr__(name: str):
    if name in {"Chat", "ChatPrompt"}:
        from .chat import Chat, ChatPrompt

        return {"Chat": Chat, "ChatPrompt": ChatPrompt}[name]

    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
