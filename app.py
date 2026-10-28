import html
import re
import warnings

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import streamlit as st
import gspread
from google.oauth2.service_account import Credentials

# -----------------------------------------------------------------------------
# 1. PAGE SETUP & STYLING
# -----------------------------------------------------------------------------
st.set_page_config(
    page_title="Executive Multi-Dashboard 2026-27",
    page_icon="📊",
    layout="wide"
)

# Dropdown mein dikhne wali Google Sheets. Nayi sheet add karne ke liye yahan ek entry add karein.
SHEET_REGISTRY = {
    "Master Sheet": {
        "id": "1wBo0zF2wlqBzY5ZQaX5CPjCOedORwg_1Eh01vje5KFU",
        "type": "tracker",
        "gid": 0,
    },
    "Sample Summary": {
        "id": "1EfQ08lXGL8YjtoaZ2ygJtNVaED7doDijo2jFvCuS7Kg",
        "type": "overview",
        "gid": 78218658,
        "data_tabs": ["2026-27", "SAMPLE SHEET 2026-27"],
    },
    "Fabricator Report": {
        "id": "1hP9Bkvu2F-qj4tXYhOCb4alfJOZZtAsMQNOjVQyWoo4",
        "type": "overview_fabricators",
        "gid": 164418035,
        "summary_tabs": ["MONTHWISE SUMMARY"],
    },
}
SHEET_ID = "1wBo0zF2wlqBzY5ZQaX5CPjCOedORwg_1Eh01vje5KFU"  # default/fallback
DEFAULT_TAB = "CONFIRMATION SHEET"
MONTHS = ["April", "May", "June", "July", "August", "September",
          "October", "November", "December", "January", "February", "March"]

CATEGORIES_LIST = ["CO-ORD SET", "KURTA PANT", "TOP", "KURTA PANT DUPATTA", "DRESS", "KAFTAN", "KURTA"]

if "dashboard_dark_mode" not in st.session_state:
    st.session_state.dashboard_dark_mode = False

with st.sidebar:
    st.markdown("### 🎨 Appearance")
    st.toggle("Dark mode", key="dashboard_dark_mode", help="Dashboard appearance mode toggle")

DARK_MODE = st.session_state.dashboard_dark_mode
if DARK_MODE:
    APP_BG, PANEL_BG, TEXT, MUTED, BORDER = "#0b1220", "#111c2e", "#e5edf7", "#9fb0c7", "#26364d"
    PLOT_TEMPLATE = "plotly_dark"
else:
    APP_BG, PANEL_BG, TEXT, MUTED, BORDER = "#f4f7fb", "#ffffff", "#172033", "#64748b", "#dce4ef"
    PLOT_TEMPLATE = "plotly_white"
px.defaults.template = PLOT_TEMPLATE

st.markdown(f"""
<style>
:root {{ color-scheme: {'dark' if DARK_MODE else 'light'}; }}
.stApp {{ background: {APP_BG}; color: {TEXT}; }}
.block-container {{ padding-top: 1.15rem; padding-bottom: 2.5rem; max-width: 1600px; }}
[data-testid="stHeader"] {{ background: transparent; }}
[data-testid="stSidebar"] {{ background: {PANEL_BG}; border-right: 1px solid {BORDER}; }}
[data-testid="stSidebar"] [data-testid="stMarkdownContainer"] p,
[data-testid="stSidebar"] label {{ color: {TEXT}; }}
[data-testid="stMetric"] {{ background: {PANEL_BG}; border: 1px solid {BORDER}; padding: 16px 18px; border-radius: 15px; box-shadow: 0 5px 18px rgba(15,23,42,.07); min-height: 105px; }}
[data-testid="stMetricLabel"] {{ color: {MUTED}; font-size: .83rem; font-weight: 650; }}
[data-testid="stMetricValue"] {{ color: {TEXT}; font-weight: 750; letter-spacing: -.025em; }}
[data-testid="stTabs"] button {{ border-radius: 10px 10px 0 0; font-weight: 650; }}
[data-testid="stDataFrame"] {{ border: 1px solid {BORDER}; border-radius: 12px; overflow: hidden; }}
[data-testid="stPlotlyChart"] {{ background: {PANEL_BG}; border: 1px solid {BORDER}; border-radius: 14px; padding: 6px; }}
hr {{ border-color: {BORDER}; }}
h1, h2, h3 {{ letter-spacing: -.025em; }}
.dashboard-hero {{ background: linear-gradient(120deg, {'#16243b' if DARK_MODE else '#e8f1ff'}, {'#172d43' if DARK_MODE else '#ffffff'}); border: 1px solid {BORDER}; border-radius: 18px; padding: 22px 26px; margin: 0 0 18px 0; }}
.dashboard-hero p {{ color: {MUTED}; margin: 4px 0 0 0; }}
.insight-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(290px, 1fr)); gap: 12px; margin: 6px 0 20px 0; }}
.insight {{ background: {PANEL_BG}; border: 1px solid {BORDER}; border-left: 4px solid #2563eb; border-radius: 12px; padding: 12px 15px; font-size: .92rem; color: {TEXT}; box-shadow: 0 3px 12px rgba(15,23,42,.05); }}
.chip {{ display: inline-block; background: {'#1d3350' if DARK_MODE else '#eef4ff'}; border: 1px solid {BORDER}; border-radius: 999px; padding: 2px 12px; margin: 10px 8px 0 0; font-size: .78rem; color: {MUTED}; }}
[data-testid="stTabs"] [role="tablist"] {{ gap: 4px; }}
</style>
""", unsafe_allow_html=True)

