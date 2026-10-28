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
#   type "tracker" -> original order-tracking dashboard (Designer / Client / Production / Fabric)
#   type "orders" -> order analytics (data tab + DASHBOARD tab), filters: month/designer/status/fabricator...
#   type "fabricators" -> har fabricator ka alag tab combine hota hai + MONTHWISE SUMMARY tab
#   type "summary" -> generic auto-analysis dashboard (kisi bhi naye sheet ke liye)
#   gid            -> sheet URL ke "gid=" wala number; wahi tab default khulega
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
    """Sheet ki rows (list of lists) se raw DataFrame banata hai.

    FIX 1: pehli asli order row (jahan column A / S.NO. number ho) dynamically dhundhi jati hai.
           Pehle header_i = 4 hard-coded tha, jisse pehla order (row 5) skip ho jata tha.
    FIX 2: neeche ki blank rows hata di jati hain, taaki On-Time % jaise ratios na bigdein.
    """
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
    totals_row = values[1] if len(values) > 1 else []   # sheet ki row 2 (totals) - data check ke liye
    return df_raw, totals_row, ws.title, first_data_row

# -----------------------------------------------------------------------------
# 4. DATA PREPARATION (DIRECT COLUMN MAPPING - PRESERVES ALL ROWS)
# -----------------------------------------------------------------------------
def prepare(raw):
    d = pd.DataFrame()

    def get_raw_col(col_letter):
        idx = col_to_idx(col_letter)
        if idx < len(raw.columns):
            return raw[idx]
        return pd.Series([""] * len(raw))

    d["date_client"] = date_col(get_raw_col("B"))                   # Col B (ORDER DATE)
    d["date_prod"] = date_col(get_raw_col("AC"))                    # Col AC (PROD DATE)
    d["designer"] = get_raw_col("C").astype(str).str.strip()        # Col C (DESIGNER)
    d["type"] = get_raw_col("D").astype(str).str.strip()            # Col D (ORDER TYPE)
    d["category"] = get_raw_col("F").astype(str).str.strip()        # Col F (CATEGORY)
    d["qty"] = num(get_raw_col("J"))                                # Col J (NO. OF PC'S)
    d["client"] = get_raw_col("N").astype(str).str.strip()          # Col N (CLIENT NAME)
    d["fabricator"] = get_raw_col("AA").astype(str).str.strip()     # Col AA (FABRICATOR)
    d["delay"] = clean_delay_days(get_raw_col("AH"))                # Col AH (DELAY DAYS)
    d["production"] = num(get_raw_col("AS"))                       # Col AS (IN PRODUCTION)
    d["received"] = num(get_raw_col("AT"))                         # Col AT (RECEIVED)
    d["pending"] = num(get_raw_col("AU"))                          # Col AU (PENDING)
    d["status"] = get_raw_col("AX").astype(str).str.strip()         # Col AX (STATUS)

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
# 5. DASHBOARD VIEWS & TABLES
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
    total_qty = x["qty"].sum()              # DIRECT SUM OF COL J
    in_prod = x["production"].sum()         # DIRECT SUM OF COL AS
    rec_done = x["received"].sum()          # DIRECT SUM OF COL AT
    pending_qty = x["pending"].sum()        # DIRECT SUM OF COL AU
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

    st.markdown("---")
    st.subheader("📦 Monthly Category Order Breakdown (Col B & Col F Matrix)")
    m_cat_matrix = []
    for m in MONTHS:
        sub_m = x[x["month_client"] == m]
        r_data = {"MONTH": m}
        for cat in CATEGORIES_LIST:
            r_data[cat] = int(sub_m[sub_m["category_clean"] == cat]["qty"].sum())
        r_data["TOTAL"] = sum(r_data[c] for c in CATEGORIES_LIST)
        m_cat_matrix.append(r_data)

    m_cat_df = pd.DataFrame(m_cat_matrix)
    m_cat_tot = {"MONTH": "TOTAL"}
    for cat in CATEGORIES_LIST:
        m_cat_tot[cat] = m_cat_df[cat].sum()
    m_cat_tot["TOTAL"] = m_cat_df["TOTAL"].sum()
    m_cat_df_display = pd.concat([m_cat_df, pd.DataFrame([m_cat_tot])], ignore_index=True)

    col_mc1, col_mc2 = st.columns([1.2, 1])
    with col_mc1:
        st.dataframe(m_cat_df_display, use_container_width=True, hide_index=True)
    with col_mc2:
        fig_stack = px.bar(m_cat_df, x="MONTH", y=CATEGORIES_LIST, title="CATEGORY DISTRIBUTION BY MONTH", barmode="stack")
        st.plotly_chart(fig_stack, use_container_width=True)

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

    st.markdown("---")
    st.subheader("🧵 Category-Wise Production Performance Breakdown")
    cat_prod_summary = []
    for cat in CATEGORIES_LIST:
        sub_c = d[d["category_clean"] == cat]
        cat_prod_summary.append({
            "CATEGORY": cat,
            "INPRODUCTION (AS)": int(sub_c["production"].sum()),
            "RECIEVED (AT)": int(sub_c["received"].sum()),
            "PENDING (AU)": int(sub_c["pending"].sum())
        })
    cp_df = pd.DataFrame(cat_prod_summary)

    cp_tot = pd.DataFrame([{
        "CATEGORY": "TOTAL",
        "INPRODUCTION (AS)": cp_df["INPRODUCTION (AS)"].sum(),
        "RECIEVED (AT)": cp_df["RECIEVED (AT)"].sum(),
        "PENDING (AU)": cp_df["PENDING (AU)"].sum()
    }])
    cp_df_display = pd.concat([cp_df, cp_tot], ignore_index=True)

    col_p1, col_p2 = st.columns([1.2, 1])
    with col_p1:
        st.dataframe(cp_df_display, use_container_width=True, hide_index=True)
    with col_p2:
        fig_cp = px.bar(cp_df, x="CATEGORY", y=["INPRODUCTION (AS)", "RECIEVED (AT)", "PENDING (AU)"], barmode="group", title="CATEGORY PRODUCTION PERFORMANCE")
        st.plotly_chart(fig_cp, use_container_width=True)

    st.markdown("---")
    st.subheader("📈 Monthly Production Fulfillment Trend (by Col AC)")
    m_ful_summary = []
    for m in MONTHS:
        sub_m = d[d["month_prod"] == m]
        m_ful_summary.append({
            "MONTH": m,
            "ORDERS": len(sub_m[sub_m.production > 0]),
            "IN PRODUCTION (AS)": int(sub_m["production"].sum()),
            "RECIEVED (AT)": int(sub_m["received"].sum())
        })
    mf_df = pd.DataFrame(m_ful_summary)

    mf_tot = pd.DataFrame([{
        "MONTH": "TOTAL",
        "ORDERS": mf_df["ORDERS"].sum(),
        "IN PRODUCTION (AS)": mf_df["IN PRODUCTION (AS)"].sum(),
        "RECIEVED (AT)": mf_df["RECIEVED (AT)"].sum()
    }])
    mf_df_display = pd.concat([mf_df, mf_tot], ignore_index=True)

    col_m1, col_m2 = st.columns([1, 1.2])
    with col_m1:
        st.dataframe(mf_df_display, use_container_width=True, hide_index=True)
    with col_m2:
        st.plotly_chart(px.line(mf_df, x="MONTH", y=["IN PRODUCTION (AS)", "RECIEVED (AT)"], markers=True, title="MONTHLY FULFILLMENT TREND ANALYSIS (Column AC)"), use_container_width=True)

    st.markdown("---")
    st.subheader("🚨 Fabricator Wise Pending Load & Overdue Matrix")
    fab_summary = d[d["fabricator"].ne("")].groupby("fabricator", as_index=False)["pending"].sum().sort_values("pending", ascending=False)
    fab_summary.columns = ["Fabricator Name", "Pending Pcs"]

    f_c1, f_c2 = st.columns([1, 1])
    with f_c1:
        st.dataframe(fab_summary, use_container_width=True, hide_index=True)
    with f_c2:
        fig_fab = px.pie(fab_summary.head(10), names="Fabricator Name", values="Pending Pcs", title="FABRICATOR PENDING PCS SHARE", hole=0.4)
        st.plotly_chart(fig_fab, use_container_width=True)

# -----------------------------------------------------------------------------
# NOTE: Aapka paste kiya hua code fabric_dashboard() ke beech me kat gaya tha.
# Neeche ka fabric_dashboard() aur main() hissa maine naye sire se likha hai
# (aapke mapped columns use karke). Agar aapka original alag tha, to apna
# fabric_dashboard() / filters wala hissa yahan wapas paste kar sakte ho;
# upar ke saare fixes (load_sheet / build_raw) waise hi kaam karenge.
# -----------------------------------------------------------------------------

