"""Vendor Rate: parity with the old Streamlit Vendor Rate tab (legacy/streamlit_app.py: its vr_* functions run on the
same rates), plus parsing of Rate_Data / the rate cards, sheet checks, filters, per-vendor tables and the API."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient

from app import main
from app.config import Settings
from app.dashboards import vendor_rate as vr
from app.sources.demo import DemoSheetSource
from app.store import DataStore

HEADER = ["Vendor", "S. No.", "Fabric (Original)", "Fabric Category", '44" Width Rate', '60" Width Rate',
          '36" Width Rate', "Per Pc / Special Rate", "", "Metric", "Value"]


def sheet_grids(records):
    """The old app's rate table written the way the sheet holds it: Rate_Data (₹ text and numbers mixed, the
    helper block on the right) and a NEW RATE SHEET card whose EKTA FABRIC block says '44/36 WIDTH'."""
    rd = [HEADER]
    for n, r in enumerate(records, start=1):
        # EKTA's old 44/36" rates sit in the 44" column of Rate_Data (the sheet has no 44/36 column there)
        c44 = r['44"'] if r['44"'] is not None else r['44/36"']
        pc = r["Per Pc"] if r["Per Pc Max"] is None else f"{r['Per Pc']:g}/{r['Per Pc Max']:g}"
        fmt = lambda v: "" if v is None else (f"₹{v}" if v else 0)          # noqa: E731  (formatted like the sheet)
        rd.append([r["Vendor"], n, r["Fabric"], "Whatever", fmt(c44), fmt(r['60"']), fmt(r['36"']), fmt(pc),
                   "", "Total Vendors" if n == 1 else "", 11 if n == 1 else ""])
    cards = [["EKTA FABRIC"], ["S. NO.", "FABRIC", "44/36 WIDTH", "60 WIDTH"], [1, "CHANDERI DIG. TOP/DUP.", 390]]
    return {"rates": rd, "cards": cards}


@pytest.fixture
def old_records(legacy):
    return legacy.vr_default_records()


@pytest.fixture
def parsed(old_records):
    return vr.parse_vendor_rate(sheet_grids(old_records))


def kpis(d):
    return {k["id"]: k for k in d["kpis"]}


def same(a, b):
    pd.testing.assert_frame_equal(a.reset_index(drop=True), b.reset_index(drop=True), check_dtype=False,
                                  check_exact=False, rtol=1e-9)


# ------------------------------------------------------------------------------------------------ parity
def test_tidy_table_identical(legacy, old_records, parsed):
    old = legacy.vr_build(old_records)
    mine = parsed["d"]
    assert list(mine.columns) == list(old.columns)
    new = mine.copy()
    new["Fabric"] = new["Fabric"].values                         # same text; compare everything else directly
    same(old.drop(columns=["Status"]), new.drop(columns=["Status"]))
    # the old app wrote emoji in front of its status text; the words are the same
    assert [s.split(" ", 1)[1] if s[0] not in "PO" else s for s in old["Status"]] == list(mine["Status"])


FILTERS = [
    ([], [], "", ""), (["RV"], [], "", ""), ([], ["Crepe"], "", ""), ([], [], 'Has 44"', ""),
    ([], [], 'Has 60"', ""), ([], [], 'Has 36"', ""), ([], [], "Per Piece only", ""), ([], [], "", "crepe RV"),
    (["VARSHA"], ["Hand Work / Dupatta"], "", ""), ([], ["Muslin"], 'Has 60"', "muslin"), (["NOBODY"], [], "", ""),
]


@pytest.mark.parametrize("vendor,cat,width,query", FILTERS)
def test_filter_benchmark_and_kpis_identical(legacy, old_records, parsed, vendor, cat, width, query):
    old_d = legacy.vr_build(old_records)

    def old_filter():                                            # the old filter takes one value ("All" = none)
        x = old_d
        if vendor:
            x = pd.concat([legacy.vr_filter(x, v, "All", "All", "") for v in vendor])
        if cat:
            x = pd.concat([legacy.vr_filter(x, "All", c, "All", "") for c in cat])
        return legacy.vr_filter(x, "All", "All", width or "All", query)
    old_x = old_filter()
    new_x = vr.vr_filter(parsed["d"], vendor, cat, width, query)
    assert list(new_x.index) == list(old_x.index)
    if new_x.empty:
        return
    same(legacy.vr_benchmark(old_x), vr.vr_benchmark(new_x))
    for col in ('44"', '60"'):
        o = legacy.vr_lowest(old_x, col)
        n = vr.vr_lowest(new_x, col)
        assert (o == "—") == (n is None)
        if n:
            assert o == f"₹{n[0]:,.0f} · {n[1]} · {n[2]}"
    d = vr.vendor_rate_dashboard(parsed, {"vendor": vendor, "fabric": cat, "width": [width] if width else [],
                                          "q": [query] if query else []})
    k = kpis(d)
    assert k["vendors"]["value"] == old_x["Vendor"].nunique() and k["offerings"]["value"] == len(old_x)
    assert k["pending"]["value"] == int(old_x["Pending Cells"].sum())


def test_compare_identical_for_every_category(legacy, old_records, parsed):
    old_d = legacy.vr_build(old_records)
    pay = vr.vendor_rate_dashboard(parsed, {})["compare"]
    assert pay["categories"] == sorted(old_d["Category"].unique()) and pay["default"] == "Crepe"
    for cat in pay["categories"]:
        c = old_d[old_d["Category"] == cat]
        mw = [w for w in legacy.VR_METER_COLS if c[w].notna().any()]
        p = pay["data"][cat]
        assert p["widths"] == mw
        if not mw:
            continue
        cmp, best = legacy.vr_compare(c, mw)
        assert [r[0] for r in p["table"]["rows"]] == list(cmp["Vendor"])
        for w in mw:
            i = [x["width"] for x in p["tiles"]].index(w)
            assert p["tiles"][i]["rate"] == best[w] == c[w].min()
            ser = next(s for s in p["chart"]["series"] if s["name"] == w)
            for v, star, rate in zip(p["chart"]["vendors"], ser["best"], ser["values"]):
                want = cmp.loc[cmp["Vendor"] == v, f"{w} Rate"].iloc[0]
                assert (rate is None) == pd.isna(want) and (rate is None or rate == want)
                assert star == (pd.notna(want) and want == best[w])      # ★ = Best Price
        stars = {r[0]: r[-1] for r in p["table"]["rows"]}
        old_stars = dict(zip(cmp["Vendor"], cmp["Best Price"].str.replace("🏆", "★")))
        assert stars == old_stars
        pc = c[c["Per Pc"].notna()]
        assert (p["pieces"] is not None) == (not pc.empty)


# ------------------------------------------------------------------------------------------------ sheet specifics
def test_reads_the_sheets_layout(parsed):
    d = parsed["d"]
    assert len(d) == 56 and d["Vendor"].nunique() == 11 and parsed["source"] == "Rate_Data"
    ekta = d[d["Vendor"] == "EKTA FABRIC"]
    assert ekta['44/36"'].notna().all() and ekta['44"'].isna().all()          # card says "44/36 WIDTH"
    r = d.set_index(["Vendor", "Fabric"])
    assert r.loc[("RV", "PLAIN CREPE"), "Status"] == 'Pending / N/A (44")'
    assert r.loc[("VARSHA", "MUSLIN PRINT HAND WORK PR PC"), "Per Pc Max"] == 125
    assert r.loc[("VARSHA", "MUSLIN PRINT HAND WORK PR PC"), "Note"] == "Range ₹120–125 per pc"
    assert r.loc[("K THREE PLUS", "MUSLIN"), "Status"] == "Pending / N/A"


def test_ekta_stays_in_44_without_a_card():
    p = vr.parse_vendor_rate({"rates": sheet_grids([{"Vendor": "EKTA FABRIC", "Fabric": "X TOP/DUP.", '36"': None,
                                                      '44"': None, '60"': None, '44/36"': 390, "Per Pc": None,
                                                      "Per Pc Max": None}])["rates"]})
    assert p["d"].iloc[0]['44"'] == 390                     # no "44/36 WIDTH" card -> read as a 44" rate


def test_kpis_and_sections(parsed):
    d = vr.vendor_rate_dashboard(parsed, {})
    k = kpis(d)
    assert [x["label"] for x in d["kpis"]] == ["Total Vendors", "Total Fabric Offerings", 'Lowest 44" Rate',
                                               'Lowest 60" Rate', "Pending / Missing Rates"]
    assert k["lowest44"]["value"] == 72 and k["lowest44"]["hint"] == "RV · PLAIN CHINON"
    assert k["lowest60"]["value"] == 85 and k["lowest60"]["hint"] == "K THREE PLUS · CHIKU CHANDERI"
    assert k["pending"]["value"] == 4
    cards = d["vendor_cards"]
    assert [c["vendor"] for c in cards][:3] == ["RV", "SWAGAT", "GOKUL"] and len(cards) == 11
    assert sum(c["items"] for c in cards) == 56
    rv = next(c for c in cards if c["vendor"] == "RV")
    assert len(rv["table"]["rows"]) == 13 and [c["label"] for c in rv["table"]["columns"]][:2] == ["Fabric", "Category"]


def test_vendor_filter_limits_cards_but_compare_stays_global(parsed):
    d = vr.vendor_rate_dashboard(parsed, {"vendor": ["RV"]})
    assert [c["vendor"] for c in d["vendor_cards"]] == ["RV"] and kpis(d)["offerings"]["value"] == 13
    crepe = d["compare"]["data"]["Crepe"]
    assert crepe["vendors"] > 1                                           # not limited by the vendor filter


def test_checks_against_the_rate_cards(parsed):
    cards = vr.parse_rate_cards([["RV", "", "", "", "", "VARSHA"],
                                 ["S. NO.", "FABRIC", "44 WIDTH", "60 WIDTH", "", "S. NO.", "FABRIC", "44 WIDTH"],
                                 [1, "CREPE", 205, 255, "", 1, " MUSLINE", 165],
                                 [2, "SILK SATIN", 300, 350, "", 2, "X", 1]])
    assert cards[0]["nums"] == [205, 255] and cards[2]["vendor"] == "VARSHA" and cards[2]["nums"] == [165]
    text = " ".join(c["text"] for c in vr.checks(parsed["d"], cards, "Rate_Data"))
    assert "CREPE (RV): rate card 205/255, Rate_Data 205/250" in text and "SILK SATIN (RV)" in text
    assert 'PLAIN CREPE (RV) 44"' in text and "no rate at all" in text


def test_rate_cards_used_when_rate_data_missing():
    p = vr.parse_vendor_rate({"cards": [["GOKUL"], ["S. NO.", "FABRIC", "44 WIDTH", "60 WIDTH"],
                                       [1, "N-CREPE", 210, 260], [2, "MUSLIN", 160, 200]]})
    d = vr.vendor_rate_dashboard(p, {})
    assert p["source"] == "NEW RATE SHEET" and kpis(d)["offerings"]["value"] == 2 and d["notices"]
    assert p["d"].iloc[0]['44"'] == 210 and p["d"].iloc[0]['60"'] == 260


def test_empty():
    d = vr.vendor_rate_dashboard(vr.parse_vendor_rate({}), {})
    assert d["empty"] and d["notices"]


def test_api_route(monkeypatch):
    settings = Settings(data_source="demo")
    store = DataStore(DemoSheetSource(), settings)
    monkeypatch.setattr(main, "get_settings", lambda: settings)
    monkeypatch.setattr(main, "get_store", lambda: store)
    c = TestClient(main.app)
    body = c.get("/api/vendor-rate").json()
    assert body["meta"]["sources"][0]["source"] == "vendor_rate" and body["kpis"]
    assert {"benchmark", "master"} <= set(body["tables"]) and body["vendor_cards"] and body["compare"]["data"]
    v = body["options"]["vendor"][0]
    one = c.get("/api/vendor-rate", params={"vendor": v}).json()
    assert kpis(one)["vendors"]["value"] == 1 and [x["vendor"] for x in one["vendor_cards"]] == [v]
    none = c.get("/api/vendor-rate", params={"q": "zzzz"}).json()
    assert none["no_match"] and store.status()["vendor_rate"]["ok"]


# ------------------------------------------------------------------------------------------------ NEW RATE SHEET tables
CARD_GRID = [
    ["RV", "", "", "", "", "", "VARSHA", "", "", "", "", "VINAYAK"],
    ["S. NO.", "FABRIC", "44 WIDTH", "60 WIDTH", "36 WIDTH", "", "S. NO.", "FABRIC", "44 WIDTH", "60 WIDTH", "",
     "S. NO.", "FABRIC", "44 WIDTH", "60 WIDTH", "36 WIDTH"],
    [1, "CREPE", 205, 250, "", "", 1, " MUSLINE", 165, 200, "", 1, "CREPE", 210, 250, ""],
    [2, "PLAIN CREPE", 0, 125, "", "", 2, "HAND WORK PR PC", 120, "", "", 7, "DIG.VISCOS ORGENZA", "", 220, 225],
    ["", "", "", "", "", ""],
    ["EKTA FABRIC"],
    ["S. NO.", "FABRIC", "44/36 WIDTH", "60 WIDTH"],
    [1, "CHANDERI DIG.TOP/DUP.", 390, ""],
    ["GOKUL"],
    ["S. NO.", "FABRIC", "44 WIDTH", "60 WIDTH"],
    [4, "RFD CREPE ", 120, ""],
]


def test_sheet_tables_keep_each_blocks_own_columns():
    cards = vr.parse_rate_cards(CARD_GRID)
    t = {x["vendor"]: x for x in vr.sheet_tables(cards, [])}
    assert list(t) == ["RV", "VARSHA", "VINAYAK", "EKTA FABRIC", "GOKUL"]
    cols = {v: [c["label"] for c in x["table"]["columns"]] for v, x in t.items()}
    assert cols["RV"] == ["S. NO.", "FABRIC", "44 WIDTH", "60 WIDTH", "36 WIDTH"]
    assert cols["VARSHA"] == ["S. NO.", "FABRIC", "44 WIDTH", "60 WIDTH"]
    assert cols["EKTA FABRIC"][2] == "44/36 WIDTH"
    assert t["RV"]["table"]["rows"][1] == [2, "PLAIN CREPE", 0, 125, None]
    assert t["VINAYAK"]["table"]["rows"][1][1:] == ["DIG.VISCOS ORGENZA", None, 220, 225]
    assert t["GOKUL"]["table"]["rows"][0][1:] == ["RFD CREPE", 120, None]          # 44 WIDTH, as the sheet has it
    only = vr.sheet_tables(cards, ["VARSHA", "GOKUL"])
    assert [x["vendor"] for x in only] == ["VARSHA", "GOKUL"]


def test_api_sheet_tables_follow_vendor_filter(parsed):
    p = vr.parse_vendor_rate({"rates": sheet_grids(vr.vr_build and [])["rates"], "cards": CARD_GRID})
    assert [x["vendor"] for x in vr.vendor_rate_dashboard(p, {})["sheet_tables"]][:2] == ["RV", "VARSHA"]
    d = vr.vendor_rate_dashboard(p, {"vendor": ["RV"]})
    assert [x["vendor"] for x in d["sheet_tables"]] == ["RV"]


def test_real_new_rate_sheet_tables():
    """The NEW RATE SHEET of FABRIC PO 11 as read from the sheet: 11 vendor blocks, 56 fabrics, own column heads."""
    from tests.real_rate_cards import grid
    t = vr.sheet_tables(vr.parse_rate_cards(grid()), [])
    assert [(x["vendor"], x["items"]) for x in t] == [
        ("RV", 13), ("VARSHA", 8), ("VINAYAK", 7), ("VIPUL", 5), ("SHREE SANTINATH", 3), ("SWAGAT", 3),
        ("VEDANSHI", 2), ("EKTA FABRIC", 5), ("BSK", 2), ("GOKUL", 4), ("K THREE PLUS", 4)]
    heads = {x["vendor"]: [c["label"] for c in x["table"]["columns"]] for x in t}
    assert heads["EKTA FABRIC"][2] == "44/36 WIDTH" and heads["VEDANSHI"][2] == "36 WIDTH"
    assert heads["K THREE PLUS"][-1] == "36 WIDTH" and "36 WIDTH" not in heads["GOKUL"]