# -----------------------------------------------------------------------------
# 2. HELPER FUNCTIONS & NUMERIC SANITIZATION
# -----------------------------------------------------------------------------
def col_to_idx(letter):
    n = 0
    for c in letter.upper():
        n = n * 26 + ord(c) - 64
    return n - 1

def num(s):
    if not isinstance(s, pd.Series):
        s = pd.Series(s)
    text = s.astype("string").str.replace("\xa0", "", regex=False).str.strip()
    text = text.replace({"": pd.NA, "-": pd.NA, "—": pd.NA, "–": pd.NA, "N/A": pd.NA, "n/a": pd.NA, "None": pd.NA, "nan": pd.NA})
    is_paren_negative = text.str.match(r"^\(.*\)$", na=False)
    cleaned = text.str.replace(",", "", regex=False).str.replace(r"[^0-9.\-]", "", regex=True)
    cleaned = cleaned.mask(is_paren_negative, "-" + cleaned.str.replace("-", "", regex=False))
    return pd.to_numeric(cleaned, errors="coerce").fillna(0).astype(float)

def clean_delay_days(s):
    parsed = num(s)
    parsed = parsed.mask(parsed > 1000, 0)
    return parsed

def date_col(s):
    res = pd.to_datetime(s, errors="coerce", dayfirst=True)
    mask = res.isna()
    if mask.any():
        res[mask] = pd.to_datetime(s[mask], errors="coerce", dayfirst=False)
    return res

# -----------------------------------------------------------------------------
# 3. GOOGLE SHEETS AUTHENTICATION & LIVE DATA LOAD
# -----------------------------------------------------------------------------
def build_raw(values):
    first = next((i for i, r in enumerate(values)
                  if r and re.fullmatch(r"\d+(\.0+)?", str(r[0]).strip())), 4)
    rows = values[first:]

    max_cols = max(len(r) for r in rows) if rows else 0
    padded_rows = [r + [""] * (max_cols - len(r)) for r in rows]
    df_raw = pd.DataFrame(padded_rows)

    if not df_raw.empty:
        b = df_raw[col_to_idx("B")].astype(str).str.strip() if col_to_idx("B") < df_raw.shape[1] else ""
        j = df_raw[col_to_idx("J")].astype(str).str.strip() if col_to_idx("J") < df_raw.shape[1] else ""
        keep = (b != "") | (j != "")
        df_raw = df_raw[keep].reset_index(drop=True)
    return df_raw, first + 1

@st.cache_resource(show_spinner=False)
def get_client():
    if "gcp_service_account" not in st.secrets:
        st.error("Google credentials missing hain. Streamlit Settings → Secrets me add karein.")
        st.stop()

    creds_dict = dict(st.secrets["gcp_service_account"])
    if "private_key" in creds_dict:
        creds_dict["private_key"] = str(creds_dict["private_key"]).replace("\\n", "\n")

    creds = Credentials.from_service_account_info(
        creds_dict,
        scopes=[
            "https://www.googleapis.com/auth/spreadsheets.readonly",
            "https://www.googleapis.com/auth/drive.readonly",
        ],
    )
    return gspread.authorize(creds)

@st.cache_data(ttl=300, show_spinner="Google Sheet se live data load ho raha hai...")
def load_sheet(sheet_id):
    try:
        book = get_client().open_by_key(sheet_id)
    except Exception as e:
        show_access_error(e)
        st.stop()

    try:
        ws = book.worksheet("CONFIRMATION SHEET")
    except gspread.WorksheetNotFound:
        try:
            ws = book.worksheet("ORDER SHEET")
        except gspread.WorksheetNotFound:
            ws = book.get_worksheet(0)

    values = ws.get_all_values()
    if not values:
        st.error("Google Sheet empty hai.")
        st.stop()

    df_raw, first_data_row = build_raw(values)
    totals_row = values[1] if len(values) > 1 else []
    return df_raw, totals_row, ws.title, first_data_row