def fabric_dashboard(d):
    st.subheader("🧵 Fabric & Vendor Tracking")
    f = d[d["fabricator"].ne("")]
    if f.empty:
        st.info("Selected filters ke liye fabricator data nahi hai."); return

    overdue = f[f["delay"] > 0]
    avg_overdue = overdue["delay"].mean() if len(overdue) > 0 else 0.0
    metrics([
        ("Fabricators", f"{f['fabricator'].nunique():,}"),
        ("In Production PCS", fmt(f["production"].sum())),
        ("Received PCS", fmt(f["received"].sum())),
        ("Pending PCS", fmt(f["pending"].sum())),
        ("Avg Overdue Days", f"{avg_overdue:.1f} Days"),
    ])

    summary = f.groupby("fabricator", as_index=False).agg(**{
        "Orders": ("qty", "size"),
        "Order Qty (J)": ("qty", "sum"),
        "In Production (AS)": ("production", "sum"),
        "Received (AT)": ("received", "sum"),
        "Pending (AU)": ("pending", "sum"),
    })
    od = overdue.groupby("fabricator")["delay"].mean()
    summary["Avg Overdue Days"] = summary["fabricator"].map(od).fillna(0).round(1)
    summary = summary.rename(columns={"fabricator": "Fabricator"}).sort_values("Pending (AU)", ascending=False)

    st.markdown("---")
    c1, c2 = st.columns([1.3, 1])
    with c1:
        st.dataframe(summary, use_container_width=True, hide_index=True)
    with c2:
        top = summary.head(15)
        st.plotly_chart(px.bar(top, x="Fabricator", y=["Received (AT)", "Pending (AU)"], barmode="stack",
                               title="FABRICATOR-WISE RECEIVED vs PENDING (TOP 15)"), use_container_width=True)

# -----------------------------------------------------------------------------
# 6. DATA CHECK (sheet ke row-2 totals se dashboard ka match)
# -----------------------------------------------------------------------------
def data_check(totals_row, d_all):
    st.caption("Sheet ki row 2 ke totals se dashboard ke totals (bina filter) match hone chahiye. "
               "Diff 0 na ho to us column ka letter ya data check karo.")
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
# 7. SUMMARY-SHEET ENGINE  (auto-detects header / numbers / dates / categories)
#    Kisi bhi summary-type Google Sheet par chalta hai - column letters hard-code nahi hain.
# -----------------------------------------------------------------------------
PALETTE = ["#2563eb", "#059669", "#f59e0b", "#dc2626", "#7c3aed",
           "#0891b2", "#db2777", "#65a30d", "#ea580c", "#475569"]
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
    """Like num() but keeps blanks as NaN (so averages / missing-% stay correct)."""
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
    """Header row = pehli row jahan kaafi cells bhari hon aur zyada tar text ho."""
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
    """Raw sheet rows -> (data DataFrame of strings, rows above header, totals rows)."""
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
    if non_id:   # sirf S.No bhari hui (khali) rows hata do
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
    """Har column ka type pehchanta hai: numeric / percent / date / category / text / id."""
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


def default_agg(col, kinds):
    return "Average" if kinds.get(col) == "percent" else "Sum"


def group_agg(df, dim, measure, agg):
    if measure is None or agg == "Count":
        return df.groupby(dim).size().reset_index(name="Value")
    return df.groupby(dim)[measure].agg(AGGS[agg]).reset_index(name="Value")


def period_series(d, date_col, measure, agg, freq="M", split=None):
    d = d.dropna(subset=[date_col]).copy()
    if d.empty:
        return pd.DataFrame(columns=["Period", "Value"])
    d["Period"] = d[date_col].dt.to_period(freq).dt.start_time
    keys = ["Period"] + ([split] if split else [])
    if split:
        d[split] = d[split].replace("", "(blank)")
    if measure is None or agg == "Count":
        g = d.groupby(keys).size().reset_index(name="Value")
    else:
        g = d.groupby(keys)[measure].agg(AGGS[agg]).reset_index(name="Value")
    return g.sort_values(keys).reset_index(drop=True)


def fmt_val(x, kind="numeric"):
    if x is None or pd.isna(x):
        return "—"
    if kind == "percent":
        return f"{x:,.1f}%"
    if abs(x) >= 1000 or float(x).is_integer():
        return f"{x:,.0f}"
    return f"{x:,.2f}"


def top_n_with_others(g, n):
    g = g.sort_values("Value", ascending=False)
    if len(g) <= n:
        return g
    head = g.head(n).copy()
    first_col = g.columns[0]
    others = pd.DataFrame({first_col: ["Others"], "Value": [g["Value"].iloc[n:].sum()]})
    return pd.concat([head, others], ignore_index=True)


def style_fig(fig, height=390):
    fig.update_layout(height=height, margin=dict(l=10, r=10, t=55, b=10), legend_title_text="",
                      font=dict(size=12), title_font_size=15)
    return fig


def build_insights(df, kinds, dim, measure, date_col):
    items = []
    agg = default_agg(measure, kinds) if measure else "Count"
    kind = kinds.get(measure) if measure else "numeric"
    label = measure or "records"
    if dim:
        sub = df[df[dim] != ""]
        g = group_agg(sub, dim, measure, agg).sort_values("Value", ascending=False)
        total = g["Value"].sum() if len(g) else 0
        additive = agg in ("Sum", "Count") and total > 0
        if len(g) >= 1:
            top = g.iloc[0]
            line = f"🏆 <b>{html.escape(str(top[dim]))}</b> leads <i>{html.escape(dim)}</i> with {fmt_val(top['Value'], kind)} {html.escape(label)}"
            if additive:
                line += f" ({top['Value'] / total * 100:.1f}% of total)"
            items.append(line + ".")
        if len(g) >= 2:
            low = g.iloc[-1]
            items.append(f"📉 Lowest: <b>{html.escape(str(low[dim]))}</b> with {fmt_val(low['Value'], kind)}.")
        if len(g) >= 5 and additive:
            share = g["Value"].head(3).sum() / total * 100
            items.append(f"🎯 Top 3 {html.escape(dim)} contribute <b>{share:.1f}%</b> of {html.escape(label)}.")
    if date_col:
        ps = period_series(df, date_col, measure, agg, "M")
        if len(ps) >= 1:
            peak = ps.loc[ps["Value"].idxmax()]
            items.append(f"📅 Peak month: <b>{peak['Period']:%b %Y}</b> ({fmt_val(peak['Value'], kind)}).")
        if len(ps) >= 2:
            prev, last = ps["Value"].iloc[-2], ps["Value"].iloc[-1]
            if prev:
                items.append(f"📈 Latest month ({ps['Period'].iloc[-1]:%b %Y}) is <b>{(last - prev) / abs(prev) * 100:+.1f}%</b> vs previous month.")
    for c in [c for c, k in kinds.items() if k in ("numeric", "percent")]:
        miss = df[c].isna().mean() * 100 if len(df) else 0
        if miss > 20:
            items.append(f"⚠️ <b>{html.escape(c)}</b> has {miss:.0f}% empty cells in this view.")
            break
    return items


def render_insights(items):
    if items:
        cards = "".join(f'<div class="insight">{i}</div>' for i in items)
        st.markdown(f'<div class="insight-grid">{cards}</div>', unsafe_allow_html=True)


def measure_picker(container, label, options, key, index=0):
    opts = list(options) + ["(Record count)"]
    choice = container.selectbox(label, opts, index=min(index, len(opts) - 1), key=key)
    return None if choice == "(Record count)" else choice


def agg_picker(container, measure, kinds, key):
    if measure is None:
        container.selectbox("Aggregation", ["Count"], key=f"{key}_count", disabled=True)
        return "Count"
    names = list(AGGS)
    return container.selectbox("Aggregation", names, index=names.index(default_agg(measure, kinds)),
                               key=f"{key}_{measure}")


