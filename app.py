import re
import pandas as pd
import plotly.express as px
import streamlit as st
import gspread
from google.oauth2.service_account import Credentials

st.set_page_config(page_title="Sample Production Dashboard", page_icon="📊", layout="wide")
SHEET_ID = "1wBo0zF2wlqBzY5ZQaX5CPjCOedORwg_1Eh01vje5KFU"
DEFAULT_TAB = "ORDER SHEET"
MONTHS = ["April", "May", "June", "July", "August", "September",
          "October", "November", "December", "January", "February", "March"]

st.markdown("""
<style>
.block-container{padding-top:1.2rem}
[data-testid="stMetric"]{background:#f8fafc;border:1px solid #dbe3ed;padding:14px;border-radius:12px}
</style>
""", unsafe_allow_html=True)


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


@st.cache_data(ttl=300, show_spinner="Google Sheet se data load ho raha hai...")
def load_sheet():
    if "gcp_service_account" not in st.secrets:
        st.error("Google credentials missing hain. Streamlit Settings → Secrets mein credentials add karein.")
        st.info("Setup instructions project ke README.md mein hain.")
        st.stop()
    creds = Credentials.from_service_account_info(
        dict(st.secrets["gcp_service_account"]),
        scopes=[
            "https://www.googleapis.com/auth/spreadsheets.readonly",
            "https://www.googleapis.com/auth/drive.readonly",
        ],
    )
    gc = gspread.authorize(creds)
    sheet_id = st.secrets.get("spreadsheet_id", SHEET_ID)
    tab_name = st.secrets.get("worksheet_name", DEFAULT_TAB)
    book = gc.open_by_key(sheet_id)
    try:
        ws = book.worksheet(tab_name)
    except gspread.WorksheetNotFound:
        st.error(f'Tab "{tab_name}" nahi mila. Available tabs: {", ".join(w.title for w in book.worksheets())}')
        st.stop()
    values = ws.get_all_values()
    if not values:
        st.error("Google Sheet empty hai.")
        st.stop()
    # The supplied Apps Script reads records from row 5, so row 4 is the
    # expected header row. Prefer it when it contains recognizable column names;
    # otherwise detect a header row from the first 10 rows.
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
    rows = [(r + [""] * max(0, width-len(r)))[:width] for r in rows]
    data = pd.DataFrame(rows, columns=headers)
    data = data.loc[~data.apply(lambda r: all(not str(v).strip() for v in r), axis=1)].copy()
    data.attrs["tab"] = tab_name
    data.attrs["header_row"] = header_i + 1
    return data


def num(s):
    """Convert numeric cells exported as numbers or text without crashing.

    Handles comma-separated values, whitespace, common dash placeholders and
    accounting negatives like (1,200). Unparseable cells become 0, matching
    Google Sheets N()/SUMPRODUCT treatment for non-numeric text.
    """
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


def prepare(raw):
    d = raw.copy()
    # Aliases first; column-letter fallbacks follow the supplied Apps Script.
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
    # Preserve whether AU was explicitly entered as numeric/text zero. A blank
    # AU cell is treated as missing data, not silently as a confirmed zero.
    d["pending_explicit_zero"] = d["pending"].astype(str).str.strip().str.replace(",", "", regex=False).isin(["0", "0.0", "0.00"])
    for c in ["qty", "production", "received", "pending", "delay"]:
        d[c] = num(d[c])
    for c in ["date", "required_date", "fabric_order_date", "planned_fabric_date", "fabric_received_date"]:
        d[c] = date_col(d[c])
    # Business rule: when Pending (AU) is 0, treat Received (AT) as the
    # final/order quantity even when the entered Order Qty (J) differs.
    # Do NOT recalculate AU from J-AT: AU=0 explicitly means fully received.
    d["effective_qty"] = d["qty"]
    fully_received = d["pending_explicit_zero"]
    d.loc[fully_received, "effective_qty"] = d.loc[fully_received, "received"]
    # Keep both quantities: original Apps Script uses J for designer/client
    # order-volume metrics, while the user's fully-received rule is exposed as
    # effective_qty for overall order view. Production delay PCS in the original
    # production script explicitly uses AS (In Production PCS), not J.
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