# -----------------------------------------------------------------------------
# 4. DATA PREPARATION (MASTER SHEET TRACKER)
# -----------------------------------------------------------------------------
def prepare(raw):
    d = pd.DataFrame()

    def get_raw_col(col_letter):
        idx = col_to_idx(col_letter)
        if idx < len(raw.columns):
            return raw[idx]
        return pd.Series([""] * len(raw))

    d["date_client"] = date_col(get_raw_col("B"))
    d["date_prod"] = date_col(get_raw_col("AC"))
    d["designer"] = get_raw_col("C").astype(str).str.strip()
    d["type"] = get_raw_col("D").astype(str).str.strip()
    d["category"] = get_raw_col("F").astype(str).str.strip()
    d["qty"] = num(get_raw_col("J"))
    d["client"] = get_raw_col("N").astype(str).str.strip()
    d["fabricator"] = get_raw_col("AA").astype(str).str.strip()
    d["delay"] = clean_delay_days(get_raw_col("AH"))
    d["production"] = num(get_raw_col("AS"))
    d["received"] = num(get_raw_col("AT"))
    d["pending"] = num(get_raw_col("AU"))
    d["status"] = get_raw_col("AX").astype(str).str.strip()

    for c in ["designer", "type", "category", "client", "fabricator", "status"]:
        d.loc[d[c].str.lower().isin(["nan", "none"]), c] = ""

    d["month_client"] = d["date_client"].dt.month_name()
    d["month_prod"] = d["date_prod"].dt.month_name()

    d["type_clean"] = d["type"].str.upper()
    d["category_clean"] = d["category"].str.upper().str.strip()

    return d

def metrics(items):
    cols = st.columns(len(items))
    for c, (label, value) in zip(cols, items):
        c.metric(label, value)

def fmt(x):
    return f"{x:,.0f}"

# -----------------------------------------------------------------------------
# 5. MASTER SHEET DASHBOARD VIEWS & TABLES
# -----------------------------------------------------------------------------
def overview(d):
    st.subheader("Executive Overview")
    metrics([
        ("Total Designs", f"{len(d[d.qty > 0]):,}"),
        ("Total Order Qty (J)", fmt(d.qty.sum())),
        ("In Production PCS (AS)", fmt(d.production.sum())),
        ("Received PCS (AT)", fmt(d.received.sum())),
    ])
    metrics([
        ("Pending PCS (AU)", fmt(d.pending.sum())),
        ("Overdue PCS (AH > 0)", fmt(d.loc[d.delay > 0, "production"].sum())),
        ("On-Time PCS (AH <= 0)", fmt(d.loc[d.delay <= 0, "production"].sum())),
        ("New Order Qty", fmt(d.loc[d.type_clean.str.contains("NEW", na=False), "qty"].sum())),
    ])
    a, b = st.columns(2)
    with a:
        m = d.dropna(subset=["date_client"]).assign(Month=lambda x: x.date_client.dt.to_period("M").astype(str)).groupby("Month", as_index=False)["qty"].sum()
        if not m.empty:
            st.plotly_chart(px.bar(m, x="Month", y="qty", title="Monthly Order Quantity (Column B)", text_auto=".2s"), use_container_width=True)
    with b:
        c = d[d.category_clean.ne("")].groupby("category_clean", as_index=False)["qty"].sum().sort_values("qty", ascending=False)
        if not c.empty:
            st.plotly_chart(px.bar(c, x="category_clean", y="qty", title="Category-wise Order Quantity (Column J)", text_auto=".2s"), use_container_width=True)

def designer_dashboard(d):
    st.subheader("👨‍🎨 Executive Designer Performance & Category Tracking Dashboard")
    x = d[d.designer.ne("")].copy()
    if x.empty:
        st.info("Selected filters ke liye designer data nahi hai."); return

    g = x.groupby("designer", as_index=False).agg(**{"Total Volume (Pcs)": ("qty", "sum"), "Total Design Count": ("qty", "size")})
    new = x[x.type_clean.str.contains("NEW", na=False)].groupby("designer").qty.sum()
    repeat = x[x.type_clean.str.contains("REPEAT", na=False)].groupby("designer").qty.sum()
    g["New Orders (Pcs)"] = g.designer.map(new).fillna(0)
    g["Repeat Orders (Pcs)"] = g.designer.map(repeat).fillna(0)

    tot_vol = g["Total Volume (Pcs)"].sum()
    g["Share %"] = g["Total Volume (Pcs)"].apply(lambda v: f"{(v / tot_vol * 100):.1f}%" if tot_vol > 0 else "0.0%")
    g = g.sort_values("Total Volume (Pcs)", ascending=False)
    top = g.iloc[0]

    metrics([
        ("TOTAL DESIGNS", f"{len(x):,}"),
        ("TOTAL QUANTITY (PCS)", fmt(tot_vol)),
        ("NEW ORDER QTY", fmt(g["New Orders (Pcs)"].sum())),
        ("REPEAT ORDER QTY", fmt(g["Repeat Orders (Pcs)"].sum())),
        ("TOP PERFORMER", f"{top.designer} ({fmt(top['Total Volume (Pcs)'])} Pcs)"),
    ])

    st.markdown("---")
    st.subheader("📊 Designer Volume & Share Breakdown")
    des_summary_df = g[["designer", "New Orders (Pcs)", "Repeat Orders (Pcs)", "Total Volume (Pcs)", "Share %", "Total Design Count"]].rename(columns={"designer": "Designer Name"})

    col_t1, col_c1 = st.columns([1.2, 1])
    with col_t1:
        st.dataframe(des_summary_df, use_container_width=True, hide_index=True)
    with col_c1:
        melted = g.melt(id_vars="designer", value_vars=["New Orders (Pcs)", "Repeat Orders (Pcs)"], var_name="Order Type", value_name="Qty")
        st.plotly_chart(px.bar(melted, x="designer", y="Qty", color="Order Type", barmode="group", title="DESIGNER PERFORMANCE: NEW vs REPEAT ORDERS (PCS)", color_discrete_sequence=["#059669", "#7C3AED"]), use_container_width=True)

    st.markdown("---")
    st.subheader("🧩 Category Wise Designer Breakdown Matrix (Pcs)")
    cat_matrix = []
    for des_name in g["designer"]:
        sub = x[x["designer"].str.upper() == des_name.upper()]
        row_data = {"Designer": des_name}
        for cat in CATEGORIES_LIST:
            row_data[cat] = int(sub[sub["category_clean"] == cat]["qty"].sum())
        row_data["TOTAL"] = sum(row_data[c] for c in CATEGORIES_LIST)
        cat_matrix.append(row_data)

    cat_df = pd.DataFrame(cat_matrix)
    tot_row = {"Designer": "TOTAL"}
    for cat in CATEGORIES_LIST:
        tot_row[cat] = cat_df[cat].sum()
    tot_row["TOTAL"] = cat_df["TOTAL"].sum()
    cat_df = pd.concat([cat_df, pd.DataFrame([tot_row])], ignore_index=True)
    st.dataframe(cat_df, use_container_width=True, hide_index=True)

