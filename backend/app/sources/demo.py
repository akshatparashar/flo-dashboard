"""Demo source: realistic sample grids laid out exactly like the five real Google Sheets.

Used when no Google service account is configured (local development, previews, automated tests). The grids go
through the same parsers as the real sheets, including the messy cases those parsers handle: text dates, part-lot
receive dates, case variants of names, TOTAL rows, helper rows, blank cells and formula junk. Names here are
invented. A few in-production rows move a little every minute so the live refresh can be seen working.
"""
from __future__ import annotations

import threading
import time
from datetime import date, timedelta

import numpy as np

from ..core import CATEGORIES_LIST, FY_MONTH_NOS, FY_START_YEAR, KNOWN_DESIGNERS, MONTHS, col_to_idx, today_ist

CLIENTS = ["AARNA RETAIL", "KAVYA TRENDS", "MEHR & CO", "NOOR STUDIO", "SAANCHI LABEL", "VASTRA HOUSE",
           "ZOYA BOUTIQUE", "INDIGO LANE"]
FABRICATORS = ["RK GARMENTS", "SHREE FAB", "MAHI EXPORTS", "AS STITCHCRAFT", "NAVKAR TEX", "PRIME CRAFT"]
SAMPLE_VENDORS = ["Lotus Sampling", "Chandni Studio", "Rangrez Works", "Sutra Lab", "Kala Kendra"]
MILLS = ["ARVIND TEXTILES", "SHUBH FABRICS", "GANGA MILLS", "PARIDHAN SILKS", "NEELKANTH TEX", "OMKAR WEAVES"]
COLLECTIONS = ["SUMMER '26", "MONSOON EDIT", "FESTIVE", "WINTER EDIT", "ESSENTIALS"]
CATEGORY_SPELLINGS = {"CO-ORD SET": ["CO-ORD SET", "Co-ord Sets", "COORD SET"], "KURTA PANT": ["KURTA PANT", "Kurta Pants"],
                      "TOP": ["TOP", "Tops"], "KURTA PANT DUPATTA": ["KURTA PANT DUPATTA", "Kurta Pant Duppata"],
                      "DRESS": ["DRESS", "Dresses"], "KAFTAN": ["KAFTAN"], "KURTA": ["KURTA", "Kurtas"]}

SHEET_TABS = {
    "1wBo0zF2wlqBzY5ZQaX5CPjCOedORwg_1Eh01vje5KFU": [("DASHBOARD", 0), ("CONFIRMATION SHEET", 11)],
    "1EfQ08lXGL8YjtoaZ2ygJtNVaED7doDijo2jFvCuS7Kg": [("SAMPLE DASHBOARD", 1), ("2026-27", 78218658)],
    "1hP9Bkvu2F-qj4tXYhOCb4alfJOZZtAsMQNOjVQyWoo4": [("FABRICATOR DASHBOARD", 2), ("MONTHWISE SUMMARY", 164418035)],
    "1CvNPrdV4rQBR3_r8oIoPsW1ak123BGj88-qYbUU1y4I": [("INDEX", 418084418), ("DASHBOARD", 3)],
    "14USlaIteR3xlHjwzJOhZjLoyAZi-xAiF4LMXUE_UR2Y": [("DASHBOARD", 4), ("NEW", 5), ("REPEAT", 6)],
}
EPOCH = date(1899, 12, 30)
FY_START = date(FY_START_YEAR, 4, 1)
FY_END = date(FY_START_YEAR + 1, 3, 31)


def serial(d: date) -> int:
    return (d - EPOCH).days


def dmy(d: date) -> str:
    return d.strftime("%d/%m/%Y")


def _now_date() -> date:
    t = today_ist().date()
    return min(max(t, date(FY_START_YEAR, 5, 20)), FY_END)


