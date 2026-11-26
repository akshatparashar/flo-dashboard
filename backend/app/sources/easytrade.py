"""Stock Ageing straight from EasyTrade, through the read-only EasyTrade MCP server.

Set two environment variables and the Stock Ageing page reads EasyTrade itself instead of a snapshot file:

    EASYTRADE_MCP_URL    the MCP address, e.g. https://<name>.ngrok-free.dev/ai/mcp
    EASYTRADE_MCP_TOKEN  the bearer token (secret: .env / Vercel only, never in git)

How it works
- The MCP server speaks JSON-RPC over "Streamable HTTP": initialize, then tools/call run_query with a SELECT.
  Read-only, at most 1,000 rows a query, 30 seconds a query, and a monthly request limit.
- The figures are yesterday's closing (EasyTrade changes during the day), so one pull per day is enough. A pull is
  cached in memory and in a file (EASYTRADE_CACHE_DIR, default the system temp folder) for that as-on date, and
  every later request that day is served from the cache: about 6-7 requests a day per server instance.
- If EasyTrade cannot be reached (the PC behind the tunnel is off, the token is wrong, the limit is used up), the
  page falls back to the last good pull, then to the SQL_SNAPSHOT_DIR file, then to demo rows, and says which.

The FIFO rules are the ones agreed for the owner's Stock Ageing Report (Claude skill "stock-ageing-report"):
database F2ETrade11, PCS only (sd_Mtrs = 0), closing = yesterday, the closing balance allocated to the newest
inward lots across the year tables, value = inward amount before GST. Sales fields for Unsold Inventory Insights
(last sale date, pcs sold in 30/90/180/365 days) come from the SL (sale) vouchers.

Run by hand to check a pull against EasyTrade's own as-on stock report (prints totals, writes the file):
    python -m app.sources.easytrade --out <folder>
"""
from __future__ import annotations

import json
import logging
import os
import re
import tempfile
import threading
from datetime import date, timedelta

import requests

log = logging.getLogger(__name__)

DATABASE = "F2ETrade11"
PAGE = 1000
_TABLE = re.compile(r"^TblStockDetails_(\d+)_(\d{4})_(\d{2,4})$")        # one stock ledger table per financial year


class EasyTradeError(RuntimeError):
    pass


# --------------------------------------------------------------------------------------------- MCP client
class MCPClient:
    """A minimal client for one MCP server over Streamable HTTP (JSON or server-sent-event replies)."""

    def __init__(self, url: str, token: str, timeout: float = 40.0, session=None):
        self.url, self.token, self.timeout = url, token, timeout
        self.http = session or requests.Session()
        self.session_id: str | None = None
        self._id = 0

    def _headers(self) -> dict:
        h = {"Authorization": f"Bearer {self.token}", "Content-Type": "application/json",
             "Accept": "application/json, text/event-stream", "ngrok-skip-browser-warning": "1"}
        if self.session_id:
            h["Mcp-Session-Id"] = self.session_id
        return h

    def _post(self, body: dict) -> dict | None:
        r = self.http.post(self.url, json=body, headers=self._headers(), timeout=self.timeout)
        if r.status_code in (401, 403):
            raise EasyTradeError("EasyTrade refused the token (check EASYTRADE_MCP_TOKEN)")
        if r.status_code >= 400:
            raise EasyTradeError(f"EasyTrade MCP answered HTTP {r.status_code}")
        self.session_id = r.headers.get("Mcp-Session-Id") or self.session_id
        if "id" not in body:                       # a notification: no reply expected
            return None
        return _rpc_reply(r.text, r.headers.get("Content-Type", ""), body["id"])

    def _call(self, method: str, params: dict) -> dict:
        self._id += 1
        reply = self._post({"jsonrpc": "2.0", "id": self._id, "method": method, "params": params})
        if reply is None:
            raise EasyTradeError(f"No reply to {method}")
        if "error" in reply:
            raise EasyTradeError(f"{method} failed: {reply['error'].get('message', reply['error'])}")
        return reply.get("result") or {}

    def connect(self):
        self._call("initialize", {"protocolVersion": "2025-03-26", "capabilities": {},
                                  "clientInfo": {"name": "flo-dashboard", "version": "1.0"}})
        self._post({"jsonrpc": "2.0", "method": "notifications/initialized"})

    def query(self, sql: str, database: str = DATABASE) -> list[dict]:
        if self.session_id is None and self._id == 0:
            self.connect()
        result = self._call("tools/call", {"name": "run_query", "arguments": {"query": sql, "database": database}})
        if result.get("isError"):
            raise EasyTradeError("run_query failed: " + _text(result)[:300])
        return _rows(result)


