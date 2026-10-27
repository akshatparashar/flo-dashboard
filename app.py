import re
import pandas as pd
import plotly.express as px
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

SHEET_ID = "1wBo0zF2wlqBzY5ZQaX5CPjCOedORwg_1Eh01vje5KFU"
DEFAULT_TAB = "CONFIRMATION SHEET"
MONTHS = ["April", "May", "June", "July", "August", "September",
          "October", "November", "December", "January", "February", "March"]

CATEGORIES_LIST = ["CO-ORD SET", "KURTA PANT", "TOP", "KURTA PANT DUPATTA", "DRESS", "KAFTAN", "KURTA"]

# Theme preference (presentation only; dashboard calculations remain unchanged)
if "dashboard_dark_mode" not in st.session_state:
    st.session_state.dashboard_dark_mode = False

with st.sidebar:
    st.markdown("### 🎨 Appearance")
    st.toggle("Dark mode", key="dashboard_dark_mode", help="Dashboard ke colors badalne ke liye. Isse calculations ya filters nahi badlenge.")

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
[data-testid="stAlert"] {{ border-radius: 12px; }}
hr {{ border-color: {BORDER}; }}
h1, h2, h3 {{ letter-spacing: -.025em; }}
.dashboard-hero {{ background: linear-gradient(120deg, {'#16243b' if DARK_MODE else '#e8f1ff'}, {'#172d43' if DARK_MODE else '#ffffff'}); border: 1px solid {BORDER}; border-radius: 18px; padding: 22px 26px; margin: 0 0 18px 0; }}
.dashboard-hero p {{ color: {MUTED}; margin: 4px 0 0 0; }}
</style>
""", unsafe_allow_html=True)

# -----------------------------------------------------------------------------
# 2. HELPER FUNCTIONS & NUMERIC SANITIZATION
# -----------------------------------------------------------------------------
def col_index(letter):
    n = 0
    for c in letter.upper():
        n = n * 26 + ord(c) - 64
    return n - 1

def get_col_by_letter(df, letter):
    idx = col_index(letter)
    if idx < len(df.columns):
        return df.columns[idx]
    return None

def num(s):
    if not isinstance(s, pd.Series):
        s = pd.Series(s)
    text = s.astype("string").str.strip()
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
    return pd.to_datetime(s, errors="coerce", dayfirst=True)

# -----------------------------------------------------------------------------
# 3. GOOGLE SHEETS AUTHENTICATION & LIVE DATA LOAD
# -----------------------------------------------------------------------------
@st.cache_data(ttl=300, show_spinner="Google Sheet se live data load ho raha hai...")
def load_sheet():
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
    gc = gspread.authorize(creds)
    sheet_id = st.secrets.get("spreadsheet_id", SHEET_ID)
    book = gc.open_by_key(sheet_id)
    
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

    header_i = 4 if len(values) > 4 else 0
        
    headers = []
    for i, v in enumerate(values[header_i]):
        name = str(v).strip() or f"Col_{i+1}"
        if name in headers:
            name = f"{name}_{i+1}"
        headers.append(name)
        
    rows = values[header_i + 1:]
    width = len(headers)
    rows = [(r + [""] * max(0, width - len(r)))[:width] for r in rows]
    data = pd.DataFrame(rows, columns=headers)
    data.attrs["tab"] = ws.title
    data.attrs["header_row"] = header_i + 1
    return data

# -----------------------------------------------------------------------------
# 4. DATA PREPARATION (WITH FULL ROW PRESERVATION)
# -----------------------------------------------------------------------------
def prepare(raw):
    d = raw.copy()
    
    letter_mapping = {
        "date": "B",                  # Order Date
        "designer": "C",              # Designer's Name
        "type": "D",                  # Order Type
        "category": "F",              # Category / Sample Product
        "qty": "J",                   # Sheet Order Qty (J)
        "client": "N",                # Client Name
        "required_date": "O",         # Delivery Date
        "fabric_order_date": "P",     # Fabric Order Date
        "planned_fabric_date": "S",  # Planned Date
        "follow_up": "T",             # Follow Up
        "fabric_received_date": "U",  # Fabric Received Date
        "fabricator": "AA",           # Fabricator's
        "delay": "AH",                # Delay Days (AH)
        "production": "AS",           # IN PRODUCTION PCS (Column AS)
        "received": "AT",             # RECEIVED PCS (Column AT)
        "pending": "AU",              # PENDING PCS (Column AU)
        "status": "AX",               # Status (Column AX)
    }
    
    for key, letter in letter_mapping.items():
        c_name = get_col_by_letter(d, letter)
        d[key] = d[c_name] if c_name is not None else ""

    for c in ["designer", "type", "category", "client", "fabricator", "status", "follow_up"]:
        d[c] = d[c].astype(str).str.strip()
        d.loc[d[c].str.lower().isin(["nan", "none"]), c] = ""
        
    for c in ["qty", "production", "received", "pending"]:
        d[c] = num(d[c])
        
    d["delay"] = clean_delay_days(d["delay"])
        
    for c in ["date", "required_date", "fabric_order_date", "planned_fabric_date", "fabric_received_date"]:
        d[c] = date_col(d[c])

    # Rule AU == 0 -> Effective Order Qty = Received Qty
    d["pending_explicit_zero"] = d["pending"].astype(str).str.strip().str.replace(",", "", regex=False).isin(["0", "0.0", "0.00"]) | (d["pending"] == 0)
    d["effective_qty"] = d["qty"]
    fully_received = d["pending_explicit_zero"] & (d["received"] > 0)
    d.loc[fully_received, "effective_qty"] = d.loc[fully_received, "received"]

    d["month"] = d["date"].dt.month_name()
    d["type_clean"] = d["type"].str.upper()
    d["category_clean"] = d["category"].str.upper().str.strip()
    
    # PRESERVE ALL ROWS WITH ANY NON-ZERO METRIC OR TEXT DATA TO MATCH 151,844 & 90,376 ACCURATELY
    d = d[
        (d["qty"] > 0) | 
        (d["production"] > 0) | 
        (d["received"] > 0) | 
        (d["pending"] > 0) | 
        (d["designer"].ne("")) | 
        (d["client"].ne("")) | 
        d["date"].notna()
    ].copy()
    
    return d

def filters(d):
    st.sidebar.header("🔎 Filters")
    month_values = [m for m in MONTHS if m in d["month"].dropna().astype(str).unique()]
    
    def select(label, values, key):
        opts = ["ALL"] + sorted({str(v) for v in values if str(v).strip() and str(v) != "nan"})
        return st.sidebar.selectbox(label, opts, key=key)
        
    month = st.sidebar.selectbox("Month", ["ALL"] + month_values)
    typ = select("Order Type", d["type_clean"].unique(), "type")
    cat = select("Category", d["category_clean"].unique(), "category")
    des = select("Designer", d["designer"].unique(), "designer")
    cli = select("Client", d["client"].unique(), "client")
    fab = select("Fabricator", d["fabricator"].unique(), "fabricator")
    risk = st.sidebar.selectbox("Delay Risk", ["ALL", "ON-TIME", "OVERDUE (>0 DAYS)"])
    
    out = d.copy()
    if month != "ALL": out = out[out["month"] == month]
    if typ != "ALL": out = out[out["type_clean"].str.contains(typ, case=False, na=False)]
    if cat != "ALL": out = out[out["category_clean"] == cat]
    if des != "ALL": out = out[out["designer"].str.upper() == des.upper()]
    if cli != "ALL": out = out[out["client"].str.upper() == cli.upper()]
    if fab != "ALL": out = out[out["fabricator"].str.upper() == fab.upper()]
    if risk == "ON-TIME": out = out[out["delay"] <= 0]
    if risk == "OVERDUE (>0 DAYS)": out = out[out["delay"] > 0]
    return out

def metrics(items):
    cols = st.columns(len(items))
    for c, (label, value) in zip(cols, items):
        c.metric(label, value)

def fmt(x):
    return f"{x:,.0f}"

# -----------------------------------------------------------------------------
# 5. DASHBOARD VIEWS & REQUIRED TABLES
# -----------------------------------------------------------------------------

# --- TAB 0: EXECUTIVE OVERVIEW ---
def overview(d):
    st.subheader("Executive Overview")
    metrics([
        ("Total Designs", f"{len(d):,}"), 
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
        m = d.dropna(subset=["date"]).assign(Month=lambda x: x.date.dt.to_period("M").astype(str)).groupby("Month", as_index=False)["qty"].sum()
        if not m.empty:
            st.plotly_chart(px.bar(m, x="Month", y="qty", title="Monthly Order Quantity", text_auto=".2s"), use_container_width=True)
    with b:
        c = d[d.category_clean.ne("")].groupby("category_clean", as_index=False)["qty"].sum().sort_values("qty", ascending=False)
        if not c.empty:
            st.plotly_chart(px.bar(c, x="category_clean", y="qty", title="Category-wise Quantity", text_auto=".2s"), use_container_width=True)

    # Additional analysis (read-only insights; original KPIs and filters are retained)
    st.markdown("---")
    st.subheader("📌 Additional Business Insights")
    total_qty = float(d["qty"].sum())
    received_qty = float(d["received"].sum())
    pending_qty = float(d["pending"].sum())
    overdue_rows = d[d["delay"] > 0]
    avg_delay = overdue_rows["delay"].mean() if not overdue_rows.empty else 0.0
    fulfillment = (received_qty / (received_qty + pending_qty) * 100) if received_qty + pending_qty > 0 else 0.0
    new_qty = float(d.loc[d["type_clean"].str.contains("NEW", na=False), "qty"].sum())
    repeat_qty = float(d.loc[d["type_clean"].str.contains("REPEAT", na=False), "qty"].sum())
    repeat_share = repeat_qty / (new_qty + repeat_qty) * 100 if new_qty + repeat_qty > 0 else 0.0
    overdue_order_share = len(overdue_rows) / len(d) * 100 if len(d) else 0.0
    metrics([
        ("RECEIVED SHARE OF (AT+AU)", f"{fulfillment:.1f}%"),
        ("OVERDUE ORDER SHARE", f"{overdue_order_share:.1f}%"),
        ("AVERAGE OVERDUE DAYS", f"{avg_delay:.1f} days"),
        ("REPEAT QTY SHARE (NEW+REPEAT)", f"{repeat_share:.1f}%"),
    ])
    insight_left, insight_right = st.columns(2)

    # Composite performance score: compare several dimensions, not one metric.
    def add_performance_score(frame):
        frame = frame.copy()
        dimensions = {
            "OrderQty": 0.20, "Orders": 0.15, "ProductionPCS": 0.15,
            "ReceivedPCS": 0.20, "OnTimeRate": 0.20, "CompletionRate": 0.10,
        }
        score = pd.Series(0.0, index=frame.index)
        for column, weight in dimensions.items():
            values = pd.to_numeric(frame[column], errors="coerce").fillna(0)
            score += values.rank(method="average", pct=True) * 100 * weight
        frame["Overall Score"] = score.round(1)
        return frame

    with insight_left:
        st.markdown("#### 🧑‍🎨 Top 3 Designer Performers")
        designer_rows = d[d["designer"].astype(str).str.strip().ne("")].copy()
        if designer_rows.empty:
            st.info("Selected filters mein designer data available nahi hai.")
        else:
            designer_perf = designer_rows.groupby("designer", as_index=False).agg(
                OrderQty=("qty", "sum"), Orders=("qty", "size"),
                ProductionPCS=("production", "sum"), ReceivedPCS=("received", "sum"),
                PendingPCS=("pending", "sum"),
                OnTimeOrders=("delay", lambda values: int((values <= 0).sum())),
                OverdueOrders=("delay", lambda values: int((values > 0).sum())),
            )
            designer_perf["OnTimeRate"] = designer_perf["OnTimeOrders"] / designer_perf["Orders"].clip(lower=1) * 100
            denom = designer_perf["ReceivedPCS"] + designer_perf["PendingPCS"]
            designer_perf["CompletionRate"] = designer_perf["ReceivedPCS"].div(denom.where(denom.ne(0), 1)) * 100
            designer_perf = add_performance_score(designer_perf).sort_values(["Overall Score", "OrderQty"], ascending=False).head(3)
            display = designer_perf.rename(columns={"designer":"Designer", "OrderQty":"Order Qty", "ProductionPCS":"In Production PCS", "ReceivedPCS":"Received PCS", "PendingPCS":"Pending PCS", "OnTimeRate":"On-time %", "OverdueOrders":"Overdue Orders", "Overall Score":"Overall Score / 100"})
            display["On-time %"] = display["On-time %"].map(lambda value: f"{value:.1f}%")
            st.dataframe(display[["Designer", "Overall Score / 100", "Order Qty", "Orders", "In Production PCS", "Received PCS", "Pending PCS", "On-time %", "Overdue Orders"]], use_container_width=True, hide_index=True)
            st.plotly_chart(px.bar(designer_perf.sort_values("Overall Score"), x="Overall Score", y="designer", orientation="h", text="Overall Score", title="Top 3 Designers — Overall Score", labels={"designer":"Designer", "Overall Score":"Score / 100"}), use_container_width=True)

    with insight_right:
        st.markdown("#### 🏭 Top 3 Fabricator Performers")
        fab_rows = d[d["fabricator"].astype(str).str.strip().ne("")].copy()
        if fab_rows.empty:
            st.info("Selected filters mein fabricator data available nahi hai.")
        else:
            fab_perf = fab_rows.groupby("fabricator", as_index=False).agg(
                OrderQty=("qty", "sum"), Orders=("qty", "size"),
                ProductionPCS=("production", "sum"), ReceivedPCS=("received", "sum"),
                PendingPCS=("pending", "sum"),
                OnTimeOrders=("delay", lambda values: int((values <= 0).sum())),
                OverdueOrders=("delay", lambda values: int((values > 0).sum())),
            )
            fab_perf["OnTimeRate"] = fab_perf["OnTimeOrders"] / fab_perf["Orders"].clip(lower=1) * 100
            denom = fab_perf["ReceivedPCS"] + fab_perf["PendingPCS"]
            fab_perf["CompletionRate"] = fab_perf["ReceivedPCS"].div(denom.where(denom.ne(0), 1)) * 100
            fab_perf = add_performance_score(fab_perf).sort_values(["Overall Score", "OrderQty"], ascending=False).head(3)
            display = fab_perf.rename(columns={"fabricator":"Fabricator", "OrderQty":"Order Qty", "ProductionPCS":"In Production PCS", "ReceivedPCS":"Received PCS", "PendingPCS":"Pending PCS", "OnTimeRate":"On-time %", "OverdueOrders":"Overdue Orders", "Overall Score":"Overall Score / 100"})
            display["On-time %"] = display["On-time %"].map(lambda value: f"{value:.1f}%")
            st.dataframe(display[["Fabricator", "Overall Score / 100", "Order Qty", "Orders", "In Production PCS", "Received PCS", "Pending PCS", "On-time %", "Overdue Orders"]], use_container_width=True, hide_index=True)
            st.plotly_chart(px.bar(fab_perf.sort_values("Overall Score"), x="Overall Score", y="fabricator", orientation="h", text="Overall Score", title="Top 3 Fabricators — Overall Score", labels={"fabricator":"Fabricator", "Overall Score":"Score / 100"}), use_container_width=True)

    with st.expander("📖 How overall performance is calculated"):
        st.markdown("""
        **Overall Score (0–100)** is a comparative score within the currently selected filters, not a replacement for existing Google Sheet KPIs.

        - **20%** total order quantity (volume)
        - **15%** number of orders handled
        - **15%** in-production quantity
        - **20%** received quantity
        - **20%** on-time order rate (AH ≤ 0)
        - **10%** completion rate (AT ÷ (AT + AU))

        Each dimension is converted to a percentile rank before combining, so different units can be compared together. Top 3 is based on the combined score; order quantity breaks ties. Scores reflect only the available sheet fields and current filters, not unrecorded quality or complexity.
        """)
# --- TAB 1: DESIGNER PERFORMANCE DASHBOARD ---
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
    
    # Table 1: Designer Name | New Orders | Repeat Orders | Total Volume | Share % | Total Design Count
    des_summary_df = g[["designer", "New Orders (Pcs)", "Repeat Orders (Pcs)", "Total Volume (Pcs)", "Share %", "Total Design Count"]].rename(columns={"designer": "Designer Name"})
    
    col_t1, col_c1 = st.columns([1.2, 1])
    with col_t1:
        st.dataframe(des_summary_df, use_container_width=True, hide_index=True)
    with col_c1:
        melted = g.melt(id_vars="designer", value_vars=["New Orders (Pcs)", "Repeat Orders (Pcs)"], var_name="Order Type", value_name="Qty")
        st.plotly_chart(px.bar(melted, x="designer", y="Qty", color="Order Type", barmode="group", title="DESIGNER PERFORMANCE: NEW vs REPEAT ORDERS (PCS)", color_discrete_sequence=["#059669", "#7C3AED"]), use_container_width=True)
        
    st.markdown("---")
    st.subheader("🧩 Category Wise Designer Breakdown Matrix (Pcs)")
    
    # Table 2: Designer | CO-ORD SET | KURTA PANT | TOP | KURTA PANT DUPATTA | DRESS | KAFTAN | KURTA | TOTAL
    cat_matrix = []
    for des_name in g["designer"]:
        sub = x[x["designer"].str.upper() == des_name.upper()]
        row_data = {"Designer": des_name}
        for cat in CATEGORIES_LIST:
            row_data[cat] = int(sub[sub["category_clean"] == cat]["qty"].sum())
        row_data["TOTAL"] = sum(row_data[c] for c in CATEGORIES_LIST)
        cat_matrix.append(row_data)
        
    cat_df = pd.DataFrame(cat_matrix)
    
    # Total Row for Category Matrix
    tot_row = {"Designer": "TOTAL"}
    for cat in CATEGORIES_LIST:
        tot_row[cat] = cat_df[cat].sum()
    tot_row["TOTAL"] = cat_df["TOTAL"].sum()
    cat_df = pd.concat([cat_df, pd.DataFrame([tot_row])], ignore_index=True)
    
    st.dataframe(cat_df, use_container_width=True, hide_index=True)

# --- TAB 2: CLIENT PERFORMANCE DASHBOARD ---
def client_dashboard(d):
    st.subheader("🏢 Executive Client Performance & Category Dashboard")
    x = d[d.client.ne("")].copy()
    if x.empty:
        st.info("Selected filters ke liye client data nahi hai."); return
        
    total_designs = len(x)
    total_qty = x["qty"].sum()
    in_prod = x["production"].sum()
    rec_done = x["received"].sum()
    pending_qty = x["pending"].sum()
    repeat_qty = x[x["type_clean"].str.contains("REPEAT", na=False)]["qty"].sum()
    new_qty = x[x["type_clean"].str.contains("NEW", na=False)]["qty"].sum()
    cat_total = total_qty

    # EXACT MATCH KPI CARDS
    metrics([
        ("TOTAL DESIGNS", f"{total_designs:,}"),
        ("TOTAL QTY (PCS)", fmt(total_qty)),
        ("IN PRODUCTION", fmt(in_prod)),
        ("RECEIVED / DONE", fmt(rec_done)),
    ])
    metrics([
        ("TOTAL PENDING QTY", fmt(pending_qty)),
        ("REPEAT ORDERS (PCS)", fmt(repeat_qty)),
        ("NEW ORDERS (PCS)", fmt(new_qty)),
        ("CATEGORY TOTAL (PCS)", fmt(cat_total)),
    ])
    
    st.markdown("---")
    st.subheader("📅 Client Fulfillment Breakdown (Monthly)")
    
    # Table 1: MONTH | ORDER QTY | IN PRODUCTION | RECEIVED | PENDING
    monthly_ful = []
    for m in MONTHS:
        sub_m = x[x["month"] == m]
        monthly_ful.append({
            "MONTH": m,
            "ORDER QTY": int(sub_m["qty"].sum()),
            "IN PRODUCTION": int(sub_m["production"].sum()),
            "RECEIVED": int(sub_m["received"].sum()),
            "PENDING": int(sub_m["pending"].sum())
        })
    m_df = pd.DataFrame(monthly_ful)
    
    # Add Total Row
    m_df_tot = pd.DataFrame([{
        "MONTH": "TOTAL",
        "ORDER QTY": m_df["ORDER QTY"].sum(),
        "IN PRODUCTION": m_df["IN PRODUCTION"].sum(),
        "RECEIVED": m_df["RECEIVED"].sum(),
        "PENDING": m_df["PENDING"].sum()
    }])
    m_df_display = pd.concat([m_df, m_df_tot], ignore_index=True)
    
    c1, c2 = st.columns([1.2, 1])
    with c1:
        st.dataframe(m_df_display, use_container_width=True, hide_index=True)
    with c2:
        q = pd.DataFrame({"Status": ["RECEIVED QTY", "PENDING QTY"], "Qty": [rec_done, pending_qty]})
        st.plotly_chart(px.pie(q, names="Status", values="Qty", hole=.45, title="ORDER FULFILLMENT RATIO (RECEIVED vs PENDING)", color_discrete_sequence=["#059669", "#DC2626"]), use_container_width=True)

    st.markdown("---")
    st.subheader("📦 Monthly Category Order Breakdown")
    
    # Table 2: MONTH | CO-ORD SET | KURTA PANT | TOP | KURTA PANT DUPATTA | DRESS | KAFTAN | KURTA | TOTAL
    m_cat_matrix = []
    for m in MONTHS:
        sub_m = x[x["month"] == m]
        r_data = {"MONTH": m}
        for cat in CATEGORIES_LIST:
            r_data[cat] = int(sub_m[sub_m["category_clean"] == cat]["qty"].sum())
        r_data["TOTAL"] = sum(r_data[c] for c in CATEGORIES_LIST)
        m_cat_matrix.append(r_data)
        
    m_cat_df = pd.DataFrame(m_cat_matrix)
    
    # Add Total Row
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

# --- TAB 3: PRODUCTION PROCESS DASHBOARD ---
def production_dashboard(d):
    st.subheader("🏭 Production Executive Process Dashboard")
    
    overdue_mask = d["delay"] > 0
    overdue = d[overdue_mask]
    avg_overdue = overdue["delay"].mean() if len(overdue) > 0 else 0.0
    
    metrics([
        ("TOTAL DESIGN", f"{len(d):,} Orders"),
        ("INPRODUCTION PCS (AS)", fmt(d.production.sum())),
        ("RECIEVED PCS (AT)", fmt(d.received.sum())),
        ("PENDING PCS (AU)", fmt(d.pending.sum())),
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
    
    # Table 1: CATEGORY | INPRODUCTION (AS) | RECIEVED (AT) | PENDING (AU)
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
    st.subheader("📈 Monthly Fulfillment Trend")
    
    # Table 2: MONTH | ORDERS | RCVD (AS) | PENDING (AT)
    m_ful_summary = []
    for m in MONTHS:
        sub_m = d[d["month"] == m]
        m_ful_summary.append({
            "MONTH": m,
            "ORDERS": len(sub_m),
            "RCVD (AS)": int(sub_m["production"].sum()),
            "PENDING (AT)": int(sub_m["received"].sum())
        })
    mf_df = pd.DataFrame(m_ful_summary)
    
    mf_tot = pd.DataFrame([{
        "MONTH": "TOTAL",
        "ORDERS": mf_df["ORDERS"].sum(),
        "RCVD (AS)": mf_df["RCVD (AS)"].sum(),
        "PENDING (AT)": mf_df["PENDING (AT)"].sum()
    }])
    mf_df_display = pd.concat([mf_df, mf_tot], ignore_index=True)
    
    col_m1, col_m2 = st.columns([1, 1.2])
    with col_m1:
        st.dataframe(mf_df_display, use_container_width=True, hide_index=True)
    with col_m2:
        st.plotly_chart(px.line(mf_df, x="MONTH", y=["RCVD (AS)", "PENDING (AT)"], markers=True, title="MONTHLY FULFILLMENT TREND ANALYSIS"), use_container_width=True)

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

# --- TAB 4: FABRIC VENDOR TRACKING ---
def fabric_dashboard(d):
    st.subheader("🧵 Fabric & Vendor Tracking")
    metrics([
        ("Fabricators / Vendors", f"{d.loc[d.fabricator.ne(''), 'fabricator'].nunique():,}"),
        ("Orders with Vendor", f"{d.fabricator.ne('').sum():,}"),
        ("Awaiting Fabric Receipt", f"{d.fabric_received_date.isna().sum():,}"),
        ("Overdue Orders", f"{(d.delay > 0).sum():,}")
    ])
    v = d[d.fabricator.ne("")].groupby("fabricator", as_index=False).agg(
        Orders=("qty", "size"), OrderQty=("qty", "sum"), PendingQty=("pending", "sum"),
        FabricReceived=("fabric_received_date", lambda s: s.notna().sum())
    )
    if not v.empty: st.dataframe(v.rename(columns={"fabricator":"Vendor / Fabricator"}), use_container_width=True, hide_index=True)

# --- TAB 5: SEARCHABLE ORDER DETAILS ---
def order_details(d):
    st.subheader("🔎 Searchable Order Details & Overdue Filters")
    
    overdue_only = st.checkbox("Show Overdue Orders Only (AH > 0)", value=False)
    query = st.text_input("Search client, designer, category, fabricator, order type or status")
    x = d.copy()
    
    if overdue_only:
        x = x[x["delay"] > 0]
        
    if query:
        mask = pd.Series(False, index=x.index)
        for c in ["client", "designer", "category", "fabricator", "type", "status"]:
            mask |= x[c].astype(str).str.contains(query, case=False, na=False)
        x = x[mask]
        
    cols = ["date","designer","client","type","category","qty","production","received","pending","fabricator","status","delay"]
    names = {"date":"Order Date","designer":"Designer","client":"Client","type":"Order Type","category":"Category","qty":"Sheet Order Qty (J)",
             "production":"In Production (AS)","received":"Received / Done (AT)","pending":"Pending Qty (AU)","fabricator":"Fabricator","status":"Status","delay":"Delay Days (AH)"}
    view = x[cols].rename(columns=names)
    st.caption(f"{len(view):,} rows filtered")
    st.dataframe(view, use_container_width=True, hide_index=True)
    st.download_button("⬇️ Download Filtered Orders CSV", view.to_csv(index=False).encode("utf-8-sig"), "filtered_orders_details.csv", "text/csv")

# -----------------------------------------------------------------------------
# MAIN APP FLOW
# -----------------------------------------------------------------------------
st.markdown("""
<div class="dashboard-hero">
  <h1 style="margin:0">📊 Sample Production &amp; Performance</h1>
  <p>Executive dashboard · Private Google Sheets connection · Data cache refreshes every 5 minutes</p>
</div>
""", unsafe_allow_html=True)

with st.sidebar:
    if st.button("🔄 Refresh Data Now", use_container_width=True):
        st.cache_data.clear()
        st.rerun()

try:
    raw = load_sheet()
    data = prepare(raw)
    st.caption(f"📄 Source: {raw.attrs.get('tab', DEFAULT_TAB)}  ·  {len(data):,} usable rows  ·  Header row: {raw.attrs.get('header_row', '?')}")
    
    if data.empty:
        st.warning("Data detect nahi hua. Sheet format check karein.")
        st.stop()
        
    filtered = filters(data)
    st.write(f"**Filtered Records:** {len(filtered):,} / {len(data):,}")
    
    tabs = st.tabs(["Executive Overview", "Designer Dashboard", "Client Dashboard", "Production Dashboard", "Fabric & Vendor", "Order Details"])
    with tabs[0]: overview(filtered)
    with tabs[1]: designer_dashboard(filtered)
    with tabs[2]: client_dashboard(filtered)
    with tabs[3]: production_dashboard(filtered)
    with tabs[4]: fabric_dashboard(filtered)
    with tabs[5]: order_details(filtered)

except Exception as e:
    st.error(f"Error Loading Google Sheets Data: {e}")