class DemoSheetSource:
    name = "demo"

    def __init__(self, seed: int = 2026):
        self.seed = seed
        self._lock = threading.Lock()
        self._day = None
        self._grids: dict = {}

    # -- source interface --------------------------------------------------------------------------------------
    def list_tabs(self, sheet_id):
        if sheet_id not in SHEET_TABS:
            from .google import SheetAccessError
            raise SheetAccessError("Unknown sheet id (demo source).")
        return list(SHEET_TABS[sheet_id])

    def get_values(self, sheet_id, tab, formatted=False):
        g = self._ensure()
        key = (sheet_id, tab, bool(formatted))
        if key not in g:
            from .google import SheetAccessError
            raise SheetAccessError(f"Tab '{tab}' has no data (demo source).")
        values = g[key]
        if tab == "CONFIRMATION SHEET":
            values = self._live_master(values)
        return values

    def get_formulas(self, sheet_id, tab, col_letter):
        g = self._ensure()
        return g.get((sheet_id, tab, "formulas", col_letter), [])

    # -- generation --------------------------------------------------------------------------------------------
    def _ensure(self):
        now = _now_date()
        with self._lock:
            if self._day != now:
                rng = np.random.RandomState(self.seed)
                grids = {}
                grids.update(self._master(rng, now))
                grids.update(self._samples(rng, now))
                grids.update(self._fabricator(rng, now))
                grids.update(self._fabric_po(rng, now))
                grids.update(self._target(rng, now))
                self._grids, self._day = grids, now
            return self._grids

    @staticmethod
    def _rand_date(rng, start: date, end: date) -> date:
        span = max((end - start).days, 0)
        return start + timedelta(days=int(rng.randint(0, span + 1)))

    def _master(self, rng, now):
        sid = "1wBo0zF2wlqBzY5ZQaX5CPjCOedORwg_1Eh01vje5KFU"
        width = col_to_idx("AX") + 1
        header = [""] * width
        for letter, name in (("A", "S.NO"), ("B", "ORDER DATE"), ("C", "DESIGNER"), ("D", "TYPE"), ("E", "STYLE NO"),
                             ("F", "CATEGORY"), ("J", "QTY"), ("N", "CLIENT"), ("AA", "FABRICATOR"),
                             ("AC", "PRODUCTION DATE"), ("AH", "DELAY DAYS"), ("AS", "IN PRODUCTION"),
                             ("AT", "RECEIVED"), ("AU", "PENDING"), ("AX", "STATUS")):
            header[col_to_idx(letter)] = name
        rows = []
        weights = np.array([1.4, 1.1, 0.9, 1.3, 1.0, 0.8, 1.2, 0.7, 1.0, 0.6])
        weights = weights / weights.sum()
        n = 430
        for i in range(n):
            od = self._rand_date(rng, FY_START, now)
            r = [""] * width
            r[0] = i + 1
            r[1] = serial(od)
            des = KNOWN_DESIGNERS[rng.choice(len(KNOWN_DESIGNERS), p=weights)]
            r[2] = des if rng.rand() > 0.03 else ""
            r[3] = "NEW" if rng.rand() < 0.68 else ("REPEAT" if rng.rand() < 0.9 else "Repeat Order")
            r[4] = f"FL-{2600 + i}"
            cat = CATEGORIES_LIST[rng.randint(len(CATEGORIES_LIST))]
            spell = CATEGORY_SPELLINGS[cat]
            r[5] = spell[rng.randint(len(spell))]
            qty = int(rng.choice([60, 80, 100, 120, 150, 200, 250, 300, 400, 500]))
            r[col_to_idx("J")] = qty
            r[col_to_idx("N")] = CLIENTS[rng.randint(len(CLIENTS))]
            prod_day = od + timedelta(days=int(rng.randint(4, 13)))
            in_prod = prod_day <= now and rng.rand() > 0.06
            r[col_to_idx("AA")] = FABRICATORS[rng.randint(len(FABRICATORS))] if rng.rand() > 0.04 else ""
            if in_prod:
                r[col_to_idx("AC")] = serial(prod_day)
                due = prod_day + timedelta(days=28)
                age = (now - prod_day).days
                frac = min(1.0, max(0.0, age / 38 + rng.normal(0, 0.18)))
                received = int(round(qty * frac / 10.0) * 10)
                received = min(received, qty)
                pending = qty - received
                if pending > 0:
                    delay = (now - due).days
                    status = "IN PRODUCTION" if received == 0 else "PARTIAL RECEIVED"
                    if received == 0 and rng.rand() < 0.4:
                        status = ["CUTTING", "STITCHING", "FINISHING"][rng.randint(3)]
                else:
                    delay = int(rng.randint(-6, 5))
                    status = "COMPLETED"
                r[col_to_idx("AH")] = delay
                r[col_to_idx("AS")] = qty
                r[col_to_idx("AT")] = received
                r[col_to_idx("AU")] = pending
                r[col_to_idx("AX")] = status
            else:
                # blank production date -> the sheet's TODAY()-blank formula yields a huge number
                r[col_to_idx("AH")] = serial(now) if rng.rand() < 0.5 else ""
                r[col_to_idx("AX")] = "CONFIRMED"
            rows.append(r)
        rows.sort(key=lambda r: r[1])
        for i, r in enumerate(rows):
            r[0] = i + 1
        total = [""] * width
        total[1] = "TOTAL"
        total[col_to_idx("J")] = sum(r[col_to_idx("J")] for r in rows)
        title = ["ORDER CONFIRMATION SHEET 2026-27"]
        grid = [title, ["", "", "GRAND TOTAL"] + [""] * (width - 3), header] + rows + [total]
        return {(sid, "CONFIRMATION SHEET", False): grid, (sid, "CONFIRMATION SHEET", True): grid}

    @staticmethod
    def _live_master(values):
        """Moves a few pcs from pending to received on some open rows; changes every 3 minutes, cycles hourly."""
        tick = int(time.time() // 180) % 20
        if tick == 0:
            return values
        out = [list(r) for r in values]
        a_t, a_u, a_x = col_to_idx("AT"), col_to_idx("AU"), col_to_idx("AX")
        moved = 0
        for r in out[3:]:
            if len(r) > a_u and isinstance(r[a_u], int) and r[a_u] >= 40 and isinstance(r[a_t], int):
                step = min(r[a_u], 10 * tick // 4 + 10)
                r[a_t] += step
                r[a_u] -= step
                if r[a_u] == 0:
                    r[a_x] = "COMPLETED"
                moved += 1
                if moved >= 6:
                    break
        return out

    def _samples(self, rng, now):
        sid = "1EfQ08lXGL8YjtoaZ2ygJtNVaED7doDijo2jFvCuS7Kg"
        header = ["S.NO", "VENDOR NAME", "SAMPLE TYPE", "STYLE NO", "FABRIC", "QTY", "SIZE", "PROCESS DATE",
                  "REMARK", "", "", "STATUS", "", "DESIGNER NAME"]
        statuses = (["Approved"] * 45 + ["Rejected"] * 14 + ["On Hold"] * 10 + ["In Process"] * 19 + [""] * 5
                    + ["APPROVED WITH CHANGES"] * 4 + ["Re-sample"] * 3)
        rows = []
        for i in range(320):
            d = self._rand_date(rng, FY_START, now)
            vendor = SAMPLE_VENDORS[rng.randint(len(SAMPLE_VENDORS))]
            if rng.rand() < 0.1:
                vendor = vendor.upper()
            designer = KNOWN_DESIGNERS[rng.randint(len(KNOWN_DESIGNERS))].title()
            if rng.rand() < 0.15:
                designer = designer.upper() + " "
            p = rng.rand()
            pdate = serial(d) if p < 0.86 else (dmy(d) if p < 0.97 else "")
            status = statuses[rng.randint(len(statuses))]
            if (now - d).days < 12 and status in ("Approved", "Rejected") and rng.rand() < 0.6:
                status = "In Process"
            rows.append([i + 1, vendor, "PROTO", f"S-{4100 + i}", "COTTON", int(rng.choice([1, 1, 2, 2, 3, 4, 6])),
                         "M", pdate, "", "", "", status, "", designer if rng.rand() > 0.02 else ""])
        return {(sid, "2026-27", False): [header] + rows, (sid, "2026-27", True): [header] + rows}

    def _fabricator(self, rng, now):
        sid = "1hP9Bkvu2F-qj4tXYhOCb4alfJOZZtAsMQNOjVQyWoo4"
        months_done = [i for i in range(12)
                       if date(FY_START_YEAR if i < 9 else FY_START_YEAR + 1, FY_MONTH_NOS[i], 1) <= now]
        data = {}
        for name in FABRICATORS:
            scale = rng.uniform(0.6, 1.5)
            vals = []
            for i in range(12):
                if i not in months_done:
                    vals.append([0.0, 0, 0, 0, 0])
                    continue
                age = len(months_done) - 1 - i
                issue = round(float(rng.uniform(900, 3600) * scale), 2)
                prod = int(issue / rng.uniform(2.3, 2.9))
                frac = min(1.0, 0.35 + 0.22 * age + rng.normal(0, 0.05))
                rcvd = int(prod * max(frac, 0.1))
                vals.append([issue, prod, rcvd, prod - rcvd, int(rcvd * rng.uniform(0.85, 1.05))])
            data[name] = vals
        data["ALL OVER"] = [[round(sum(data[f][i][k] for f in FABRICATORS), 2) if k == 0 else
                             sum(data[f][i][k] for f in FABRICATORS) for k in range(5)] for i in range(12)]

        names = FABRICATORS + ["ALL OVER"]
        rows_needed = ((len(names) + 1) // 2) * 17 + 2
        raw = [["" for _ in range(15)] for _ in range(rows_needed)]
        disp = [["" for _ in range(15)] for _ in range(rows_needed)]
        raw[0][0] = disp[0][0] = "MONTHWISE SUMMARY 2026-27"
        for b, name in enumerate(names):
            top, left = 2 + (b // 2) * 17, (b % 2) * 8
            title = "Position of Stock ALL OVER" if name == "ALL OVER" else f"Position Of Stock ({name})"
            raw[top][left] = disp[top][left] = title
            hdr = ["Month", "Fabric Issue", "Pcs Under Production", "RCVD", "Remaining", "Monthly Incoming"]
            for k, h in enumerate(hdr):
                raw[top + 1][left + k] = disp[top + 1][left + k] = h
            for i in range(12):
                raw[top + 2 + i][left] = disp[top + 2 + i][left] = MONTHS[i]
                for k in range(5):
                    v = data[name][i][k]
                    raw[top + 2 + i][left + 1 + k] = v
                    disp[top + 2 + i][left + 1 + k] = f"{v:,.2f}" if k == 0 else f"{v:,}"
            raw[top + 14][left] = disp[top + 14][left] = "Total"
            for k in range(5):
                v = sum(data[name][i][k] for i in range(12))
                raw[top + 14][left + 1 + k] = v
                disp[top + 14][left + 1 + k] = f"{v:,.2f}" if k == 0 else f"{v:,}"
        return {(sid, "MONTHWISE SUMMARY", False): raw, (sid, "MONTHWISE SUMMARY", True): disp}

    def _fabric_po(self, rng, now):
        sid = "1CvNPrdV4rQBR3_r8oIoPsW1ak123BGj88-qYbUU1y4I"
        header = ["S.NO", "VENDOR NAME", "PO NO.", "ORDER DATE", "DELIVERY DATE", "RCVD DATE", "DELAY DAYS",
                  "ORDER TYPE", "CLIENT NAME", "DESIGNER NAME", "COLLECTION NAME", "STATUS", "ACTUAL ORDER QTY.",
                  "TOTAL MTR OF FABRIC ORDERED", "TOTAL MTR OF FABRIC RCVD", "PENDING", "EXCESS", "REMARK",
                  "TOTAL PC", "ITEM"]
        rows = [header, ["", dmy(now), "", "", "", "", "", "", "", "", "", "", "", "", "", "", "", "", "", ""]]
        pos = []
        for i in range(170):
            od = self._rand_date(rng, FY_START, now)
            due = od + timedelta(days=15)
            ordered = float(int(rng.uniform(150, 2800)))
            age = (now - od).days
            lead = int(rng.choice([8, 10, 12, 13, 14, 15, 16, 18, 21, 26, 33]))
            p = rng.rand()
            if p < 0.025:
                status, rcvd, rdate = "CANCELLED", 0.0, ""
            elif age > lead and p < 0.86:
                status, rcvd = "RCVD", ordered
                rdate = od + timedelta(days=lead)
                rdate = serial(rdate) if rng.rand() < 0.8 else dmy(rdate)
            elif age > 9 and p < 0.93:
                status = "PARTIAL RCVD"
                rcvd = float(int(ordered * rng.uniform(0.4, 0.85)))
                d1 = od + timedelta(days=int(rng.randint(7, 14)))
                rdate = dmy(d1)
                if age > 20 and rng.rand() < 0.5:
                    rdate = f"{dmy(d1)}+{dmy(d1 + timedelta(days=int(rng.randint(5, 12))))}"
            else:
                status, rcvd, rdate = ("PENDING" if rng.rand() < 0.85 else "IN TRANSIT"), 0.0, ""
            if status == "RCVD" and rng.rand() < 0.06:
                status = ""            # blank status but fully received -> counted as received
            pcs = int(ordered / rng.uniform(2.2, 3.0))
            pos.append([0, MILLS[rng.randint(len(MILLS))], f"FPO/{2600 + i}", serial(od),
                        serial(due) if rng.rand() > 0.05 else "", rdate, "",
                        "NEW" if rng.rand() < 0.7 else "REPEAT", CLIENTS[rng.randint(len(CLIENTS))],
                        KNOWN_DESIGNERS[rng.randint(len(KNOWN_DESIGNERS))],
                        COLLECTIONS[rng.randint(len(COLLECTIONS))], status, pcs, ordered, rcvd,
                        max(ordered - rcvd, 0.0) if status != "CANCELLED" else 0.0, 0, "", pcs,
                        CATEGORIES_LIST[rng.randint(len(CATEGORIES_LIST))]])
        pos.sort(key=lambda r: r[3])
        for i, r in enumerate(pos):
            r[0] = i + 1
        rows += pos
        rows.append(["", "TOTAL", "", "", "", "", "", "", "", "", "", "", sum(r[12] for r in pos),
                     sum(r[13] for r in pos), sum(r[14] for r in pos), sum(r[15] for r in pos), "", "", "", ""])
        return {(sid, "INDEX", False): rows, (sid, "INDEX", True): rows}

    def _target(self, rng, now):
        sid = "14USlaIteR3xlHjwzJOhZjLoyAZi-xAiF4LMXUE_UR2Y"
        header = ["S.NO", "ORDER DATE", "IMAGE", "BARCODE", "ITEM NAME", "SIZE", "NO.OF PCS", "RATE", "ORDER BY",
                  "DESIGNER", "TOTAL AMOUNT"]
        monthly_target = 50.2e7 / 12
        pace = [0.84, 0.97, 1.09, 0.91, 1.13, 0.99, 1.05, 0.96, 1.02, 0.93, 1.0, 1.08]
        new_lines = []
        for i in range(12):
            start = date(FY_START_YEAR if i < 9 else FY_START_YEAR + 1, FY_MONTH_NOS[i], 1)
            if start > now:
                break
            nxt = date(start.year + (start.month == 12), start.month % 12 + 1, 1)
            end = min(nxt - timedelta(days=1), now)
            frac = ((end - start).days + 1) / ((nxt - start).days)
            goal = monthly_target * pace[i] * frac
            got = 0.0
            while got < goal:
                pcs = int(rng.randint(5, 40) * 10)
                rate = int(rng.randint(13, 48) * 50)
                d = self._rand_date(rng, start, end)
                new_lines.append([d, f"FL{30000 + len(new_lines):05d}", CATEGORIES_LIST[rng.randint(7)], pcs, rate,
                                  CLIENTS[rng.randint(len(CLIENTS))],
                                  KNOWN_DESIGNERS[rng.randint(len(KNOWN_DESIGNERS))]])
                got += pcs * rate
        new_lines.sort(key=lambda r: r[0])
        rep_lines = []
        popular = [new_lines[int(k)] for k in rng.choice(len(new_lines), size=min(40, len(new_lines)), replace=False)]
        for src in popular:
            for _ in range(int(rng.choice([1, 1, 2, 2, 3, 4, 5]))):
                d = src[0] + timedelta(days=int(rng.randint(15, 80)))
                if d > now:
                    continue
                rep_lines.append([d, src[1], src[2], int(rng.randint(5, 30) * 10), src[4], src[5], src[6]])
        rep_lines.sort(key=lambda r: r[0])

        def tab(lines, label, quirks):
            out = [[f"DESIGNER'S TARGET ACHIEVED 2026-27 — {label}"], header]
            for n, (d, bc, item, pcs, rate, by, des) in enumerate(lines, start=1):
                total = pcs * rate
                date_cell = serial(d)
                if quirks and n == 7:
                    total += 500          # sheet total typed differently
                if quirks and n == 19:
                    rate, total = "", 0    # missing rate
                if quirks and n == 33:
                    date_cell = ""         # missing order date
                out.append([n, date_cell, "", bc, item, rng.choice(["S-XXL", "FREE", "M-XL"]), pcs, rate, by, des,
                            total])
            out.append(["", "", "", "", "TOTAL", "", sum(r[3] for r in lines), "", "", "",
                        sum(r[3] * r[4] for r in lines)])
            return out

        return {(sid, "NEW", False): tab(new_lines, "NEW", True), (sid, "REPEAT", False): tab(rep_lines, "REPEAT",
                                                                                               False)}