def _rpc_reply(text: str, content_type: str, want_id) -> dict | None:
    """The JSON-RPC reply with id ``want_id``, from a plain JSON body or from an event stream."""
    if "text/event-stream" in content_type:
        for line in text.splitlines():
            if line.startswith("data:"):
                try:
                    msg = json.loads(line[5:].strip())
                except ValueError:
                    continue
                if isinstance(msg, dict) and msg.get("id") == want_id:
                    return msg
        return None
    try:
        msg = json.loads(text) if text.strip() else None
    except ValueError as e:
        raise EasyTradeError("EasyTrade MCP sent something that is not JSON") from e
    if isinstance(msg, list):
        msg = next((m for m in msg if isinstance(m, dict) and m.get("id") == want_id), None)
    return msg


def _text(result: dict) -> str:
    return "".join(c.get("text", "") for c in result.get("content") or [] if isinstance(c, dict))


def _rows(result: dict) -> list[dict]:
    """Rows of a run_query result, as dicts. Accepts structuredContent or JSON text, rows as dicts or as lists."""
    data = result.get("structuredContent")
    if not data:
        txt = _text(result)
        try:
            data = json.loads(txt)
        except ValueError as e:
            raise EasyTradeError("run_query returned text that is not JSON: " + txt[:200]) from e
    if isinstance(data, list):
        return data
    if data.get("truncated"):
        raise EasyTradeError("run_query cut the result short; the page size is too big")
    rows = data.get("rows") or []
    cols = data.get("columns")
    if rows and isinstance(rows[0], (list, tuple)) and cols:
        names = [c["name"] if isinstance(c, dict) else c for c in cols]
        rows = [dict(zip(names, r)) for r in rows]
    return rows


# --------------------------------------------------------------------------------------------- the SQL
def fy_start(day: date) -> date:
    return date(day.year if day.month >= 4 else day.year - 1, 4, 1)


def year_tables(names: list[str]) -> list[tuple[str, date, date]]:
    """(table, FY start, FY end) for each yearly stock table, oldest first. Backup copies with a timestamp suffix and
    the plain TblStockDetails are left out by the name pattern."""
    out = []
    for n in names:
        m = _TABLE.match(n)
        if m:
            start = int(m.group(2))
            out.append((n, date(start, 4, 1), date(start + 1, 3, 31)))
    return sorted(out, key=lambda t: t[1])


