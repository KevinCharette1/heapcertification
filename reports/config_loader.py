from dataclasses import dataclass
from pathlib import Path

import yaml

DEFAULT_CONFIG_PATH = Path("report_config.yaml")


@dataclass
class ContractorConfig:
    name: str
    source: str                    # "clickup" | "google_doc"
    clickup_doc_id: str | None
    clickup_page_id: str | None    # optional; auto-fetches first page if None
    google_doc_id: str | None


@dataclass
class ClientConfig:
    id: str
    name: str
    google_doc_id: str             # target doc where consolidated report gets prepended
    contractors: list[ContractorConfig]


def load_report_config(path: Path = DEFAULT_CONFIG_PATH) -> list[ClientConfig]:
    """Load and validate report_config.yaml. Raises FileNotFoundError or ValueError."""
    if not path.exists():
        raise FileNotFoundError(
            f"Config file not found: {path}\n"
            "Create report_config.yaml — see .env.example comments for structure."
        )

    with open(path) as f:
        raw = yaml.safe_load(f)

    if not raw or "clients" not in raw:
        raise ValueError("report_config.yaml must have a top-level 'clients' list.")

    clients = []
    for i, c in enumerate(raw["clients"]):
        _require(c, "id", f"clients[{i}]")
        _require(c, "name", f"clients[{i}]")
        _require(c, "google_doc_id", f"clients[{i}]")

        contractors = []
        for j, ct in enumerate(c.get("contractors", [])):
            loc = f"clients[{i}].contractors[{j}]"
            _require(ct, "name", loc)
            _require(ct, "source", loc)
            source = ct["source"]
            if source not in ("clickup", "google_doc"):
                raise ValueError(
                    f"{loc}.source must be 'clickup' or 'google_doc', got '{source}'"
                )
            contractors.append(ContractorConfig(
                name=ct["name"],
                source=source,
                clickup_doc_id=ct.get("clickup_doc_id"),
                clickup_page_id=ct.get("clickup_page_id"),
                google_doc_id=ct.get("google_doc_id"),
            ))

        clients.append(ClientConfig(
            id=c["id"],
            name=c["name"],
            google_doc_id=c["google_doc_id"],
            contractors=contractors,
        ))

    return clients


def _require(obj: dict, key: str, location: str) -> None:
    if not obj.get(key):
        raise ValueError(f"Missing required field '{key}' in {location}")
