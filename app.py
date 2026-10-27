import re
import json
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

st.markdown("""
<style>
.block-container{padding-top:1.2rem}
[data-testid="stMetric"]{background:#f8fafc;border:1px solid #dbe3ed;padding:14px;border-radius:12px}
</style>
""", unsafe_allow_html=True)

# -----------------------------------------------------------------------------
# 2. HELPER FUNCTIONS FOR ROBUST COLUMN INDEXING
# -----------------------------------------------------------------------------
def norm(x):
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9]+", " ", str(x).lower())).strip()

def col_index(letter):
    n = 0
    for c in letter.upper():
        n = n * 26 + ord(c) - 64
    return n - 1

def choose_col(df, aliases, fallback):
    headers = {norm(c): c for c in df.columns}
    for alias in aliases:
        if norm(alias) in headers:
            return headers[norm(alias)]
    for alias in aliases:
        a = norm(alias)
        if len(a) >= 5:
            for h, original in headers.items():
                if a in h or h in a:
                    return original
    idx = col_index(fallback)
    return df.columns[idx] if idx < len(df.columns) else None

def num(s):
    if not isinstance(s, pd.Series):
        s = pd.Series(s)
    text = s.astype("string").str.strip()
    text = text.replace({"": pd.NA, "-": pd.NA, "—": pd.NA, "–": pd.NA, "N/A": pd.NA, "n/a": pd.NA, "None": pd.NA, "nan": pd.NA})
    is_paren_negative = text.str.match(r"^\(.*\)$", na=False)
    cleaned = text.str.replace(",", "", regex=False).str.replace(r"[^0-9.\-]", "", regex=True)
    cleaned = cleaned.mask(is_paren_negative, "-" + cleaned.str.replace("-", "", regex=False))
    return pd.to_numeric(cleaned, errors="coerce").fillna(0).astype(float)

def date_col(s):
    return pd.to_datetime(s, errors="coerce", dayfirst=True)

# -----------------------------------------------------------------------------
# 3. GOOGLE SHEETS DATA RETRIEVAL (WITH PEM SANITIZATION)
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
        
    def header_score(row):
        cells = [norm(v) for v in row if str(v).strip()]
        keywords = ["designer", "client", "order", "category", "sample", "fabricator", "pcs", "date"]
        return sum(any(k in cell for cell in cells) for k in keywords)

    header_i = 3 if len(values) > 3 and header_score(values[3]) >= 2 else 0
    if header_i == 0:
        header_i = max(range(min(10, len(values))), key=lambda i: header_score(values[i]))
        
    headers = []
    for i, v in enumerate(values[header_i]):
        name = str(v).strip() or f"Unnamed_{i+1}"
        if name in headers:
            name = f"{name}_{i+1}"
        headers.append(name)
        
    rows = values[header_i + 1:]
    width = len(headers)
    rows = [(r + [""] * max(0, width - len(r)))[:width] for r in rows]
    data = pd.DataFrame(rows, columns=headers)
    data = data.loc[~data.apply(lambda r: all(not str(v).strip() for v in r), axis=1)].copy()
    data.attrs["tab"] = ws.title
    data.attrs["header_row"] = header_i + 1
    return data

