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

# Dropdown mein dikhne wali Google Sheets
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

# -----------------------------------------------------------------------------
# 5. MASTER SHEET DASHBOARD VIEWS
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
        st.plotly_chart(px.pie(q, names="Status", values="Qty", hole=.45, title="ORDER FULFILLMENT RATIO (RECEIVED vs PENDING)", color_discrete_sequence=["#059669", "#DC2626"]), use_container_width=True)

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
# 6. GENERIC TABLE UTILITIES
# -----------------------------------------------------------------------------
PALETTE = ["#2563eb", "#059669", "#f59e0b", "#dc2626", "#7c3aed", "#0891b2", "#db2777", "#65a30d", "#ea580c", "#475569"]
px.defaults.color_discrete_sequence = PALETTE

def show_access_error(e):
    email = ""
    try:
        email = st.secrets["gcp_service_account"]["client_email"]
    except Exception:
        pass
    st.error("Could not open this Google Sheet. Share it with service account: " + (f"**{email}**" if email else "email from secrets"))

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

def style_fig(fig, height=380):
    fig.update_layout(
        height=height,
        margin=dict(l=10, r=10, t=50, b=10),
        legend_title_text="",
        font=dict(size=12),
        title_font_size=15
    )
    return fig

# -----------------------------------------------------------------------------
# 7. PARSER & DASHBOARD FOR "MONTHWISE SUMMARY" (FABRICATOR REPORT)
# -----------------------------------------------------------------------------
def parse_monthwise_summary_sheet(values):
    """
    Parses the multi-block grid layout in 'MONTHWISE SUMMARY' tab:
    Position Of Stock <NAME> followed by columns:
    [Month, fabric issue (mtr), Pcs Under Production, RCVD, Remaining, monthly incoming]
    """
    records = []
    if not values:
        return pd.DataFrame()

    for r_idx, row in enumerate(values):
        for c_idx, cell in enumerate(row):
            cell_str = str(cell).strip()
            if re.search(r"position\s*of\s*stock", cell_str, re.I):
                fab_name = re.sub(r"position\s*of\s*stock\s*[:\-]?", "", cell_str, flags=re.I).strip()
                fab_name = re.sub(r"^[(\[]|[)\]]$", "", fab_name).strip()
                if "ALL OVER" in fab_name.upper():
                    fab_name = "ALL OVER (CONSOLIDATED)"
                if not fab_name:
                    fab_name = "UNKNOWN"

                # Find header row right below title
                header_row_idx = None
                for scan_r in range(r_idx + 1, min(r_idx + 4, len(values))):
                    scan_row = values[scan_r]
                    if c_idx < len(scan_row) and re.search(r"month", str(scan_row[c_idx]), re.I):
                        header_row_idx = scan_r
                        break

                if header_row_idx is None:
                    continue

                h_row = values[header_row_idx]
                col_map = {}
                for offset in range(0, 8):
                    curr_col = c_idx + offset
                    if curr_col < len(h_row):
                        h_val = str(h_row[curr_col]).strip().lower()
                        if not h_val and offset > 4:
                            break
                        if "month" in h_val and "month" not in col_map:
                            col_map["month"] = curr_col
                        elif ("fabric" in h_val or "issue" in h_val or "mtr" in h_val) and "fabric_issue" not in col_map:
                            col_map["fabric_issue"] = curr_col
                        elif ("under" in h_val or "production" in h_val or "pcs" in h_val) and "production" not in col_map:
                            col_map["production"] = curr_col
                        elif ("rcvd" in h_val or "received" in h_val) and "received" not in col_map:
                            col_map["received"] = curr_col
                        elif ("remain" in h_val or "pending" in h_val) and "remaining" not in col_map:
                            col_map["remaining"] = curr_col
                        elif "incoming" in h_val and "incoming" not in col_map:
                            col_map["incoming"] = curr_col

                if "month" not in col_map:
                    continue

                # Read data rows
                for data_r in range(header_row_idx + 1, len(values)):
                    d_row = values[data_r]
                    if c_idx >= len(d_row):
                        break
                    m_val = str(d_row[c_idx]).strip()
                    if not m_val:
                        continue
                    if re.search(r"^total", m_val, re.I):
                        break
                    if re.search(r"position\s*of\s*stock", m_val, re.I):
                        break
                    if not re.search(r"(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)", m_val, re.I):
                        continue

                    def get_num(key):
                        idx = col_map.get(key)
                        if idx is not None and idx < len(d_row):
                            val = d_row[idx]
                            return float(num(pd.Series([val])).iloc[0])
                        return 0.0

                    issue_val = get_num("fabric_issue")
                    prod_val = get_num("production")
                    rcvd_val = get_num("received")
                    rem_val = get_num("remaining")
                    inc_val = get_num("incoming")

                    # Status tagging
                    if prod_val == 0 and issue_val == 0:
                        status = "No Orders"
                    elif rem_val == 0 and prod_val > 0:
                        status = "Completed (100%)"
                    elif rcvd_val > 0 and rem_val > 0:
                        status = "In Progress"
                    elif rcvd_val == 0 and prod_val > 0:
                        status = "Pending / Not Started"
                    else:
                        status = "In Progress" if rem_val > 0 else "Completed (100%)"

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
        # Standardize month sorting
        month_order = [
            "April-26", "May-26", "June-26", "July-26", "August-26", "September-26",
            "October-26", "November-26", "December-26", "January-27", "February-27", "March-27"
        ]
        df["Month_Order"] = df["Month"].apply(lambda m: month_order.index(m) if m in month_order else 99)
        df = df.sort_values(["Month_Order", "Fabricator"]).drop(columns=["Month_Order"])
    return df