def client_dashboard(d):
    st.subheader("🏢 Executive Client Performance Dashboard (Date: Col B, Direct Column J Sum)")
    x = d.copy()

    total_designs = len(x[x.qty > 0])
    total_qty = x["qty"].sum()
    in_prod = x["production"].sum()
    rec_done = x["received"].sum()
    pending_qty = x["pending"].sum()
    repeat_qty = x[x["type_clean"].str.contains("REPEAT", na=False)]["qty"].sum()
    new_qty = x[x["type_clean"].str.contains("NEW", na=False)]["qty"].sum()

    metrics([
        ("TOTAL DESIGNS", f"{total_designs:,}"),
        ("TOTAL QTY (PCS) [Col J]", fmt(total_qty)),
        ("IN PRODUCTION [Col AS]", fmt(in_prod)),
        ("RECEIVED / DONE [Col AT]", fmt(rec_done)),
    ])
    metrics([
        ("TOTAL PENDING QTY [Col AU]", fmt(pending_qty)),
        ("REPEAT ORDERS (PCS)", fmt(repeat_qty)),
        ("NEW ORDERS (PCS)", fmt(new_qty)),
        ("CATEGORY TOTAL (PCS)", fmt(total_qty)),
    ])

    st.markdown("---")
    st.subheader("📅 Client Fulfillment Breakdown (Monthly Filtered by Col B Date)")
    monthly_ful = []
    for m in MONTHS:
        sub_m = x[x["month_client"] == m]
        monthly_ful.append({
            "MONTH": m,
            "ORDER QTY (J)": int(sub_m["qty"].sum()),
            "IN PRODUCTION (AS)": int(sub_m["production"].sum()),
            "RECEIVED (AT)": int(sub_m["received"].sum()),
            "PENDING (AU)": int(sub_m["pending"].sum())
        })
    m_df = pd.DataFrame(monthly_ful)
    m_df_tot = pd.DataFrame([{
        "MONTH": "TOTAL",
        "ORDER QTY (J)": m_df["ORDER QTY (J)"].sum(),
        "IN PRODUCTION (AS)": m_df["IN PRODUCTION (AS)"].sum(),
        "RECEIVED (AT)": m_df["RECEIVED (AT)"].sum(),
        "PENDING (AU)": m_df["PENDING (AU)"].sum()
    }])
    m_df_display = pd.concat([m_df, m_df_tot], ignore_index=True)

    c1, c2 = st.columns([1.2, 1])
    with c1:
        st.dataframe(m_df_display, use_container_width=True, hide_index=True)
    with c2:
        q = pd.DataFrame({"Status": ["RECEIVED QTY", "PENDING QTY"], "Qty": [rec_done, pending_qty]})
        st.plotly_chart(px.pie(q, names="Status", values="Qty", hole=.45, title="ORDER FULFILLMENT RATIO (RECEIVED vs PENDING)", color_discrete_sequence=["#059669", "#DC2626"]), use_container_width=True)

def production_dashboard(d):
    st.subheader("🏭 Production Executive Process Dashboard (Date: Col AC, Prod: Col AS)")

    overdue_mask = d["delay"] > 0
    overdue = d[overdue_mask]
    avg_overdue = overdue["delay"].mean() if len(overdue) > 0 else 0.0

    metrics([
        ("TOTAL DESIGN", f"{len(d[d.production > 0]):,} Orders"),
        ("INPRODUCTION PCS [Col AS]", fmt(d.production.sum())),
        ("RECIEVED PCS [Col AT]", fmt(d.received.sum())),
        ("PENDING PCS [Col AU]", fmt(d.pending.sum())),
        ("OVERDUE PCS (AH > 0)", fmt(d.loc[overdue_mask, "production"].sum())),
    ])

    metrics([
        ("AVG OVERDUE DAYS", f"{avg_overdue:.1f} Days"),
        ("ON-TIME DELIVERY %", f"{((len(d[d.delay <= 0]) / len(d) * 100) if len(d) > 0 else 0):.1f}%"),
        ("ON-TIME PCS (AH <= 0)", fmt(d.loc[d.delay <= 0, "production"].sum())),
        ("OVERDUE ORDERS COUNT", f"{len(overdue):,} Orders"),
    ])