def summary_dashboard(df_all, kinds, totals_raw, preface, raw_values, ctx):
    key = ctx["key"]
    k = lambda s: f"{key}_{s}"
    numeric_cols = [c for c, t in kinds.items() if t in ("numeric", "percent")]
    cat_cols = [c for c, t in kinds.items() if t == "category"]
    text_cols = [c for c, t in kinds.items() if t == "text"]
    date_cols = [c for c, t in kinds.items() if t == "date"]
    dim_options = cat_cols or text_cols
    month_cols = [c for c in numeric_cols if MONTH_COL_RE.match(c.strip())]

    # ---------------- sidebar: column setup + filters ----------------
    with st.sidebar:
        with st.expander("⚙️ Column setup (optional)"):
            pm = measure_picker(st, "Main measure", numeric_cols, k("pm"))
            pd_sel = st.selectbox("Main dimension", dim_options, key=k("pdim")) if dim_options else None
            dc_sel = st.selectbox("Date column", ["(none)"] + date_cols, index=1 if date_cols else 0, key=k("dc"))
        date_col = None if dc_sel == "(none)" else dc_sel
        st.markdown("### 🔎 Filters")
        selections = {}
        for c in [c for c in cat_cols if (df_all[c] != "").any() and df_all[c].nunique() <= 30][:5]:
            selections[c] = st.multiselect(c, order_values(df_all[c]), key=k(f"f_{c}"))
        date_range = None
        if date_col and df_all[date_col].notna().any():
            lo, hi = df_all[date_col].min().date(), df_all[date_col].max().date()
            if lo < hi:
                date_range = st.date_input("Date range", value=(lo, hi), min_value=lo, max_value=hi, key=k("dr"))

    df = df_all.copy()
    for c, sel in selections.items():
        if sel:
            df = df[df[c].isin(sel)]
    if date_range and len(date_range) == 2:
        df = df[df[date_col].isna() | ((df[date_col].dt.date >= date_range[0]) & (df[date_col].dt.date <= date_range[1]))]

    chips = [f"Tab: {ctx['tab']}", f"{len(df):,} of {len(df_all):,} rows", f"{len(df_all.columns)} columns",
             f"{len(numeric_cols)} measures", f"{len(dim_options)} dimensions"]
    chips_html = "".join(f'<span class="chip">{html.escape(c)}</span>' for c in chips)
    st.markdown(f"""<div class="dashboard-hero"><h2>📋 {html.escape(ctx['sheet_name'])}</h2>
        <p>Complete analysis dashboard · auto-built from the Google Sheet</p>{chips_html}</div>""", unsafe_allow_html=True)

    if df.empty:
        st.warning("No rows match the selected filters.")
        st.stop()

    pm_idx = numeric_cols.index(pm) if pm in numeric_cols else len(numeric_cols)
    dim_idx = dim_options.index(pd_sel) if pd_sel in dim_options else 0

    t_ov, t_bd, t_tr, t_cp, t_pv, t_dt = st.tabs(
        ["📊 Overview", "🧩 Breakdown", "📈 Trends", "🔬 Compare", "🧮 Pivot", "🗃️ Data & Quality"])

    # ======================= OVERVIEW =======================
    with t_ov:
        agg_main = default_agg(pm, kinds) if pm else "Count"
        kpis = [("Records", f"{len(df):,}")]
        if pd_sel:
            kpis.append((f"Unique {pd_sel}", f"{df.loc[df[pd_sel] != '', pd_sel].nunique():,}"))
        shown = ([pm] if pm else []) + [c for c in numeric_cols if c != pm]
        for c in shown[:6]:
            a = default_agg(c, kinds)
            kpis.append((f"{'Total' if a == 'Sum' else 'Avg'} {c}", fmt_val(df[c].agg(AGGS[a]), kinds[c])))
        for i in range(0, len(kpis), 4):
            metrics(kpis[i:i + 4])

        st.markdown("#### 💡 Key insights")
        render_insights(build_insights(df, kinds, pd_sel, pm, date_col))

        c1, c2 = st.columns(2)
        if pd_sel:
            g = group_agg(df[df[pd_sel] != ""], pd_sel, pm, agg_main).sort_values("Value", ascending=False)
            with c1:
                top = g.head(10).sort_values("Value")
                fig = px.bar(top, x="Value", y=pd_sel, orientation="h", text_auto=".3s",
                             title=f"Top {len(top)} {pd_sel} by {pm or 'records'}")
                st.plotly_chart(style_fig(fig), use_container_width=True)
            with c2:
                if agg_main in ("Sum", "Count") and (g["Value"] > 0).any():
                    pie = top_n_with_others(g[g["Value"] > 0], 8)
                    fig = px.pie(pie, names=pd_sel, values="Value", hole=0.5, title=f"{pd_sel} share of {pm or 'records'}")
                    st.plotly_chart(style_fig(fig), use_container_width=True)
                else:
                    fig = px.box(df[df[pd_sel] != ""], y=pm, title=f"Distribution of {pm}")
                    st.plotly_chart(style_fig(fig), use_container_width=True)
        c3, c4 = st.columns(2)
        with c3:
            if date_col:
                ps = period_series(df, date_col, pm, agg_main, "M")
                if not ps.empty:
                    fig = px.area(ps, x="Period", y="Value", markers=True, title=f"Monthly trend · {pm or 'records'}")
                    st.plotly_chart(style_fig(fig), use_container_width=True)
            elif month_cols:
                tot = pd.DataFrame({"Month": month_cols, "Value": [df[c].sum() for c in month_cols]})
                st.plotly_chart(style_fig(px.bar(tot, x="Month", y="Value", text_auto=".3s", title="Month-wise total")),
                                use_container_width=True)
        with c4:
            plain = [c for c in numeric_cols if kinds[c] == "numeric" and c not in month_cols]
            if len(plain) >= 2:
                tot = pd.DataFrame({"Measure": plain, "Total": [df[c].sum() for c in plain]})
                st.plotly_chart(style_fig(px.bar(tot, x="Measure", y="Total", text_auto=".3s", title="Totals of all measures")),
                                use_container_width=True)

        if numeric_cols:
            st.markdown("#### Measure summary")
            rows = []
            for c in numeric_cols:
                s = df[c]
                rows.append({"Measure": c, "Total": s.sum() if kinds[c] == "numeric" else np.nan,
                             "Average": s.mean(), "Median": s.median(), "Min": s.min(), "Max": s.max(),
                             "Filled rows": int(s.notna().sum())})
            st.dataframe(pd.DataFrame(rows).round(2), use_container_width=True, hide_index=True)

    # ======================= BREAKDOWN =======================
    with t_bd:
        if not dim_options:
            st.info("No category/text column detected for a breakdown.")
        else:
            c1, c2, c3, c4 = st.columns([1.3, 1.3, 1, 1])
            dim = c1.selectbox("Group by", dim_options, index=dim_idx, key=k("bd_dim"))
            measure = measure_picker(c2, "Measure", numeric_cols, k("bd_m"), index=pm_idx)
            agg = agg_picker(c3, measure, kinds, k("bd_a"))
            topn = c4.slider("Show top", 3, 50, 15, key=k("bd_n"))
            c5, c6 = st.columns([1.3, 2])
            split_opts = ["(none)"] + [c for c in dim_options if c != dim]
            split = c5.selectbox("Split bars by (optional)", split_opts, key=k("bd_s"))
            by_value = c6.toggle("Sort by value (off = natural / month order)", True, key=k("bd_sort"))

            sub = df[df[dim] != ""]
            g = group_agg(sub, dim, measure, agg)
            if by_value:
                g = g.sort_values("Value", ascending=False)
            else:
                g = g.set_index(dim).reindex(order_values(sub[dim])).reset_index()
            additive = agg in ("Sum", "Count") and (g["Value"] >= 0).all() and g["Value"].sum() > 0
            kind = kinds.get(measure) if measure else "numeric"
            vlabel = f"{agg} of {measure}" if measure else "Records"
            table = g.copy()
            table.insert(0, "Rank", range(1, len(table) + 1))
            if additive:
                table["Share %"] = (table["Value"] / table["Value"].sum() * 100).round(1)
                table["Cumulative %"] = table["Share %"].cumsum().round(1)
            table = table.rename(columns={"Value": vlabel})

            left, right = st.columns([1, 1.25])
            with left:
                st.dataframe(table, use_container_width=True, hide_index=True, height=430)
            with right:
                top = g.head(topn)
                if split != "(none)":
                    keep = top[dim].tolist()
                    sg = df[df[dim].isin(keep) & (df[split] != "")]
                    sg = (sg.groupby([dim, split]).size().reset_index(name="Value") if measure is None or agg == "Count"
                          else sg.groupby([dim, split])[measure].agg(AGGS[agg]).reset_index(name="Value"))
                    fig = px.bar(sg, x=dim, y="Value", color=split, barmode="stack", title=f"{vlabel} by {dim}, split by {split}")
                    fig.update_xaxes(categoryorder="array", categoryarray=keep)
                else:
                    fig = px.bar(top, x=dim, y="Value", text_auto=".3s", title=f"{vlabel} by {dim} (top {len(top)})")
                    fig.update_yaxes(title=vlabel)
                st.plotly_chart(style_fig(fig, 430), use_container_width=True)

            if additive and by_value and len(g) >= 2:
                p1, p2 = st.columns(2)
                with p1:
                    t = g.head(topn)
                    cum = (t["Value"].cumsum() / g["Value"].sum() * 100)
                    fig = make_subplots(specs=[[{"secondary_y": True}]])
                    fig.add_trace(go.Bar(x=t[dim], y=t["Value"], name=vlabel, marker_color=PALETTE[0]), secondary_y=False)
                    fig.add_trace(go.Scatter(x=t[dim], y=cum, name="Cumulative %", mode="lines+markers",
                                             line=dict(color=PALETTE[2])), secondary_y=True)
                    fig.update_yaxes(range=[0, 105], title="Cumulative %", secondary_y=True)
                    fig.update_layout(title="Pareto (80/20) view")
                    st.plotly_chart(style_fig(fig), use_container_width=True)
                with p2:
                    tm = g[g["Value"] > 0].head(topn)
                    if not tm.empty:
                        fig = px.treemap(tm, path=[dim], values="Value", title=f"Treemap · {vlabel}")
                        st.plotly_chart(style_fig(fig), use_container_width=True)

    # ======================= TRENDS =======================
    with t_tr:
        if not date_col and len(month_cols) < 3:
            st.info("No date column (or month columns) detected. If your sheet has one, pick it under "
                    "**Column setup → Date column** in the sidebar.")
        if date_col:
            c1, c2, c3, c4 = st.columns([1, 1.4, 1.4, 0.8])
            period = c1.selectbox("Period", ["Daily", "Weekly", "Monthly", "Quarterly"], index=2, key=k("tr_p"))
            measure = measure_picker(c2, "Measure", numeric_cols, k("tr_m"), index=pm_idx)
            split = c3.selectbox("Split by", ["(none)"] + dim_options, key=k("tr_s"))
            cumulative = c4.toggle("Cumulative", key=k("tr_c"))
            agg = default_agg(measure, kinds) if measure else "Count"
            freq = {"Daily": "D", "Weekly": "W", "Monthly": "M", "Quarterly": "Q"}[period]
            g = period_series(df, date_col, measure, agg, freq, None if split == "(none)" else split)
            vlabel = f"{agg} of {measure}" if measure else "Records"
            if g.empty:
                st.info("No dated rows in the current selection.")
            else:
                if cumulative:
                    g["Value"] = g.groupby(split)["Value"].cumsum() if split != "(none)" else g["Value"].cumsum()
                if split != "(none)":
                    fig = (px.line(g, x="Period", y="Value", color=split, markers=True) if cumulative
                           else px.bar(g, x="Period", y="Value", color=split, barmode="stack"))
                else:
                    fig = px.bar(g, x="Period", y="Value", text_auto=".3s")
                    if len(g) >= 3 and not cumulative:
                        fig.add_trace(go.Scatter(x=g["Period"], y=g["Value"].rolling(3, min_periods=1).mean(),
                                                 name="3-period avg", mode="lines", line=dict(color=PALETTE[2], width=3)))
                fig.update_layout(title=f"{period} trend · {vlabel}")
                st.plotly_chart(style_fig(fig, 420), use_container_width=True)
                tbl = g.copy()
                if split == "(none)":
                    tbl["Change %"] = (tbl["Value"].pct_change() * 100).round(1)
                tbl["Period"] = tbl["Period"].dt.strftime("%d %b %Y")
                st.dataframe(tbl.rename(columns={"Value": vlabel}), use_container_width=True, hide_index=True)
        if len(month_cols) >= 3:
            st.markdown("#### Month-wise profile (from month columns)")
            tot = pd.DataFrame({"Month": month_cols, "Value": [df[c].sum() for c in month_cols]})
            a, b = st.columns(2)
            a.plotly_chart(style_fig(px.line(tot, x="Month", y="Value", markers=True, title="Total by month")), use_container_width=True)
            if dim_options:
                dim = dim_options[dim_idx]
                wide = df[df[dim] != ""].groupby(dim)[month_cols].sum()
                keep = wide.sum(axis=1).sort_values(ascending=False).head(8).index
                long = wide.loc[keep].reset_index().melt(id_vars=dim, var_name="Month", value_name="Value")
                b.plotly_chart(style_fig(px.line(long, x="Month", y="Value", color=dim, markers=True,
                                                 title=f"Top 8 {dim} by month")), use_container_width=True)

    # ======================= COMPARE =======================
    with t_cp:
        if len(numeric_cols) >= 2:
            c1, c2, c3, c4 = st.columns(4)
            x = c1.selectbox("X axis", numeric_cols, key=k("cp_x"))
            y = c2.selectbox("Y axis", numeric_cols, index=1, key=k("cp_y"))
            color = c3.selectbox("Colour by", ["(none)"] + dim_options, key=k("cp_c"))
            size = c4.selectbox("Bubble size", ["(none)"] + numeric_cols, key=k("cp_z"))
            sc = df.dropna(subset=[x, y]).copy()
            if size != "(none)":
                sc = sc.dropna(subset=[size])
                sc[size] = sc[size].abs()
            hover = dim_options[:1] if dim_options else None
            fig = px.scatter(sc, x=x, y=y, color=None if color == "(none)" else color,
                             size=None if size == "(none)" else size, hover_name=hover[0] if hover else None,
                             title=f"{y} vs {x}")
            st.plotly_chart(style_fig(fig, 430), use_container_width=True)
            corr = df[numeric_cols].corr().dropna(how="all").dropna(how="all", axis=1)
            if len(corr) >= 2:
                fig = px.imshow(corr, text_auto=".2f", zmin=-1, zmax=1, color_continuous_scale="RdBu_r",
                                aspect="auto", title="Correlation between measures")
                st.plotly_chart(style_fig(fig, 430), use_container_width=True)
        if numeric_cols:
            st.markdown("#### Distribution")
            d1, d2 = st.columns(2)
            m = d1.selectbox("Measure", numeric_cols, index=min(pm_idx, len(numeric_cols) - 1), key=k("ds_m"))
            grp = d2.selectbox("Compare across", ["(none)"] + dim_options, key=k("ds_g"))
            a, b = st.columns(2)
            a.plotly_chart(style_fig(px.histogram(df.dropna(subset=[m]), x=m, nbins=25, title=f"Histogram · {m}")), use_container_width=True)
            if grp != "(none)":
                keep = df[grp][df[grp] != ""].value_counts().head(12).index
                b.plotly_chart(style_fig(px.box(df[df[grp].isin(keep)], x=grp, y=m, points="outliers", title=f"{m} by {grp}")),
                               use_container_width=True)
        elif len(numeric_cols) < 2:
            st.info("Not enough numeric columns for comparison charts.")

    # ======================= PIVOT =======================
    with t_pv:
        if not dim_options:
            st.info("No category column detected for a pivot table.")
        else:
            c1, c2, c3, c4 = st.columns(4)
            rows_dim = c1.selectbox("Rows", dim_options, index=dim_idx, key=k("pv_r"))
            col_opts = ["(none)"] + [c for c in dim_options if c != rows_dim]
            cols_dim = c2.selectbox("Columns", col_opts, key=k("pv_c"))
            measure = measure_picker(c3, "Measure", numeric_cols, k("pv_m"), index=pm_idx)
            agg = agg_picker(c4, measure, kinds, k("pv_a"))
            sub = df[df[rows_dim] != ""]
            if cols_dim != "(none)":
                sub = sub[sub[cols_dim] != ""]
            if cols_dim != "(none)" and sub[cols_dim].nunique() > 40:
                st.warning("Too many distinct values in the Columns field - pick a smaller one.")
            else:
                if measure is None or agg == "Count":
                    pt = (pd.crosstab(sub[rows_dim], sub[cols_dim], margins=True, margins_name="TOTAL")
                          if cols_dim != "(none)" else sub.groupby(rows_dim).size().to_frame("Records"))
                else:
                    pt = pd.pivot_table(sub, index=rows_dim, columns=None if cols_dim == "(none)" else cols_dim,
                                        values=measure, aggfunc=AGGS[agg], fill_value=0,
                                        margins=cols_dim != "(none)", margins_name="TOTAL")
                pt.columns = [str(c) for c in pt.columns]
                if cols_dim != "(none)":
                    order = order_values(sub[cols_dim])
                    pt = pt[[c for c in order if c in pt.columns] + ["TOTAL"]]
                st.dataframe(pt.reset_index(), use_container_width=True, hide_index=True)
                core = pt.drop(index="TOTAL", errors="ignore").drop(columns="TOTAL", errors="ignore")
                if core.shape[0] >= 1 and core.shape[1] >= 1 and cols_dim != "(none)":
                    fig = px.imshow(core, text_auto=".2s", aspect="auto", color_continuous_scale="Blues",
                                    title=f"Heatmap · {rows_dim} × {cols_dim}")
                    st.plotly_chart(style_fig(fig, 460), use_container_width=True)

    # ======================= DATA & QUALITY =======================
    with t_dt:
        st.markdown("#### Filtered data")
        st.dataframe(df, use_container_width=True, hide_index=True, height=380)
        st.download_button("⬇️ Download filtered data (CSV)", df.to_csv(index=False).encode("utf-8"),
                           file_name=f"{ctx['sheet_name']}_{ctx['tab']}.csv".replace(" ", "_"), mime="text/csv")

        st.markdown("#### Column profile")
        prof = []
        for c in df_all.columns:
            s = df_all[c]
            empty = s.isna() | (s.astype(str) == "") if kinds[c] != "numeric" and kinds[c] != "percent" else s.isna()
            prof.append({"Column": c, "Detected as": kinds[c], "Filled": int((~empty).sum()),
                         "Missing %": round(empty.mean() * 100, 1), "Unique": int(s[~empty].nunique()),
                         "Example": str(s[~empty].iloc[0])[:40] if (~empty).any() else ""})
        st.dataframe(pd.DataFrame(prof), use_container_width=True, hide_index=True)

        sum_cols = [c for c in numeric_cols if kinds[c] == "numeric" and c in totals_raw.columns]
        if len(totals_raw) and sum_cols:
            st.markdown("#### ✅ Sheet totals row vs dashboard")
            st.caption("The sheet's own 'Total' row is compared with the sum of the rows used here (no filters). Diff should be 0.")
            trow = totals_raw.iloc[0]
            rows = []
            for c in sum_cols:
                sheet_val = num_nan(pd.Series([trow[c]])).iloc[0]
                mine = df_all[c].sum()
                rows.append({"Column": c, "Sheet total": sheet_val, "Dashboard": mine,
                             "Diff": (mine - sheet_val) if pd.notna(sheet_val) else np.nan})
            st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

        if preface:
            with st.expander("Rows above the header (title / notes)"):
                st.dataframe(pd.DataFrame(preface).astype(str), use_container_width=True, hide_index=True)
        with st.expander("Raw sheet exactly as in Google Sheets (for troubleshooting)"):
            width = max(len(r) for r in raw_values)
            st.dataframe(pd.DataFrame([list(r) + [""] * (width - len(r)) for r in raw_values]).astype(str),
                         use_container_width=True, hide_index=True)


