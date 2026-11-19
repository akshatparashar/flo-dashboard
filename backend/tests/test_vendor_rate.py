"""Vendor Rate: the numbers must equal the sheet's own "Vendor Rate Dashboard" tab (FABRIC PO 11) on the real rate
list, plus parsing of the rate cards, sheet checks, filters and the API route."""
from __future__ import annotations

import math

import pytest
from fastapi.testclient import TestClient

from app import main
from app.config import Settings
from app.dashboards import vendor_rate as vr
from app.sources.demo import DemoSheetSource
from app.store import DataStore

# The real rate list as the sheet shows it (Vendor | Fabric | Category | 44" | 60" | 36" | Per Pc / Special).
REAL = [
    ("RV", "CREPE", "Crepe", 205, 250, "", ""), ("RV", "MUL CHANDERI", "Mul Chanderi", 195, 240, "", ""),
    ("RV", "BASIC SILK", "Silk", 170, 195, "", ""), ("RV", "CLASSIC SILK", "Silk", 175, 200, "", ""),
    ("RV", "RUSSIAN SILK", "Russian Silk", 200, 230, "", ""), ("RV", "CHINON", "Chinon", 185, 235, "", ""),
    ("RV", "VISCOSE MUSLINE", "Muslin", 165, 195, "", ""), ("RV", "PLAIN ORGENZA", "Organza", 80, 120, "", ""),
    ("RV", "PLAIN CREPE", "Crepe", 0, 125, "", ""), ("RV", "PLAIN CHINON", "Chinon", 72, 115, "", ""),
    ("RV", "ORGANZA PRINTED", "Organza", 185, 235, "", ""),
    ("RV", "SUPER COTTON (DIGITAL PRINT)", "Cotton", 145, 170, "", ""), ("RV", "DOBBY", "Other", "", 200, "", ""),
    ("SWAGAT", "REMI SILK", "Silk", 175, 230, "", ""), ("SWAGAT", "NATURAL CREPE", "Crepe", 230, 280, "", ""),
    ("SWAGAT", "SAND CREPE", "Crepe", 210, 280, "", ""),
    ("GOKUL", "N-CREPE", "Crepe", 210, 260, "", ""), ("GOKUL", "MUSLIN", "Muslin", 160, 200, "", ""),
    ("GOKUL", "DIG. COTTON", "Cotton", 160, 200, "", ""), ("GOKUL", "RFD CREPE", "Crepe", "", "", "", 120),
    ("VARSHA", "MUSLINE", "Muslin", 165, 200, "", ""),
    ("VARSHA", "MUSLINE PRINTED DUPATTA", "Muslin", 160, 210, "", ""),
    ("VARSHA", "CREPE", "Crepe", 232, 295, "", ""), ("VARSHA", "SANTOON (DYED)", "Other", 90, "", "", ""),
    ("VARSHA", "HAND WORK PR PC", "Hand Work / Dupatta", "", "", "", 120),
    ("VARSHA", "CREPE HAND WORK PR PC", "Hand Work / Dupatta", "", "", "", 160),
    ("VARSHA", "MUSLIN PRINT HAND WORK PR PC", "Hand Work / Dupatta", "", "", "", "120/125"),
    ("VARSHA", "CHINON DUPATTA MTR", "Chinon", 220, 275, "", ""),
    ("VIPUL", "MUSLINE", "Muslin", 160, 185, "", ""), ("VIPUL", "CREPE", "Crepe", 220, 265, "", ""),
    ("VIPUL", "ORGENZA", "Organza", "", 220, "", ""), ("VIPUL", "RUSSIAN SILK", "Russian Silk", 185, "", "", ""),
    ("VIPUL", "CHINON SIFON", "Chinon", 180, 230, "", ""),
    ("EKTA FABRIC", "CHANDERI DIG. TOP/DUP.", "Mul Chanderi", 390, "", "", ""),
    ("EKTA FABRIC", "LILEN DIG.TOP/DUP.", "Linen", 435, "", "", ""),
    ("EKTA FABRIC", "MODAL DAYED DIG.TOP/DUP.", "Other", 675, "", "", ""),
    ("EKTA FABRIC", "MOONGA DIG.TOP/DUP. JAMDANI", "Other", 675, "", "", ""),
    ("EKTA FABRIC", "MOONGA FLEB DIG.TOP/DUP. JAMDANI", "Other", 565, "", "", ""),
    ("VINAYAK", "CREPE", "Crepe", 210, 250, "", ""), ("VINAYAK", "BEMBER RUSSION SILK", "Russian Silk", 250, "", "", ""),
    ("VINAYAK", "MUSLIN", "Muslin", 145, 180, "", ""), ("VINAYAK", "MUL CHANDERI", "Mul Chanderi", "", 225, "", ""),
    ("VINAYAK", "ORGENZA (PRINTED)", "Organza", "", 235, "", ""),
    ("VINAYAK", "DIG. 60*60 COTTON", "Cotton", 135, "", "", ""),
    ("VINAYAK", "DIG.VISCOS ORGENZA", "Organza", "", 220, 225, ""),
    ("SHREE SANTINATH", "FLEX LILEN", "Linen", "", 132, "", ""),
    ("SHREE SANTINATH", "FLEX LILEN DUPATTA (PER PC)", "Linen", "", "", "", 145),
    ("SHREE SANTINATH", "FLEX WRINKLE SWISS", "Other", "", 142, "", ""),
    ("VEDANSHI", "PLAIN ORGENZA", "Organza", "", 135, 85, ""), ("VEDANSHI", "MUSLIN", "Muslin", "", 200, 165, ""),
    ("BSK", "MUL CHANDERI", "Mul Chanderi", 175, 210, "", ""), ("BSK", "COTTON", "Cotton", "", 155, "", ""),
    ("K THREE PLUS", "CHIKU CHANDERI", "Mul Chanderi", "", 85, 73, ""), ("K THREE PLUS", "MUSLIN", "Muslin", "", "", "", ""),
    ("K THREE PLUS", "COTTON SILK", "Silk", "", "", "", ""), ("K THREE PLUS", "GAJJI SILK", "Silk", "", "", "", ""),
]
# The sheet's Vendor Benchmark Summary: Items, Avg 44", Avg 60", Min 60", Max 60" (shown rounded to whole ₹).
SHEET_BENCH = {
    "RV": (13, 162, 193, 115, 250), "SWAGAT": (3, 205, 263, 230, 280), "GOKUL": (4, 177, 220, 200, 260),
    "VARSHA": (8, 173, 245, 200, 295), "VIPUL": (5, 186, 225, 185, 265), "EKTA FABRIC": (5, 548, None, None, None),
    "VINAYAK": (7, 185, 222, 180, 250), "SHREE SANTINATH": (3, None, 137, 132, 142),
    "VEDANSHI": (2, None, 168, 135, 200), "BSK": (2, 175, 183, 155, 210), "K THREE PLUS": (4, None, 85, 85, 85),
}
HEADER = ["Vendor", "S. No.", "Fabric (Original)", "Fabric Category", '44" Width Rate', '60" Width Rate',
          '36" Width Rate', "Per Pc / Special Rate", "Metric", "Value", "Vendor", "Offerings Count"]


