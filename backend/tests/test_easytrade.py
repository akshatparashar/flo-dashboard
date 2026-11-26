"""EasyTrade live source: the MCP conversation, paging, the cache that keeps requests to one pull a day, and the
fallbacks when EasyTrade cannot be reached. Runs against a fake MCP server; no network."""
from __future__ import annotations

import json as jsonlib
from datetime import date

import pytest

from app.dashboards import stock_ageing as sta
from app.sources import easytrade as et


class Resp:
    def __init__(self, body, status=200, sse=False, session=None):
        self.status_code = status
        self.headers = {"Content-Type": "text/event-stream" if sse else "application/json"}
        if session:
            self.headers["Mcp-Session-Id"] = session
        self.text = body if isinstance(body, str) else jsonlib.dumps(body)


def row(i):
    return {"c": "620419", "pn": "Suit Stitched", "dc": f"70- {i}", "dn": f"DESIGN {i}", "b": 2, "q1": 2, "q2": 0, "q3": 0,
            "q4": 0, "q5": 0, "q6": 0, "v1": 1000, "v2": 0, "v3": 0, "v4": 0, "v5": 0, "v6": 0, "oi": "2026-11-10",
            "li": "2026-11-10", "fi": "2026-11-10", "wa": 15, "rop": 0, "ls": "2026-11-20T00:00:00", "sa": 5, "s30": 5,
            "s90": 5, "s180": 5, "s365": 5}


class FakeMCP:
    """Answers initialize, the initialized notification and run_query; counts every HTTP request."""

    def __init__(self, designs=1500, sse=False, fail=False):
        self.designs, self.sse, self.fail = designs, sse, fail
        self.requests, self.queries = 0, []

    def post(self, url, json=None, headers=None, timeout=None):
        self.requests += 1
        if self.fail:
            raise et.requests.ConnectionError("tunnel down")
        assert headers["Authorization"] == "Bearer secret"
        if json["method"] == "initialize":
            return Resp({"jsonrpc": "2.0", "id": json["id"], "result": {"protocolVersion": "2025-03-26"}}, session="s1")
        if json["method"] == "notifications/initialized":
            return Resp("", status=202)
        assert headers.get("Mcp-Session-Id") == "s1"
        sql = json["params"]["arguments"]["query"]
        assert json["params"]["arguments"]["database"] == "F2ETrade11"
        assert sql.lstrip().upper().startswith(("SELECT", "WITH"))
        self.queries.append(sql)
        if "INFORMATION_SCHEMA" in sql:
            rows = [{"TABLE_NAME": n} for n in ("TblStockDetails", "TblStockDetails_1_2023_2024", "TblStockDetails_2_2024_2025",
                                                "TblStockDetails_3_2025_26", "TblStockDetails_4_2026_2027",
                                                "TblStockDetails_4_2026_2027_20260612132926")]
        elif "negkeys" in sql:
            rows = [{"items": self.designs, "qty": 2 * self.designs, "negkeys": 0}]
        else:
            off = int(sql.split("OFFSET ")[1].split()[0])
            rows = [row(i) for i in range(off, min(off + 1000, self.designs))]
        body = {"jsonrpc": "2.0", "id": json["id"],
                "result": {"content": [{"type": "text", "text": jsonlib.dumps({"rows": rows, "row_count": len(rows),
                                                                                          "truncated": False})}]}}
        return Resp("event: message\ndata: " + jsonlib.dumps(body) + "\n\n" if self.sse else body, sse=self.sse)


@pytest.fixture()
def env(monkeypatch, tmp_path):
    monkeypatch.setenv("EASYTRADE_MCP_URL", "https://example.test/ai/mcp")
    monkeypatch.setenv("EASYTRADE_MCP_TOKEN", "secret")
    monkeypatch.setenv("EASYTRADE_CACHE_DIR", str(tmp_path))
    monkeypatch.delenv("SQL_SNAPSHOT_DIR", raising=False)
    et._memo.clear()
    et._failed.clear()
    return tmp_path


def use(monkeypatch, fake):
    monkeypatch.setattr(et.requests, "Session", lambda: fake)


@pytest.mark.parametrize("sse", [False, True])
def test_pull_pages_through_all_designs(monkeypatch, env, sse):
    fake = FakeMCP(designs=2300, sse=sse)
    use(monkeypatch, fake)
    snap = et.pull(et.MCPClient("https://example.test/ai/mcp", "secret"), date(2026, 11, 25))
    assert len(snap["items"]) == 2300 and snap["has_sales"]
    assert snap["control"] == {"items": 2300, "qty": 4600.0, "negkeys": 0}
    detail = [q for q in fake.queries if "OFFSET" in q]
    assert len(detail) == 3                                            # 1000 + 1000 + 300
    assert "_20260612132926" not in detail[0] and "FROM TblStockDetails WHERE" not in detail[0]   # backups skipped
    assert "sd_VDate < '2026-11-26'" in detail[0] and "'2026-11-25') age" in detail[0]
    first = snap["items"][0]
    assert first["d"] == "70- 0" and first["ls"] == "2026-11-20" and first["b"] == 2.0


def test_one_pull_a_day_then_cache(monkeypatch, env):
    fake = FakeMCP(designs=10)
    use(monkeypatch, fake)
    snap, problem = et.live_snapshot(today=date(2026, 11, 26))
    assert problem is None and snap["as_on"] == "2026-11-25"
    used = fake.requests
    assert used == 5                    # initialize, initialized, table list, control, one page
    et.live_snapshot(today=date(2026, 11, 26))
    et._memo.clear()                    # a new server instance: the cache file still serves it
    et.live_snapshot(today=date(2026, 11, 26))
    assert fake.requests == used
    assert (env / "flo_stock_ageing_2026-11-25.json").exists()


def test_unreachable_falls_back_and_waits_before_retrying(monkeypatch, env):
    use(monkeypatch, FakeMCP(designs=10))
    et.live_snapshot(today=date(2026, 11, 25))                          # a good pull the day before
    et._memo.clear()
    down = FakeMCP(fail=True)
    use(monkeypatch, down)
    snap, problem = et.live_snapshot(today=date(2026, 11, 26))
    assert snap["as_on"] == "2026-11-24" and "could not be reached" in problem
    et.live_snapshot(today=date(2026, 11, 26))
    assert down.requests == 1                                          # no hammering while it is down


def test_page_uses_live_data_and_says_when_it_is_old(monkeypatch, env):
    use(monkeypatch, FakeMCP(designs=10))
    real = et.live_snapshot
    monkeypatch.setattr(et, "live_snapshot", lambda: real(today=date(2026, 11, 26)))
    snap = sta.load_snapshot()
    assert not snap["demo"] and snap["source"].startswith("EasyTrade")
    page = sta.stock_ageing_dashboard(snap, {})
    assert not any("Demo rows" in n["text"] for n in page.get("notices", []))


def test_not_configured_keeps_the_old_behaviour(monkeypatch, env):
    monkeypatch.delenv("EASYTRADE_MCP_TOKEN")
    assert sta.load_snapshot()["demo"]


def test_bad_token_is_reported():
    class Deny:
        def post(self, *a, **k):
            return Resp({"error": "nope"}, status=401)

    with pytest.raises(et.EasyTradeError, match="token"):
        et.MCPClient("u", "t", session=Deny()).query("SELECT 1")