# -----------------------------------------------------------------------------
# 8. GOOGLE ACCESS HELPERS FOR SUMMARY SHEETS
# -----------------------------------------------------------------------------
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
    st.error("Could not open this Google Sheet. Share it (Viewer access is enough) with the service account"
             + (f": **{email}**" if email else " email from your Streamlit secrets.") + " and click refresh.")
    st.caption(f"Technical detail: {type(e).__name__}: {e}")


# -----------------------------------------------------------------------------
# 10. ORDER-ANALYTICS ENGINE  (Summary Sheet 2026-27  &  Fabricator Report Sheet)
#     Columns header-name se pehchane jaate hain (Month / Designer / Status / Fabricator ...).
#     Galat ho to sidebar "Map columns" se badal sakte hain.
# -----------------------------------------------------------------------------
STD = {"date": "Order Date", "month": "Month", "designer": "Designer", "status": "Status",
       "fabricator": "Fabricator", "category": "Category", "client": "Client", "type": "Order Type",
       "qty": "Order Qty", "production": "In Production", "received": "Received",
       "pending": "Pending", "delay": "Delay Days"}
TEXT_ROLES = ["designer", "status", "fabricator", "category", "client", "type"]
NUM_ROLES = ["qty", "production", "received", "pending", "delay"]
ROLE_LABELS = {"date": "Order date", "month": "Month (if no date)", "designer": "Designer", "status": "Status",
               "fabricator": "Fabricator", "category": "Category", "client": "Client", "type": "Order type",
               "qty": "Order qty (pcs)", "production": "In production (pcs)", "received": "Received (pcs)",
               "pending": "Pending (pcs)", "delay": "Delay days"}