def rate_data():
    rows, n, last = [HEADER], 0, None
    for v, f, c, a, b, d, e in REAL:
        n = n + 1 if v == last else 1
        last = v
        money = [f"₹{x}" if isinstance(x, int) else x for x in (a, b, d, e)]      # formatted like the sheet
        rows.append([v, n, f, c, *money, "Total Vendors" if n == 1 and v == "RV" else "", 11 if v == "RV" else "",
                     v, n])                                                        # helper block on the right
    return rows


CARDS = [
    ["RV", "", "", "", "", "VARSHA"],
    ["S. NO.", "FABRIC", "44 WIDTH", "60 WIDTH", "36 WIDTH", "S. NO.", "FABRIC", "44 WIDTH", "60 WIDTH"],
    [1, "CREPE", 205, 255, "", 1, " MUSLINE", 165, 200],                      # 60" changed 250 -> 255
    [2, "MUL CHANDERI", 195, 240, "", 2, "SILK SATIN", 300, 350],             # new at VARSHA
    ["", "", "", "", "", ""],
    ["GOKUL"],
    ["S. NO.", "FABRIC", "44 WIDTH", "60 WIDTH"],
    [1, "N-CREPE", 210, 260],
    [4, "RFD CREPE ", "", "", 120],                                            # unlabelled column after headers
]


@pytest.fixture
def parsed():
    return vr.parse_vendor_rate({"rates": rate_data(), "cards": CARDS})


def kpis(d):
    return {k["id"]: k["value"] for k in d["kpis"]}


def rnd(v):
    return None if v is None or (isinstance(v, float) and math.isnan(v)) else math.floor(v + 0.5)


def test_rate_data_parsed(parsed):
    d = parsed["d"]
    assert len(d) == 56 and d["vendor"].nunique() == 11 and parsed["source"] == "Rate_Data"
    r = d.set_index(["vendor", "fabric"])
    assert math.isnan(r.loc[("RV", "PLAIN CREPE"), "r44"]) and r.loc[("RV", "PLAIN CREPE"), "r44_zero"]
    assert r.loc[("VARSHA", "MUSLIN PRINT HAND WORK PR PC"), "pc_text"] == "120/125"
    assert r.loc[("VEDANSHI", "PLAIN ORGENZA"), "r36"] == 85


