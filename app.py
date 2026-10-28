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

# Dropdown mein dikhne wali Google Sheets. Nayi sheet add karne ke liye yahan entry add karein.
SPREADSHEETS = {
    "Original Dashboard Sheet": "1wBo0zF2wlqBzY5ZQaX5CPjCOedORwg_1Eh01vje5KFU",
    "Second Google Sheet": "1EfQ08lXGL8YjtoaZ2ygJtNVaED7doDijo2jFvCuS7Kg",
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


@st.cache_data(ttl=300, show_spinner="Google Sheet se live data load ho raha hai...")
def load_sheet(sheet_id):
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
# 7. MAIN APP (filters + tabs)
# -----------------------------------------------------------------------------
def main():
    # Dono Google Sheets dropdown mein dikhengi. IDs upar SPREADSHEETS mein configured hain.
    # Optional: Streamlit Secrets ke [spreadsheets] section se is list ko override kar sakte hain.
    sheet_options = dict(st.secrets.get("spreadsheets", SPREADSHEETS))
    if not sheet_options:
        st.error("Kam se kam ek Google Sheet configure karein.")
        st.stop()

    with st.sidebar:
        st.markdown("### 📚 Google Sheet")
        selected_sheet_name = st.selectbox("Select Google Sheet", list(sheet_options.keys()))
        selected_sheet_id = str(sheet_options[selected_sheet_name]).strip()

    raw, totals_row, tab_name, first_data_row = load_sheet(selected_sheet_id)
    d_all = prepare(raw)

    with st.sidebar:
        st.markdown("### 🔎 Filters")
        months_present = [m for m in MONTHS if m in set(d_all["month_client"].dropna())]
        sel_months = st.multiselect("Order month (Col B)", months_present)
        sel_designers = st.multiselect("Designer", sorted(x for x in d_all["designer"].unique() if x))
        sel_clients = st.multiselect("Client", sorted(x for x in d_all["client"].unique() if x))
        sel_fabs = st.multiselect("Fabricator", sorted(x for x in d_all["fabricator"].unique() if x))
        if st.button("🔄 Data refresh karo"):
            st.cache_data.clear()
            st.rerun()

    d = d_all.copy()
    if sel_months:
        d = d[d["month_client"].isin(sel_months)]
    if sel_designers:
        d = d[d["designer"].isin(sel_designers)]
    if sel_clients:
        d = d[d["client"].isin(sel_clients)]
    if sel_fabs:
        d = d[d["fabricator"].isin(sel_fabs)]

    st.markdown(
        f"""<div class="dashboard-hero"><h2>📊 Executive Multi-Dashboard 2026-27</h2>
        <p>Google Sheet: <b>{selected_sheet_name}</b> · Tab: <b>{tab_name}</b> · {len(d):,} rows (data row {first_data_row} se)</p></div>""",
        unsafe_allow_html=True)

    if d.empty:
        st.warning("Is filter me koi data nahi mila.")
        st.stop()

    t1, t2, t3, t4, t5 = st.tabs(["Overview", "Designer", "Client", "Production", "Fabric"])
    with t1:
        overview(d)
    with t2:
        designer_dashboard(d)
    with t3:
        client_dashboard(d)
    with t4:
        production_dashboard(d)
    with t5:
        fabric_dashboard(d)

    with st.expander("✅ Data check (sheet totals se match)"):
        data_check(totals_row, d_all)


if __name__ == "__main__":
    main()