def data_check(totals_row, d_all):
    st.caption("Sheet ki row 2 ke totals se dashboard ke totals match hone chahiye.")
    items = [("Total Qty (J)", "J", d_all["qty"].sum()),
             ("In Production (AS)", "AS", d_all["production"].sum()),
             ("Received (AT)", "AT", d_all["received"].sum()),
             ("Pending (AU)", "AU", d_all["pending"].sum())]
    rows = []
    for label, letter, mine in items:
        idx = col_to_idx(letter)
        cell = totals_row[idx] if idx < len(totals_row) else ""
        sheet_val = float(num(pd.Series([cell])).iloc[0])
        rows.append({"Column": label, "Sheet row-2 total": sheet_val,
                     "Dashboard": float(mine), "Diff": float(mine) - sheet_val})
    out = pd.DataFrame(rows)
    st.dataframe(out, use_container_width=True, hide_index=True)

# -----------------------------------------------------------------------------
# 6. GENERIC SUMMARY ENGINE & AUTO-ANALYSIS HELPER FUNCTIONS
# -----------------------------------------------------------------------------
PALETTE = ["#2563eb", "#059669", "#f59e0b", "#dc2626", "#7c3aed", "#0891b2", "#db2777", "#65a30d", "#ea580c", "#475569"]
px.defaults.color_discrete_sequence = PALETTE

MONTH_ABBR = [m[:3].lower() for m in MONTHS]
MONTH_COL_RE = re.compile(r"^(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*[\s\-'/_.]*\d{0,4}$", re.I)
ID_COL_RE = re.compile(r"^(s\.?\s*no\.?|sr\.?\s*no\.?|sl\.?\s*no\.?|serial.*|#|id|index)$", re.I)
CATEGORY_NUM_RE = re.compile(r"^(year|fy|financial year|week|quarter|month no\.?)$", re.I)
TOTAL_RE = re.compile(r"^(grand\s*|sub\s*|net\s*)?total\b", re.I)
BLANKS = {"", "nan", "none", "-", "—", "–", "n/a", "na", "#n/a", "#div/0!", "#ref!", "#value!", "#error!"}
AGGS = {"Sum": "sum", "Average": "mean", "Median": "median", "Max": "max", "Min": "min", "Count": "count"}

def is_number_like(s):
    t = re.sub(r"[,\s₹$€£%()\xa0]", "", str(s))
    if t in ("", "-", "."):
        return False
    try:
        float(t)
        return True
    except ValueError:
        return False

def blank_mask(s):
    return s.astype(str).str.strip().str.lower().isin(BLANKS)

def num_nan(s):
    if not isinstance(s, pd.Series):
        s = pd.Series(s)
    text = s.astype(str).str.replace("\xa0", "", regex=False).str.strip()
    text = text.mask(text.str.lower().isin(BLANKS))
    neg = text.str.match(r"^\(.*\)$", na=False)
    cleaned = text.str.replace(",", "", regex=False).str.replace(r"[^0-9.\-]", "", regex=True)
    cleaned = cleaned.mask(neg, "-" + cleaned.str.replace("-", "", regex=False))
    out = pd.to_numeric(cleaned, errors="coerce")
    return pd.Series(np.asarray(out, dtype="float64"), index=s.index)

def date_series(s):
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        res = pd.to_datetime(s, errors="coerce", dayfirst=True)
        miss = res.isna() & s.notna() & (s.astype(str).str.strip() != "")
        if miss.any():
            res[miss] = pd.to_datetime(s[miss], errors="coerce", dayfirst=False)
    return res

def make_unique(names):
    seen, out = {}, []
    for i, n in enumerate(names):
        n = re.sub(r"\s+", " ", str(n)).strip() or f"Column {i + 1}"
        if n in seen:
            seen[n] += 1
            n = f"{n} ({seen[n]})"
        else:
            seen[n] = 1
        out.append(n)
    return out

def detect_header_row(values, scan=15):
    head = values[:scan]
    counts = [sum(1 for c in r if str(c).strip()) for r in head]
    if not counts or max(counts) == 0:
        return 0
    best = max(counts)
    for i, r in enumerate(head):
        filled = [str(c).strip() for c in r if str(c).strip()]
        if len(filled) >= max(2, 0.6 * best):
            if sum(is_number_like(c) for c in filled) / len(filled) < 0.4:
                return i
    return counts.index(best)

