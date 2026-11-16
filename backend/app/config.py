"""Settings and the registry of Google Sheets the dashboard reads.

Everything that changes between environments comes from environment variables (see backend/.env.example).
"""
from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass, field
from functools import lru_cache


SHEET_REGISTRY: dict[str, dict] = {
    "tracker": {
        "name": "Master Sheet",
        "id": "1wBo0zF2wlqBzY5ZQaX5CPjCOedORwg_1Eh01vje5KFU",
        # Data tab the sheet dashboards are built from (first match wins).
        "source_tabs": ["CONFIRMATION SHEET", "ORDER SHEET"],
    },
    "sample_summary": {
        "name": "Sample Summary",
        "id": "1EfQ08lXGL8YjtoaZ2ygJtNVaED7doDijo2jFvCuS7Kg",
        "gid": 78218658,  # fallback only (used if none of the tab names below exist)
        "source_tabs": ["2026-27", "SAMPLE SHEET 2026-27", "Sheet1"],
    },
    "overview_fabricators": {
        "name": "Fabricator Report",
        "id": "1hP9Bkvu2F-qj4tXYhOCb4alfJOZZtAsMQNOjVQyWoo4",
        "gid": 164418035,  # fallback only
        "source_tabs": ["MONTHWISE SUMMARY", "MONTHWISE SUMMARY 2026-27"],
        "name_regex": r"monthwise|monthly\s*summary",
    },
    "fabric_po": {
        "name": "Fabric PO",
        "id": "1CvNPrdV4rQBR3_r8oIoPsW1ak123BGj88-qYbUU1y4I",
        "gid": 418084418,  # fallback only (INDEX tab)
        "source_tabs": ["INDEX"],
        "name_regex": r"^\s*index\s*$",
    },
    "target_revenue": {
        "name": "Designer Target",
        "id": "14USlaIteR3xlHjwzJOhZjLoyAZi-xAiF4LMXUE_UR2Y",
        "source_tabs": ["NEW"],  # NEW orders -> yearly target applies here
        "repeat_tabs": ["REPEAT"],  # REPEAT orders -> revenue only
        "annual_target_cr": 50.2,  # yearly NEW target in crore
    },
}


@dataclass(frozen=True)
class Settings:
    data_source: str = "demo"                   # "google" or "demo"
    service_account_info: dict | None = None    # parsed service-account JSON (google mode)
    live_ttl: int = 60                          # sheet DATA is re-read at most this often (seconds)
    tab_ttl: int = 600                          # tab list is re-read at most this often (seconds)
    refresh_cooldown: int = 15                  # minimum seconds between two forced refreshes
    passcode: str | None = None                 # when set, the API requires a login
    token_secret: str = "dev-only-secret"
    token_hours: int = 24 * 14
    cors_origins: list[str] = field(default_factory=list)


def _load_service_account() -> dict | None:
    raw = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON", "").strip()
    path = os.getenv("GOOGLE_SERVICE_ACCOUNT_FILE", "").strip()
    if not raw and path and os.path.isfile(path):
        with open(path, encoding="utf-8") as fh:
            raw = fh.read()
    if not raw:
        return None
    info = json.loads(raw)
    if "private_key" in info:
        info["private_key"] = str(info["private_key"]).replace("\\n", "\n")
    return info


def _load_dotenv() -> None:
    """Minimal .env reader (KEY=VALUE lines) so local runs need no extra package."""
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    env_path = os.path.join(here, ".env")
    if not os.path.isfile(env_path):
        return
    with open(env_path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            value = value.strip()
            if len(value) >= 2 and value[0] == value[-1] and value[0] in "'\"":
                value = value[1:-1]
            os.environ.setdefault(key.strip(), value)


_PUBLIC_SECRETS = {"", "dev-only-secret", "change-me"}


def _token_secret(sa: dict | None) -> str:
    """TOKEN_SECRET, or — if it was left empty or at the example value — one derived from the service account's private
    key, so a forgotten setting never leaves sign-in tokens signed with a publicly known secret."""
    secret = os.getenv("TOKEN_SECRET", "").strip()
    if secret not in _PUBLIC_SECRETS:
        return secret
    if sa and sa.get("private_key"):
        return hashlib.sha256(("flo-token:" + sa["private_key"]).encode()).hexdigest()
    return "dev-only-secret"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    _load_dotenv()
    sa = _load_service_account()
    source = os.getenv("DATA_SOURCE", "").strip().lower() or ("google" if sa else "demo")
    if source == "google" and sa is None:
        raise RuntimeError("DATA_SOURCE=google needs GOOGLE_SERVICE_ACCOUNT_JSON or GOOGLE_SERVICE_ACCOUNT_FILE.")
    origins = [o.strip() for o in os.getenv("CORS_ORIGINS", "").split(",") if o.strip()]
    return Settings(
        data_source=source,
        service_account_info=sa,
        live_ttl=int(os.getenv("LIVE_TTL_SECONDS", "60")),
        tab_ttl=int(os.getenv("TAB_TTL_SECONDS", "600")),
        refresh_cooldown=int(os.getenv("REFRESH_COOLDOWN_SECONDS", "15")),
        passcode=os.getenv("DASHBOARD_PASSCODE") or None,
        token_secret=_token_secret(sa),
        token_hours=int(os.getenv("TOKEN_HOURS", str(24 * 14))),
        cors_origins=origins,
    )
