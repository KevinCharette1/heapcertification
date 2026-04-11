from dataclasses import dataclass, field
from datetime import date


@dataclass
class ContractorReport:
    contractor_name: str
    client_id: str
    source: str          # "clickup" | "google_doc"
    raw_text: str
    week_ending: date
    fetch_error: str | None = None


@dataclass
class ClientDraft:
    client_id: str
    client_name: str
    week_ending: date
    consolidated_text: str
    target_google_doc_id: str
    source_reports: list[ContractorReport] = field(default_factory=list)