def split_table(values):
    hdr = detect_header_row(values)
    preface = [r for r in values[:hdr] if any(str(c).strip() for c in r)]
    body = values[hdr + 1:]
    width = max([len(values[hdr])] + [len(r) for r in body]) if body else len(values[hdr])
    header = list(values[hdr]) + [""] * (width - len(values[hdr]))
    header = make_unique(header)
    body = [list(r) + [""] * (width - len(r)) for r in body]
    df = pd.DataFrame(body, columns=header).astype(str)
    df = df.apply(lambda c: c.str.strip())
    df = df.loc[(df != "").any(axis=1)]
    df = df.loc[:, (df != "").any(axis=0)]
    non_id = [c for c in df.columns if not ID_COL_RE.match(c.strip())]
    if non_id:
        df = df.loc[(df[non_id] != "").any(axis=1)]

    def first_text(row):
        for v in row:
            if v and not is_number_like(v):
                return v
        return ""

    is_total = df.apply(lambda r: bool(TOTAL_RE.match(first_text(r))), axis=1) if len(df) else pd.Series(dtype=bool)
    totals = df[is_total].reset_index(drop=True)
    df = df[~is_total].reset_index(drop=True)
    return df, preface, totals

def infer_table(df):
    typed, kinds = pd.DataFrame(index=df.index), {}
    for col in df.columns:
        raw = df[col].astype(str).str.strip()
        is_blank = blank_mask(raw)
        filled = raw[~is_blank]
        if filled.empty:
            continue
        sample = filled.head(300)
        if sample.map(is_number_like).mean() >= 0.8:
            if ID_COL_RE.match(col.strip()):
                typed[col], kinds[col] = raw, "id"
            elif CATEGORY_NUM_RE.match(col.strip()):
                typed[col], kinds[col] = raw.where(~is_blank, ""), "category"
            elif sample.str.contains("%").mean() >= 0.5:
                typed[col], kinds[col] = num_nan(raw), "percent"
            else:
                typed[col], kinds[col] = num_nan(raw), "numeric"
            continue
        if sample.str.contains(r"\d").mean() >= 0.9:
            parsed = date_series(raw.where(~is_blank))
            if parsed.notna().sum() / len(filled) >= 0.8:
                typed[col], kinds[col] = parsed, "date"
                continue
        typed[col] = raw.where(~is_blank, "")
        n = filled.nunique()
        kinds[col] = "category" if (n <= 40 and (n <= 0.7 * len(filled) or n <= 8)) else "text"
    return typed, kinds

def order_values(series):
    vals = sorted({str(v) for v in series if str(v).strip() != ""})
    low = [v.strip().lower() for v in vals]
    if vals and all(v in MONTH_ABBR or v in [m.lower() for m in MONTHS] for v in low):
        return sorted(vals, key=lambda v: MONTH_ABBR.index(v.strip().lower()[:3]))
    return vals

def style_fig(fig, height=390):
    fig.update_layout(height=height, margin=dict(l=10, r=10, t=55, b=10), legend_title_text="",
                      font=dict(size=12), title_font_size=15)
    return fig

@st.cache_data(ttl=300, show_spinner="Loading sheet tabs...")
def list_tabs(sheet_id):
    book = get_client().open_by_key(sheet_id)
    return [(ws.title, ws.id) for ws in book.worksheets()]

@st.cache_data(ttl=300, show_spinner="Loading live data from Google Sheet...")
def load_tab_values(sheet_id, tab_title):
    return get_client().open_by_key(sheet_id).worksheet(tab_title).get_all_values()

def show_access_error(e):
    email = ""
    try:
        email = st.secrets["gcp_service_account"]["client_email"]
    except Exception:
        pass
    st.error("Could not open this Google Sheet. Share it with service account: " + (f"**{email}**" if email else "email from secrets"))

@st.cache_data(ttl=300, show_spinner="Loading data from Google Sheets...")
def load_many_tabs(sheet_id, titles):
    book = get_client().open_by_key(sheet_id)
    out = {}
    titles = list(titles)
    for i in range(0, len(titles), 15):
        chunk = titles[i:i + 15]
        try:
            res = book.values_batch_get(["'" + t.replace("'", "''") + "'" for t in chunk])
            for t, vr in zip(chunk, res.get("valueRanges", [])):
                out[t] = vr.get("values", [])
        except Exception:
            for t in chunk:
                out[t] = book.worksheet(t).get_all_values()
    return out

def find_tab(titles, wanted, exclude_re=None):
    nw = re.sub(r"[^a-z0-9]", "", str(wanted).lower())
    pool = [t for t in titles if not (exclude_re and exclude_re.search(t))]
    for t in pool:
        if re.sub(r"[^a-z0-9]", "", str(t).lower()) == nw:
            return t
    return None

SKIP_TAB_RE = re.compile(r"summary|dashboard|master|total|index|instruction|readme|config|template", re.I)

