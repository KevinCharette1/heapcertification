"""
Agentic loop for the LinkedIn Campaign Agent.

Runs a Claude tool-use loop: send messages → handle tool calls → repeat
until Claude returns a final text response (stop_reason == "end_turn").
"""

import anthropic

from agent.tool_handlers import ToolHandler
from agent.tools import LINKEDIN_TOOLS
from agent.prompts import build_system_prompt

MAX_ITERATIONS = 20  # safety cap — prevents runaway loops


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

        messages = conversation_history + [{"role": "user", "content": user_message}]
        system = build_system_prompt(self._account_id)

        for iteration in range(MAX_ITERATIONS):
            response = self._client.messages.create(
                model=self._model,
                max_tokens=4096,
                system=system,
                messages=messages,
                tools=LINKEDIN_TOOLS,
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