def render_fabricator_sheet(sheet_name, cfg):
    sid = cfg["id"]
    try:
        tabs = list_tabs(sid)
        titles = [t for t, _ in tabs]
    except Exception as e:
        show_access_error(e)
        st.stop()

    summary_tab = find_tab(titles, "MONTHWISE SUMMARY")
    if not summary_tab:
        summary_tab = titles[0] if titles else "MONTHWISE SUMMARY"

    try:
        raw_values = load_tab_values(sid, summary_tab)
    except Exception as e:
        show_access_error(e)
        st.stop()

    if not raw_values:
        st.warning(f"Tab '{summary_tab}' empty hai.")
        st.stop()

    df_parsed = parse_monthwise_summary_sheet(raw_values)
    if df_parsed.empty:
        st.error("Sheet se Fabricator summary data extract nahi ho saka. Format verify karein.")
        st.stop()

    # Separate 'ALL OVER (CONSOLIDATED)' from individual fabricators
    is_consolidated = df_parsed["Fabricator"].str.contains("ALL OVER", case=False, na=False)
    df_consolidated = df_parsed[is_consolidated].copy()
    df_vendors = df_parsed[~is_consolidated].copy()

    # If all records are consolidated, fallback
    df_work = df_vendors if not df_vendors.empty else df_consolidated

    # -------------------------------------------------------------------------
    # SIDEBAR FILTERS (Fabricator Name, Month, Production Status)
    # -------------------------------------------------------------------------
    with st.sidebar:
        st.markdown("### 🔎 Fabricator Filters")

        # 1. Fabricator Filter
        all_fabs = sorted(df_work["Fabricator"].unique())
        fab_opts = ["All"] + all_fabs
        sel_fabs = st.multiselect("Fabricator Name", options=fab_opts, default=["All"], key="fab_filter_name")

        # 2. Month Filter
        all_months = list(dict.fromkeys(df_work["Month"].tolist()))
        month_opts = ["All"] + all_months
        sel_months = st.multiselect("Month", options=month_opts, default=["All"], key="fab_filter_month")

        # 3. Production Status Filter
        all_statuses = ["Completed (100%)", "In Progress", "Pending / Not Started", "No Orders"]
        status_opts = ["All"] + [s for s in all_statuses if s in df_work["Production Status"].values]
        sel_status = st.multiselect("Production Status", options=status_opts, default=["All"], key="fab_filter_status")

        hide_zero_prod = st.checkbox("Hide Zero-Production Rows", value=True, help="Aise months hide karein jisme production start nahi hui")

        if st.button("🔄 Refresh Data", key="fab_refresh_btn"):
            st.cache_data.clear()
            st.rerun()

    # Filter Application
    filtered = df_work.copy()
    if "All" not in sel_fabs and sel_fabs:
        filtered = filtered[filtered["Fabricator"].isin(sel_fabs)]
    if "All" not in sel_months and sel_months:
        filtered = filtered[filtered["Month"].isin(sel_months)]
    if "All" not in sel_status and sel_status:
        filtered = filtered[filtered["Production Status"].isin(sel_status)]
    if hide_zero_prod:
        filtered = filtered[(filtered["Pcs Under Production"] > 0) | (filtered["Fabric Issue (mtr)"] > 0)]

    # -------------------------------------------------------------------------
    # MAIN DASHBOARD HEADER
    # -------------------------------------------------------------------------
    st.markdown(
        f"""<div class="dashboard-hero">
        <h2>🧵 {sheet_name} · Executive Performance Dashboard</h2>
        <p>Live Source Tab: <b>{html.escape(summary_tab)}</b> · {filtered['Fabricator'].nunique():,} Active Fabricators · {len(filtered):,} Month-Vendor Records</p>
        </div>""",
        unsafe_allow_html=True
    )

    if filtered.empty:
        st.warning("Selected filters ke saath koi record match nahi hua. Kripya sidebar se filter reset karein.")
        st.stop()

    # -------------------------------------------------------------------------
    # EXECUTIVE KPI CARDS
    # -------------------------------------------------------------------------
    tot_fabric = filtered["Fabric Issue (mtr)"].sum()
    tot_prod = filtered["Pcs Under Production"].sum()
    tot_rcvd = filtered["RCVD (Pcs)"].sum()
    tot_rem = filtered["Remaining (Pcs)"].sum()
    tot_incoming = filtered["Monthly Incoming (Pcs)"].sum()

    fulfillment_rate = (tot_rcvd / tot_prod * 100) if tot_prod > 0 else 0.0
    avg_fabric_pc = (tot_fabric / tot_prod) if tot_prod > 0 else 0.0

    st.markdown("#### 📌 Key Performance Indicators (MONTHWISE SUMMARY)")
    k1, k2, k3, k4 = st.columns(4)
    k1.metric("Total Fabric Issued", f"{tot_fabric:,.1f} Mtr")
    k2.metric("Pcs Under Production", fmt(tot_prod))
    k3.metric("Received Pcs (RCVD)", fmt(tot_rcvd))
    k4.metric("Remaining Backlog", fmt(tot_rem))

    k5, k6, k7, k8 = st.columns(4)
    k5.metric("Overall Fulfillment %", f"{fulfillment_rate:.1f}%")
    k6.metric("Total Monthly Incoming", fmt(tot_incoming))
    k7.metric("Avg Fabric / Pc", f"{avg_fabric_pc:.2f} Mtr")
    k8.metric("Active Vendors Filtered", f"{filtered['Fabricator'].nunique():,}")

    st.markdown("---")

    # -------------------------------------------------------------------------
    # DASHBOARD TABS
    # -------------------------------------------------------------------------
    tab_overview, tab_comparison, tab_table, tab_consolidated = st.tabs([
        "📈 Production & Status Trends",
        "👥 Fabricator Comparison",
        "📋 Monthly Breakdown Table",
        "🏛️ Consolidated All-Over Stock"
    ])

    with tab_overview:
        c1, c2 = st.columns([1.3, 1])
        with c1:
            # Monthly Production vs RCVD vs Remaining Trend
            m_agg = filtered.groupby("Month", as_index=False).agg({
                "Pcs Under Production": "sum",
                "RCVD (Pcs)": "sum",
                "Remaining (Pcs)": "sum"
            })
            # Preserve month chronological order
            month_order = [
                "April-26", "May-26", "June-26", "July-26", "August-26", "September-26",
                "October-26", "November-26", "December-26", "January-27", "February-27", "March-27"
            ]
            m_agg["order"] = m_agg["Month"].apply(lambda m: month_order.index(m) if m in month_order else 99)
            m_agg = m_agg.sort_values("order").drop(columns=["order"])

            fig_trend = go.Figure()
            fig_trend.add_trace(go.Bar(name="Under Production", x=m_agg["Month"], y=m_agg["Pcs Under Production"], marker_color="#2563eb"))
            fig_trend.add_trace(go.Bar(name="Received (RCVD)", x=m_agg["Month"], y=m_agg["RCVD (Pcs)"], marker_color="#059669"))
            fig_trend.add_trace(go.Bar(name="Remaining", x=m_agg["Month"], y=m_agg["Remaining (Pcs)"], marker_color="#dc2626"))
            fig_trend.update_layout(
                title="Monthly Production vs Delivery vs Remaining (Pcs)",
                barmode="group",
                xaxis_title="Month",
                yaxis_title="Pieces"
            )
            st.plotly_chart(style_fig(fig_trend, 400), use_container_width=True)

        with c2:
            # Production Status Ratio
            status_counts = filtered["Production Status"].value_counts().reset_index()
            status_counts.columns = ["Status", "Records"]
            status_colors = {
                "Completed (100%)": "#059669",
                "In Progress": "#f59e0b",
                "Pending / Not Started": "#dc2626",
                "No Orders": "#94a3b8"
            }
            fig_status = px.pie(
                status_counts,
                names="Status",
                values="Records",
                title="Vendor Orders Status Breakdown",
                hole=0.45,
                color="Status",
                color_discrete_map=status_colors
            )
            st.plotly_chart(style_fig(fig_status, 400), use_container_width=True)

        st.markdown("---")

        c3, c4 = st.columns(2)
        with c3:
            # Fabric Issue vs Production Correlation
            m_fab = filtered.groupby("Month", as_index=False).agg({
                "Fabric Issue (mtr)": "sum",
                "Pcs Under Production": "sum"
            })
            m_fab["order"] = m_fab["Month"].apply(lambda m: month_order.index(m) if m in month_order else 99)
            m_fab = m_fab.sort_values("order").drop(columns=["order"])

            fig_dual = make_subplots(specs=[[{"secondary_y": True}]])
            fig_dual.add_trace(
                go.Bar(name="Fabric Issue (mtr)", x=m_fab["Month"], y=m_fab["Fabric Issue (mtr)"], marker_color="#0891b2"),
                secondary_y=False
            )
            fig_dual.add_trace(
                go.Scatter(name="Under Production (Pcs)", x=m_fab["Month"], y=m_fab["Pcs Under Production"], mode="lines+markers", line=dict(color="#ea580c", width=3)),
                secondary_y=True
            )
            fig_dual.update_layout(title="Fabric Issued (Mtrs) vs Production Output (Pcs)")
            fig_dual.update_yaxes(title_text="Fabric Issued (Mtr)", secondary_y=False)
            fig_dual.update_yaxes(title_text="Pieces Under Production", secondary_y=True)
            st.plotly_chart(style_fig(fig_dual, 380), use_container_width=True)

        with c4:
            # Fabricator Volume Share
            fab_share = filtered.groupby("Fabricator", as_index=False)["Pcs Under Production"].sum().sort_values("Pcs Under Production", ascending=False)
            fig_fab_pie = px.pie(
                fab_share,
                names="Fabricator",
                values="Pcs Under Production",
                title="Fabricator Production Volume Share",
                hole=0.45
            )
            st.plotly_chart(style_fig(fig_fab_pie, 380), use_container_width=True)

    with tab_comparison:
        st.subheader("👥 Fabricator Performance & Backlog Analysis")
        fab_summary = filtered.groupby("Fabricator", as_index=False).agg({
            "Fabric Issue (mtr)": "sum",
            "Pcs Under Production": "sum",
            "RCVD (Pcs)": "sum",
            "Remaining (Pcs)": "sum",
            "Monthly Incoming (Pcs)": "sum"
        })
        fab_summary["Fulfillment %"] = fab_summary.apply(
            lambda r: f"{(r['RCVD (Pcs)'] / r['Pcs Under Production'] * 100):.1f}%" if r["Pcs Under Production"] > 0 else "0.0%",
            axis=1
        )
        fab_summary["Avg Mtr/Pc"] = fab_summary.apply(
            lambda r: f"{(r['Fabric Issue (mtr)'] / r['Pcs Under Production']):.2f}" if r["Pcs Under Production"] > 0 else "0.00",
            axis=1
        )
        fab_summary = fab_summary.sort_values("Pcs Under Production", ascending=False)

        # Stacked fulfillment chart
        fig_stack = go.Figure()
        fig_stack.add_trace(go.Bar(
            name="Received (RCVD)",
            x=fab_summary["Fabricator"],
            y=fab_summary["RCVD (Pcs)"],
            marker_color="#059669"
        ))
        fig_stack.add_trace(go.Bar(
            name="Pending Backlog",
            x=fab_summary["Fabricator"],
            y=fab_summary["Remaining (Pcs)"],
            marker_color="#dc2626"
        ))
        fig_stack.update_layout(
            barmode="stack",
            title="Fabricator Received vs Pending Backlog (Pcs)",
            xaxis_title="Fabricator",
            yaxis_title="Pcs"
        )
        st.plotly_chart(style_fig(fig_stack, 390), use_container_width=True)

        st.markdown("#### 📋 Fabricator Scorecard Summary")
        # Add grand total row
        tot_summary_row = pd.DataFrame([{
            "Fabricator": "TOTAL",
            "Fabric Issue (mtr)": fab_summary["Fabric Issue (mtr)"].sum(),
            "Pcs Under Production": fab_summary["Pcs Under Production"].sum(),
            "RCVD (Pcs)": fab_summary["RCVD (Pcs)"].sum(),
            "Remaining (Pcs)": fab_summary["Remaining (Pcs)"].sum(),
            "Monthly Incoming (Pcs)": fab_summary["Monthly Incoming (Pcs)"].sum(),
            "Fulfillment %": f"{(fab_summary['RCVD (Pcs)'].sum() / fab_summary['Pcs Under Production'].sum() * 100):.1f}%" if fab_summary["Pcs Under Production"].sum() > 0 else "0.0%",
            "Avg Mtr/Pc": f"{(fab_summary['Fabric Issue (mtr)'].sum() / fab_summary['Pcs Under Production'].sum()):.2f}" if fab_summary["Pcs Under Production"].sum() > 0 else "0.00"
        }])
        fab_summary_display = pd.concat([fab_summary, tot_summary_row], ignore_index=True)

        st.dataframe(
            fab_summary_display.style.format({
                "Fabric Issue (mtr)": "{:,.2f}",
                "Pcs Under Production": "{:,.0f}",
                "RCVD (Pcs)": "{:,.0f}",
                "Remaining (Pcs)": "{:,.0f}",
                "Monthly Incoming (Pcs)": "{:,.0f}"
            }),
            use_container_width=True,
            hide_index=True
        )

    with tab_table:
        st.subheader("📋 Filtered Month-by-Month Production Records")
        display_df = filtered[[
            "Fabricator", "Month", "Fabric Issue (mtr)", "Pcs Under Production",
            "RCVD (Pcs)", "Remaining (Pcs)", "Monthly Incoming (Pcs)", "Production Status"
        ]].copy()

        st.dataframe(
            display_df.style.format({
                "Fabric Issue (mtr)": "{:,.2f}",
                "Pcs Under Production": "{:,.0f}",
                "RCVD (Pcs)": "{:,.0f}",
                "Remaining (Pcs)": "{:,.0f}",
                "Monthly Incoming (Pcs)": "{:,.0f}"
            }),
            use_container_width=True,
            hide_index=True
        )

    with tab_consolidated:
        st.subheader("🏛️ Consolidated Position Of Stock (ALL OVER)")
        if not df_consolidated.empty:
            c_display = df_consolidated[[
                "Month", "Fabric Issue (mtr)", "Pcs Under Production",
                "RCVD (Pcs)", "Remaining (Pcs)", "Monthly Incoming (Pcs)"
            ]].copy()

            tot_c = pd.DataFrame([{
                "Month": "GRAND TOTAL",
                "Fabric Issue (mtr)": c_display["Fabric Issue (mtr)"].sum(),
                "Pcs Under Production": c_display["Pcs Under Production"].sum(),
                "RCVD (Pcs)": c_display["RCVD (Pcs)"].sum(),
                "Remaining (Pcs)": c_display["Remaining (Pcs)"].sum(),
                "Monthly Incoming (Pcs)": c_display["Monthly Incoming (Pcs)"].sum()
            }])
            c_display_tot = pd.concat([c_display, tot_c], ignore_index=True)

            st.dataframe(
                c_display_tot.style.format({
                    "Fabric Issue (mtr)": "{:,.2f}",
                    "Pcs Under Production": "{:,.0f}",
                    "RCVD (Pcs)": "{:,.0f}",
                    "Remaining (Pcs)": "{:,.0f}",
                    "Monthly Incoming (Pcs)": "{:,.0f}"
                }),
                use_container_width=True,
                hide_index=True
            )
        else:
            st.info("Consolidated 'ALL OVER' table sheet me detect nahi hua.")

# -----------------------------------------------------------------------------
# 8. SIMPLE OVERVIEW SHEET HANDLER
# -----------------------------------------------------------------------------
def split_table(values):
    if not values:
        return pd.DataFrame(), [], pd.DataFrame()
    hdr = 0
    header = values[hdr]
    body = values[hdr + 1:]
    df = pd.DataFrame(body, columns=header).astype(str)
    return df, [], pd.DataFrame()

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
# 9. MAIN APPLICATION ROUTER
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