# -----------------------------------------------------------------------------
# 7. UPDATED & DEDICATED FABRICATOR REPORT SHEET HANDLER
# -----------------------------------------------------------------------------
def render_fabricator_sheet(sheet_name, cfg):
    sid = cfg["id"]
    try:
        titles = [t for t, _ in list_tabs(sid)]
        sum_defaults = [t for t in (find_tab(titles, w) for w in cfg.get("summary_tabs", [])) if t]
        fab_tabs = [t for t in titles if t not in sum_defaults and not SKIP_TAB_RE.search(t)]
        if not fab_tabs:
            fab_tabs = [t for t in titles if not SKIP_TAB_RE.search(t)]
        values = load_many_tabs(sid, tuple(fab_tabs))
    except Exception as e:
        show_access_error(e)
        st.stop()

    frames = []
    for tab_name in fab_tabs:
        v = values.get(tab_name) or []
        if not v or not any(str(c).strip() for row in v for c in row):
            continue
        df, _preface, _totals = split_table(v)
        if df.empty:
            continue
        df.columns = [str(c).strip() or f"Column {i+1}" for i, c in enumerate(df.columns)]
        df = df.loc[:, ~pd.Index(df.columns).duplicated()]
        df["Fabricator_Name"] = tab_name
        frames.append(df)

    if not frames:
        st.warning("Is spreadsheet mein usable fabricator data nahi mila.")
        st.stop()

    df_raw = pd.concat(frames, ignore_index=True, sort=False).fillna("").astype(str)
    df_all, _kinds = infer_table(df_raw)
    
    # Auto-detect key columns
    fab_col = "Fabricator_Name"
    qty_col = next((c for c in df_all.columns if re.search(r"qty|quantity|pcs|pieces", c, re.I)), None)
    month_col = next((c for c in df_all.columns if re.search(r"month", c, re.I)), None)
    cat_col = next((c for c in df_all.columns if re.search(r"category", c, re.I)), None)
    status_col = next((c for c in df_all.columns if re.search(r"status", c, re.I)), None)

    # Sidebar Filters
    with st.sidebar:
        st.markdown("### 🔎 Fabricator Filters")
        
        all_fabs = sorted(df_all[fab_col].unique())
        sel_fabs = st.multiselect("Fabricator Name", options=all_fabs, default=[])
        
        sel_months = []
        if month_col:
            all_months = order_values(df_all[month_col])
            sel_months = st.multiselect("Month", options=all_months, default=[])
            
        sel_cats = []
        if cat_col:
            all_cats = sorted([x for x in df_all[cat_col].unique() if x])
            sel_cats = st.multiselect("Category", options=all_cats, default=[])

        sel_status = []
        if status_col:
            all_status = sorted([x for x in df_all[status_col].unique() if x])
            sel_status = st.multiselect("Status", options=all_status, default=[])

        if st.button("🔄 Refresh Data", key="fab_refresh"):
            st.cache_data.clear()
            st.rerun()

    # Filter Application
    filtered_df = df_all.copy()
    if sel_fabs:
        filtered_df = filtered_df[filtered_df[fab_col].isin(sel_fabs)]
    if sel_months and month_col:
        filtered_df = filtered_df[filtered_df[month_col].isin(sel_months)]
    if sel_cats and cat_col:
        filtered_df = filtered_df[filtered_df[cat_col].isin(sel_cats)]
    if sel_status and status_col:
        filtered_df = filtered_df[filtered_df[status_col].isin(sel_status)]

    st.markdown(
        f"""<div class="dashboard-hero">
        <h2>🧵 {sheet_name}</h2>
        <p>Clean Vendor Analytics & Executive Dashboard · {len(filtered_df):,} Rows Analyzed</p>
        </div>""",
        unsafe_allow_html=True
    )

    t1, t2 = st.tabs(["📊 Executive Clean Dashboard", "🗃️ Combined Raw Data"])

    with t1:
        # Metrics
        total_orders = len(filtered_df)
        active_fabs = filtered_df[fab_col].nunique()
        total_pcs = num(filtered_df[qty_col]).sum() if qty_col else 0

        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Active Fabricators", f"{active_fabs:,}")
        m2.metric("Total Records / Orders", f"{total_orders:,}")
        m3.metric("Total Quantity (Pcs)", fmt(total_pcs))
        if cat_col:
            m4.metric("Categories Covered", f"{filtered_df[cat_col].nunique():,}")
        else:
            m4.metric("Status", "Data Active")

        st.markdown("---")

        # Visual Analytics Charts
        c1, c2 = st.columns(2)
        with c1:
            if qty_col:
                fab_qty = filtered_df.groupby(fab_col)[qty_col].apply(lambda s: num(s).sum()).reset_index()
                fig_pie = px.pie(fab_qty, names=fab_col, values=qty_col, title="Fabricator Volume Share (Pcs)", hole=0.45)
                st.plotly_chart(style_fig(fig_pie, 380), use_container_width=True)
            else:
                fab_count = filtered_df[fab_col].value_counts().reset_index()
                fab_count.columns = [fab_col, "Count"]
                fig_pie = px.pie(fab_count, names=fab_col, values="Count", title="Fabricator Order Distribution", hole=0.45)
                st.plotly_chart(style_fig(fig_pie, 380), use_container_width=True)

        with c2:
            if month_col:
                if qty_col:
                    m_qty = filtered_df.groupby(month_col)[qty_col].apply(lambda s: num(s).sum()).reset_index()
                    fig_bar = px.bar(m_qty, x=month_col, y=qty_col, title="Monthly Order Volume (Pcs)", text_auto=".2s")
                else:
                    m_count = filtered_df[month_col].value_counts().reset_index()
                    m_count.columns = [month_col, "Count"]
                    fig_bar = px.bar(m_count, x=month_col, y="Count", title="Monthly Order Count", text_auto=True)
                st.plotly_chart(style_fig(fig_bar, 380), use_container_width=True)
            else:
                st.info("Month column detect nahi hua.")

        st.markdown("---")
        st.subheader("📋 Fabricator Performance Summary Table")
        
        if qty_col:
            summary_group = filtered_df.groupby(fab_col).agg(
                Total_Orders=(fab_col, "count"),
                Total_Pcs=(qty_col, lambda s: int(num(s).sum()))
            ).reset_index().sort_values("Total_Pcs", ascending=False)
        else:
            summary_group = filtered_df[fab_col].value_counts().reset_index()
            summary_group.columns = [fab_col, "Total_Orders"]

        st.dataframe(summary_group, use_container_width=True, hide_index=True)

    with t2:
        st.dataframe(filtered_df, use_container_width=True, hide_index=True)