ROLE_RULES = {
    "date": [r"order\s*date", r"^date$", r"\bdate\b"],
    "month": [r"^month$", r"\bmonth\b"],
    "designer": [r"designer"],
    "status": [r"status"],
    "fabricator": [r"fabricator", r"vendor", r"karigar", r"supplier"],
    "category": [r"category"],
    "client": [r"client", r"customer", r"buyer"],
    "type": [r"order\s*type", r"^type$", r"\btype\b"],
    "qty": [r"no\.?\s*of\s*pc", r"\bqty\b", r"quantity", r"\bpcs\b", r"pieces"],
    "production": [r"in\s*production", r"production"],
    "received": [r"receiv"],
    "pending": [r"pending", r"balance"],
    "delay": [r"delay", r"overdue\s*days"],
}
ROLE_KINDS = {r: {"category", "text"} for r in TEXT_ROLES}
ROLE_KINDS.update({r: {"numeric", "percent"} for r in NUM_ROLES})
ROLE_KINDS.update({"date": {"date"}, "month": {"category", "text", "date"}})
NEG_DATE = r"prod|deliver|receiv|dispatch|due|ship"
CAL_MONTHS = ["january", "february", "march", "april", "may", "june", "july", "august", "september",
              "october", "november", "december"]
DASH_RE = re.compile(r"dashboard", re.I)
SKIP_TAB_RE = re.compile(r"summary|dashboard|master|total|index|instruction|readme|config|template", re.I)


def norm_name(s):
    return re.sub(r"[^a-z0-9]", "", str(s).lower())


def find_tab(titles, wanted, exclude_re=None):
    nw = norm_name(wanted)
    pool = [t for t in titles if not (exclude_re and exclude_re.search(t))]
    for t in pool:
        if norm_name(t) == nw:
            return t
    for t in pool:
        if nw and nw in norm_name(t):
            return t
    return None


def month_name_of(x):
    t = str(x).strip().lower()
    if re.fullmatch(r"\d{1,2}", t) and 1 <= int(t) <= 12:
        return CAL_MONTHS[int(t) - 1].capitalize()
    t = t[:3]
    return MONTHS[MONTH_ABBR.index(t)] if t in MONTH_ABBR else ""


def month_idx(m):
    return MONTHS.index(m) if m in MONTHS else 99


# ---------------- loading many tabs in ONE api call ----------------
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


# ---------------- "DASHBOARD" / "MONTHWISE SUMMARY" tab -> tables + charts ----------------
def extract_blocks(values):
    """Ek tab me jitni bhi tables hain (blank row/column se alag) unhe alag-alag nikalta hai."""
    if not values:
        return []
    w = max(len(r) for r in values)
    grid = [[str(c).strip() for c in r] + [""] * (w - len(r)) for r in values]
    n = len(grid)
    row_has = [any(r) for r in grid]
    regions, r = [], 0
    while r < n:
        if not row_has[r]:
            r += 1
            continue
        r0 = r
        while r < n and row_has[r]:
            r += 1
        band = grid[r0:r]
        col_has = [any(row[j] for row in band) for j in range(w)]
        j = 0
        while j < w:
            if not col_has[j]:
                j += 1
                continue
            c0 = j
            while j < w and col_has[j]:
                j += 1
            regions.append([row[c0:j] for row in band])

    blocks, pending_title = [], ""
    for reg in regions:
        rows = reg
        title = [pending_title] if pending_title else []
        pending_title = ""
        while len(rows) > 1 and sum(1 for c in rows[0] if c) == 1 and len(rows[0]) > 1:
            title.append(next(c for c in rows[0] if c))
            rows = rows[1:]
        filled_cells = sum(1 for row in rows for c in row if c)
        if len(rows) == 1 and filled_cells == 1:
            pending_title = next(c for c in rows[0] if c)
            continue
        if len(rows) < 2:
            blocks.append({"title": " · ".join(title) or "Values", "note": " | ".join(c for c in rows[0] if c), "df": None})
            continue
        hdr = make_unique(rows[0])
        df = pd.DataFrame(rows[1:], columns=hdr).astype(str)
        df = df.loc[:, (df != "").any(axis=0)]
        df = df.loc[(df != "").any(axis=1)].reset_index(drop=True)
        if df.empty:
            continue
        blocks.append({"title": " · ".join(title) or "Table", "note": "", "df": df})
    return blocks[:40]


def render_blocks(blocks, key):
    if not blocks:
        st.info("No tables found in this tab.")
        return
    for i, b in enumerate(blocks):
        st.markdown(f"#### {html.escape(b['title'])}", unsafe_allow_html=True)
        if b["df"] is None:
            st.caption(b["note"])
            continue
        df = b["df"]
        typed, kd = infer_table(df)
        label_col = df.columns[0]
        mask_total = df[label_col].astype(str).str.match(TOTAL_RE)
        nums = [c for c in typed.columns if kd.get(c) in ("numeric", "percent")]
        plain = [c for c in nums if kd[c] == "numeric"] or nums
        left, right = st.columns([1.25, 1])
        with left:
            st.dataframe(df, use_container_width=True, hide_index=True)
        with right:
            if plain and 2 <= int((~mask_total).sum()) <= 80 and label_col not in plain:
                pick = st.multiselect("Columns to chart", plain, default=plain[:4], key=f"{key}_blk{i}")
                if pick:
                    plot = typed.loc[~mask_total, [label_col] + pick].copy()
                    labels = plot[label_col].astype(str)
                    if kd.get(label_col) == "date":
                        plot[label_col] = labels
                    long = plot.melt(id_vars=label_col, var_name="Measure", value_name="Value")
                    months_like = all(v.strip().lower()[:3] in MONTH_ABBR for v in labels if v.strip())
                    if months_like:
                        fig = px.line(long, x=label_col, y="Value", color="Measure", markers=True)
                    else:
                        fig = px.bar(long, x=label_col, y="Value", color="Measure", barmode="group")
                    st.plotly_chart(style_fig(fig, 360), use_container_width=True)
            else:
                st.caption("No chart for this table (needs a label column + numeric columns).")
        st.markdown("---")


# ---------------- column roles & standard order frame ----------------
def detect_roles(kinds):
    roles, used = {}, set()
    for role, pats in ROLE_RULES.items():
        want = ROLE_KINDS[role]
        for pat in pats:
            hit = next((c for c, kd in kinds.items()
                        if c not in used and kd in want and re.search(pat, c.lower())
                        and not (role == "date" and re.search(NEG_DATE, c.lower()))), None)
            if hit:
                roles[role] = hit
                used.add(hit)
                break
    return roles


