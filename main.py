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


def cmd_reports(settings, dry_run: bool = False) -> None:
    """
    Weekly report consolidation command.

    Usage:
        python main.py reports            # fetch, preview, approve, write to Google Docs
        python main.py reports --dry-run  # fetch and preview only — no Google Docs writes
    """
    import anthropic as _anthropic
    from datetime import date, timedelta
    from reports.config_loader import load_report_config
    from reports.clickup_reader import ClickUpReader
    from reports.google_docs_client import GoogleDocsClient
    from reports.consolidator import Consolidator
    from reports.models import ContractorReport

    # Validate required settings
    missing = []
    if not settings.clickup_api_token:
        missing.append("CLICKUP_API_TOKEN")
    if not settings.clickup_workspace_id:
        missing.append("CLICKUP_WORKSPACE_ID")
    if not settings.google_sa_key_file:
        missing.append("GOOGLE_SA_KEY_FILE")
    if missing:
        print("Error: the following env vars are required for the reports command:")
        for m in missing:
            print(f"  {m}")
        sys.exit(1)

    # Week ending = most recent Sunday (or today if today is Sunday)
    today = date.today()
    days_back = (today.weekday() + 1) % 7  # Sunday=6 → 0, Monday=0 → 1, …
    week_ending = today - timedelta(days=days_back)

    mode = " [DRY RUN — no writes]" if dry_run else ""
    print(f"Weekly Report Consolidation — Week Ending {week_ending.strftime('%B %d, %Y')}{mode}")
    print("─" * 60)

    # Load client/contractor config
    try:
        clients = load_report_config()
    except (FileNotFoundError, ValueError) as e:
        print(f"Error: {e}")
        sys.exit(1)

    print(f"Found {len(clients)} client(s) in report_config.yaml\n")

    # Initialise API clients
    clickup = ClickUpReader(
        api_token=settings.clickup_api_token,
        workspace_id=settings.clickup_workspace_id,
    )
    gdocs = GoogleDocsClient(client_secrets_file=settings.google_client_secret_file)
    anthropic_client = _anthropic.Anthropic(api_key=settings.anthropic_api_key)
    consolidator = Consolidator(anthropic_client=anthropic_client, model=settings.claude_model)

    # ── Fetch + consolidate ──────────────────────────────────────────────
    drafts = []
    for client_cfg in clients:
        print(f"Client: {client_cfg.name}")
        reports = []

        for contractor in client_cfg.contractors:
            print(
                f"  Fetching {contractor.name} ({contractor.source})...",
                end=" ",
                flush=True,
            )
            try:
                if contractor.source == "clickup":
                    raw = clickup.fetch_doc_content(
                        doc_id=contractor.clickup_doc_id,
                        page_id=contractor.clickup_page_id,
                    )
                elif contractor.source == "google_doc":
                    raw = gdocs.read_doc_text(contractor.google_doc_id)
                else:
                    raise ValueError(f"Unknown source type: {contractor.source!r}")
                reports.append(ContractorReport(
                    contractor_name=contractor.name,
                    client_id=client_cfg.id,
                    source=contractor.source,
                    raw_text=raw,
                    week_ending=week_ending,
                ))
                print("OK")
            except Exception as e:
                print(f"FAILED ({e})")
                reports.append(ContractorReport(
                    contractor_name=contractor.name,
                    client_id=client_cfg.id,
                    source=contractor.source,
                    raw_text="",
                    week_ending=week_ending,
                    fetch_error=str(e),
                ))

        print("  Consolidating with Claude...", end=" ", flush=True)
        draft = consolidator.consolidate(
            client_name=client_cfg.name,
            client_id=client_cfg.id,
            target_doc_id=client_cfg.google_doc_id,
            reports=reports,
            week_ending=week_ending,
        )
        drafts.append(draft)
        print("done\n")

    # ── Preview + approval loop ──────────────────────────────────────────
    print("=" * 60)
    print("DRAFT PREVIEW")
    print("=" * 60)

    approved = []
    skipped = []

    for draft in drafts:
        print(f"\n{'─' * 60}")
        print(f"Client:     {draft.client_name}")
        print(f"Target doc: https://docs.google.com/document/d/{draft.target_google_doc_id}")
        print(f"{'─' * 60}")
        print(draft.consolidated_text)
        print(f"{'─' * 60}")

        if dry_run:
            print("[dry-run] Skipping approval prompt.")
            skipped.append(draft)
            continue

        while True:
            try:
                choice = input(
                    f"\nApprove for {draft.client_name}? [y]es / [n]o / [e]dit: "
                ).strip().lower()
            except (EOFError, KeyboardInterrupt):
                print("\nAborted.")
                sys.exit(0)

            if choice in ("y", "yes"):
                approved.append(draft)
                break
            elif choice in ("n", "no"):
                skipped.append(draft)
                print(f"  Skipped.")
                break
            elif choice in ("e", "edit"):
                print("Paste your revised report below.")
                print("(Press Enter twice on a blank line to finish.)\n")
                lines = []
                blank_count = 0
                while blank_count < 1:
                    line = input()
                    if line == "":
                        blank_count += 1
                    else:
                        blank_count = 0
                    lines.append(line)
                draft.consolidated_text = "\n".join(lines).rstrip()
                print("\nRevised draft saved. Preview:\n")
                print(draft.consolidated_text)
                print(f"{'─' * 60}")
            else:
                print("  Please enter 'y', 'n', or 'e'.")

    # ── Write approved drafts ────────────────────────────────────────────
    if not approved:
        print(f"\nNo drafts approved. Nothing written.")
        return

    print(f"\nWriting {len(approved)} approved report(s) to Google Docs...")
    for draft in approved:
        print(f"  Prepending to {draft.client_name}'s doc...", end=" ", flush=True)
        try:
            gdocs.prepend_to_doc(draft.target_google_doc_id, draft.consolidated_text)
            print("done")
        except Exception as e:
            print(f"FAILED: {e}")

    print(f"\nSummary: {len(approved)} written, {len(skipped)} skipped.")


def cmd_chat(settings) -> None:
    """Start the interactive agent chat loop."""
    if not settings.linkedin_client_id or not settings.linkedin_client_secret:
        print("Error: LINKEDIN_CLIENT_ID and LINKEDIN_CLIENT_SECRET must be set in .env")
        print("Run 'python main.py login' after setting those values.")
        sys.exit(1)

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
        elif command == "reports":
            dry_run = "--dry-run" in sys.argv
            cmd_reports(settings, dry_run=dry_run)
        else:
            print(f"Unknown command: {command}")
            print("Usage: python main.py [login | reports [--dry-run]]")
            sys.exit(1)
    else:
        cmd_chat(settings)


if __name__ == "__main__":
    main()
