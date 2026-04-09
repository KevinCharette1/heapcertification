"""
Agentic loop for the LinkedIn Campaign Agent.

Runs a Claude tool-use loop: send messages → handle tool calls → repeat
until Claude returns a final text response (stop_reason == "end_turn").

Cost optimisations applied:
  1. Prompt caching — system prompt + tool definitions are marked with
     cache_control so Anthropic caches them after the first call.
     Cached tokens cost ~90% less than uncached input tokens.
  2. History trimming — only the last MAX_HISTORY messages are sent,
     preventing unbounded token growth over long sessions.
  3. Reduced max_tokens — capped at 1024; typical responses are 200-600 tokens.
"""

import anthropic

from agent.tool_handlers import ToolHandler
from agent.tools import LINKEDIN_TOOLS
from agent.prompts import build_system_prompt

MAX_ITERATIONS = 20   # safety cap — prevents runaway loops
MAX_HISTORY = 20      # keep last 10 conversation turns (user + assistant pairs)

# Cache the tool list: mark the final tool so Anthropic caches the entire
# tools block on the first call. Subsequent calls within the 5-min cache
# window pay ~10% of normal input token cost for these definitions.
_TOOLS_CACHED = [
    *LINKEDIN_TOOLS[:-1],
    {**LINKEDIN_TOOLS[-1], "cache_control": {"type": "ephemeral"}},
]


class AgentRunner:
    def __init__(
        self,
        anthropic_client: anthropic.Anthropic,
        tool_handler: ToolHandler,
        account_id: str,
        model: str = "claude-sonnet-4-6",
    ):
        self._client = anthropic_client
        self._handler = tool_handler
        self._account_id = account_id
        self._model = model

    def run(
        self,
        user_message: str,
        conversation_history: list | None = None,
    ) -> tuple[str, list]:
        """
        Send a user message and run the agentic loop to completion.

        Returns:
            (final_text_response, updated_conversation_history)

        The caller should persist conversation_history between turns to enable
        multi-turn conversations.
        """
        if conversation_history is None:
            conversation_history = []

        # Trim history before adding the new user message so the total sent
        # to the API never exceeds MAX_HISTORY + 1 messages.
        trimmed = conversation_history[-MAX_HISTORY:] if len(conversation_history) > MAX_HISTORY else conversation_history
        messages = trimmed + [{"role": "user", "content": user_message}]

        # System prompt passed as a list with cache_control so Anthropic
        # caches it after the first call (~90% discount on subsequent calls).
        system = [
            {
                "type": "text",
                "text": build_system_prompt(self._account_id),
                "cache_control": {"type": "ephemeral"},
            }
        ]

        for iteration in range(MAX_ITERATIONS):
            response = self._client.messages.create(
                model=self._model,
                max_tokens=1024,
                system=system,
                messages=messages,
                tools=_TOOLS_CACHED,
            )

            # Append the assistant turn to history
            messages.append({"role": "assistant", "content": response.content})

            if response.stop_reason == "end_turn":
                text = _extract_text(response.content)
                return text, messages

            if response.stop_reason == "tool_use":
                tool_results = []
                for block in response.content:
                    if block.type == "tool_use":
                        _print_tool_call(block.name, block.input)
                        result_str = self._handler.dispatch(block.name, block.input)
                        tool_results.append(
                            {
                                "type": "tool_result",
                                "tool_use_id": block.id,
                                "content": result_str,
                            }
                        )
                messages.append({"role": "user", "content": tool_results})
                continue

            # Unexpected stop reason — return whatever text we have
            break

        text = _extract_text(response.content) if response else "(no response)"
        return text, messages


def _extract_text(content: list) -> str:
    parts = [block.text for block in content if hasattr(block, "text") and block.text]
    return "\n".join(parts) if parts else "(no response)"


def _print_tool_call(name: str, inp: dict) -> None:
    """Print a compact tool call indicator for the CLI."""
    # Show the most useful field from the input (name, query, campaign_id, etc.)
    label = (
        inp.get("name")
        or inp.get("query")
        or inp.get("campaign_id")
        or inp.get("account_id")
        or ""
    )
    if label:
        print(f"  [→ {name}: {label}]")
    else:
        print(f"  [→ {name}]")