def build_orders(df_all, kinds, roles):
    d = pd.DataFrame(index=df_all.index)
    has = {}
    dc = roles.get("date")
    d[STD["date"]] = df_all[dc] if dc and kinds.get(dc) == "date" else pd.NaT
    d[STD["date"]] = pd.to_datetime(d[STD["date"]], errors="coerce")
    has["date"] = bool(d[STD["date"]].notna().any())

    month = d[STD["date"]].dt.month_name().fillna("").astype(object) if has["date"] else pd.Series("", index=df_all.index, dtype=object)
    mc = roles.get("month")
    if mc:
        alt = df_all[mc].dt.month_name().fillna("") if kinds.get(mc) == "date" else df_all[mc].astype(str).map(month_name_of)
        month = month.where(month != "", alt.astype(object))
    d[STD["month"]] = month
    has["month"] = bool((month != "").any())

    for r in TEXT_ROLES:
        col = roles.get(r)
        s = df_all[col].astype(str).str.strip() if col else pd.Series("", index=df_all.index)
        s = s.where(~s.str.lower().isin(BLANKS), "")
        if r in ("status", "category", "type"):
            s = s.str.upper()
        d[STD[r]] = s
        has[r] = bool((s != "").any())

    for r in NUM_ROLES:
        col = roles.get(r)
        if col:
            s = df_all[col]
            has[r] = bool(s.notna().any())
            s = s.fillna(0.0).astype(float)
            if r == "delay":
                s = s.mask(s > 1000, 0.0)
        else:
            s, has[r] = pd.Series(0.0, index=df_all.index), False
        d[STD[r]] = s

    mapped = set(c for c in roles.values() if c)
    for c in df_all.columns:
        if c in mapped:
            continue
        d[c + " (sheet)" if c in STD.values() else c] = df_all[c]
    return d, has


def nb(d, col):
    return d[d[col] != ""]


# ---------------- KPIs with month comparison ----------------
def kpi_defs(has):
    q, p, r, pe, dl = STD["qty"], STD["production"], STD["received"], STD["pending"], STD["delay"]

    def pct(d):
        base = d[p].sum() if has["production"] and d[p].sum() > 0 else d[q].sum()
        return float(d[r].sum() / base * 100) if base else 0.0

    defs = [("Total Orders", lambda d: float(len(d[d[q] > 0]) if has["qty"] else len(d)), "int", False, True)]
    if has["qty"]:
        defs.append(("Order Qty (Pcs)", lambda d: float(d[q].sum()), "int", False, True))
    if has["production"]:
        defs.append(("In Production", lambda d: float(d[p].sum()), "int", False, True))
    if has["received"]:
        defs.append(("Received", lambda d: float(d[r].sum()), "int", False, True))
    if has["pending"]:
        defs.append(("Pending", lambda d: float(d[pe].sum()), "int", True, True))
    if has["received"]:
        defs.append(("Received %", pct, "pct", False, False))
    if has["delay"]:
        defs.append(("Overdue Orders", lambda d: float((d[dl] > 0).sum()), "int", True, True))
        defs.append(("Avg Overdue Days", lambda d: float(d.loc[d[dl] > 0, dl].mean()) if (d[dl] > 0).any() else 0.0,
                     "days", True, False))
    if has["fabricator"]:
        defs.append(("Fabricators", lambda d: float(nb(d, STD["fabricator"])[STD["fabricator"]].nunique()), "int", False, False))
    if has["designer"]:
        defs.append(("Designers", lambda d: float(nb(d, STD["designer"])[STD["designer"]].nunique()), "int", False, False))
    return defs


def fmt_kpi(x, kind):
    if kind == "pct":
        return f"{x:.1f}%"
    if kind == "days":
        return f"{x:.1f} d"
    return f"{x:,.0f}"


def delta_text(cur, prev, kind):
    if kind == "pct":
        diff = cur - prev
        return (f"{diff:+.1f} pp" if abs(diff) >= 0.05 else "0.0 pp"), diff
    if prev == 0:
        return ("new" if cur else None), (cur - prev)
    pct = (cur - prev) / abs(prev) * 100
    return f"{pct:+.1f}%", pct


def render_kpis(d, d_nm, sel_months, defs, cmp_mode, key):
    cur = {lbl: fn(d) for lbl, fn, *_ in defs}
    prev, note = None, ""
    if sel_months:
        sel = sorted(sel_months, key=month_idx)
        first, n = month_idx(sel[0]), len(sel)
        present = {m for m in d_nm["Month"].unique() if m}
        if cmp_mode == "Previous month(s)":
            pm = MONTHS[max(0, first - n):first]
            pm = [m for m in pm if m in present] or pm
            base = d_nm[d_nm["Month"].isin(pm)]
            if pm and len(base):
                prev = {lbl: fn(base) for lbl, fn, *_ in defs}
                note = f"**{', '.join(sel)}** vs previous: **{', '.join(pm)}**"
        else:
            em = [m for m in MONTHS[:first] if m in present]
            base = d_nm[d_nm["Month"].isin(em)]
            if em and len(base):
                prev = {}
                for lbl, fn, _k, _i, additive in defs:
                    v = fn(base)
                    prev[lbl] = v / len(em) * n if additive else v
                note = f"**{', '.join(sel)}** vs average of earlier months (**{em[0]} → {em[-1]}**, {len(em)} month(s))"
        if prev is None:
            st.info("No earlier month found in the data to compare with (April is the first month of the FY).")
        else:
            st.caption("📊 Comparison: " + note + "  ·  green = better, red = worse")
    else:
        st.caption("💡 Select a month in the sidebar to see how every KPI changed vs previous month(s).")

    for i in range(0, len(defs), 5):
        cols = st.columns(5)
        for c, (lbl, fn, kind, inverse, additive) in zip(cols, defs[i:i + 5]):
            if prev is None:
                c.metric(lbl, fmt_kpi(cur[lbl], kind))
            else:
                txt, raw = delta_text(cur[lbl], prev[lbl], kind)
                color = "off" if (raw is None or abs(raw) < 0.05) else ("inverse" if inverse else "normal")
                c.metric(lbl, fmt_kpi(cur[lbl], kind), delta=txt, delta_color=color,
                         help=f"Comparison value: {fmt_kpi(prev[lbl], kind)}")
    return cur, prev


# ---------------- summaries ----------------
def entity_summary(d, dim, has):
    x = nb(d, dim)
    q, p, r, pe, dl = STD["qty"], STD["production"], STD["received"], STD["pending"], STD["delay"]
    aggs = {"Orders": (q, "size")}
    for role, name in (("qty", "Order Qty"), ("production", "In Production"), ("received", "Received"), ("pending", "Pending")):
        if has[role]:
            aggs[name] = (STD[role], "sum")
    g = x.groupby(dim).agg(**aggs).reset_index()
    if has["received"]:
        base = g["In Production"] if has["production"] and g["In Production"].sum() > 0 else (g["Order Qty"] if has["qty"] else None)
        if base is not None:
            g["Received %"] = (g["Received"] / base.where(base > 0) * 100).round(1)
    if has["delay"]:
        od = x[x[dl] > 0]
        g["Overdue Orders"] = g[dim].map(od.groupby(dim).size()).fillna(0).astype(int)
        g["Avg Overdue Days"] = g[dim].map(od.groupby(dim)[dl].mean()).fillna(0).round(1)
    sort_col = "Order Qty" if has["qty"] else "Orders"
    g = g.sort_values(sort_col, ascending=False).reset_index(drop=True)
    if has["qty"] and g["Order Qty"].sum() > 0:
        g["Share %"] = (g["Order Qty"] / g["Order Qty"].sum() * 100).round(1)
    return g


def monthly_table(d, has):
    x = nb(d, "Month")
    aggs = {"Orders": (STD["qty"], "size")}
    for role, name in (("qty", "Order Qty"), ("production", "In Production"), ("received", "Received"), ("pending", "Pending")):
        if has[role]:
            aggs[name] = (STD[role], "sum")
    g = x.groupby("Month").agg(**aggs)
    g = g.reindex([m for m in MONTHS if m in g.index]).reset_index()
    if has["received"]:
        base = g["In Production"] if has["production"] and g["In Production"].sum() > 0 else (g["Order Qty"] if has["qty"] else None)
        if base is not None:
            g["Received %"] = (g["Received"] / base.where(base > 0) * 100).round(1)
    for c in ("Order Qty", "Pending", "Received"):
        if c in g.columns:
            g[f"{c} MoM %"] = (g[c].pct_change() * 100).replace([np.inf, -np.inf], np.nan).round(1)
    return g