def fifo_sql(tables: list[tuple[str, date, date]], as_on: date, offset: int) -> str:
    """One page of the per-design FIFO ageing, with the sales fields. The skill's query, grouped by product + design
    (F2ETrade11 PCS stock has no colour / size split)."""
    cutoff = as_on + timedelta(days=1)
    cur = tables[-1][0]
    parts = []
    for i, (name, fs, fe) in enumerate(tables):
        end = as_on if name == cur else fe
        skip_op = "" if i == 0 else " AND sd_VType<>'OP'"            # later years' OP rows are carry-forwards
        upto = f" AND sd_VDate < '{cutoff}'" if name == cur else ""
        parts.append(f"SELECT {i + 1} yr, CAST('{fs}' AS date) fs, CAST('{end}' AS date) fe, sd_ID, sd_VType, sd_VDate, "
                     f"sd_ProductID, sd_DesignID, sd_Qty, sd_Mtrs, sd_Amount, sd_AmountBFT FROM {name} "
                     f"WHERE sd_VNature='I'{skip_op}{upto}")
    sales = " UNION ALL ".join(
        f"SELECT sd_ProductID, sd_DesignID, sd_VDate, sd_Qty, sd_Mtrs FROM {name} WHERE sd_VType='SL'"
        + (f" AND sd_VDate < '{cutoff}'" if name == cur else "") for name, _, _ in tables)
    return f"""WITH R AS ({' UNION ALL '.join(parts)}),
L AS (
 SELECT yr, sd_ID id, sd_VType vt, ISNULL(sd_ProductID,0) p, ISNULL(sd_DesignID,0) d, ABS(ISNULL(sd_Qty,0)) m,
  ABS(CASE WHEN ISNULL(sd_AmountBFT,0)<>0 THEN sd_AmountBFT ELSE ISNULL(sd_Amount,0) END) v,
  CASE WHEN CONVERT(date,sd_VDate)<fs THEN fs WHEN CONVERT(date,sd_VDate)>fe THEN fe ELSE CONVERT(date,sd_VDate) END dt
 FROM R WHERE ISNULL(sd_Mtrs,0)=0
),
B AS (
 SELECT ISNULL(sd_ProductID,0) p, ISNULL(sd_DesignID,0) d, SUM(ISNULL(sd_Qty,0)) bal
 FROM {cur} WHERE ISNULL(sd_Mtrs,0)=0 AND sd_VDate < '{cutoff}' GROUP BY ISNULL(sd_ProductID,0), ISNULL(sd_DesignID,0)
),
F AS (
 SELECT L.*, B.bal, SUM(L.m) OVER (PARTITION BY L.p,L.d ORDER BY L.dt DESC, L.yr DESC, L.id DESC ROWS UNBOUNDED PRECEDING) cum
 FROM L JOIN B ON B.p=L.p AND B.d=L.d WHERE B.bal>0.0001 AND L.m>0
),
A AS (SELECT *, CASE WHEN cum<=bal THEN m WHEN cum-m<bal THEN bal-(cum-m) ELSE 0 END aq, DATEDIFF(day, dt, '{as_on}') age FROM F),
K AS (
 SELECT p,d,
  SUM(CASE WHEN age<=30 THEN aq ELSE 0 END) q1, SUM(CASE WHEN age BETWEEN 31 AND 60 THEN aq ELSE 0 END) q2,
  SUM(CASE WHEN age BETWEEN 61 AND 90 THEN aq ELSE 0 END) q3, SUM(CASE WHEN age BETWEEN 91 AND 180 THEN aq ELSE 0 END) q4,
  SUM(CASE WHEN age BETWEEN 181 AND 365 THEN aq ELSE 0 END) q5, SUM(CASE WHEN age>365 THEN aq ELSE 0 END) q6,
  SUM(CASE WHEN age<=30 THEN aq*v/m ELSE 0 END) v1, SUM(CASE WHEN age BETWEEN 31 AND 60 THEN aq*v/m ELSE 0 END) v2,
  SUM(CASE WHEN age BETWEEN 61 AND 90 THEN aq*v/m ELSE 0 END) v3, SUM(CASE WHEN age BETWEEN 91 AND 180 THEN aq*v/m ELSE 0 END) v4,
  SUM(CASE WHEN age BETWEEN 181 AND 365 THEN aq*v/m ELSE 0 END) v5, SUM(CASE WHEN age>365 THEN aq*v/m ELSE 0 END) v6,
  MIN(CASE WHEN aq>0 THEN dt END) oi, MAX(CASE WHEN aq>0 THEN dt END) li, MIN(dt) fi,
  SUM(CASE WHEN aq>0 AND vt='OP' THEN aq ELSE 0 END) rop,
  SUM(aq*age)/NULLIF(SUM(aq),0) wa
 FROM A GROUP BY p,d
),
S AS (
 SELECT ISNULL(sd_ProductID,0) p, ISNULL(sd_DesignID,0) d, MAX(CONVERT(date,sd_VDate)) ls, SUM(ABS(ISNULL(sd_Qty,0))) sa,
  SUM(CASE WHEN DATEDIFF(day, sd_VDate, '{as_on}') < 30 THEN ABS(ISNULL(sd_Qty,0)) ELSE 0 END) s30,
  SUM(CASE WHEN DATEDIFF(day, sd_VDate, '{as_on}') < 90 THEN ABS(ISNULL(sd_Qty,0)) ELSE 0 END) s90,
  SUM(CASE WHEN DATEDIFF(day, sd_VDate, '{as_on}') < 180 THEN ABS(ISNULL(sd_Qty,0)) ELSE 0 END) s180,
  SUM(CASE WHEN DATEDIFF(day, sd_VDate, '{as_on}') < 365 THEN ABS(ISNULL(sd_Qty,0)) ELSE 0 END) s365
 FROM ({sales}) X WHERE ISNULL(sd_Mtrs,0)=0 GROUP BY ISNULL(sd_ProductID,0), ISNULL(sd_DesignID,0)
)
SELECT ISNULL(cg.cate_name,'') c, ISNULL(pr.pdt_name,'') pn, ISNULL(dm.Desg_Code,'') dc, ISNULL(dm.Desg_Desc,'') dn,
 B.bal b, K.q1, K.q2, K.q3, K.q4, K.q5, K.q6, ROUND(K.v1,2) v1, ROUND(K.v2,2) v2, ROUND(K.v3,2) v3, ROUND(K.v4,2) v4,
 ROUND(K.v5,2) v5, ROUND(K.v6,2) v6, K.oi, K.li, K.fi, ROUND(K.wa,0) wa, K.rop,
 S.ls, ISNULL(S.sa,0) sa, ISNULL(S.s30,0) s30, ISNULL(S.s90,0) s90, ISNULL(S.s180,0) s180, ISNULL(S.s365,0) s365
FROM B LEFT JOIN K ON K.p=B.p AND K.d=B.d LEFT JOIN S ON S.p=B.p AND S.d=B.d
LEFT JOIN MstProduct pr ON pr.pdtid=B.p LEFT JOIN MstCategory cg ON cg.cate_id=pr.cate_id
LEFT JOIN TabDesignMast dm ON dm.ID=B.d
WHERE B.bal>0.0001
ORDER BY B.p, B.d OFFSET {offset} ROWS FETCH NEXT {PAGE} ROWS ONLY"""


