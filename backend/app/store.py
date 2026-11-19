"""Data store: reads the sheets through a source, caches the grids for LIVE_TTL seconds, parses them once per change.

- Only one request per sheet tab is in flight at a time (others wait for it), so a burst of users costs Google
  one read per minute, not one per user.
- If Google fails and an older copy exists, the older copy is served and the dataset is marked stale.
- Parsed datasets are cached by the version (hash) of the grids they came from.
"""
from __future__ import annotations

import hashlib
import json
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime, timezone

from .config import SHEET_REGISTRY, Settings, sheet_id
from .core import find_tab, idx_to_col, pick_default_tab, today_ist
from .dashboards import fabric_po as fpo
from .dashboards import fabricator as fab
from .dashboards import flo_future as ffu
from .dashboards import master as mst
from .dashboards import samples as smp
from .dashboards import target as tgt
from .sources.google import SheetAccessError

KINDS = ["tracker", "sample_summary", "overview_fabricators", "fabric_po", "target_revenue", "flo_future"]
# Kinds whose numbers depend on today's date (overdue / due soon), so their parsed copy is redone each day.
DATED_KINDS = {"fabric_po", "flo_future"}
FLO_FUTURE_PARTS = ("samples", "outsource", "visits")


def _now() -> float:
    return time.time()


def _iso(ts: float | None) -> str | None:
    return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat() if ts else None


def _digest(obj) -> str:
    return hashlib.sha1(json.dumps(obj, default=str, separators=(",", ":")).encode()).hexdigest()[:12]


@dataclass
class Entry:
    value: object
    fetched_at: float
    expires_at: float
    version: str = ""
    error: str | None = None


@dataclass
class Dataset:
    kind: str
    data: object | None
    fetched_at: float | None
    version: str
    error: str | None = None
    stale: bool = False
    tabs: list = field(default_factory=list)


class TTLCache:
    def __init__(self):
        self._data: dict = {}
        self._locks: dict = {}
        self._guard = threading.Lock()

    def _lock(self, key):
        with self._guard:
            return self._locks.setdefault(key, threading.Lock())

    def get(self, key, ttl: float, loader, versioned=False) -> Entry:
        e = self._data.get(key)
        if e is not None and e.expires_at > _now():
            return e
        with self._lock(key):
            e = self._data.get(key)
            if e is not None and e.expires_at > _now():
                return e
            try:
                value = loader()
            except Exception as ex:
                if e is not None:              # serve the last good copy, retry soon
                    stale = Entry(e.value, e.fetched_at, _now() + min(ttl, 20), e.version, str(ex))
                    self._data[key] = stale
                    return stale
                raise
            t = _now()
            fresh = Entry(value, t, t + ttl, _digest(value) if versioned else "")
            self._data[key] = fresh
            return fresh

    def clear(self):
        with self._guard:
            self._data.clear()