def test_matches_sheet_vendor_benchmark(parsed):
    t = vr.vendor_rate_dashboard(parsed, {})["tables"]["vendors"]
    cols = [c["label"] for c in t["columns"]]
    got = {r[0]: tuple(rnd(r[cols.index(c)]) if c != "Items" else r[1] for c in
                       ("Items", 'Avg 44" Rate', 'Avg 60" Rate', 'Min 60" Rate', 'Max 60" Rate')) for r in t["rows"]}
    assert got == SHEET_BENCH
    assert [r[0] for r in t["rows"]] == list(SHEET_BENCH)                   # sheet order


def test_kpis_match_sheet_metrics(parsed):
    k = kpis(vr.vendor_rate_dashboard(parsed, {}))
    assert k["vendors"] == 11 and k["offerings"] == 56                     # sheet: Total Vendors / Offerings
    assert rnd(k["avg44"]) == 227 and rnd(k["avg60"]) == 205               # sheet: Avg 44" / 60" Width Rate
    assert k["cheapest_vendor"] == "K THREE PLUS" and k["no_rate"] == 3


def test_category_compare_and_rate_list(parsed):
    d = vr.vendor_rate_dashboard(parsed, {})
    t = d["tables"]["categories"]
    cols = [c["label"] for c in t["columns"]]
    crepe = next(r for r in t["rows"] if r[0] == "Crepe")
    assert crepe[cols.index('Best 60" Rate')] == 125 and crepe[cols.index('Best 60" Vendor')] == "RV"
    assert crepe[cols.index('Max 60" Rate')] == 295
    assert crepe[cols.index('Best 44" Vendor')] == "RV" and crepe[cols.index('Best 44" Rate')] == 205  # RV's 0 = no rate
    rl = d["tables"]["rates"]
    rc = [c["label"] for c in rl["columns"]]
    varsha_crepe = next(r for r in rl["rows"] if r[0] == "CREPE" and r[1] == "VARSHA")
    assert varsha_crepe[rc.index('vs Best 60" %')] == pytest.approx(136.0)  # 295 vs 125
    hw = next(r for r in rl["rows"] if r[0] == "MUSLIN PRINT HAND WORK PR PC")
    assert hw[rc.index("Per Pc / Special")] == "120/125"


def test_filters(parsed):
    d = vr.vendor_rate_dashboard(parsed, {"vendor": ["RV"]})
    assert kpis(d)["offerings"] == 13 and rnd(kpis(d)["avg60"]) == 193
    assert len(d["tables"]["vendors"]["rows"]) == 11                       # comparisons keep every vendor
    d = vr.vendor_rate_dashboard(parsed, {"fabric": ["Crepe"]})
    assert kpis(d)["offerings"] == 9
    assert {r[0] for r in d["tables"]["vendors"]["rows"]} == {"RV", "SWAGAT", "GOKUL", "VARSHA", "VIPUL", "VINAYAK"}
    m = d["charts"]["matrix60"]
    assert m["rows"] == ["Crepe"] and "EKTA FABRIC" not in m["columns"]


def test_checks_and_rate_cards(parsed):
    text = " ".join(c["text"] for c in vr.vendor_rate_dashboard(parsed, {})["checks"])
    assert "PLAIN CREPE (RV)" in text and "120/125" in text and "no rate at all" in text
    assert "SILK SATIN (VARSHA)" in text                                  # on the rate card, not in Rate_Data
    assert "CREPE (RV): rate card 205/255, Rate_Data 205/250" in text
    assert "RFD CREPE" not in text.split("differ")[-1]                    # 120 in an unlabelled column still matches
    cards = {(c["vendor"], c["fabric"]): c["nums"] for c in vr.parse_rate_cards(CARDS)}
    assert cards[("GOKUL", "RFD CREPE")] == [120] and cards[("VARSHA", "MUSLINE")] == [165, 200]


def test_rate_cards_used_when_rate_data_missing():
    p = vr.parse_vendor_rate({"cards": CARDS})
    d = vr.vendor_rate_dashboard(p, {})
    assert p["source"] == "NEW RATE SHEET" and kpis(d)["offerings"] == 6 and d["notices"]
    assert p["d"].set_index("fabric").loc["SILK SATIN", "category"] == "Silk"


@pytest.mark.parametrize("name,cat", [("CREPE HAND WORK PR PC", "Hand Work / Dupatta"),
                                      ("BEMBER RUSSION SILK", "Russian Silk"), ("CHIKU CHANDERI", "Mul Chanderi"),
                                      ("COTTON SILK", "Silk"), ("FLEX LILEN DUPATTA (PER PC)", "Linen"),
                                      ("DIG.VISCOS ORGENZA", "Organza"), ("DOBBY", "Other")])
def test_category_rules_match_the_sheet(name, cat):
    assert vr.category_of(name) == cat
    assert next(c for v, f, c, *_ in REAL if f == name) == cat


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
    v = body["options"]["vendor"][0]
    one = c.get("/api/vendor-rate", params={"vendor": v}).json()
    assert kpis(one)["vendors"] == 1
    assert store.status()["vendor_rate"]["ok"]