def control_sql(tables: list[tuple[str, date, date]], as_on: date) -> str:
    """The ledger's own closing total, to check the pages add up (and negative-stock items, which are not aged)."""
    cur = tables[-1][0]
    cutoff = as_on + timedelta(days=1)
    return (f"SELECT COUNT(CASE WHEN bal>0.0001 THEN 1 END) items, SUM(CASE WHEN bal>0.0001 THEN bal ELSE 0 END) qty, "
            f"COUNT(CASE WHEN bal<-0.0001 THEN 1 END) negkeys FROM (SELECT ISNULL(sd_ProductID,0) p, "
            f"ISNULL(sd_DesignID,0) d, SUM(ISNULL(sd_Qty,0)) bal FROM {cur} WHERE ISNULL(sd_Mtrs,0)=0 AND sd_VDate < "
            f"'{cutoff}' GROUP BY ISNULL(sd_ProductID,0), ISNULL(sd_DesignID,0)) B")


# --------------------------------------------------------------------------------------------- snapshot
def _d(v) -> str | None:
    return str(v)[:10] if v not in (None, "") else None


def _f(v) -> float:
    try:
        return float(v or 0)
    except (TypeError, ValueError):
        return 0.0


def item(row: dict) -> dict:
    out = {"c": row.get("c") or "", "p": row.get("pn") or "", "d": row.get("dc") or "", "n": row.get("dn") or "",
           "b": _f(row.get("b")), "oi": _d(row.get("oi")), "li": _d(row.get("li")), "fi": _d(row.get("fi")),
           "wa": _f(row.get("wa")), "rop": _f(row.get("rop"))}
    for k in ("q1", "q2", "q3", "q4", "q5", "q6", "v1", "v2", "v3", "v4", "v5", "v6", "sa", "s30", "s90", "s180", "s365"):
        out[k] = _f(row.get(k))
    if row.get("ls"):
        out["ls"] = _d(row["ls"])
    return out


def pull(client: MCPClient, as_on: date) -> dict:
    """A full Stock Ageing snapshot as on ``as_on`` closing: 1 table list + 1 control + one query per 1,000 designs."""
    names = [r.get("TABLE_NAME") or r.get("table_name") or next(iter(r.values()), "") for r in client.query(
        "SELECT TABLE_NAME FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_NAME LIKE 'TblStockDetails[_]%'")]
    tables = [t for t in year_tables(names) if t[1] <= as_on]
    if not tables:
        raise EasyTradeError("No yearly TblStockDetails tables found in F2ETrade11")
    ctl = client.query(control_sql(tables, as_on))[0]
    items: list[dict] = []
    while True:
        page = client.query(fifo_sql(tables, as_on, len(items)))
        items += [item(r) for r in page]
        if len(page) < PAGE:
            break
    return {"as_on": str(as_on), "source": f"EasyTrade {DATABASE} (live, via MCP)", "unit": "PCS", "items": items,
            "has_sales": True, "control": {"items": int(_f(ctl.get("items"))), "qty": _f(ctl.get("qty")),
                                           "negkeys": int(_f(ctl.get("negkeys")))}}