def render_simple_overview_sheet(sheet_name, cfg):
    sid = cfg["id"]
    try:
        tabs = list_tabs(sid)
    except Exception as e:
        show_access_error(e)
        st.stop()

    titles = [t for t, _ in tabs]
    preferred = cfg.get("data_tabs", [])
    tab = next((find_tab(titles, name) for name in preferred if find_tab(titles, name)), None)
    if tab is None:
        tab = titles[0] if titles else None

    if tab is None:
        st.error("Worksheet nahi mili.")
        st.stop()

    with st.sidebar:
        st.caption(f"Data tab: {tab}")
        if st.button("🔄 Refresh data", key=f"{sid}_overview_refresh"):
            st.cache_data.clear()
            st.rerun()

    try:
        values = load_tab_values(sid, tab)
    except Exception as e:
        show_access_error(e)
        st.stop()

    if not values:
        st.warning(f"'{tab}' tab empty hai.")
        st.stop()

    df_raw, _preface, _totals = split_table(values)
    st.markdown(f"### 📊 {sheet_name}")
    st.dataframe(df_raw, use_container_width=True, hide_index=True)

# -----------------------------------------------------------------------------
# 8. MAIN APPLICATION ROUTER
# -----------------------------------------------------------------------------
def get_registry():
    return dict(SHEET_REGISTRY)

def render_tracker(sheet_name, sheet_id):
    raw, totals_row, tab_name, first_data_row = load_sheet(sheet_id)
    d_all = prepare(raw)

    with st.sidebar:
        st.markdown("### 🔎 Filters")
        months_present = [m for m in MONTHS if m in set(d_all["month_client"].dropna())]
        month_options = ["All"] + [x for x in months_present if x != "All"]
        designer_options = ["All"] + sorted(x for x in d_all["designer"].unique() if x and x != "All")
        client_options = ["All"] + sorted(x for x in d_all["client"].unique() if x and x != "All")
        fab_options = ["All"] + sorted(x for x in d_all["fabricator"].unique() if x and x != "All")

        sel_months = st.multiselect("Order month (Col B)", month_options, default=["All"], key=f"{sheet_id}_month")
        sel_designers = st.multiselect("Designer", designer_options, default=["All"], key=f"{sheet_id}_designer")
        sel_clients = st.multiselect("Client", client_options, default=["All"], key=f"{sheet_id}_client")
        sel_fabs = st.multiselect("Fabricator", fab_options, default=["All"], key=f"{sheet_id}_fabricator")
        if st.button("🔄 Refresh data", key=f"{sheet_id}_refresh"):
            st.cache_data.clear()
            st.rerun()

    d = d_all.copy()
    if "All" not in sel_months:
        d = d[d["month_client"].isin(sel_months)]
    if "All" not in sel_designers:
        d = d[d["designer"].isin(sel_designers)]
    if "All" not in sel_clients:
        d = d[d["client"].isin(sel_clients)]
    if "All" not in sel_fabs:
        d = d[d["fabricator"].isin(sel_fabs)]

    st.markdown(
        f"""<div class="dashboard-hero"><h2>📊 {html.escape(sheet_name)} · Executive Dashboard 2026-27</h2>
        <p>Tab: <b>{html.escape(tab_name)}</b> · {len(d):,} rows (data row {first_data_row} se)</p></div>""",
        unsafe_allow_html=True)

    if d.empty:
        st.warning("Is filter me koi data nahi mila.")
        st.stop()

    t1, t2, t3, t4 = st.tabs(["Overview", "Designer", "Client", "Production"])
    with t1:
        overview(d)
    with t2:
        designer_dashboard(d)
    with t3:
        client_dashboard(d)
    with t4:
        production_dashboard(d)

    with st.expander("✅ Data check (sheet totals se match)"):
        data_check(totals_row, d_all)

def main():
    registry = get_registry()
    with st.sidebar:
        st.markdown("### 📚 Select Dashboard")
        selected = st.selectbox("Google Sheet", list(registry.keys()), key="sheet_choice")
        cfg = registry[selected]

    kind = cfg.get("type", "tracker")
    if kind == "tracker":
        render_tracker(selected, cfg["id"])
    elif kind == "overview":
        render_simple_overview_sheet(selected, cfg)
    elif kind == "overview_fabricators":
        render_fabricator_sheet(selected, cfg)

if __name__ == "__main__":
    main()
