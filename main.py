#!/usr/bin/env python3
"""
LinkedIn Campaign Agent — CLI entry point.

Usage:
    python main.py login    # First-time OAuth setup (opens browser)
    python main.py          # Start the interactive agent chat loop
"""

import json
import sys
from pathlib import Path

import anthropic

from config import get_settings
from linkedin.client import LinkedInClient
from linkedin.oauth import show_oauth_url, complete_oauth_from_url
from agent.runner import AgentRunner
from agent.tool_handlers import ToolHandler

TOKENS_FILE = Path("tokens.json")


def load_tokens() -> dict | None:
    if not TOKENS_FILE.exists():
        return None
    with open(TOKENS_FILE) as f:
        return json.load(f)


def save_tokens(tokens: dict) -> None:
    with open(TOKENS_FILE, "w") as f:
        json.dump(tokens, f, indent=2)
    TOKENS_FILE.chmod(0o600)  # owner read/write only


def cmd_login(settings, callback_url: str | None = None) -> None:
    """
    OAuth login — two-step flow:
      Step 1: python main.py login
        → prints the auth URL; saves state to .oauth_state
      Step 2: python main.py login 'http://localhost:8888/callback?code=...&state=...'
        → completes auth using the pasted callback URL
    """
    if callback_url:
        # Step 2 — complete the flow with the pasted callback URL
        tokens = complete_oauth_from_url(callback_url, settings)
        save_tokens(tokens)
        name = tokens.get("member_name") or tokens.get("member_id") or "unknown"
        print(f"\nAuthenticated as: {name}")
        print(f"Tokens saved to {TOKENS_FILE}")
        print("\nRun 'python main.py' to start the agent.")
    else:
        # Step 1 — show the auth URL
        show_oauth_url(settings)


def pick_account(accounts: list[dict]) -> dict:
    """Interactively select an ad account from the list."""
    if len(accounts) == 1:
        print(f"Using account: {accounts[0]['name']} ({accounts[0]['id']})")
        return accounts[0]

    print("\nYour LinkedIn ad accounts:")
    for i, acc in enumerate(accounts, 1):
        currency = f"  [{acc.get('currency', '')}]" if acc.get("currency") else ""
        print(f"  {i}. {acc['name']}{currency}")
        print(f"     {acc['id']}")

    while True:
        choice = input("\nWhich account are you working on? (enter number) > ").strip()
        if choice.isdigit() and 1 <= int(choice) <= len(accounts):
            account = accounts[int(choice) - 1]
            print(f"\nWorking on: {account['name']}")
            return account
        print(f"Please enter a number between 1 and {len(accounts)}.")


def cmd_chat(settings) -> None:
    """Start the interactive agent chat loop."""
    tokens = load_tokens()
    if not tokens:
        print("No authentication tokens found.")
        print("Run 'python main.py login' first to connect your LinkedIn account.")
        sys.exit(1)

    linkedin_client = LinkedInClient(tokens, settings)

    # Account selection
    print("Fetching your LinkedIn ad accounts...", end=" ", flush=True)
    try:
        accounts = linkedin_client.list_ad_accounts()
    except Exception as e:
        from linkedin.exceptions import LinkedInAPIError
        print(f"\nFailed to fetch ad accounts: {e}")
        if isinstance(e, LinkedInAPIError) and e.status_code == 403:
            print("\n403 Permission denied. To fix this:")
            print("  1. Go to https://www.linkedin.com/developers/apps → your app → Products tab")
            print("  2. Find 'Advertising API' — ensure its status is 'Approved'")
            print("  3. If approved: click 'View Ad Accounts' and link your ad account to the app")
            print("  4. Run 'python main.py login' again to refresh your token")
        elif isinstance(e, LinkedInAPIError) and e.status_code == 401:
            print("Your token has expired. Run 'python main.py login' to re-authenticate.")
        else:
            print("Run 'python main.py login' to re-authenticate if the issue persists.")
        sys.exit(1)

    if not accounts:
        print("\nNo active ad accounts found for this LinkedIn account.")
        sys.exit(1)
    print(f"found {len(accounts)}.")

    account = pick_account(accounts)
    account_id = account["id"]

    anthropic_client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
    tool_handler = ToolHandler(linkedin_client, account_id)
    runner = AgentRunner(
        anthropic_client=anthropic_client,
        tool_handler=tool_handler,
        account_id=account_id,
        model=settings.claude_model,
    )

    print("\n" + "─" * 60)
    print("LinkedIn Campaign Agent is ready.")
    print("Type your request in plain English, or:")
    print("  'switch account' — change the active ad account")
    print("  'exit' or 'quit'  — end the session")
    print("─" * 60 + "\n")

    conversation_history: list = []

    while True:
        try:
            user_input = input("You: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nGoodbye!")
            break

        if not user_input:
            continue

        if user_input.lower() in ("exit", "quit", "bye", "q"):
            print("Goodbye!")
            break

        if user_input.lower() in ("switch account", "change account"):
            account = pick_account(accounts)
            account_id = account["id"]
            tool_handler = ToolHandler(linkedin_client, account_id)
            runner = AgentRunner(
                anthropic_client=anthropic_client,
                tool_handler=tool_handler,
                account_id=account_id,
                model=settings.claude_model,
            )
            conversation_history = []
            print(f"Switched to: {account['name']}\n")
            continue

        try:
            print("Agent:", end=" ", flush=True)
            response, conversation_history = runner.run(user_input, conversation_history)
            print(response)
        except Exception as e:
            print(f"\n[Error] {e}")
            print("You can keep going — the conversation history is preserved.\n")
            continue

        print()


def main() -> None:
    settings = get_settings()

    if len(sys.argv) > 1:
        command = sys.argv[1].lower()
        if command == "login":
            callback_url = sys.argv[2] if len(sys.argv) > 2 else None
            cmd_login(settings, callback_url=callback_url)
        else:
            print(f"Unknown command: {command}")
            print("Usage: python main.py [login]")
            sys.exit(1)
    else:
        cmd_chat(settings)


if __name__ == "__main__":
    main()