# --------------------------------------------------------------------------------------------- cache
_lock = threading.Lock()
_memo: dict[str, dict] = {}
_failed: dict[str, float] = {}


def configured() -> bool:
    return bool(os.getenv("EASYTRADE_MCP_URL", "").strip() and os.getenv("EASYTRADE_MCP_TOKEN", "").strip())


def _cache_path(as_on: date) -> str:
    folder = os.getenv("EASYTRADE_CACHE_DIR", "").strip() or tempfile.gettempdir()
    return os.path.join(folder, f"flo_stock_ageing_{as_on}.json")


def _last_good() -> dict | None:
    folder = os.getenv("EASYTRADE_CACHE_DIR", "").strip() or tempfile.gettempdir()
    try:
        files = sorted(f for f in os.listdir(folder) if re.fullmatch(r"flo_stock_ageing_\d{4}-\d{2}-\d{2}\.json", f))
    except OSError:
        return None
    for f in reversed(files):
        try:
            with open(os.path.join(folder, f), encoding="utf-8") as fh:
                return json.load(fh)
        except (OSError, ValueError):
            continue
    return None


def live_snapshot(today: date | None = None, retry_after: float = 600.0) -> tuple[dict | None, str | None]:
    """(snapshot, problem). The pull for yesterday's closing, from memory, the cache file or EasyTrade (once a day).
    After a failed pull EasyTrade is not asked again for ``retry_after`` seconds, to save the monthly request limit;
    meanwhile the last good pull is returned with the problem."""
    import time

    as_on = (today or date.today()) - timedelta(days=1)
    key = str(as_on)
    with _lock:
        if key in _memo:
            return _memo[key], None
        path = _cache_path(as_on)
        try:
            with open(path, encoding="utf-8") as fh:
                _memo[key] = json.load(fh)
                return _memo[key], None
        except (OSError, ValueError):
            pass
        if time.time() - _failed.get(key, 0) < retry_after:
            return _last_good(), "EasyTrade could not be reached a few minutes ago"
        try:
            client = MCPClient(os.environ["EASYTRADE_MCP_URL"].strip(), os.environ["EASYTRADE_MCP_TOKEN"].strip())
            snap = pull(client, as_on)
        except (EasyTradeError, requests.RequestException, KeyError, IndexError, ValueError) as e:
            _failed[key] = time.time()
            log.warning("EasyTrade pull failed: %s", e)
            return _last_good(), f"EasyTrade could not be reached ({type(e).__name__})"
        _memo.clear()
        _memo[key] = snap
        try:
            with open(path, "w", encoding="utf-8") as fh:
                json.dump(snap, fh)
        except OSError:
            pass                                    # read-only disk: the memory copy still serves this instance
        return snap, None


def _main():
    import argparse

    ap = argparse.ArgumentParser(description="Pull the Stock Ageing snapshot from EasyTrade (as on yesterday).")
    ap.add_argument("--out", help="folder to write stock_ageing.json into (for SQL_SNAPSHOT_DIR)")
    a = ap.parse_args()
    if not configured():
        raise SystemExit("Set EASYTRADE_MCP_URL and EASYTRADE_MCP_TOKEN first (e.g. in backend/.env).")
    as_on = date.today() - timedelta(days=1)
    snap = pull(MCPClient(os.environ["EASYTRADE_MCP_URL"].strip(), os.environ["EASYTRADE_MCP_TOKEN"].strip()), as_on)
    qty = sum(i["b"] for i in snap["items"])
    print(f"As on {as_on} closing: {len(snap['items'])} designs, {qty:,.0f} pcs "
          f"(ledger: {snap['control']['items']} items, {snap['control']['qty']:,.0f} pcs; "
          f"{snap['control']['negkeys']} items with negative stock, not aged)")
    if a.out:
        os.makedirs(a.out, exist_ok=True)
        with open(os.path.join(a.out, "stock_ageing.json"), "w", encoding="utf-8") as fh:
            json.dump(snap, fh)
        print("Wrote", os.path.join(a.out, "stock_ageing.json"))


if __name__ == "__main__":
    from ..config import _load_dotenv

    _load_dotenv()
    _main()