def order_insights(d, d_nm, has, cur, prev, sel_months):
    items = []
    q, pe, dl = STD["qty"], STD["pending"], STD["delay"]
    if has["designer"]:
        g = entity_summary(d, STD["designer"], has)
        if len(g) and has["qty"] and g["Order Qty"].sum() > 0:
            t = g.iloc[0]
            items.append(f"🎨 Top designer <b>{html.escape(str(t['Designer']))}</b> – {t['Order Qty']:,.0f} pcs ({t['Share %']:.1f}% of orders).")
    if has["fabricator"] and has["pending"]:
        g = entity_summary(d, STD["fabricator"], has).sort_values("Pending", ascending=False)
        if len(g) and g["Pending"].sum() > 0:
            t = g.iloc[0]
            items.append(f"🧵 Highest pending: <b>{html.escape(str(t['Fabricator']))}</b> with {t['Pending']:,.0f} pcs "
                         f"({t['Pending'] / g['Pending'].sum() * 100:.1f}% of all pending).")
        if has["received"] and "Received %" in g.columns:
            gg = g[g["Orders"] >= 2].dropna(subset=["Received %"])
            if len(gg) >= 2:
                b = gg.sort_values("Received %").iloc[0]
                items.append(f"🐢 Lowest received %: <b>{html.escape(str(b['Fabricator']))}</b> ({b['Received %']:.1f}%).")
    if has["status"]:
        s = nb(d, STD["status"]).groupby(STD["status"]).size().sort_values(ascending=False)
        if len(s):
            items.append(f"📌 Most common status: <b>{html.escape(str(s.index[0]))}</b> ({s.iloc[0] / s.sum() * 100:.0f}% of orders).")
    if has["delay"] and has["pending"]:
        late = d[(d[dl] > 30) & (d[pe] > 0)][pe].sum()
        if late > 0:
            items.append(f"⏰ <b>{late:,.0f} pcs</b> are pending for more than 30 days overdue.")
    if has["delay"] and len(d):
        share = (d[dl] > 0).mean() * 100
        items.append(f"🚨 {share:.0f}% of orders are overdue (delay days > 0).")
    if has["qty"] and has["month"]:
        mt = d_nm[d_nm["Month"] != ""].groupby("Month")[q].sum()
        if len(mt):
            items.append(f"📅 Busiest month: <b>{html.escape(mt.idxmax())}</b> ({mt.max():,.0f} pcs).")
    if prev is not None and sel_months:
        for lbl in ("Order Qty (Pcs)", "Pending", "Received"):
            if lbl in cur and prev.get(lbl):
                ch = (cur[lbl] - prev[lbl]) / abs(prev[lbl]) * 100
                arrow = "▲" if ch > 0 else "▼"
                items.append(f"{arrow} {lbl} is <b>{ch:+.1f}%</b> vs comparison period.")
    return items


def pivot_ui(d, dims, measures, key, default_row=0):
    c1, c2, c3, c4 = st.columns(4)
    rows_dim = c1.selectbox("Rows", dims, index=min(default_row, len(dims) - 1), key=f"{key}_r")
    cols_dim = c2.selectbox("Columns", ["(none)"] + [x for x in dims if x != rows_dim], key=f"{key}_c")
    measure = c3.selectbox("Measure", measures + ["(Order count)"], key=f"{key}_m")
    agg = c4.selectbox("Aggregation", ["Sum", "Average", "Max", "Min", "Count"],
                       index=4 if measure == "(Order count)" else 0, key=f"{key}_a")
    sub = nb(d, rows_dim)
    if cols_dim != "(none)":
        sub = nb(sub, cols_dim)
        if sub[cols_dim].nunique() > 40:
            st.warning("Too many distinct values in Columns - pick another field.")
            return
    cnt = measure == "(Order count)" or agg == "Count"
    if cols_dim == "(none)":
        pt = (sub.groupby(rows_dim).size().to_frame("Orders") if cnt
              else sub.groupby(rows_dim)[measure].agg(AGGS[agg]).to_frame(f"{agg} of {measure}"))
    elif cnt:
        pt = pd.crosstab(sub[rows_dim], sub[cols_dim], margins=True, margins_name="TOTAL")
    else:
        pt = pd.pivot_table(sub, index=rows_dim, columns=cols_dim, values=measure, aggfunc=AGGS[agg],
                            fill_value=0, margins=True, margins_name="TOTAL")
    pt.columns = [str(c) for c in pt.columns]
    if cols_dim != "(none)":
        order = order_values(sub[cols_dim]) if cols_dim == "Month" else sorted(c for c in pt.columns if c != "TOTAL")
        pt = pt[[c for c in order if c in pt.columns] + ["TOTAL"]]
        if rows_dim == "Month":
            idx = [m for m in MONTHS if m in pt.index] + ["TOTAL"]
            pt = pt.reindex(idx)
    st.dataframe(pt.reset_index(), use_container_width=True, hide_index=True)
    core = pt.drop(index="TOTAL", errors="ignore").drop(columns="TOTAL", errors="ignore")
    if cols_dim != "(none)" and core.shape[0] >= 1 and core.shape[1] >= 1:
        fig = px.imshow(core, text_auto=".2s", aspect="auto", color_continuous_scale="Blues",
                        title=f"Heatmap · {rows_dim} × {cols_dim}")
        st.plotly_chart(style_fig(fig, 460), use_container_width=True)


# ---------------- the dashboard ----------------

def orders_dashboard(df_all, kinds, ctx, block_sources=None, force_roles=None):
    """Clean single-page overview for non-master spreadsheets; no complex filters/tabs."""
    key = ctx["key"]
    auto = detect_roles(kinds)
    auto.update({r: c for r, c in (force_roles or {}).items() if c in kinds})

    d_all, has = build_orders(df_all, kinds, auto)
    d = d_all.copy()

    # Minimal controls only: manual refresh. No extra filter panels or mapping controls.
    with st.sidebar:
        st.markdown("### 🔎 Controls")
        if st.button("🔄 Refresh data", key=f"{key}_refresh"):
            st.cache_data.clear()
            st.rerun()

    st.markdown(
        f"""<div class="dashboard-hero">
        <h2>{html.escape(ctx.get('title', 'Dashboard'))}</h2>
        <p>{html.escape(ctx.get('subtitle', 'Overview'))} · {len(d):,} rows</p>
        </div>""",
        unsafe_allow_html=True,
    )

    q_col = STD.get("qty")
    status_col = STD.get("status")
    date_col_name = STD.get("date")
    month_col = "Month"

    # KPI cards
    kpis = []
    kpis.append(("Total Records", f"{len(d):,}"))
    if has.get("qty") and q_col in d:
        kpis.append(("Total Quantity", fmt(nb(d, q_col)[q_col].sum())))
    if has.get("status") and status_col in d:
        status = d[status_col].astype(str).str.strip().str.upper()
        approved = status.str.contains("APPROV|COMPLETE|ACCEPT", regex=True).sum()
        rejected = status.str.contains("REJECT", regex=True).sum()
        hold = status.str.contains("HOLD", regex=True).sum()
        process = status.str.contains("PROCESS|PENDING|PROGRESS", regex=True).sum()
        kpis.extend([
            ("Approved / Complete", f"{approved:,}"),
            ("Rejected", f"{rejected:,}"),
            ("On Hold", f"{hold:,}"),
            ("In Process", f"{process:,}"),
        ])
    elif has.get("fabricator") and STD.get("fabricator") in d:
        kpis.append(("Fabricators", f"{d[STD['fabricator']].nunique():,}"))

    cols = st.columns(min(4, len(kpis)))
    for i, (label, value) in enumerate(kpis):
        with cols[i % len(cols)]:
            st.metric(label, value)

    # Two-column charts; use only fields that were detected in the source.
    left, right = st.columns(2)
    with left:
        if has.get("status") and status_col in d:
            counts = d[status_col].replace("", "Unknown").fillna("Unknown").value_counts().rename_axis("Status").reset_index(name="Records")
            fig = px.pie(counts, names="Status", values="Records", hole=0.58, title="Status Distribution")
            st.plotly_chart(style_fig(fig, 360), use_container_width=True)
        elif has.get("designer") and STD.get("designer") in d:
            counts = d[STD["designer"]].replace("", "Unknown").value_counts().head(12).rename_axis("Designer").reset_index(name="Records")
            fig = px.bar(counts, x="Designer", y="Records", title="Top Designers", text_auto=True)
            st.plotly_chart(style_fig(fig, 360), use_container_width=True)
        elif has.get("fabricator") and STD.get("fabricator") in d:
            counts = d[STD["fabricator"]].replace("", "Unknown").value_counts().head(12).rename_axis("Fabricator").reset_index(name="Records")
            fig = px.bar(counts, x="Fabricator", y="Records", title="Records by Fabricator", text_auto=True)
            st.plotly_chart(style_fig(fig, 360), use_container_width=True)
        else:
            st.info("Status / Designer field was not detected for a chart.")

    with right:
        if has.get("month") and month_col in d:
            month_counts = d[month_col].replace("", "Unknown").value_counts().rename_axis("Month").reset_index(name="Records")
            month_counts["sort"] = month_counts["Month"].map(month_idx).fillna(99)
            month_counts = month_counts.sort_values("sort")
            fig = px.bar(month_counts, x="Month", y="Records", title="Monthly Records", text_auto=True)
            st.plotly_chart(style_fig(fig, 360), use_container_width=True)
        elif has.get("qty") and q_col in d and has.get("fabricator") and STD.get("fabricator") in d:
            tmp = d.copy()
            tmp[q_col] = pd.to_numeric(tmp[q_col], errors="coerce").fillna(0)
            grouped = tmp.groupby(STD["fabricator"], dropna=False)[q_col].sum().reset_index()
            fig = px.bar(grouped, x=STD["fabricator"], y=q_col, title="Quantity by Fabricator", text_auto=True)
            st.plotly_chart(style_fig(fig, 360), use_container_width=True)
        elif has.get("qty") and q_col in d:
            tmp = pd.to_numeric(d[q_col], errors="coerce").fillna(0)
            st.metric("Quantity total", fmt(tmp.sum()))
        else:
            st.info("Month / Quantity field was not detected for a chart.")

    # Compact detail table, not a collection of extra tabs.
    with st.expander("View source data", expanded=False):
        st.dataframe(df_all, use_container_width=True, hide_index=True)


