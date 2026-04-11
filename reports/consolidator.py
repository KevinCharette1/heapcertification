from datetime import date

import anthropic

from .models import ClientDraft, ContractorReport

SYSTEM_PROMPT = """\
You are a professional technical writer creating weekly status reports for clients.
You receive raw contractor weekly updates for a single client and produce one polished,
client-facing consolidated report. Follow these rules:

1. Group updates by contractor, summarizing accomplishments and blockers concisely
2. Use professional, plain language — no internal jargon or tool-specific terminology
3. Flag any blockers or risks prominently under a "Risks / Blockers" section
4. Keep the total length under 400 words
5. Use exactly this structure:

## Weekly Update — [Client Name] — Week Ending [Date]

### Summary
2-3 sentence overview of the week's progress across all contractors.

### Contractor Updates
**[Contractor Name]**
- [bullet point accomplishments]
- Blocker: [if any — otherwise omit this line]

### Risks / Blockers
[If none, write "None this week."]

### Next Steps
[Inferred from the reports — what is expected next week]
"""


class Consolidator:
    def __init__(self, anthropic_client: anthropic.Anthropic, model: str):
        self._client = anthropic_client
        self._model = model

    def consolidate(
        self,
        client_name: str,
        client_id: str,
        target_doc_id: str,
        reports: list[ContractorReport],
        week_ending: date,
    ) -> ClientDraft:
        """
        Use Claude to synthesize contractor reports into one client-facing draft.
        Reports with fetch_error are noted but excluded from content blocks.
        """
        report_blocks = []
        error_notes = []

        for r in reports:
            if r.fetch_error:
                error_notes.append(
                    f"- {r.contractor_name}: report could not be fetched — {r.fetch_error}"
                )
            else:
                report_blocks.append(
                    f"=== Report from {r.contractor_name} (source: {r.source}) ===\n"
                    f"{r.raw_text.strip()}\n"
                )

        user_msg = (
            f"Client: {client_name}\n"
            f"Week Ending: {week_ending.strftime('%B %d, %Y')}\n\n"
        )
        if error_notes:
            user_msg += (
                "NOTE — the following contractor reports could not be fetched "
                "and should be mentioned as unavailable:\n"
                + "\n".join(error_notes)
                + "\n\n"
            )
        if report_blocks:
            user_msg += "\n\n".join(report_blocks)
        else:
            user_msg += "(No contractor reports were available this week.)"

        response = self._client.messages.create(
            model=self._model,
            max_tokens=1024,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_msg}],
        )

        consolidated_text = response.content[0].text

        return ClientDraft(
            client_id=client_id,
            client_name=client_name,
            week_ending=week_ending,
            consolidated_text=consolidated_text,
            target_google_doc_id=target_doc_id,
            source_reports=reports,
        )
