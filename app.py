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
# 1. PAGE SETUP & MODERN EXECUTIVE STYLING
# -----------------------------------------------------------------------------
st.set_page_config(
    page_title="Executive Operations & Production Hub 2026-27",
    page_icon="📊",
    layout="wide"
)

SHEET_REGISTRY = {
    "Master Sheet": {
        "id": "1wBo0zF2wlqBzY5ZQaX5CPjCOedORwg_1Eh01vje5KFU",
        "type": "tracker",
        "gid": 0,
    },
    "Sample Summary": {
        "id": "1EfQ08lXGL8YjtoaZ2ygJtNVaED7doDijo2jFvCuS7Kg",
        "type": "sample_summary",
        "gid": 78218658,
        "data_tabs": ["SAMPLE SUMMARY", "SAMPLE SHEET 2026-27", "2026-27"],
    },
    "Fabricator Report": {
        "id": "1hP9Bkvu2F-qj4tXYhOCb4alfJOZZtAsMQNOjVQyWoo4",
        "type": "overview_fabricators",
        "gid": 164418035,
        "summary_tabs": ["MONTHWISE SUMMARY"],
    },
}

SHEET_ID = "1wBo0zF2wlqBzY5ZQaX5CPjCOedORwg_1Eh01vje5KFU"
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
    APP_BG, PANEL_BG, TEXT, MUTED, BORDER = "#0a0f1d", "#12192b", "#eaf0f8", "#94a3b8", "#1e293b"
    CARD_BG, CHIP_BG, ACCENT = "#162035", "#1e2c45", "#38bdf8"
    PLOT_TEMPLATE = "plotly_dark"
else:
    APP_BG, PANEL_BG, TEXT, MUTED, BORDER = "#f8fafc", "#ffffff", "#0f172a", "#64748b", "#e2e8f0"
    CARD_BG, CHIP_BG, ACCENT = "#f1f5f9", "#e2e8f0", "#2563eb"
    PLOT_TEMPLATE = "plotly_white"

px.defaults.template = PLOT_TEMPLATE
PALETTE = ["#2563eb", "#059669", "#d97706", "#dc2626", "#7c3aed", "#0891b2", "#db2777", "#65a30d"]
px.defaults.color_discrete_sequence = PALETTE