class DataStore:
    def __init__(self, source, settings: Settings):
        self.source = source
        self.settings = settings
        self.raw = TTLCache()
        self._parsed: dict = {}
        self._parsed_lock = threading.Lock()
        self._last_refresh = 0.0
        self._pool = ThreadPoolExecutor(max_workers=8)    # grid fetches (never wait on anything)
        self._outer = ThreadPoolExecutor(max_workers=5)   # datasets (wait on grid fetches)

    # -- low level ---------------------------------------------------------------------------------------------
    def tabs(self, sheet_id) -> list[tuple[str, int]]:
        return self.raw.get(("tabs", sheet_id), self.settings.tab_ttl,
                            lambda: self.source.list_tabs(sheet_id)).value

    def grid(self, sheet_id, tab, formatted=False) -> Entry:
        return self.raw.get(("grid", sheet_id, tab, formatted), self.settings.live_ttl,
                            lambda: self.source.get_values(sheet_id, tab, formatted), versioned=True)

    def formulas(self, sheet_id, tab, col_letter) -> Entry:
        def load():
            try:
                return self.source.get_formulas(sheet_id, tab, col_letter)
            except Exception:
                return []           # images are optional; the dashboard works without them
        return self.raw.get(("formulas", sheet_id, tab, col_letter), self.settings.live_ttl, load, versioned=True)

    def refresh(self) -> bool:
        """Drops cached grids so the next read goes to Google. Rate-limited by REFRESH_COOLDOWN_SECONDS."""
        if _now() - self._last_refresh < self.settings.refresh_cooldown:
            return False
        self._last_refresh = _now()
        self.raw.clear()
        return True

    # -- tab choice (same rules as the original dashboards) ----------------------------------------------------
    def source_tabs(self, kind) -> list:
        cfg = SHEET_REGISTRY[kind]
        meta = self.tabs(sheet_id(kind))
        if not meta:
            raise SheetAccessError("No tabs found on the sheet.")
        if kind == "tracker":
            titles = [t for t, _ in meta]
            src = next((t for t in (find_tab(titles, c) for c in cfg["source_tabs"]) if t), None)
            return [src or next((t for t in titles if "DASHBOARD" not in t.upper()), titles[0])]
        if kind == "flo_future":
            titles = [t for t, _ in meta]
            tabs = [next((x for x in (find_tab(titles, n) for n in cfg[f"{part}_tabs"]) if x), None)
                    for part in FLO_FUTURE_PARTS]
            if tabs[0] is None and tabs[1] is None:
                raise SheetAccessError("The FLO Future sheet has no 'Samples' or 'Outsource Projects' tab.")
            return tabs
        if kind == "target_revenue":
            titles = [t for t, _ in meta]
            return [next((x for x in (find_tab(titles, n) for n in cfg.get(key, [default])) if x), None)
                    for key, default in (("source_tabs", "NEW"), ("repeat_tabs", "REPEAT"))]
        return [pick_default_tab(meta, cfg.get("source_tabs", []), cfg.get("gid"), cfg.get("name_regex"))]

    def _entries(self, kind) -> tuple[list, list]:
        """Fetches every grid a dataset needs (in parallel). Returns (tabs, entries)."""
        sid = sheet_id(kind)
        tabs = self.source_tabs(kind)
        jobs = []
        if kind == "overview_fabricators":
            jobs = [(tabs[0], True), (tabs[0], False)]
        elif kind in ("target_revenue", "flo_future"):
            jobs = [(t, False) for t in tabs if t]
        else:
            jobs = [(tabs[0], False)]
        entries = list(self._pool.map(lambda j: self.grid(sid, j[0], j[1]), jobs))
        if kind == "target_revenue":
            extra = []
            for t, e in zip([t for t in tabs if t], entries):
                hr = tgt.tgt_header_row(e.value)
                cmap = tgt.tgt_col_map(e.value[hr if hr is not None else 1]) if len(e.value) > 1 else {"image": 2}
                extra.append(self.formulas(sid, t, idx_to_col(cmap["image"])))
            entries += extra
        return tabs, entries

    def _parse(self, kind, tabs, entries):
        if kind == "tracker":
            d, err = mst.parse_master(entries[0].value)
            if err:
                raise SheetAccessError(err)
            return d
        if kind == "sample_summary":
            return smp.parse_samples(entries[0].value)
        if kind == "overview_fabricators":
            return fab.parse_fabricator(entries[0].value, entries[1].value)
        if kind == "fabric_po":
            return fpo.parse_fabric_po(entries[0].value, today_ist())
        if kind == "flo_future":
            grids = iter(entries)
            return ffu.parse_flo_future({part: (next(grids).value if t else [])
                                         for part, t in zip(FLO_FUTURE_PARTS, tabs)})
        if kind == "target_revenue":
            present = [t for t in tabs if t]
            grids = dict(zip(present, entries[:len(present)]))
            forms = dict(zip(present, entries[len(present):]))
            packs = []
            for source, t in zip(("NEW", "REPEAT"), tabs):
                packs.append((source, t, grids[t].value if t else [], forms[t].value if t else []))
            return tgt.parse_target(packs)
        raise KeyError(kind)

    def dataset(self, kind) -> Dataset:
        try:
            tabs, entries = self._entries(kind)
        except SheetAccessError as e:
            return Dataset(kind, None, None, "", error=str(e))
        except Exception as e:
            return Dataset(kind, None, None, "", error=f"{type(e).__name__}: {e}")
        version = _digest([e.version for e in entries] + ([str(today_ist().date())] if kind in DATED_KINDS else []))
        fetched = min(e.fetched_at for e in entries)
        stale_err = next((e.error for e in entries if e.error), None)
        with self._parsed_lock:
            hit = self._parsed.get(kind)
        if hit and hit[0] == version:
            data = hit[1]
        else:
            try:
                data = self._parse(kind, tabs, entries)
            except SheetAccessError as e:
                return Dataset(kind, None, fetched, version, error=str(e), tabs=tabs)
            with self._parsed_lock:
                self._parsed[kind] = (version, data)
        return Dataset(kind, data, fetched, version, error=stale_err, stale=bool(stale_err), tabs=tabs)

    def datasets(self, kinds) -> dict:
        kinds = list(kinds)
        return dict(zip(kinds, self._outer.map(self.dataset, kinds)))

    def status(self) -> dict:
        """Per-source sync state for the header (does not fetch anything new beyond the normal cache)."""
        out = {}
        for kind, ds in self.datasets(KINDS).items():
            out[kind] = {"name": SHEET_REGISTRY[kind]["name"], "ok": ds.data is not None and not ds.stale,
                         "error": ds.error, "stale": ds.stale, "synced_at": _iso(ds.fetched_at),
                         "version": ds.version, "tabs": [t for t in ds.tabs if t]}
        return out


def meta(ds: Dataset) -> dict:
    return {"source": ds.kind, "synced_at": _iso(ds.fetched_at), "version": ds.version, "stale": ds.stale,
            "error": ds.error}
