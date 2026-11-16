"""Google Sheets source - read-only.

Uses the Sheets API v4 directly with the `spreadsheets.readonly` scope only: the service account can read the
sheets it has been shared with and can never write to them.
"""
from __future__ import annotations

import time
from urllib.parse import quote

from google.auth.transport.requests import AuthorizedSession
from google.oauth2.service_account import Credentials

SCOPES = ["https://www.googleapis.com/auth/spreadsheets.readonly"]
API = "https://sheets.googleapis.com/v4/spreadsheets"


class SheetAccessError(Exception):
    pass


def a1_tab(title: str) -> str:
    return "'" + str(title).replace("'", "''") + "'"


class GoogleSheetSource:
    name = "google"

    def __init__(self, service_account_info: dict, timeout: float = 30.0):
        creds = Credentials.from_service_account_info(service_account_info, scopes=SCOPES)
        self.session = AuthorizedSession(creds)
        self.timeout = timeout
        self.client_email = service_account_info.get("client_email", "")

    def _get(self, url: str, params: dict | None = None) -> dict:
        last = None
        for attempt in range(3):
            try:
                resp = self.session.get(url, params=params, timeout=self.timeout)
            except Exception as e:  # network error
                last = e
            else:
                if resp.status_code == 200:
                    return resp.json()
                if resp.status_code in (429, 500, 502, 503, 504):
                    last = SheetAccessError(f"Google API {resp.status_code}")
                else:
                    try:
                        msg = resp.json().get("error", {}).get("message", resp.text[:200])
                    except Exception:
                        msg = resp.text[:200]
                    hint = ""
                    if resp.status_code in (403, 404) and self.client_email:
                        hint = f" Share the sheet with {self.client_email} as Viewer."
                    raise SheetAccessError(f"Google API {resp.status_code}: {msg}.{hint}")
            time.sleep(0.6 * (2 ** attempt))
        raise SheetAccessError(f"Google Sheets could not be reached: {last}")

    def list_tabs(self, sheet_id: str) -> list[tuple[str, int]]:
        data = self._get(f"{API}/{sheet_id}", {"fields": "sheets.properties(title,sheetId,index)"})
        props = [s["properties"] for s in data.get("sheets", [])]
        props.sort(key=lambda p: p.get("index", 0))
        return [(p["title"], p["sheetId"]) for p in props]

    def get_values(self, sheet_id: str, tab: str, formatted: bool = False) -> list[list]:
        params = {} if formatted else {"valueRenderOption": "UNFORMATTED_VALUE",
                                       "dateTimeRenderOption": "SERIAL_NUMBER"}
        data = self._get(f"{API}/{sheet_id}/values/{quote(a1_tab(tab), safe='')}", params)
        return data.get("values", [])

    def get_formulas(self, sheet_id: str, tab: str, col_letter: str) -> list[list]:
        rng = f"{a1_tab(tab)}!{col_letter}:{col_letter}"
        data = self._get(f"{API}/{sheet_id}/values/{quote(rng, safe='')}", {"valueRenderOption": "FORMULA"})
        return data.get("values", [])