st.markdown(f"""
<style>
:root {{
    --app-bg: {APP_BG};
    --panel-bg: {PANEL_BG};
    --card-bg: {CARD_BG};
    --text-color: {TEXT};
    --muted-color: {MUTED};
    --border-color: {BORDER};
    --chip-bg: {CHIP_BG};
    --accent: {ACCENT};
}}
.stApp {{ background-color: var(--app-bg); color: var(--text-color); font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; }}
.block-container {{ padding-top: 1.15rem; padding-bottom: 2.8rem; max-width: 1650px; }}
[data-testid="stSidebar"] {{ background-color: var(--panel-bg); border-right: 1px solid var(--border-color); }}
[data-testid="stSidebar"] h3 {{ font-size: .83rem; font-weight: 750; text-transform: uppercase; letter-spacing: 0.08em; color: var(--muted-color); margin-bottom: 0.6rem; }}
[data-testid="stSidebar"] label {{ font-size: .78rem !important; font-weight: 650 !important; color: var(--text-color) !important; margin-bottom: 3px; }}
.sidebar-filter-card {{ background: var(--card-bg); border: 1px solid var(--border-color); border-radius: 12px; padding: 12px; margin-bottom: 12px; }}

/* Compact Sleek MultiSelect Chips */
.stMultiSelect [data-baseweb="select"] > div {{ border-radius: 8px; border: 1px solid var(--border-color); background: var(--panel-bg); min-height: 36px; }}
.stMultiSelect [data-baseweb="tag"] {{ background-color: var(--chip-bg) !important; border: 1px solid var(--border-color) !important; border-radius: 5px !important; padding: 1px 6px !important; margin: 2px !important; }}
.stMultiSelect [data-baseweb="tag"] span {{ color: var(--text-color) !important; font-size: 0.76rem !important; font-weight: 550 !important; }}

/* Executive Metric Cards */
[data-testid="stMetric"] {{ background: var(--panel-bg); border: 1px solid var(--border-color); border-top: 3px solid var(--accent); padding: 14px 18px; border-radius: 12px; box-shadow: 0 4px 14px rgba(0,0,0,0.04); }}
[data-testid="stMetricLabel"] {{ color: var(--muted-color); font-size: .78rem; font-weight: 700; text-transform: uppercase; letter-spacing: .03em; }}
[data-testid="stMetricValue"] {{ color: var(--text-color); font-weight: 800; font-size: 1.55rem; }}

/* Tab Navigation */
[data-testid="stTabs"] button {{ border-radius: 8px 8px 0 0; font-weight: 700; font-size: .92rem; padding: 10px 20px; }}
[data-testid="stPlotlyChart"] {{ background: var(--panel-bg); border: 1px solid var(--border-color); border-radius: 12px; padding: 8px; }}
[data-testid="stDataFrame"] {{ border: 1px solid var(--border-color); border-radius: 10px; overflow: hidden; }}

.dashboard-hero {{
    background: linear-gradient(135deg, {'#131e33 0%, #172a48 100%' if DARK_MODE else '#ffffff 0%, #edf4ff 100%'});
    border: 1px solid var(--border-color); border-radius: 14px; padding: 18px 22px; margin-bottom: 18px;
    box-shadow: 0 4px 15px rgba(0,0,0,0.03);
}}
.dashboard-hero h2 {{ margin: 0; font-size: 1.45rem; font-weight: 800; letter-spacing: -0.02em; }}
.dashboard-hero p {{ color: var(--muted-color); margin: 3px 0 0 0; font-size: .88rem; }}
.section-badge {{ display: inline-flex; align-items: center; background: var(--chip-bg); padding: 3px 10px; border-radius: 6px; font-size: 0.78rem; font-weight: 700; margin-bottom: 8px; }}
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

def metrics(items):
    cols = st.columns(len(items))
    for c, (label, value) in zip(cols, items):
        c.metric(label, value)

def fmt(x):
    return f"{x:,.0f}"

def style_fig(fig, height=360):
    fig.update_layout(
        height=height,
        margin=dict(l=12, r=12, t=46, b=10),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        font=dict(size=11),
        title_font=dict(size=14, family="-apple-system, sans-serif")
    )
    return fig

def handle_smart_all_filter(key):
    """Cleanly manages 'All' option in Streamlit multiselect."""
    selected = st.session_state.get(key, [])
    prev_key = f"{key}_prev_state"
    prev = st.session_state.get(prev_key, ["All"])

    if not selected:
        st.session_state[key] = ["All"]
    elif "All" in selected and len(selected) > 1:
        if "All" in prev:
            st.session_state[key] = [x for x in selected if x != "All"]
        else:
            st.session_state[key] = ["All"]
    st.session_state[prev_key] = st.session_state[key]

# -----------------------------------------------------------------------------
# 3. GOOGLE SHEETS AUTHENTICATION & CORE SHEET LOADERS (ERROR-SAFE)
# -----------------------------------------------------------------------------
def show_access_error(e):
    email = ""
    try:
        email = st.secrets["gcp_service_account"]["client_email"]
    except Exception:
        pass
    st.error("Could not open this Google Sheet. Share it with service account: " + (f"**{email}**" if email else "email from secrets"))

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

@st.cache_data(ttl=300, show_spinner="Sheet tabs load ho rahe hain...")
def list_tabs(sheet_id):
    book = get_client().open_by_key(sheet_id)
    return [(ws.title, ws.id) for ws in book.worksheets()]

@st.cache_data(ttl=300, show_spinner="Google Sheet se data load ho raha hai...")
def load_tab_values(sheet_id, tab_title):
    return get_client().open_by_key(sheet_id).worksheet(tab_title).get_all_values()

def find_tab(titles, wanted):
    nw = re.sub(r"[^a-z0-9]", "", str(wanted).lower())
    for t in titles:
        if re.sub(r"[^a-z0-9]", "", str(t).lower()) == nw:
            return t
    return None

# -----------------------------------------------------------------------------
# 4. MASTER SHEET DATA PREPARATION & VIEWS (UNCHANGED CORE LOGIC)
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
            st.plotly_chart(style_fig(px.bar(m, x="Month", y="qty", title="Monthly Order Quantity (Column B)", text_auto=".2s")), use_container_width=True)
    with b:
        c = d[d.category_clean.ne("")].groupby("category_clean", as_index=False)["qty"].sum().sort_values("qty", ascending=False)
        if not c.empty:
            st.plotly_chart(style_fig(px.bar(c, x="category_clean", y="qty", title="Category-wise Order Quantity (Column J)", text_auto=".2s")), use_container_width=True)

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
        st.plotly_chart(style_fig(px.bar(melted, x="designer", y="Qty", color="Order Type", barmode="group", title="DESIGNER PERFORMANCE: NEW vs REPEAT ORDERS (PCS)", color_discrete_sequence=["#059669", "#7C3AED"])), use_container_width=True)

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
    st.subheader("🏢 Executive Client Performance Dashboard")
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
    st.subheader("📅 Client Fulfillment Breakdown")
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
        st.plotly_chart(style_fig(px.pie(q, names="Status", values="Qty", hole=.45, title="ORDER FULFILLMENT RATIO (RECEIVED vs PENDING)", color_discrete_sequence=["#059669", "#DC2626"])), use_container_width=True)

def production_dashboard(d):
    st.subheader("🏭 Production Executive Process Dashboard")
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
    items = [("Total Qty (J)", "J", d_all["qty"].sum()),
             ("In Production (AS)", "AS", d_all["production"].sum()),
             ("Received (AT)", "AT", d_all["received"].sum()),
             ("Pending (AU)", "AU", d_all["pending"].sum())]
    rows = []
    for label, letter, mine in items:
        idx = col_to_idx(letter)
        cell = totals_row[idx] if idx < len(totals_row) else ""
        sheet_val = float(num(pd.Series([cell])).iloc[0])
        rows.append({"Column": label, "Sheet row-2 total": sheet_val, "Dashboard": float(mine), "Diff": float(mine) - sheet_val})
    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

def render_tracker(sheet_name, sheet_id):
    raw, totals_row, tab_name, first_data_row = load_sheet(sheet_id)
    d_all = prepare(raw)

    with st.sidebar:
        st.markdown('<div class="sidebar-filter-card">', unsafe_allow_html=True)
        st.markdown("### 🔍 Master Sheet Filters")
        months_present = [m for m in MONTHS if m in set(d_all["month_client"].dropna())]
        month_options = ["All"] + [x for x in months_present if x != "All"]
        designer_options = ["All"] + sorted(x for x in d_all["designer"].unique() if x and x != "All")
        client_options = ["All"] + sorted(x for x in d_all["client"].unique() if x and x != "All")
        fab_options = ["All"] + sorted(x for x in d_all["fabricator"].unique() if x and x != "All")

        for k in [f"{sheet_id}_m", f"{sheet_id}_d", f"{sheet_id}_c", f"{sheet_id}_f"]:
            if k not in st.session_state: st.session_state[k] = ["All"]

        sel_months = st.multiselect("Order Month", month_options, key=f"{sheet_id}_m", on_change=handle_smart_all_filter, args=(f"{sheet_id}_m",))
        sel_designers = st.multiselect("Designer", designer_options, key=f"{sheet_id}_d", on_change=handle_smart_all_filter, args=(f"{sheet_id}_d",))
        sel_clients = st.multiselect("Client", client_options, key=f"{sheet_id}_c", on_change=handle_smart_all_filter, args=(f"{sheet_id}_c",))
        sel_fabs = st.multiselect("Fabricator", fab_options, key=f"{sheet_id}_f", on_change=handle_smart_all_filter, args=(f"{sheet_id}_f",))
        if st.button("🔄 Refresh Data", key=f"{sheet_id}_ref"):
            st.cache_data.clear()
            st.rerun()
        st.markdown('</div>', unsafe_allow_html=True)

    d = d_all.copy()
    if "All" not in sel_months and sel_months: d = d[d["month_client"].isin(sel_months)]
    if "All" not in sel_designers and sel_designers: d = d[d["designer"].isin(sel_designers)]
    if "All" not in sel_clients and sel_clients: d = d[d["client"].isin(sel_clients)]
    if "All" not in sel_fabs and sel_fabs: d = d[d["fabricator"].isin(sel_fabs)]

    st.markdown(
        f"""<div class="dashboard-hero"><h2>📊 {html.escape(sheet_name)} · Executive Dashboard</h2>
        <p>Source Tab: <b>{html.escape(tab_name)}</b> · {len(d):,} Rows (Data row {first_data_row} se)</p></div>""",
        unsafe_allow_html=True
    )

    t1, t2, t3, t4 = st.tabs(["Overview", "Designer Hub", "Client Fulfillment", "Production Delay Tracker"])
    with t1: overview(d)
    with t2: designer_dashboard(d)
    with t3: client_dashboard(d)
    with t4: production_dashboard(d)
    with st.expander("✅ Reconciliation / Sheet Totals Check"): data_check(totals_row, d_all)

# -----------------------------------------------------------------------------
# 5. FABRICATOR REPORT ENGINE (2 COMBINED TABS: CHARTS + TABLES TOGETHER)
# -----------------------------------------------------------------------------
def parse_fabricator_summary_grid(values):
    records = []
    if not values: return pd.DataFrame()

    for r_idx, row in enumerate(values):
        for c_idx, cell in enumerate(row):
            cell_str = str(cell).strip()
            if re.search(r"position\s*of\s*stock", cell_str, re.I):
                fab_name = re.sub(r"position\s*of\s*stock\s*[:\-]?", "", cell_str, flags=re.I).strip()
                fab_name = re.sub(r"^[(\[]|[)\]]$", "", fab_name).strip()
                if "ALL OVER" in fab_name.upper(): fab_name = "ALL OVER (CONSOLIDATED)"
                if not fab_name: fab_name = "UNKNOWN"

                header_row_idx = None
                for scan_r in range(r_idx + 1, min(r_idx + 4, len(values))):
                    scan_row = values[scan_r]
                    if c_idx < len(scan_row) and re.search(r"month", str(scan_row[c_idx]), re.I):
                        header_row_idx = scan_r
                        break
                if header_row_idx is None: continue

                h_row = values[header_row_idx]
                col_map = {}
                for offset in range(0, 8):
                    curr_col = c_idx + offset
                    if curr_col < len(h_row):
                        h_val = str(h_row[curr_col]).strip().lower()
                        if not h_val and offset > 4: break
                        if "month" in h_val and "month" not in col_map: col_map["month"] = curr_col
                        elif ("fabric" in h_val or "issue" in h_val or "mtr" in h_val) and "fabric_issue" not in col_map: col_map["fabric_issue"] = curr_col
                        elif ("under" in h_val or "production" in h_val or "pcs" in h_val) and "production" not in col_map: col_map["production"] = curr_col
                        elif ("rcvd" in h_val or "received" in h_val) and "received" not in col_map: col_map["received"] = curr_col
                        elif ("remain" in h_val or "pending" in h_val) and "remaining" not in col_map: col_map["remaining"] = curr_col
                        elif "incoming" in h_val and "incoming" not in col_map: col_map["incoming"] = curr_col

                if "month" not in col_map: continue

                for data_r in range(header_row_idx + 1, len(values)):
                    d_row = values[data_r]
                    if c_idx >= len(d_row): break
                    m_val = str(d_row[c_idx]).strip()
                    if not m_val or re.search(r"^total|position\s*of\s*stock", m_val, re.I): break
                    if not re.search(r"(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)", m_val, re.I): continue

                    def get_val(k):
                        idx = col_map.get(k)
                        if idx is not None and idx < len(d_row):
                            return float(num(pd.Series([d_row[idx]])).iloc[0])
                        return 0.0

                    issue_val = get_val("fabric_issue")
                    prod_val = get_val("production")
                    rcvd_val = get_val("received")
                    rem_val = get_val("remaining")
                    inc_val = get_val("incoming")

                    if prod_val == 0 and issue_val == 0: status = "No Orders"
                    elif rem_val == 0 and prod_val > 0: status = "Completed (100%)"
                    elif rcvd_val > 0 and rem_val > 0: status = "In Progress"
                    elif rcvd_val == 0 and prod_val > 0: status = "Pending / Not Started"
                    else: status = "In Progress" if rem_val > 0 else "Completed (100%)"

                    records.append({
                        "Fabricator": fab_name,
                        "Month": m_val,
                        "Fabric Issue (mtr)": issue_val,
                        "Pcs Under Production": int(prod_val),
                        "RCVD (Pcs)": int(rcvd_val),
                        "Remaining (Pcs)": int(rem_val),
                        "Monthly Incoming (Pcs)": int(inc_val),
                        "Production Status": status,
                    })

    df = pd.DataFrame(records)
    if not df.empty:
        month_order = [f"{m}-26" for m in MONTHS[:9]] + [f"{m}-27" for m in MONTHS[9:]]
        df["Month_Order"] = df["Month"].apply(lambda m: month_order.index(m) if m in month_order else 99)
        df = df.sort_values(["Month_Order", "Fabricator"]).drop(columns=["Month_Order"])
    return df

def render_fabricator_dashboard(sheet_name, cfg):
    sid = cfg["id"]
    try:
        tabs = list_tabs(sid)
        titles = [t for t, _ in tabs]
    except Exception as e:
        show_access_error(e)
        st.stop()

    summary_tab = find_tab(titles, "MONTHWISE SUMMARY") or (titles[0] if titles else "MONTHWISE SUMMARY")
    raw_values = load_tab_values(sid, summary_tab)
    df_parsed = parse_fabricator_summary_grid(raw_values)

    if df_parsed.empty:
        st.error("Sheet me fabricator block data detect nahi hua.")
        st.stop()

    is_cons = df_parsed["Fabricator"].str.contains("ALL OVER", case=False, na=False)
    df_consolidated = df_parsed[is_cons].copy()
    df_vendors = df_parsed[~is_cons].copy()
    df_work = df_vendors if not df_vendors.empty else df_consolidated

    # --- SIDEBAR FILTERS ---
    with st.sidebar:
        st.markdown('<div class="sidebar-filter-card">', unsafe_allow_html=True)
        st.markdown("### 🔍 Fabricator Filters")

        all_fabs = sorted(df_work["Fabricator"].unique())
        fab_opts = ["All"] + all_fabs
        if "f_fab" not in st.session_state: st.session_state["f_fab"] = ["All"]
        sel_fabs = st.multiselect("Fabricator Name", options=fab_opts, key="f_fab", on_change=handle_smart_all_filter, args=("f_fab",))

        all_months = list(dict.fromkeys(df_work["Month"].tolist()))
        month_opts = ["All"] + all_months
        if "f_month" not in st.session_state: st.session_state["f_month"] = ["All"]
        sel_months = st.multiselect("Month", options=month_opts, key="f_month", on_change=handle_smart_all_filter, args=("f_month",))

        all_stat = ["Completed (100%)", "In Progress", "Pending / Not Started", "No Orders"]
        status_opts = ["All"] + [s for s in all_stat if s in df_work["Production Status"].values]
        if "f_stat" not in st.session_state: st.session_state["f_stat"] = ["All"]
        sel_status = st.multiselect("Production Status", options=status_opts, key="f_stat", on_change=handle_smart_all_filter, args=("f_stat",))

        hide_zero = st.checkbox("Hide Zero Production Months", value=True)
        if st.button("🔄 Refresh Data", key="fab_ref"):
            st.cache_data.clear()
            st.rerun()
        st.markdown('</div>', unsafe_allow_html=True)

    filtered = df_work.copy()
    if "All" not in sel_fabs and sel_fabs: filtered = filtered[filtered["Fabricator"].isin(sel_fabs)]
    if "All" not in sel_months and sel_months: filtered = filtered[filtered["Month"].isin(sel_months)]
    if "All" not in sel_status and sel_status: filtered = filtered[filtered["Production Status"].isin(sel_status)]
    if hide_zero: filtered = filtered[(filtered["Pcs Under Production"] > 0) | (filtered["Fabric Issue (mtr)"] > 0)]

    st.markdown(
        f"""<div class="dashboard-hero">
        <h2>🧵 {sheet_name} · Executive Operations Dashboard</h2>
        <p>Active Source: <b>{html.escape(summary_tab)}</b> · {filtered['Fabricator'].nunique():,} Fabricator(s) Filtered · Live Sync 2026-27</p>
        </div>""",
        unsafe_allow_html=True
    )

    if filtered.empty:
        st.warning("Selected filters ke saath koi record match nahi hua. Kripya sidebar filter reset karein.")
        st.stop()

    tot_fab = filtered["Fabric Issue (mtr)"].sum()
    tot_prod = filtered["Pcs Under Production"].sum()
    tot_rcvd = filtered["RCVD (Pcs)"].sum()
    tot_rem = filtered["Remaining (Pcs)"].sum()
    ful_rate = (tot_rcvd / tot_prod * 100) if tot_prod > 0 else 0.0

    k1, k2, k3, k4, k5 = st.columns(5)
    k1.metric("Fabric Issued", f"{tot_fab:,.1f} Mtr")
    k2.metric("Under Production", fmt(tot_prod) + " Pcs")
    k3.metric("Received (RCVD)", fmt(tot_rcvd) + " Pcs")
    k4.metric("Pending Backlog", fmt(tot_rem) + " Pcs")
    k5.metric("Fulfillment Rate", f"{ful_rate:.1f}%")

    st.markdown("---")

    # --- EXACTLY 2 COMBINED TABS (CHARTS + TABLES TOGETHER) ---
    t1, t2 = st.tabs([
        "📊 Monthly Trend & Production Pipeline",
        "👥 Vendor Scorecard & Backlog Deep-Dive"
    ])

    month_order = [f"{m}-26" for m in MONTHS[:9]] + [f"{m}-27" for m in MONTHS[9:]]

    # TAB 1: Monthly Trends + Monthly Breakdown Table
    with t1:
        st.markdown('<div class="section-badge">📈 Monthly Performance Trends</div>', unsafe_allow_html=True)
        c1, c2 = st.columns([1.35, 1])
        with c1:
            m_agg = filtered.groupby("Month", as_index=False).agg({"Pcs Under Production": "sum", "RCVD (Pcs)": "sum", "Remaining (Pcs)": "sum"})
            m_agg["order"] = m_agg["Month"].apply(lambda m: month_order.index(m) if m in month_order else 99)
            m_agg = m_agg.sort_values("order").drop(columns=["order"])

            fig_bar = go.Figure()
            fig_bar.add_trace(go.Bar(name="Under Production", x=m_agg["Month"], y=m_agg["Pcs Under Production"], marker_color="#2563eb"))
            fig_bar.add_trace(go.Bar(name="Received (RCVD)", x=m_agg["Month"], y=m_agg["RCVD (Pcs)"], marker_color="#059669"))
            fig_bar.add_trace(go.Bar(name="Pending Backlog", x=m_agg["Month"], y=m_agg["Remaining (Pcs)"], marker_color="#dc2626"))
            fig_bar.update_layout(title="Monthly Production vs Delivery vs Backlog (Pcs)", barmode="group", xaxis_title="Month")
            st.plotly_chart(style_fig(fig_bar, 350), use_container_width=True)

        with c2:
            status_df = filtered["Production Status"].value_counts().reset_index()
            status_df.columns = ["Status", "Count"]
            color_map = {"Completed (100%)": "#059669", "In Progress": "#f59e0b", "Pending / Not Started": "#dc2626", "No Orders": "#94a3b8"}
            fig_pie = px.pie(status_df, names="Status", values="Count", title="Order Status Distribution", hole=0.48, color="Status", color_discrete_map=color_map)
            st.plotly_chart(style_fig(fig_pie, 350), use_container_width=True)

        st.markdown("#### 📋 Month-by-Month Production Breakdown Matrix")
        m_display = filtered[["Fabricator", "Month", "Fabric Issue (mtr)", "Pcs Under Production", "RCVD (Pcs)", "Remaining (Pcs)", "Monthly Incoming (Pcs)", "Production Status"]].copy()
        st.dataframe(
            m_display.style.format({
                "Fabric Issue (mtr)": "{:,.2f}",
                "Pcs Under Production": "{:,.0f}",
                "RCVD (Pcs)": "{:,.0f}",
                "Remaining (Pcs)": "{:,.0f}",
                "Monthly Incoming (Pcs)": "{:,.0f}"
            }),
            use_container_width=True,
            hide_index=True
        )

    # TAB 2: Vendor Visuals + Vendor Scorecard Matrix
    with t2:
        st.markdown('<div class="section-badge">👥 Vendor Comparative Analytics</div>', unsafe_allow_html=True)
        v1, v2 = st.columns([1.3, 1])
        fab_summary = filtered.groupby("Fabricator", as_index=False).agg({
            "Fabric Issue (mtr)": "sum",
            "Pcs Under Production": "sum",
            "RCVD (Pcs)": "sum",
            "Remaining (Pcs)": "sum",
            "Monthly Incoming (Pcs)": "sum"
        }).sort_values("Pcs Under Production", ascending=False)

        with v1:
            fig_vbar = go.Figure()
            fig_vbar.add_trace(go.Bar(name="Received Pcs", x=fab_summary["Fabricator"], y=fab_summary["RCVD (Pcs)"], marker_color="#059669"))
            fig_vbar.add_trace(go.Bar(name="Remaining Backlog", x=fab_summary["Fabricator"], y=fab_summary["Remaining (Pcs)"], marker_color="#dc2626"))
            fig_vbar.update_layout(title="Fabricator Completed vs Pending Backlog", barmode="stack")
            st.plotly_chart(style_fig(fig_vbar, 340), use_container_width=True)

        with v2:
            fig_vpie = px.pie(fab_summary, names="Fabricator", values="Pcs Under Production", title="Fabricator Production Share", hole=0.45)
            st.plotly_chart(style_fig(fig_vpie, 340), use_container_width=True)

        st.markdown("#### 📋 Fabricator Performance Scorecard with Grand Totals")
        fab_summary["Fulfillment %"] = fab_summary.apply(lambda r: f"{(r['RCVD (Pcs)'] / r['Pcs Under Production'] * 100):.1f}%" if r["Pcs Under Production"] > 0 else "0.0%", axis=1)
        fab_summary["Avg Mtr/Pc"] = fab_summary.apply(lambda r: f"{(r['Fabric Issue (mtr)'] / r['Pcs Under Production']):.2f}" if r["Pcs Under Production"] > 0 else "0.00", axis=1)

        tot_row = pd.DataFrame([{
            "Fabricator": "GRAND TOTAL",
            "Fabric Issue (mtr)": fab_summary["Fabric Issue (mtr)"].sum(),
            "Pcs Under Production": fab_summary["Pcs Under Production"].sum(),
            "RCVD (Pcs)": fab_summary["RCVD (Pcs)"].sum(),
            "Remaining (Pcs)": fab_summary["Remaining (Pcs)"].sum(),
            "Monthly Incoming (Pcs)": fab_summary["Monthly Incoming (Pcs)"].sum(),
            "Fulfillment %": f"{(fab_summary['RCVD (Pcs)'].sum() / fab_summary['Pcs Under Production'].sum() * 100):.1f}%" if fab_summary["Pcs Under Production"].sum() > 0 else "0.0%",
            "Avg Mtr/Pc": f"{(fab_summary['Fabric Issue (mtr)'].sum() / fab_summary['Pcs Under Production'].sum()):.2f}" if fab_summary["Pcs Under Production"].sum() > 0 else "0.00"
        }])
        fab_scorecard = pd.concat([fab_summary, tot_row], ignore_index=True)
        st.dataframe(
            fab_scorecard.style.format({
                "Fabric Issue (mtr)": "{:,.2f}",
                "Pcs Under Production": "{:,.0f}",
                "RCVD (Pcs)": "{:,.0f}",
                "Remaining (Pcs)": "{:,.0f}",
                "Monthly Incoming (Pcs)": "{:,.0f}"
            }),
            use_container_width=True,
            hide_index=True
        )

        if not df_consolidated.empty:
            with st.expander("🏛️ Consolidated Position Of Stock (ALL OVER Reference Table)"):
                c_tbl = df_consolidated[["Month", "Fabric Issue (mtr)", "Pcs Under Production", "RCVD (Pcs)", "Remaining (Pcs)", "Monthly Incoming (Pcs)"]]
                st.dataframe(c_tbl, use_container_width=True, hide_index=True)

# -----------------------------------------------------------------------------
# 6. SAMPLE SUMMARY ENGINE (PARSER & 2 INTEGRATED TABS)
# -----------------------------------------------------------------------------
def parse_sample_summary_sheet(values):
    summary_data = {
        "total_samples": 0, "approved": 0, "rejected": 0, "hold": 0,
        "on_process": 0, "approval_ratio": 0.0, "overdue_pcs": 0, "avg_delay": 0.0,
        "monthly_breakdown": []
    }
    if not values: return summary_data

    # Scan for headline KPIs
    for r_idx, row in enumerate(values):
        row_str = " ".join([str(c) for c in row]).upper()
        if "TOTAL SAMPLES" in row_str and "APPROVED" in row_str:
            if r_idx + 1 < len(values):
                val_row = values[r_idx + 1]
                nums = [float(num(pd.Series([c])).iloc[0]) for c in val_row if str(c).strip()]
                if len(nums) >= 5:
                    summary_data["total_samples"] = int(nums[0])
                    summary_data["approved"] = int(nums[1])
                    summary_data["rejected"] = int(nums[2])
                    summary_data["hold"] = int(nums[3])
                    summary_data["on_process"] = int(nums[4])
                    if len(nums) >= 6: summary_data["approval_ratio"] = nums[5]
                    if len(nums) >= 7: summary_data["overdue_pcs"] = int(nums[6])
                    if len(nums) >= 8: summary_data["avg_delay"] = nums[7]

    # Scan for monthly status breakdown grid
    for r_idx, row in enumerate(values):
        row_str = " ".join([str(c) for c in row]).upper()
        if "MONTH" in row_str and "APPROVED" in row_str and "REJECTED" in row_str:
            for d_idx in range(r_idx + 1, min(r_idx + 15, len(values))):
                d_row = values[d_idx]
                m_name = next((str(c).strip() for c in d_row if re.search(r"(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)", str(c), re.I)), None)
                if not m_name or "TOTAL" in m_name.upper(): continue
                d_nums = [float(num(pd.Series([c])).iloc[0]) for c in d_row if re.search(r"^\d+(\.\d+)?$", str(c).strip())]
                if len(d_nums) >= 4:
                    summary_data["monthly_breakdown"].append({
                        "Month": m_name,
                        "Approved": int(d_nums[0]),
                        "Rejected": int(d_nums[1]),
                        "Hold": int(d_nums[2]),
                        "Process": int(d_nums[3]),
                        "Total": int(d_nums[4]) if len(d_nums) >= 5 else sum(int(x) for x in d_nums[:4])
                    })

    if summary_data["total_samples"] == 0 and summary_data["monthly_breakdown"]:
        m_df = pd.DataFrame(summary_data["monthly_breakdown"])
        summary_data["approved"] = m_df["Approved"].sum()
        summary_data["rejected"] = m_df["Rejected"].sum()
        summary_data["hold"] = m_df["Hold"].sum()
        summary_data["on_process"] = m_df["Process"].sum()
        summary_data["total_samples"] = m_df["Total"].sum()
        if summary_data["total_samples"] > 0:
            summary_data["approval_ratio"] = (summary_data["approved"] / summary_data["total_samples"]) * 100

    return summary_data

def render_sample_summary_dashboard(sheet_name, cfg):
    sid = cfg["id"]
    try:
        tabs = list_tabs(sid)
        titles = [t for t, _ in tabs]
    except Exception as e:
        show_access_error(e)
        st.stop()

    pref_tab = next((find_tab(titles, t) for t in cfg.get("data_tabs", []) if find_tab(titles, t)), titles[0] if titles else None)
    raw_values = load_tab_values(sid, pref_tab)
    parsed = parse_sample_summary_sheet(raw_values)

    with st.sidebar:
        st.markdown('<div class="sidebar-filter-card">', unsafe_allow_html=True)
        st.markdown("### 🔍 Sample Dashboard Filters")

        m_list = [m["Month"] for m in parsed["monthly_breakdown"]] if parsed["monthly_breakdown"] else [f"{m}-26" for m in MONTHS[:9]]
        month_opts = ["All"] + m_list
        if "s_month" not in st.session_state: st.session_state["s_month"] = ["All"]
        sel_months = st.multiselect("Month", options=month_opts, key="s_month", on_change=handle_smart_all_filter, args=("s_month",))

        stat_opts = ["All", "APPROVED", "REJECTED", "HOLD", "ON PROCESS"]
        if "s_stat" not in st.session_state: st.session_state["s_stat"] = ["All"]
        sel_status = st.multiselect("Status Filter", options=stat_opts, key="s_stat", on_change=handle_smart_all_filter, args=("s_stat",))

        risk_opts = ["All", "On-Time (0 Days)", "Overdue (>0 Days)"]
        sel_risk = st.selectbox("Delay Risk Assessment", risk_opts)

        if st.button("🔄 Refresh Data", key="samp_ref"):
            st.cache_data.clear()
            st.rerun()
        st.markdown('</div>', unsafe_allow_html=True)

    st.markdown(
        f"""<div class="dashboard-hero">
        <h2>🔬 {sheet_name} · Executive Process & QA Hub</h2>
        <p>Active Source: <b>{html.escape(pref_tab)}</b> · Real-Time Sampling & QA Workflow Monitoring</p>
        </div>""",
        unsafe_allow_html=True
    )

    m_records = parsed["monthly_breakdown"]
    df_m = pd.DataFrame(m_records) if m_records else pd.DataFrame(columns=["Month", "Approved", "Rejected", "Hold", "Process", "Total"])
    if not df_m.empty and "All" not in sel_months and sel_months:
        df_m = df_m[df_m["Month"].isin(sel_months)]

    tot_s = df_m["Total"].sum() if (not df_m.empty and df_m["Total"].sum() > 0) else parsed["total_samples"]
    app_s = df_m["Approved"].sum() if (not df_m.empty and df_m["Approved"].sum() > 0) else parsed["approved"]
    rej_s = df_m["Rejected"].sum() if (not df_m.empty and df_m["Rejected"].sum() > 0) else parsed["rejected"]
    hld_s = df_m["Hold"].sum() if (not df_m.empty and df_m["Hold"].sum() > 0) else parsed["hold"]
    prc_s = df_m["Process"].sum() if (not df_m.empty and df_m["Process"].sum() > 0) else parsed["on_process"]
    ratio = (app_s / tot_s * 100) if tot_s > 0 else parsed["approval_ratio"]

    k1, k2, k3, k4, k5, k6 = st.columns(6)
    k1.metric("Total Samples", fmt(tot_s) + " Pcs")
    k2.metric("Approved", fmt(app_s) + " Pcs")
    k3.metric("Approval Ratio", f"{ratio:.1f}%")
    k4.metric("Rejected", fmt(rej_s) + " Pcs")
    k5.metric("On Hold", fmt(hld_s) + " Pcs")
    k6.metric("In Process", fmt(prc_s) + " Pcs")

    st.markdown("---")

    # --- EXACTLY 2 COMBINED TABS ---
    t1, t2 = st.tabs([
        "📊 Sample Pipeline & Approval Health",
        "📋 Monthly Breakdown & Workflow Matrix"
    ])

    with t1:
        st.markdown('<div class="section-badge">📊 Sample Funnel & Approval Ratio</div>', unsafe_allow_html=True)
        c1, c2 = st.columns([1.3, 1])

        with c1:
            if not df_m.empty:
                fig_m = go.Figure()
                fig_m.add_trace(go.Bar(name="Approved", x=df_m["Month"], y=df_m["Approved"], marker_color="#059669"))
                fig_m.add_trace(go.Bar(name="Rejected", x=df_m["Month"], y=df_m["Rejected"], marker_color="#dc2626"))
                fig_m.add_trace(go.Bar(name="Hold", x=df_m["Month"], y=df_m["Hold"], marker_color="#f59e0b"))
                fig_m.add_trace(go.Bar(name="In Process", x=df_m["Month"], y=df_m["Process"], marker_color="#2563eb"))
                fig_m.update_layout(title="Monthly Sample Status Volume (Pcs)", barmode="stack", xaxis_title="Month")
                st.plotly_chart(style_fig(fig_m, 350), use_container_width=True)
            else:
                st.info("Monthly progression data is current blank in sheet.")

        with c2:
            status_summary = pd.DataFrame({
                "Status": ["Approved", "Rejected", "On Hold", "In Process"],
                "Count": [app_s, rej_s, hld_s, prc_s]
            })
            fig_pie = px.pie(
                status_summary,
                names="Status",
                values="Count",
                title="Sampling Outcome Share",
                hole=0.48,
                color="Status",
                color_discrete_map={"Approved": "#059669", "Rejected": "#dc2626", "On Hold": "#f59e0b", "In Process": "#2563eb"}
            )
            st.plotly_chart(style_fig(fig_pie, 350), use_container_width=True)

        st.markdown("#### 📋 Sampling QA Process Health Summary")
        summary_tbl = pd.DataFrame([{
            "Category": "All Samples",
            "Total Inward": tot_s,
            "Approved (Passed)": app_s,
            "Rejected": rej_s,
            "Hold": hld_s,
            "Active In Process": prc_s,
            "Pass Ratio (%)": f"{ratio:.1f}%"
        }])
        st.dataframe(summary_tbl, use_container_width=True, hide_index=True)

    with t2:
        st.markdown('<div class="section-badge">📅 Monthly Detailed Progression</div>', unsafe_allow_html=True)
        if not df_m.empty:
            df_display = df_m.copy()
            df_display["Approval %"] = df_display.apply(lambda r: f"{(r['Approved'] / r['Total'] * 100):.1f}%" if r["Total"] > 0 else "0.0%", axis=1)

            tot_row = pd.DataFrame([{
                "Month": "GRAND TOTAL",
                "Approved": df_display["Approved"].sum(),
                "Rejected": df_display["Rejected"].sum(),
                "Hold": df_display["Hold"].sum(),
                "Process": df_display["Process"].sum(),
                "Total": df_display["Total"].sum(),
                "Approval %": f"{(df_display['Approved'].sum() / df_display['Total'].sum() * 100):.1f}%" if df_display["Total"].sum() > 0 else "0.0%"
            }])
            df_display = pd.concat([df_display, tot_row], ignore_index=True)

            st.dataframe(
                df_display.style.format({
                    "Approved": "{:,.0f}",
                    "Rejected": "{:,.0f}",
                    "Hold": "{:,.0f}",
                    "Process": "{:,.0f}",
                    "Total": "{:,.0f}"
                }),
                use_container_width=True,
                hide_index=True
            )
        else:
            st.info("Monthly progression data is current blank in sheet.")

        with st.expander("📄 View Source Sheet Raw Matrix"):
            if raw_values:
                df_src = pd.DataFrame(raw_values).fillna("")
                st.dataframe(df_src, use_container_width=True, hide_index=True)

# -----------------------------------------------------------------------------
# 7. MAIN ROUTER
# -----------------------------------------------------------------------------
def main():
    with st.sidebar:
        st.markdown('<div class="sidebar-filter-card">', unsafe_allow_html=True)
        st.markdown("### 🗂️ Workspace Selection")
        selected = st.selectbox("Active Google Sheet", list(SHEET_REGISTRY.keys()), key="ws_choice")
        st.markdown('</div>', unsafe_allow_html=True)

    cfg = SHEET_REGISTRY[selected]
    kind = cfg.get("type", "tracker")

    if kind == "tracker":
        render_tracker(selected, cfg["id"])
    elif kind == "overview_fabricators":
        render_fabricator_dashboard(selected, cfg)
    elif kind == "sample_summary":
        render_sample_summary_dashboard(selected, cfg)

if __name__ == "__main__":
    main()