# -----------------------------------------------------------------------------
# 4. DATA PREPARATION & COLUMN MAPPING ALIGNED WITH APPS SCRIPT
# -----------------------------------------------------------------------------
def prepare(raw):
    d = raw.copy()
    fields = {
        "date": (["Order Date", "Date", "Order Booking Date"], "B"),
        "designer": (["Designer's Name", "Designer Name", "Designer"], "C"),
        "type": (["Order Type", "Type"], "D"),
        "category": (["Sample Product", "Category", "Product"], "F"),
        "qty": (["No. of Pcs", "No of Pcs", "Order Qty", "Order Quantity", "Quantity", "Qty"], "J"),
        "client": (["Client Name", "Client", "Customer Name"], "N"),
        "fabricator": (["Fabricator", "Fabricator Name", "Vendor Name", "Vendor"], "AA"),
        "delay": (["Delay Days", "Overdue Days", "Delay (Days)", "Days Delayed"], "AH"),
        "production": (["In Production", "In Production Qty", "Production Qty", "Production Quantity"], "AS"),
        "received": (["Received Qty", "Received Quantity", "Received / Done", "Received"], "AT"),
        "pending": (["Pending Qty", "Pending Quantity", "Total Pending Qty", "Pending"], "AU"),
        "status": (["Status", "Production Status", "Order Status"], "AX"),
        "required_date": (["Customer Required Delivery Date", "Required Delivery Date", "Required Date"], "O"),
        "fabric_order_date": (["Fabric Order Date"], "P"),
        "planned_fabric_date": (["Planned reqd Date", "Planned Required Date", "Planned Date"], "S"),
        "follow_up": (["Follow Up", "Follow-up", "Followup"], "T"),
        "fabric_received_date": (["Rcvd Date", "Received Date", "Fabric Received Date"], "U"),
    }
    
    for key, (aliases, letter) in fields.items():
        c = choose_col(d, aliases, letter)
        d[key] = d[c] if c is not None else ""
        
    for c in ["designer", "type", "category", "client", "fabricator", "status", "follow_up"]:
        d[c] = d[c].astype(str).str.strip()
        d.loc[d[c].str.lower().isin(["nan", "none"]), c] = ""
        
    d["pending_explicit_zero"] = d["pending"].astype(str).str.strip().str.replace(",", "", regex=False).isin(["0", "0.0", "0.00"])
    
    for c in ["qty", "production", "received", "pending", "delay"]:
        d[c] = num(d[c])
        
    for c in ["date", "required_date", "fabric_order_date", "planned_fabric_date", "fabric_received_date"]:
        d[c] = date_col(d[c])
        
    d["effective_qty"] = d["qty"]
    fully_received = d["pending_explicit_zero"]
    d.loc[fully_received, "effective_qty"] = d.loc[fully_received, "received"]
    
    d["month"] = d["date"].dt.month_name()
    d["type_clean"] = d["type"].str.upper()
    d["category_clean"] = d["category"].str.upper().str.strip()
    
    d = d[(d["designer"].ne("")) | (d["client"].ne("")) | (d["qty"] != 0) | d["date"].notna()].copy()
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
# 5. DASHBOARD VIEWS MATCHING APPS SCRIPT FORMULAS
# -----------------------------------------------------------------------------
def overview(d):
    st.subheader("Executive Overview")
    metrics([
        ("Total Designs", f"{len(d):,}"), ("Total Order Qty (J)", fmt(d.qty.sum())),
        ("In Production PCS (AS)", fmt(d.production.sum())), ("Received PCS (AT)", fmt(d.received.sum())),
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

def designer_dashboard(d):
    st.subheader("1. Designer Performance & Category Tracking")
    x = d[d.designer.ne("")].copy()
    if x.empty:
        st.info("Selected filters ke liye designer data nahi hai."); return
        
    g = x.groupby("designer", as_index=False).agg(**{"Total Volume (Pcs)": ("qty", "sum"), "Design Count": ("qty", "size")})
    new = x[x.type_clean.str.contains("NEW", na=False)].groupby("designer").qty.sum()
    repeat = x[x.type_clean.str.contains("REPEAT", na=False)].groupby("designer").qty.sum()
    g["New Orders (Pcs)"] = g.designer.map(new).fillna(0)
    g["Repeat Orders (Pcs)"] = g.designer.map(repeat).fillna(0)
    
    tot_vol = g["Total Volume (Pcs)"].sum()
    g["Share %"] = g["Total Volume (Pcs)"].apply(lambda v: f"{(v / tot_vol * 100):.1f}%" if tot_vol > 0 else "0.0%")
    g = g.sort_values("Total Volume (Pcs)", ascending=False)
    top = g.iloc[0]
    
    metrics([
        ("Designers", f"{g.designer.nunique():,}"), 
        ("Top Performer", top.designer),
        ("Top Performer Qty", fmt(top["Total Volume (Pcs)"])), 
        ("New Qty", fmt(g["New Orders (Pcs)"].sum())),
        ("Repeat Qty", fmt(g["Repeat Orders (Pcs)"].sum()))
    ])
    
    a, b = st.columns(2)
    with a:
        st.plotly_chart(px.bar(g.head(20), x="designer", y="Total Volume (Pcs)", title="DESIGNER VOLUME (PCS)", text_auto=".2s"), use_container_width=True)
    with b:
        melted = g.melt(id_vars="designer", value_vars=["New Orders (Pcs)", "Repeat Orders (Pcs)"], var_name="Order Type", value_name="Qty")
        st.plotly_chart(px.bar(melted, x="designer", y="Qty", color="Order Type", barmode="group", title="NEW vs REPEAT BY DESIGNER", color_discrete_sequence=["#059669", "#7C3AED"]), use_container_width=True)
        
    st.markdown("#### Category Wise Designer Breakdown (Pcs)")
    categories_list = ["CO-ORD SET", "KURTA PANT", "TOP", "KURTA PANT DUPATTA", "DRESS", "KAFTAN", "KURTA"]
    cat_matrix = []
    for des_name in g["designer"]:
        sub = x[x["designer"].str.upper() == des_name.upper()]
        row_data = {"Designer": des_name}
        for cat in categories_list:
            row_data[cat] = sub[sub["category_clean"] == cat]["qty"].sum()
        row_data["TOTAL"] = sum(row_data[c] for c in categories_list)
        cat_matrix.append(row_data)
        
    cat_df = pd.DataFrame(cat_matrix)
    st.dataframe(cat_df, use_container_width=True, hide_index=True)

def client_dashboard(d):
    st.subheader("2. Client Performance & Fulfillment")
    x = d[d.client.ne("")].copy()
    if x.empty:
        st.info("Selected filters ke liye client data nahi hai."); return
        
    # Apps Script Formula: Pending rows filter (Status < "DONE" and Pending > 0)
    pending_rows = x[(x.status.str.strip().str.upper() < "DONE") & (x.pending > 0)]
    
    metrics([
        ("Total Designs", f"{len(x):,}"),
        ("Total Order Qty (J)", fmt(x.qty.sum())),
        ("In Production (AS)", fmt(x.production.sum())),
        ("Received / Done (AT)", fmt(x.received.sum())),
        ("Total Pending Qty (AU)", fmt(pending_rows.pending.sum())),
    ])
    
    metrics([
        ("Repeat Orders (Pcs)", fmt(x.loc[x.type_clean.str.contains("REPEAT", na=False), "qty"].sum())),
        ("New Orders (Pcs)", fmt(x.loc[x.type_clean.str.contains("NEW", na=False), "qty"].sum())),
    ])
    
    a, b = st.columns(2)
    with a:
        g = x.groupby("client", as_index=False)["qty"].sum().sort_values("qty", ascending=False).head(20)
        st.plotly_chart(px.bar(g, x="client", y="qty", title="TOP 20 CLIENTS BY ORDER QTY", text_auto=".2s"), use_container_width=True)
    with b:
        q = pd.DataFrame({"Status": ["Received / Done", "Pending"], "Qty": [x.received.sum(), pending_rows.pending.sum()]})
        q = q[q.Qty > 0]
        if not q.empty:
            st.plotly_chart(px.pie(q, names="Status", values="Qty", hole=.45, title="ORDER FULFILLMENT RATIO", color_discrete_sequence=["#059669", "#DC2626"]), use_container_width=True)

def production_dashboard(d):
    st.subheader("3. Production Process & Delay Analysis")
    overdue = d[d.delay > 0]
    pending_rows = d[(d.status.str.strip().str.upper() < "DONE") & (d.pending > 0)]
    
    metrics([
        ("Orders / Designs", f"{len(d):,}"),
        ("In Production PCS (AS)", fmt(d.production.sum())),
        ("Received PCS (AT)", fmt(d.received.sum())),
        ("Pending PCS (AU)", fmt(pending_rows.pending.sum())),
        ("Overdue PCS (AH > 0)", fmt(d.loc[d.delay > 0, "production"].sum())),
    ])
    
    metrics([
        ("Avg Overdue Days", f"{overdue.delay.mean():.1f}" if len(overdue) else "0.0"),
        ("On-Time Delivery %", f"{((len(d[d.delay <= 0]) / len(d) * 100) if len(d) > 0 else 0):.1f}%"),
        ("On-Time PCS (AH <= 0)", fmt(d.loc[d.delay <= 0, "production"].sum())),
        ("Overdue Orders Count", f"{len(overdue):,}"),
    ])
    
    a, b = st.columns(2)
    with a:
        x = d[d.category_clean.ne("")].groupby("category_clean", as_index=False).agg(
            **{"In Production": ("production", "sum"), "Received": ("received", "sum"), "Pending": ("pending", "sum")}
        )
        if not x.empty:
            st.plotly_chart(px.bar(x, x="category_clean", y=["In Production", "Received", "Pending"], barmode="group", title="CATEGORY PRODUCTION PERFORMANCE"), use_container_width=True)
    with b:
        x = d[d.fabricator.ne("")].groupby("fabricator", as_index=False).pending.sum().sort_values("pending", ascending=False).head(15)
        if not x.empty:
            st.plotly_chart(px.pie(x, names="fabricator", values="pending", title="FABRICATOR PENDING PCS SHARE", hole=0.4), use_container_width=True)

def fabric_dashboard(d):
    st.subheader("Fabric & Vendor Tracking")
    metrics([
        ("Fabricators / Vendors", f"{d.loc[d.fabricator.ne(''), 'fabricator'].nunique():,}"),
        ("Orders with Vendor", f"{d.fabricator.ne('').sum():,}"),
        ("Awaiting Fabric Receipt", f"{d.fabric_received_date.isna().sum():,}"),
        ("Overdue Orders", f"{(d.delay > 0).sum():,}")
    ])
    v = d[d.fabricator.ne("")].groupby("fabricator", as_index=False).agg(
        Orders=("effective_qty", "size"), OrderQty=("effective_qty", "sum"), PendingQty=("pending", "sum"),
        FabricReceived=("fabric_received_date", lambda s: s.notna().sum())
    )
    if not v.empty: st.dataframe(v.rename(columns={"fabricator":"Vendor / Fabricator"}), use_container_width=True, hide_index=True)

def order_details(d):
    st.subheader("Searchable Order Details")
    query = st.text_input("Search client, designer, category, fabricator, order type or status")
    x = d.copy()
    if query:
        mask = pd.Series(False, index=x.index)
        for c in ["client", "designer", "category", "fabricator", "type", "status"]:
            mask |= x[c].astype(str).str.contains(query, case=False, na=False)
        x = x[mask]
    cols = ["date","designer","client","type","category","qty","effective_qty","production","received","pending","fabricator","status","delay"]
    names = {"date":"Order Date","designer":"Designer","client":"Client","type":"Order Type","category":"Category","qty":"Sheet Order Qty (J)","effective_qty":"Effective Order Qty",
             "production":"In Production (AS)","received":"Received / Done (AT)","pending":"Pending Qty (AU)","fabricator":"Fabricator","status":"Status","delay":"Delay Days (AH)"}
    view = x[cols].rename(columns=names)
    st.caption(f"{len(view):,} rows")
    st.dataframe(view, use_container_width=True, hide_index=True)
    st.download_button("⬇️ Download filtered orders CSV", view.to_csv(index=False).encode("utf-8-sig"), "filtered_orders.csv", "text/csv")

# -----------------------------------------------------------------------------
# MAIN APP EXECUTION FLOW
# -----------------------------------------------------------------------------
st.title("📊 Sample Production & Performance Executive Dashboard")
st.caption("Private Google Sheet Connection · Auto-refreshed every 5 minutes")

with st.sidebar:
    if st.button("🔄 Refresh Data Now", use_container_width=True):
        st.cache_data.clear()
        st.rerun()

try:
    raw = load_sheet()
    data = prepare(raw)
    st.caption(f"Source tab: {raw.attrs.get('tab', DEFAULT_TAB)} · Total Rows: {len(data):,} · Header Row: {raw.attrs.get('header_row', '?')}")
    
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
