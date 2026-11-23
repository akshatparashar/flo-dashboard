"""FLO Operations API (read-only).

Every dashboard is one GET endpoint that takes its filters as query parameters (repeat a parameter to select
several values: ?month=April-26&month=May-26) and returns ready-to-draw JSON: KPIs, tables and chart series.
The same endpoints are meant to be the tools of the AI assistant (see docs/CHATBOT.md).
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import time
from functools import lru_cache
from typing import Annotated

from fastapi import Depends, FastAPI, Header, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from .assistant import Assistant
from .assistant.gemini import GeminiInterpreter
from .assistant.memory import ConversationStore
from .config import SHEET_REGISTRY, get_settings
from .core import FY_LABEL, FY_MONTH_LABELS, MONTHNO_TO_LABEL, now_ist
from .dashboards import fabric_po as fpo
from .dashboards import fabricator as fab
from .dashboards import flo_future as ffu
from .dashboards import fw_orders as fwo
from .dashboards import in_out_sale as ios
from .dashboards import master as mst
from .dashboards import overview as ovw
from .dashboards import samples as smp
from .dashboards import target as tgt
from .dashboards import vendor_rate as vrt
from .store import KINDS, Dataset, DataStore, meta

API_VERSION = "1.0.0"


@lru_cache(maxsize=1)
def get_store() -> DataStore:
    settings = get_settings()
    if settings.data_source == "google":
        from .sources.google import GoogleSheetSource
        source = GoogleSheetSource(settings.service_account_info)
    else:
        from .sources.demo import DemoSheetSource
        source = DemoSheetSource()
    return DataStore(source, settings)


app = FastAPI(title="FLO Operations API", version=API_VERSION, docs_url="/api/docs", openapi_url="/api/openapi.json")
app.add_middleware(GZipMiddleware, minimum_size=1024)
_origins = get_settings().cors_origins
if _origins:
    app.add_middleware(CORSMiddleware, allow_origins=_origins, allow_methods=["GET", "POST"],
                       allow_headers=["Authorization", "Content-Type"])


@app.middleware("http")
async def no_store(request, call_next):
    response = await call_next(request)
    if request.url.path.startswith("/api/"):
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
    return response


# ------------------------------------------------------------------------------------------------ auth
def _sign(payload: str) -> str:
    key = get_settings().token_secret.encode()
    return base64.urlsafe_b64encode(hmac.new(key, payload.encode(), hashlib.sha256).digest()).decode().rstrip("=")


def make_token() -> str:
    exp = int(time.time()) + get_settings().token_hours * 3600
    payload = base64.urlsafe_b64encode(json.dumps({"exp": exp}).encode()).decode().rstrip("=")
    return f"{payload}.{_sign(payload)}"


def check_token(token: str) -> bool:
    try:
        payload, sig = token.split(".", 1)
        if not hmac.compare_digest(sig, _sign(payload)):
            return False
        data = json.loads(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)))
        return int(data.get("exp", 0)) > time.time()
    except Exception:
        return False


def require_auth(authorization: str | None = Header(default=None)):
    if not get_settings().passcode:
        return
    token = (authorization or "").removeprefix("Bearer ").strip()
    if not token or not check_token(token):
        raise HTTPException(status_code=401, detail="Sign in required.")


class Login(BaseModel):
    passcode: str


@app.get("/api/auth/status")
def auth_status(authorization: str | None = Header(default=None)):
    required = bool(get_settings().passcode)
    token = (authorization or "").removeprefix("Bearer ").strip()
    return {"required": required, "signed_in": (not required) or (bool(token) and check_token(token))}


_failed_logins: dict[str, list[float]] = {}


@app.post("/api/auth/login")
def login(body: Login):
    passcode = get_settings().passcode
    if not passcode:
        return {"token": "", "required": False}
    now = time.time()
    recent = [t for t in _failed_logins.get("all", []) if now - t < 60]
    if len(recent) >= 10:
        raise HTTPException(status_code=429, detail="Too many attempts. Wait a minute and try again.")
    if not hmac.compare_digest(body.passcode.encode(), passcode.encode()):
        _failed_logins["all"] = recent + [now]
        raise HTTPException(status_code=401, detail="That passcode is not right.")
    return {"token": make_token(), "required": True, "expires_in_hours": get_settings().token_hours}


# ------------------------------------------------------------------------------------------------ helpers
def _need(ds: Dataset):
    if ds.data is None:
        raise HTTPException(status_code=503, detail=ds.error or f"{SHEET_REGISTRY[ds.kind]['name']} is unavailable.")
    return ds.data


def _envelope(body: dict, *datasets: Dataset) -> dict:
    s = get_settings()
    metas = [meta(d) for d in datasets]
    synced = [m["synced_at"] for m in metas if m["synced_at"]]
    return {"meta": {"fy": FY_LABEL, "fy_months": FY_MONTH_LABELS, "source": s.data_source, "ttl": s.live_ttl,
                     "server_time": now_ist().isoformat(), "synced_at": min(synced) if synced else None,
                     "version": "-".join(m["version"] for m in metas), "stale": any(m["stale"] for m in metas),
                     "sources": metas},
            **body}


def _clean(values: list[str] | None) -> list[str]:
    return [v for v in (values or []) if v not in ("", "All")]


# One Query() per parameter (a shared Query instance would bind every list parameter to the first one's name).
Multi = Annotated[list[str], Query()]


# ------------------------------------------------------------------------------------------------ routes
@app.get("/api/health")
def health():
    s = get_settings()
    return {"ok": True, "version": API_VERSION, "source": s.data_source, "ttl": s.live_ttl,
            "auth_required": bool(s.passcode)}


@app.get("/api/status", dependencies=[Depends(require_auth)])
def status():
    s = get_settings()
    return {"source": s.data_source, "ttl": s.live_ttl, "fy": FY_LABEL, "server_time": now_ist().isoformat(),
            "sources": get_store().status()}


@app.post("/api/refresh", dependencies=[Depends(require_auth)])
def refresh():
    done = get_store().refresh()
    return {"refreshed": done, "cooldown": get_settings().refresh_cooldown}


@app.get("/api/overview", dependencies=[Depends(require_auth)])
def overview(month: Multi = []):
    ds = get_store().datasets(["tracker", "sample_summary", "overview_fabricators", "fabric_po", "flo_future"])
    sources = {k: (v.data, v.error if v.data is None else None) for k, v in ds.items()}
    return _envelope(ovw.overview_dashboard(sources, _clean(month)), *ds.values())


def _master_filters(**kw):
    out = {k: _clean(v) for k, v in kw.items() if k != "risk"}
    out["risk"] = kw.get("risk") or ""
    return out


@app.get("/api/designer", dependencies=[Depends(require_auth)])
def designer(month: Multi = [], designer: Multi = [], order_type: Multi = []):
    ds = get_store().dataset("tracker")
    d = _need(ds)
    f = _master_filters(month=month, designer=designer, order_type=order_type)
    opts = mst.master_options(d)
    body = mst.designer_dashboard(d, f)
    body["options"] = {k: opts[k] for k in ("month", "designer", "order_type")}
    return _envelope(body, ds)


@app.get("/api/client", dependencies=[Depends(require_auth)])
def client(month: Multi = [], client: Multi = [], order_type: Multi = [],
           category: Multi = []):
    ds = get_store().dataset("tracker")
    d = _need(ds)
    f = _master_filters(month=month, client=client, order_type=order_type, category=category)
    opts = mst.master_options(d)
    body = mst.client_dashboard(d, f)
    body["options"] = {k: opts[k] for k in ("month", "client", "order_type", "category")}
    # FW ORDER'S (DASHBOARD tab). A problem with that tab must never take the rest of the page down.
    fw = get_store().dataset("fw_orders")
    body["fw_orders"] = fwo.fw_orders_dashboard(fw.data) if fw.data is not None else None
    if fw.data is None and fw.error:
        body["fw_orders_error"] = fw.error
    return _envelope(body, ds)


@app.get("/api/production", dependencies=[Depends(require_auth)])
def production(month: Multi = [], fabricator: Multi = [], status: Multi = [],
               category: Multi = [], designer: Multi = [], risk: str = ""):
    ds = get_store().dataset("tracker")
    d = _need(ds)
    f = _master_filters(month=month, fabricator=fabricator, status=status, category=category, designer=designer,
                        risk=risk)
    opts = mst.master_options(d)
    body = mst.production_dashboard(d, f)
    body["options"] = {k: opts[k] for k in ("month", "fabricator", "status", "category", "designer", "risk")}
    return _envelope(body, ds)


@app.get("/api/samples", dependencies=[Depends(require_auth)])
def samples(month: Multi = [], designer: Multi = [], status: Multi = [], vendor: Multi = []):
    ds = get_store().dataset("sample_summary")
    f = {"month": _clean(month), "designer": _clean(designer), "status": _clean(status), "vendor": _clean(vendor)}
    return _envelope(smp.samples_dashboard(_need(ds), f), ds)


@app.get("/api/fabricator", dependencies=[Depends(require_auth)])
def fabricator(fabricator: Multi = [], month: Multi = [], metric: str = fab.DEFAULT_METRIC):
    ds = get_store().dataset("overview_fabricators")
    f = {"fabricator": _clean(fabricator), "month": _clean(month), "metric": metric}
    return _envelope(fab.fabricator_dashboard(_need(ds), f), ds)


@app.get("/api/fabric-po", dependencies=[Depends(require_auth)])
def fabric_po(month: Multi = [], vendor: Multi = [], order_type: Multi = [],
              client: Multi = [], designer: Multi = [], item: Multi = [],
              status: Multi = []):
    ds = get_store().dataset("fabric_po")
    f = {"month": _clean(month), "vendor": _clean(vendor), "order_type": _clean(order_type),
         "client": _clean(client), "designer": _clean(designer), "item": _clean(item), "status": _clean(status)}
    return _envelope(fpo.fabric_po_dashboard(_need(ds), f), ds)


@app.get("/api/target", dependencies=[Depends(require_auth)])
def target(month: Multi = [], designer: Multi = [], item: Multi = [],
           order_by: Multi = [], source: Multi = [],
           annual_target_cr: float = Query(default=SHEET_REGISTRY["target_revenue"]["annual_target_cr"], ge=0,
                                           le=100000)):
    ds = get_store().dataset("target_revenue")
    f = {"month": _clean(month), "designer": _clean(designer), "item": _clean(item), "order_by": _clean(order_by),
         "source": _clean(source)}
    return _envelope(tgt.target_dashboard(_need(ds), f, annual_target_cr), ds)


@app.get("/api/flo-future", dependencies=[Depends(require_auth)])
def flo_future(designer: Multi = [], team: Multi = [], status: Multi = [], due: Multi = []):
    """FLO Future: promised samples, visits & meetings (same filters as the old dashboard: designer, team, status,
    due status)."""
    ds = get_store().dataset("flo_future")
    f = {"designer": _clean(designer), "team": _clean(team), "status": _clean(status), "due": _clean(due)}
    return _envelope(ffu.flo_future_dashboard(_need(ds), f), ds)


@app.get("/api/vendor-rate", dependencies=[Depends(require_auth)])
def vendor_rate(vendor: Multi = [], fabric: Multi = [], width: str = "", q: Annotated[str, Query(max_length=80)] = ""):
    """Vendor Rate: fabric rates per vendor. `fabric` = fabric category (Crepe, Silk ...), `width` = one of
    'Has 44"', 'Has 60"', 'Has 36"', 'Per Piece only', `q` = free-text search over vendor / fabric / category."""
    ds = get_store().dataset("vendor_rate")
    f = {"vendor": _clean(vendor), "fabric": _clean(fabric), "width": [width] if width not in ("", "All") else [],
         "q": [q] if q.strip() else []}
    return _envelope(vrt.vendor_rate_dashboard(_need(ds), f), ds)


@app.get("/api/in-out-sale", dependencies=[Depends(require_auth)])
def in_out_sale(month: Multi = [], fabricator: Multi = [], type: Multi = []):
    """In/Out Sale: this year vs last year (sale pcs, sale amount, net sale), the in -> out flow per month and the
    fabricator-wise incoming pieces. `month` applies to everything; `fabricator` and `type` (In-house / Outsource)
    apply to the fabricator part."""
    ds = get_store().dataset("in_out_sale")
    f = {"month": _clean(month), "fabricator": _clean(fabricator), "type": _clean(type)}
    return _envelope(ios.in_out_sale_dashboard(_need(ds), f), ds)


@app.get("/api/context", dependencies=[Depends(require_auth)])
def context(month: Multi = []):
    """Compact, text-friendly snapshot of every dashboard for the AI assistant (no tables, no chart series)."""
    store = get_store()
    ds = store.datasets(KINDS)
    months = _clean(month)
    sources = {k: (v.data, v.error if v.data is None else None) for k, v in ds.items()
               if k not in ("target_revenue", "flo_future", "vendor_rate", "in_out_sale")}
    ov = ovw.overview_dashboard(sources, months)
    out = {"alerts": [{"kind": a["kind"], "text": a["text"]} for a in ov["alerts"]],
           "errors": [e["text"] for e in ov["errors"]], "sections": {}}
    for name, sec in ov["sections"].items():
        if "kpis" in sec:
            out["sections"][name] = {k["label"]: (k["value"], k["unit"]) for k in sec["kpis"]}
    if ds["target_revenue"].data is not None:
        t = tgt.target_dashboard(ds["target_revenue"].data, {"month": months})
        if "tracker" in t:
            out["sections"]["target"] = {k["label"]: (k["value"], k["unit"]) for k in t["tracker"]["kpis"]}
    if ds["flo_future"].data is not None:
        ff = ffu.flo_future_dashboard(ds["flo_future"].data, {})
        if not ff.get("empty"):
            out["sections"]["flo_future"] = {k["label"]: (k["value"], k["unit"]) for k in ff["kpis"]}
    if ds["vendor_rate"].data is not None:
        vd = vrt.vendor_rate_dashboard(ds["vendor_rate"].data, {})
        if not vd.get("empty"):
            out["sections"]["vendor_rate"] = {k["label"]: (k["value"], k["unit"]) for k in vd["kpis"]}
    out["filters"] = {"month": months or "all"}
    return _envelope(out, *ds.values())


# ------------------------------------------------------------------------------------------------ assistant
_ASSISTANT_PAGES = {"overview": overview, "designer": designer, "client": client, "production": production,
                    "samples": samples, "fabricator": fabricator, "fabric-po": fabric_po, "target": target,
                    "flo-future": flo_future, "vendor-rate": vendor_rate}


def _assistant_fetch(page: str, filters: dict) -> dict:
    """The assistant reads the dashboard only through the same read-only functions the pages call."""
    kwargs = dict(filters)
    if page == "target":
        kwargs.setdefault("annual_target_cr", SHEET_REGISTRY["target_revenue"]["annual_target_cr"])
    return _ASSISTANT_PAGES[page](**kwargs)


@lru_cache(maxsize=1)
def get_assistant() -> Assistant:
    return Assistant(_assistant_fetch, today_month=lambda: MONTHNO_TO_LABEL.get(now_ist().month),
                     today=lambda: now_ist().date(), interpreter=GeminiInterpreter.from_env())


class ChatIn(BaseModel):
    message: str = Field(min_length=1, max_length=500)
    context: dict | None = None
    conversation_id: str | None = Field(default=None, max_length=64)


@lru_cache(maxsize=1)
def get_conversations() -> ConversationStore:
    return ConversationStore()


@app.post("/api/chat", dependencies=[Depends(require_auth)])
def chat(body: ChatIn):
    """FLO Assistant: answers a question from the dashboard's own numbers (read-only).

    With ``conversation_id`` the server remembers the chat (last 15 messages) and uses it for follow-ups; without one
    a new conversation is started and its id is returned. ``context`` (the older, browser-held memory) still works."""
    store = get_conversations()
    conv = body.conversation_id if ConversationStore.valid(body.conversation_id) else ConversationStore.new_id()
    history = store.contexts(conv)
    context = history[-1] if history else body.context
    reply = get_assistant().answer(body.message, context, history)
    store.add(conv, "user", body.message)
    store.add(conv, "assistant", reply["answer"], reply.get("context") if reply.get("understood") else None,
              {"page": reply.get("page"), "page_label": reply.get("page_label")})
    return {**reply, "conversation_id": conv}


@app.get("/api/chat/{conversation_id}", dependencies=[Depends(require_auth)])
def chat_history(conversation_id: str):
    """The remembered messages of one conversation (for showing it again after a reload)."""
    if not ConversationStore.valid(conversation_id):
        raise HTTPException(status_code=404, detail="Unknown conversation.")
    msgs = get_conversations().messages(conversation_id)
    return {"conversation_id": conversation_id,
            "messages": [{"role": m["role"], "text": m["text"], "page": m.get("page"), "page_label": m.get("page_label")}
                         for m in msgs]}


# ------------------------------------------------------------------------------------------------ static (optional)
_dist = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "frontend", "dist")
if os.getenv("SERVE_FRONTEND") == "1" and os.path.isdir(_dist):
    from fastapi.staticfiles import StaticFiles

    app.mount("/", StaticFiles(directory=_dist, html=True), name="frontend")


@app.exception_handler(Exception)
async def unhandled(request, exc):
    return JSONResponse(status_code=500, content={"detail": "Something went wrong on the server."})
