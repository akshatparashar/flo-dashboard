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

def num_strict(s):
    if not isinstance(s, pd.Series):
        s = pd.Series(s)
    text = s.astype("string").str.strip()
    cleaned = text.str.replace(",", "", regex=False).str.replace(r"[^0-9.\-]", "", regex=True)
    return pd.to_numeric(cleaned, errors="coerce").fillna(0)

def clean_delay_days(s):
    parsed = num_strict(s)
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
# 4. DATA PREPARATION (RAW ROW RETENTION FOR 100% ACCURACY)
# -----------------------------------------------------------------------------
def prepare(raw):
    d = raw.copy()
    
    letter_mapping = {
        "date_client": "B",           # Client Dashboard Date (Column B)
        "date_prod": "AC",            # Production Dashboard Date (Column AC)
        "designer": "C",              # Designer's Name
        "type": "D",                  # Order Type
        "category": "F",              # Category / Sample Product
        "qty": "J",                   # Direct Sheet Order Qty (Column J)
        "client": "N",                # Client Name
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

    for c in ["designer", "type", "category", "client", "fabricator", "status"]:
        d[c] = d[c].astype(str).str.strip()
        d.loc[d[c].str.lower().isin(["nan", "none"]), c] = ""
        
    for c in ["qty", "production", "received", "pending"]:
        d[c] = num_strict(d[c])
        
    d["delay"] = clean_delay_days(d["delay"])
    
    d["date_client"] = date_col(d["date_client"])
    d["date_prod"] = date_col(d["date_prod"])

    d["month_client"] = d["date_client"].dt.month_name()
    d["month_prod"] = d["date_prod"].dt.month_name()
    
    d["type_clean"] = d["type"].str.upper()
    d["category_clean"] = d["category"].str.upper().str.strip()
    
    # NO DROPPING OF ROWS TO ENSURE 100% ACCURATE COLUMN J SUM
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
        ("Total Order Qty (Col J Direct)", fmt(d.qty.sum())),
        ("In Production PCS (Col AS Direct)", fmt(d.production.sum())), 
        ("Received PCS (Col AT Direct)", fmt(d.received.sum())),
    ])
    metrics([
        ("Pending PCS (Col AU Direct)", fmt(d.pending.sum())),
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
    st.subheader("👨‍🎨 Executive Designer Performance Dashboard")
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

# CLIENT DASHBOARD: STRICTLY RAW SUM OF COLUMN J (NO FILTERS / NO CONDITIONS)
def client_dashboard(d):
    st.subheader("🏢 Executive Client Performance Dashboard (Date: Col B, Total Qty: Col J Direct)")
    x = d[d.client.ne("")].copy()
    if x.empty:
        st.info("Selected filters ke liye client data nahi hai."); return
        
    total_designs = len(x)
    total_qty = x["qty"].sum()              # EXACT RAW SUM OF COLUMN J
    in_prod = x["production"].sum()         # EXACT RAW SUM OF COLUMN AS
    rec_done = x["received"].sum()          # EXACT RAW SUM OF COLUMN AT
    pending_qty = x["pending"].sum()        # EXACT RAW SUM OF COLUMN AU
    repeat_qty = x[x["type_clean"].str.contains("REPEAT", na=False)]["qty"].sum()
    new_qty = x[x["type_clean"].str.contains("NEW", na=False)]["qty"].sum()

    metrics([
        ("TOTAL DESIGNS", f"{total_designs:,}"),
        ("TOTAL QTY (PCS) [Col J Raw]", fmt(total_qty)),
        ("IN PRODUCTION [Col AS Raw]", fmt(in_prod)),
        ("RECEIVED / DONE [Col AT Raw]", fmt(rec_done)),
    ])
    metrics([
        ("TOTAL PENDING QTY [Col AU Raw]", fmt(pending_qty)),
        ("REPEAT ORDERS (PCS)", fmt(repeat_qty)),
        ("NEW ORDERS (PCS)", fmt(new_qty)),
        ("CATEGORY TOTAL (PCS)", fmt(total_qty)),
    ])
    
    st.markdown("---")
    st.subheader("📅 Client Fulfillment Breakdown (Monthly Filtered by Col B)")
    monthly_ful = []
    for m in MONTHS:
        sub_m = x[x["month_client"] == m]
        monthly_ful.append({
            "MONTH": m,
            "ORDER QTY (Col J)": int(sub_m["qty"].sum()),
            "IN PRODUCTION (Col AS)": int(sub_m["production"].sum()),
            "RECEIVED (Col AT)": int(sub_m["received"].sum()),
            "PENDING (Col AU)": int(sub_m["pending"].sum())
        })
    m_df = pd.DataFrame(monthly_ful)
    m_df_tot = pd.DataFrame([{
        "MONTH": "TOTAL",
        "ORDER QTY (Col J)": m_df["ORDER QTY (Col J)"].sum(),
        "IN PRODUCTION (Col AS)": m_df["IN PRODUCTION (Col AS)"].sum(),
        "RECEIVED (Col AT)": m_df["RECEIVED (Col AT)"].sum(),
        "PENDING (Col AU)": m_df["PENDING (Col AU)"].sum()
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
        ("TOTAL DESIGN", f"{len(d):,} Orders"),
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

def fabric_dashboard(d):
    st.subheader("🧵 Fabric & Vendor Tracking")
    metrics([
        ("Fabricators / Vendors", f"{d.loc[d.fabricator.ne(''), 'fabricator'].nunique():,}"),
        ("Orders with Vendor", f"{d.fabricator.ne('').sum():,}"),
        ("Overdue Orders", f"{(d.delay > 0).sum():,}")
    ])
    v = d[d.fabricator.ne("")].groupby("fabricator", as_index=False).agg(
        Orders=("qty", "size"), OrderQty=("qty", "sum"), PendingQty=("pending", "sum")
    )
    if not v.empty: st.dataframe(v.rename(columns={"fabricator":"Vendor / Fabricator"}), use_container_width=True, hide_index=True)

def order_details(d):
    st.subheader("🔎 Searchable Order Details")
    query = st.text_input("Search client, designer, category, fabricator, order type or status", key="search_query_input")
    x = d.copy()
    if query:
        mask = pd.Series(False, index=x.index)
        for c in ["client", "designer", "category", "fabricator", "type", "status"]:
            mask |= x[c].astype(str).str.contains(query, case=False, na=False)
        x = x[mask]
        
    cols = ["date_client","date_prod","designer","client","type","category","qty","production","received","pending","fabricator","status","delay"]
    names = {"date_client":"Order Date (B)","date_prod":"Prod Date (AC)","designer":"Designer","client":"Client","type":"Order Type","category":"Category","qty":"Sheet Order Qty (J)",
             "production":"In Production (AS)","received":"Received / Done (AT)","pending":"Pending Qty (AU)","fabricator":"Fabricator","status":"Status","delay":"Delay Days (AH)"}
    view = x[cols].rename(columns=names)
    st.caption(f"{len(view):,} rows filtered")
    st.dataframe(view, use_container_width=True, hide_index=True)

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
    st.caption(f"📄 Source: {raw.attrs.get('tab', DEFAULT_TAB)}  ·  {len(data):,} total sheet rows")
    
    st.sidebar.header("🔎 Global Filters")
    active_tab = st.selectbox(
        "📌 View Dashboard Section", 
        ["Executive Overview", "Designer Dashboard", "Client Dashboard", "Production Dashboard", "Fabric & Vendor", "Order Details"],
        key="global_active_tab"
    )
    
    is_prod = (active_tab == "Production Dashboard")
    target_month_col = "month_prod" if is_prod else "month_client"
    
    month_opts = ["ALL"] + [m for m in MONTHS if m in data[target_month_col].dropna().astype(str).unique()]
    month_val = st.sidebar.selectbox("Month", month_opts, key="global_month_filter")
    
    filtered_data = data.copy()
    if month_val != "ALL": 
        filtered_data = filtered_data[filtered_data[target_month_col] == month_val]
        
    st.write(f"**Filtered Records:** {len(filtered_data):,} / {len(data):,}")
    
    if active_tab == "Executive Overview":
        overview(filtered_data)
    elif active_tab == "Designer Dashboard":
        designer_dashboard(filtered_data)
    elif active_tab == "Client Dashboard":
        client_dashboard(filtered_data)
    elif active_tab == "Production Dashboard":
        production_dashboard(filtered_data)
    elif active_tab == "Fabric & Vendor":
        fabric_dashboard(filtered_data)
    elif active_tab == "Order Details":
        order_details(filtered_data)

except Exception as e:
    st.error(f"Error Loading Google Sheets Data: {e}")