# ---------------- sheet-type renderers ----------------
def _pick_tabs_ui(titles, cfg):
    data_default = None
    for w in cfg.get("data_tabs", []):
        data_default = find_tab(titles, w, DASH_RE) or data_default
    dash_default = None
    for w in cfg.get("dash_tabs", []):
        dash_default = find_tab(titles, w) or dash_default
    with st.sidebar:
        with st.expander("🗂️ Tabs used", expanded=False):
            di = titles.index(data_default) if data_default in titles else 0
            data_tab = st.selectbox("Data tab", titles, index=di, key=f"dt_{cfg['id']}")
            opts = ["(none)"] + titles
            dsi = opts.index(dash_default) if dash_default in opts else 0
            dash_tab = st.selectbox("Calculations / dashboard tab", opts, index=dsi, key=f"dsh_{cfg['id']}")
    return data_tab, (None if dash_tab == "(none)" else dash_tab)


def render_orders_sheet(sheet_name, cfg):
    sid = cfg["id"]
    try:
        titles = [t for t, _ in list_tabs(sid)]
        data_tab, dash_tab = _pick_tabs_ui(titles, cfg)
        wanted = tuple(dict.fromkeys([data_tab] + ([dash_tab] if dash_tab else [])))
        vals = load_many_tabs(sid, wanted)
    except Exception as e:
        show_access_error(e)
        st.stop()
    if not vals.get(data_tab) or not any(str(c).strip() for r in vals[data_tab] for c in r):
        st.warning(f"The tab '{data_tab}' is empty - pick the correct data tab under 'Tabs used' in the sidebar.")
        st.stop()
    df_raw, _pre, _tot = split_table(vals[data_tab])
    if df_raw.empty:
        st.warning("Header found but no data rows below it.")
        st.stop()
    df_all, kinds = infer_table(df_raw)
    ctx = {"key": f"{sid}_{data_tab}", "title": f"📋 {sheet_name}",
           "subtitle": f"Data tab: {data_tab}" + (f" · Calculations: {dash_tab}" if dash_tab else ""),
           "tabs_used": list(wanted)}
    sources = [(dash_tab, vals[dash_tab])] if dash_tab and vals.get(dash_tab) else []
    orders_dashboard(df_all, kinds, ctx, sources)



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

    frames, skipped = [], []
    for tab_name in fab_tabs:
        v = values.get(tab_name) or []
        if not v or not any(str(c).strip() for row in v for c in row):
            skipped.append(tab_name)
            continue
        df, _preface, _totals = split_table(v)
        if df.empty:
            skipped.append(tab_name)
            continue
        df.columns = [str(c).strip() or f"Column {i+1}" for i, c in enumerate(df.columns)]
        df = df.loc[:, ~pd.Index(df.columns).duplicated()]
        df["Fabricator (Tab)"] = tab_name
        frames.append(df)

    if not frames:
        st.warning("Is spreadsheet mein usable fabricator data nahi mila.")
        st.stop()

    df_raw = pd.concat(frames, ignore_index=True, sort=False).fillna("").astype(str)
    df_all, kinds = infer_table(df_raw)
    ctx = {
        "key": f"{sid}_fabricator_overview",
        "title": f"🧵 {sheet_name}",
        "subtitle": f"Fabricator overview · {len(frames)} data tabs combined",
        "tabs_used": [t for t in fab_tabs if t not in skipped],
    }
    orders_dashboard(
        df_all, kinds, ctx, block_sources=[],
        force_roles={"fabricator": "Fabricator (Tab)"}
    )


def render_simple_overview_sheet(sheet_name, cfg):
    """One clean overview for Sample Summary; choose a sensible data tab automatically."""
    sid = cfg["id"]
    try:
        tabs = list_tabs(sid)
    except Exception as e:
        show_access_error(e)
        st.stop()

    titles = [t for t, _ in tabs]
    # Prefer the actual sample register tab; don't accidentally use the formatted dashboard tab.
    preferred = cfg.get("data_tabs", [])
    tab = next((find_tab(titles, name, DASH_RE) for name in preferred if find_tab(titles, name, DASH_RE)), None)
    if tab is None:
        tab = next((t for t in titles if not DASH_RE.search(t) and not SKIP_TAB_RE.search(t)), titles[0] if titles else None)
    if tab is None:
        st.error("Google Sheet mein koi worksheet nahi mili.")
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

    if not values or not any(str(c).strip() for row in values for c in row):
        st.warning(f"'{tab}' tab empty hai.")
        st.stop()

    df_raw, _preface, _totals = split_table(values)
    if df_raw.empty:
        st.warning(f"'{tab}' mein header ke neeche data rows nahi mile.")
        st.stop()

    df_all, kinds = infer_table(df_raw)
    ctx = {
        "key": f"{sid}_{tab}_simple",
        "title": f"📊 {sheet_name}",
        "subtitle": f"Overview · Source tab: {tab}",
    }
    orders_dashboard(df_all, kinds, ctx, block_sources=[])


# -----------------------------------------------------------------------------
# 9. MAIN APP  (sheet dropdown -> matching dashboard)
# -----------------------------------------------------------------------------
def get_registry():
    """Code wali SHEET_REGISTRY + (optional) secrets [spreadsheets] se extra sheets."""
    reg = dict(SHEET_REGISTRY)
    known_ids = {v["id"] for v in reg.values()}
    try:
        extra = dict(st.secrets.get("spreadsheets", {}))
    except Exception:
        extra = {}
    for name, v in extra.items():
        cfg = {"id": str(v).strip(), "type": "tracker", "gid": None} if isinstance(v, str) else \
              {"id": str(v["id"]).strip(), "type": v.get("type", "summary"), "gid": v.get("gid")}
        if cfg["id"] not in known_ids:
            reg[name] = cfg
    return reg


def render_tracker(sheet_name, sheet_id):
    """Master order-tracker dashboard (original logic, unchanged)."""
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


def render_summary(sheet_name, cfg):
    sid = cfg["id"]
    try:
        tabs = list_tabs(sid)
    except Exception as e:
        show_access_error(e)
        st.stop()

    titles = [t for t, _ in tabs]
    default_idx = 0
    if cfg.get("gid") is not None:
        default_idx = next((i for i, (_, g) in enumerate(tabs) if int(g) == int(cfg["gid"])), 0)

    with st.sidebar:
        st.markdown("### 🗂️ Sheet Tab")
        tab = st.selectbox("Select tab", titles, index=default_idx, key=f"tab_{sid}")
        if st.button("🔄 Refresh data", key=f"refresh_{sid}"):
            st.cache_data.clear()
            st.rerun()

    try:
        values = load_tab_values(sid, tab)
    except Exception as e:
        show_access_error(e)
        st.stop()

    if not values or not any(str(c).strip() for r in values for c in r):
        st.warning(f"The tab '{tab}' is empty.")
        st.stop()

    df_raw, preface, totals_raw = split_table(values)
    if df_raw.empty:
        st.warning("Header found but no data rows below it.")
        st.stop()
    df_all, kinds = infer_table(df_raw)
    ctx = {"sheet_name": sheet_name, "tab": tab, "key": f"{sid}_{tab}"}
    summary_dashboard(df_all, kinds, totals_raw, preface, values, ctx)


def main():
    registry = get_registry()
    with st.sidebar:
        st.markdown("### 📚 Select Dashboard")
        selected = st.selectbox("Google Sheet", list(registry.keys()), key="sheet_choice")
        cfg = registry[selected]

    kind = cfg.get("type", "tracker")
    if kind == "tracker":
        render_tracker(selected, cfg["id"])
    elif kind == "orders":
        render_simple_overview_sheet(selected, cfg)
    elif kind == "fabricators":
        render_fabricator_sheet(selected, cfg)
    elif kind == "overview":
        render_simple_overview_sheet(selected, cfg)
    elif kind == "overview_fabricators":
        render_fabricator_sheet(selected, cfg)
    else:
        render_summary(selected, cfg)


if __name__ == "__main__":
    main()