def overview(d):
    st.subheader("Executive Overview")
    metrics([
        ("Total Designs", f"{len(d):,}"), ("Total Order Qty", fmt(d.qty.sum())),
        ("In Production PCS", fmt(d.production.sum())), ("Received PCS", fmt(d.received.sum())),
    ])
    metrics([
        ("Pending PCS", fmt(d.pending.sum())),
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
    a, b = st.columns(2)
    with a:
        x = pd.DataFrame({"Status": ["Received / Done", "Pending"], "Quantity": [d.received.sum(), d.pending.sum()]})
        x = x[x.Quantity > 0]
        if not x.empty: st.plotly_chart(px.pie(x, names="Status", values="Quantity", hole=.5, title="Received vs Pending"), use_container_width=True)
    with b:
        x = d[d.type_clean.ne("")].groupby("type_clean", as_index=False)["qty"].sum()
        if not x.empty: st.plotly_chart(px.pie(x, names="type_clean", values="qty", hole=.5, title="New vs Repeat Orders"), use_container_width=True)


def designer_dashboard(d):
    st.subheader("Designer Performance")
    x = d[d.designer.ne("")].copy()
    if x.empty:
        st.info("Selected filters ke liye designer data nahi hai."); return
    g = x.groupby("designer", as_index=False).agg(**{"Total Volume (Pcs)": ("qty", "sum"), "Design Count": ("qty", "size")})
    new = x[x.type_clean.str.contains("NEW", na=False)].groupby("designer").qty.sum()
    repeat = x[x.type_clean.str.contains("REPEAT", na=False)].groupby("designer").qty.sum()
    g["New Orders (Pcs)"] = g.designer.map(new).fillna(0)
    g["Repeat Orders (Pcs)"] = g.designer.map(repeat).fillna(0)
    g["Share %"] = g["Total Volume (Pcs)"] / max(g["Total Volume (Pcs)"].sum(), 1) * 100
    g = g.sort_values("Total Volume (Pcs)", ascending=False)
    top = g.iloc[0]
    metrics([("Designers", f"{g.designer.nunique():,}"), ("Top Performer", top.designer),
             ("Top Performer Qty", fmt(top["Total Volume (Pcs)"])), ("New Qty", fmt(g["New Orders (Pcs)"].sum())),
             ("Repeat Qty", fmt(g["Repeat Orders (Pcs)"].sum()))])
    a, b = st.columns(2)
    with a:
        st.plotly_chart(px.bar(g.head(20), x="designer", y="Total Volume (Pcs)", title="Designer Volume", text_auto=".2s"), use_container_width=True)
    with b:
        melted = g.melt(id_vars="designer", value_vars=["New Orders (Pcs)", "Repeat Orders (Pcs)"], var_name="Order Type", value_name="Qty")
        st.plotly_chart(px.bar(melted, x="designer", y="Qty", color="Order Type", barmode="group", title="New vs Repeat by Designer"), use_container_width=True)
    trend = x.dropna(subset=["date"]).copy()
    if not trend.empty:
        trend["Month"] = trend.date.dt.to_period("M").astype(str)
        trend = trend.groupby(["Month", "designer"], as_index=False)["qty"].sum()
        st.plotly_chart(px.line(trend, x="Month", y="qty", color="designer", markers=True, title="Monthly Designer Trend"), use_container_width=True)
    st.dataframe(g.rename(columns={"designer": "Designer"}), use_container_width=True, hide_index=True)


def client_dashboard(d):
    st.subheader("Client Analysis")
    x = d[d.client.ne("")].copy()
    if x.empty:
        st.info("Selected filters ke liye client data nahi hai."); return
    g = x.groupby("client", as_index=False).agg(
        **{"Order Count": ("qty", "size"), "Order Qty": ("qty", "sum"),
           "In Production": ("production", "sum"), "Received / Done": ("received", "sum"), "Pending Qty": ("pending", "sum")})
    g = g.sort_values("Order Qty", ascending=False)
    metrics([("Clients", f"{x.client.nunique():,}"), ("Total Order Qty", fmt(x.qty.sum())),
             ("Repeat Qty", fmt(x.loc[x.type_clean.str.contains("REPEAT", na=False), "qty"].sum())),
             ("Pending Qty", fmt(x.pending.sum()))])
    a, b = st.columns(2)
    with a:
        st.plotly_chart(px.bar(g.head(20), x="client", y="Order Qty", title="Top 20 Clients by Quantity", text_auto=".2s"), use_container_width=True)
    with b:
        # Apps Script excludes completed / zero-pending rows from Pending KPI.
        pending_rows = x[(x.status.str.strip().str.upper() < "DONE") & (x.pending > 0)]
        q = pd.DataFrame({"Status": ["Received / Done", "Pending"], "Qty": [x.received.sum(), pending_rows.pending.sum()]})
        q = q[q.Qty > 0]
        if not q.empty: st.plotly_chart(px.pie(q, names="Status", values="Qty", hole=.5, title="Fulfilment Ratio"), use_container_width=True)
    cats = x[x.category_clean.ne("")].groupby("category_clean", as_index=False).qty.sum()
    if not cats.empty: st.plotly_chart(px.bar(cats, x="category_clean", y="qty", title="Category-wise Client Orders", text_auto=".2s"), use_container_width=True)
    st.dataframe(g.rename(columns={"client": "Client"}), use_container_width=True, hide_index=True)


def production_dashboard(d):
    st.subheader("Production Process & Delay Analysis")
    # The original production Apps Script calculates overdue/on-time PCS from AS.
    overdue = d[d.delay > 0]
    pending_rows = d[(d.status.str.strip().str.upper() < "DONE") & (d.pending > 0)]
    metrics([("Orders / Designs", f"{len(d):,}"), ("In Production PCS", fmt(d.production.sum())),
             ("Received PCS", fmt(d.received.sum())), ("Pending PCS", fmt(pending_rows.pending.sum()))])
    metrics([("Overdue PCS (AH > 0)", fmt(d.loc[d.delay > 0, "production"].sum())),
             ("On-Time PCS (AH <= 0)", fmt(d.loc[d.delay <= 0, "production"].sum())),
             ("Average Overdue Days", f"{overdue.delay.mean():.1f}" if len(overdue) else "0.0"),
             ("Overdue Orders", f"{len(overdue):,}")])
    a, b = st.columns(2)
    with a:
        x = d[d.category_clean.ne("")].groupby("category_clean", as_index=False).agg(
            **{"In Production": ("production", "sum"), "Received": ("received", "sum"), "Pending": ("pending", "sum")})
        if not x.empty: st.plotly_chart(px.bar(x, x="category_clean", y=["In Production", "Received", "Pending"], barmode="group", title="Category Production Performance"), use_container_width=True)
    with b:
        x = d[d.fabricator.ne("")].groupby("fabricator", as_index=False).pending.sum().sort_values("pending", ascending=False).head(15)
        if not x.empty: st.plotly_chart(px.bar(x, x="fabricator", y="pending", title="Pending Qty by Fabricator", text_auto=".2s"), use_container_width=True)
    x = d.dropna(subset=["date"]).copy()
    if not x.empty:
        x["Month"] = x.date.dt.to_period("M").astype(str)
        x = x.groupby("Month", as_index=False).agg(**{"Order Qty": ("effective_qty", "sum"), "Production": ("production", "sum"), "Received": ("received", "sum"), "Pending": ("pending", "sum")})
        st.plotly_chart(px.line(x, x="Month", y=["Order Qty", "Production", "Received", "Pending"], markers=True, title="Monthly Fulfilment Trend"), use_container_width=True)
    if not overdue.empty:
        st.markdown("#### Overdue Orders")
        st.dataframe(overdue[["date", "designer", "client", "category", "effective_qty", "fabricator", "production", "received", "pending", "delay"]]
                     .rename(columns={"date":"Order Date","designer":"Designer","client":"Client","category":"Category","effective_qty":"Order Qty","fabricator":"Fabricator","production":"In Production","received":"Received","pending":"Pending Qty","delay":"Delay Days"})
                     .sort_values("Delay Days", ascending=False), use_container_width=True, hide_index=True)


def fabric_dashboard(d):
    st.subheader("Fabric & Vendor Tracking")
    metrics([("Fabricators / Vendors", f"{d.loc[d.fabricator.ne(''), 'fabricator'].nunique():,}"),
             ("Orders with Vendor", f"{d.fabricator.ne('').sum():,}"),
             ("Awaiting Fabric Receipt", f"{d.fabric_received_date.isna().sum():,}"),
             ("Overdue Orders", f"{(d.delay > 0).sum():,}")])
    v = d[d.fabricator.ne("")].groupby("fabricator", as_index=False).agg(
        Orders=("effective_qty", "size"), OrderQty=("effective_qty", "sum"), PendingQty=("pending", "sum"),
        FabricReceived=("fabric_received_date", lambda s: s.notna().sum()))
    if not v.empty: st.dataframe(v.rename(columns={"fabricator":"Vendor / Fabricator"}), use_container_width=True, hide_index=True)
    waiting = d[d.fabric_order_date.notna() & d.fabric_received_date.isna()]
    if not waiting.empty:
        st.markdown("#### Fabric ordered but receipt date is blank")
        st.dataframe(waiting[["fabric_order_date","fabricator","designer","client","category","effective_qty","planned_fabric_date","follow_up"]]
                     .rename(columns={"fabric_order_date":"Fabric Order Date","fabricator":"Vendor","designer":"Designer","client":"Client","category":"Category","effective_qty":"Order Qty","planned_fabric_date":"Planned Date","follow_up":"Follow Up"}), use_container_width=True, hide_index=True)


def order_details(d):
    st.subheader("Searchable Order Details")
    query = st.text_input("Search client, designer, category, fabricator, order type or status")
    x = d.copy()
    if query:
        mask = pd.Series(False, index=x.index)
        for c in ["client", "designer", "category", "fabricator", "type", "status"]:
            mask |= x[c].astype(str).str.contains(query, case=False, na=False)
        x = x[mask]
    cols = ["date","designer","client","type","category","qty","effective_qty","production","received","pending","fabricator","status","delay","required_date","fabric_order_date","planned_fabric_date","fabric_received_date","follow_up"]
    names = {"date":"Order Date","designer":"Designer","client":"Client","type":"Order Type","category":"Category","qty":"Sheet Order Qty (J)","effective_qty":"Effective Order Qty",
             "production":"In Production","received":"Received / Done","pending":"Pending Qty","fabricator":"Fabricator","status":"Status","delay":"Delay Days",
             "required_date":"Required Delivery Date","fabric_order_date":"Fabric Order Date","planned_fabric_date":"Planned Fabric Date","fabric_received_date":"Fabric Received Date","follow_up":"Follow Up"}
    view = x[cols].rename(columns=names)
    st.caption(f"{len(view):,} rows")
    st.dataframe(view, use_container_width=True, hide_index=True)
    st.download_button("⬇️ Download filtered orders CSV", view.to_csv(index=False).encode("utf-8-sig"), "filtered_orders.csv", "text/csv")


st.title("📊 Sample Production & Performance Dashboard")
st.caption("Private Google Sheet connection · refresh cache every 5 minutes")
with st.sidebar:
    if st.button("🔄 Refresh data now", use_container_width=True):
        st.cache_data.clear()
        st.rerun()

raw = load_sheet()
data = prepare(raw)
st.caption(f"Source tab: {raw.attrs.get('tab', DEFAULT_TAB)} · Rows: {len(data):,} · Detected header row: {raw.attrs.get('header_row', '?')}")
if data.empty:
    st.warning("Data detect nahi hua. Worksheet aur header row check karein.")
    st.stop()
filtered = filters(data)
st.write(f"**Filtered records:** {len(filtered):,} / {len(data):,}")
tabs = st.tabs(["Executive Overview", "Designer Dashboard", "Client Dashboard", "Production Dashboard", "Fabric & Vendor", "Order Details"])
with tabs[0]: overview(filtered)
with tabs[1]: designer_dashboard(filtered)
with tabs[2]: client_dashboard(filtered)
with tabs[3]: production_dashboard(filtered)
with tabs[4]: fabric_dashboard(filtered)
with tabs[5]: order_details(filtered)

with st.expander("Column mapping / important check"):
    st.write("Column mapping: B=Order Date, C=Designer, D=Order Type, F=Category, J=Sheet Order Qty, N=Client, AA=Fabricator, AH=Delay Days, AS=In Production PCS, AT=Received PCS, AU=Pending PCS, AX=Status.")
    st.info("Formula mapping from the supplied Apps Script: Designer and Client order quantities use J; Production totals use AS (In Production), AT (Received), and AU (Pending); Production Overdue/On-Time PCS use AS filtered by AH > 0 / AH <= 0. The separate Effective Order Qty view applies your rule: when AU is explicitly 0, use AT; otherwise use J. Blank AU is not treated as an explicit zero.")
