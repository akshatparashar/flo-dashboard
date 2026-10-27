import streamlit as st
import pandas as pd
import plotly.express as px
import gspread
from google.oauth2.service_account import Credentials

# Streamlit Page Setup
st.set_page_config(
    page_title="Executive Multi-Dashboard 2026-27",
    page_icon="📊",
    layout="wide"
)

# 1. Google Sheets Live Data Fetching
@st.cache_data(ttl=300)  # Auto Refresh Cache every 5 Minutes
def load_sheet_data():
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    credentials = Credentials.from_service_account_info(
        st.secrets["gcp_service_account"],
        scopes=scope
    )
    client = gspread.authorize(credentials)
    
    # Master Sheet Access Key
    sheet_key = "1wBo0zF2wlqBzY5ZQaX5CPjCOedORwg_1Eh01vje5KFU"
    spreadsheet = client.open_by_key(sheet_key)
    
    # Primary Raw Data Sheet ("ORDER SHEET" or "CONFIRMATION SHEET")
    try:
        worksheet = spreadsheet.worksheet("CONFIRMATION SHEET")
    except:
        try:
            worksheet = spreadsheet.worksheet("ORDER SHEET")
        except:
            worksheet = spreadsheet.get_worksheet(0)
            
    df = pd.DataFrame(worksheet.get_all_records())
    return df

try:
    raw_df = load_sheet_data()
    
    # Data Normalization
    raw_df.columns = [str(c).strip() for c in raw_df.columns]
    
    # Top Sidebar Navigation
    st.sidebar.title("🎛️ Management Dashboards")
    selected_dashboard = st.sidebar.radio(
        "Select Executive View:",
        [
            "1. Designer Performance & Category Tracking",
            "2. Client Performance & Fulfillment",
            "3. Production Process & Vendor Performance"
        ]
    )
    st.sidebar.markdown("---")
    st.sidebar.subheader("🔍 Interactive Filters")

    # Helper Month List
    fy_months = ["April", "May", "June", "July", "August", "September", "October", "November", "December", "January", "February", "March"]

    # -------------------------------------------------------------
    # 1. DESIGNER PERFORMANCE & CATEGORY TRACKING DASHBOARD
    # -------------------------------------------------------------
    if selected_dashboard == "1. Designer Performance & Category Tracking":
        st.title("👨‍🎨 Executive Designer Performance & Category Tracking Dashboard")
        st.markdown("---")

        # Column Mapping as per Apps Script Code (Col B: Date, Col C: Designer, Col D: Type, Col F: Item, Col J: Qty)
        col_date = raw_df.columns[1] if len(raw_df.columns) > 1 else "DATE"
        col_des  = raw_df.columns[2] if len(raw_df.columns) > 2 else "DESIGNER"
        col_type = raw_df.columns[3] if len(raw_df.columns) > 3 else "ORDER TYPE"
        col_item = raw_df.columns[5] if len(raw_df.columns) > 5 else "CATEGORY"
        col_qty  = raw_df.columns[9] if len(raw_df.columns) > 9 else "ORDER QTY"

        # Sidebar Filters
        month_opt = ["ALL"] + fy_months
        sel_month = st.sidebar.selectbox("Select Month", month_opt)

        des_list = ["ALL"] + sorted([str(x).strip().upper() for x in raw_df[col_des].unique() if str(x).strip() != ""])
        sel_des = st.sidebar.selectbox("Select Designer", des_list)

        type_list = ["ALL", "NEW", "REPEAT"]
        sel_type = st.sidebar.selectbox("Order Type", type_list)

        # Filtering Data
        df = raw_df.copy()
        if sel_month != "ALL":
            df = df[df[col_date].astype(str).str.contains(sel_month, case=False, na=False)]
        if sel_des != "ALL":
            df = df[df[col_des].astype(str).str.upper().str.strip() == sel_des]
        if sel_type != "ALL":
            df = df[df[col_type].astype(str).str.contains(sel_type, case=False, na=False)]

        # Numeric Conversion
        df[col_qty] = pd.to_numeric(df[col_qty], errors='coerce').fillna(0)

        # KPI Calculations
        total_designs = len(df)
        total_qty = int(df[col_qty].sum())
        new_qty = int(df[df[col_type].astype(str).str.contains("NEW", case=False, na=False)][col_qty].sum())
        repeat_qty = int(df[df[col_type].astype(str).str.contains("REPEAT", case=False, na=False)][col_qty].sum())
        
        # Top Performer
        des_grouped = df.groupby(col_des)[col_qty].sum()
        top_performer = f"{des_grouped.idxmax()} ({int(des_grouped.max()):,} Pcs)" if not des_grouped.empty else "N/A"

        # Render Top KPI Cards
        k1, k2, k3, k4, k5 = st.columns(5)
        k1.metric("TOTAL DESIGNS", f"{total_designs:,}")
        k2.metric("TOTAL QUANTITY (PCS)", f"{total_qty:,}")
        k3.metric("NEW ORDER QTY", f"{new_qty:,}")
        k4.metric("REPEAT ORDER QTY", f"{repeat_qty:,}")
        k5.metric("TOP PERFORMER", top_performer)

        st.markdown("---")

        # Section A: Designer Volume & Share Breakdown Table + Chart
        st.subheader("📊 Designer Volume & Share Breakdown")
        
        c_tbl, c_chart = st.columns([1.2, 1])

        with c_tbl:
            des_summary = []
            all_designers = [x for x in des_list if x != "ALL"]
            for d in all_designers:
                sub_d = raw_df[raw_df[col_des].astype(str).str.upper().str.strip() == d]
                if sel_month != "ALL":
                    sub_d = sub_d[sub_d[col_date].astype(str).str.contains(sel_month, case=False, na=False)]
                if sel_type != "ALL":
                    sub_d = sub_d[sub_d[col_type].astype(str).str.contains(sel_type, case=False, na=False)]
                
                sub_d[col_qty] = pd.to_numeric(sub_d[col_qty], errors='coerce').fillna(0)
                
                d_new = int(sub_d[sub_d[col_type].astype(str).str.contains("NEW", case=False, na=False)][col_qty].sum())
                d_repeat = int(sub_d[sub_d[col_type].astype(str).str.contains("REPEAT", case=False, na=False)][col_qty].sum())
                d_total = d_new + d_repeat
                d_designs = len(sub_d)

                des_summary.append({
                    "Designer Name": d,
                    "New Orders (Pcs)": d_new,
                    "Repeat Orders (Pcs)": d_repeat,
                    "Total Volume (Pcs)": d_total,
                    "Total Design Count": d_designs
                })

            des_df = pd.DataFrame(des_summary)
            grand_total_vol = des_df["Total Volume (Pcs)"].sum()
            des_df["Share %"] = des_df["Total Volume (Pcs)"].apply(lambda x: f"{(x/grand_total_vol*100):.1f}%" if grand_total_vol > 0 else "0.0%")
            
            st.dataframe(des_df, use_container_width=True)

        with c_chart:
            fig_bar = px.bar(
                des_df, x="Designer Name", y=["New Orders (Pcs)", "Repeat Orders (Pcs)"],
                title="DESIGNER PERFORMANCE: NEW vs REPEAT ORDERS (PCS)",
                barmode="group", color_discrete_sequence=["#059669", "#7C3AED"]
            )
            st.plotly_chart(fig_bar, use_container_width=True)

        # Section B: Category Wise Matrix
        st.subheader("👗 Category Wise Designer Breakdown Matrix (Pcs)")
        cat_list = ["CO-ORD SET", "KURTA PANT", "TOP", "KURTA PANT DUPATTA", "DRESS", "KAFTAN", "KURTA"]
        
        matrix_data = []
        for d in all_designers:
            row_dict = {"Designer": d}
            sub_d = raw_df[raw_df[col_des].astype(str).str.upper().str.strip() == d]
            if sel_month != "ALL":
                sub_d = sub_d[sub_d[col_date].astype(str).str.contains(sel_month, case=False, na=False)]
            if sel_type != "ALL":
                sub_d = sub_d[sub_d[col_type].astype(str).str.contains(sel_type, case=False, na=False)]
            sub_d[col_qty] = pd.to_numeric(sub_d[col_qty], errors='coerce').fillna(0)

            for cat in cat_list:
                cat_val = sub_d[sub_d[col_item].astype(str).str.upper().str.strip() == cat][col_qty].sum()
                row_dict[cat] = int(cat_val)
            
            row_dict["TOTAL"] = sum([row_dict[c] for c in cat_list])
            matrix_data.append(row_dict)

        cat_matrix_df = pd.DataFrame(matrix_data)
        st.dataframe(cat_matrix_df, use_container_width=True)

    # -------------------------------------------------------------
    # 2. CLIENT PERFORMANCE & FULFILLMENT DASHBOARD
    # -------------------------------------------------------------
    elif selected_dashboard == "2. Client Performance & Fulfillment":
        st.title("🏢 Executive Client Performance & Category Dashboard")
        st.markdown("---")

        # Column Mapping (Col B: Date, Col D: Type, Col F: Item, Col J: Order Qty, Col N: Client, Col AS: Prod, Col AT: Rec, Col AU: Pending, Col AX: Status)
        col_date    = raw_df.columns[1] if len(raw_df.columns) > 1 else "DATE"
        col_type    = raw_df.columns[3] if len(raw_df.columns) > 3 else "ORDER TYPE"
        col_item    = raw_df.columns[5] if len(raw_df.columns) > 5 else "CATEGORY"
        col_ord_qty = raw_df.columns[9] if len(raw_df.columns) > 9 else "ORDER QTY"
        col_client  = raw_df.columns[13] if len(raw_df.columns) > 13 else "CLIENT NAME"
        
        col_prod    = raw_df.columns[44] if len(raw_df.columns) > 44 else "IN PRODUCTION"
        col_rec     = raw_df.columns[45] if len(raw_df.columns) > 45 else "RECEIVED QTY"
        col_pend    = raw_df.columns[46] if len(raw_df.columns) > 46 else "PENDING QTY"
        col_status  = raw_df.columns[49] if len(raw_df.columns) > 49 else "STATUS"

        # Sidebar Filters
        sel_month  = st.sidebar.selectbox("Select Month", ["ALL"] + fy_months)
        client_opts= ["ALL"] + sorted([str(x).strip().upper() for x in raw_df[col_client].unique() if str(x).strip() != ""])
        sel_client = st.sidebar.selectbox("Select Client Name", client_opts)
        sel_type   = st.sidebar.selectbox("Order Type", ["ALL", "NEW", "REPEAT"])
        cat_opts   = ["ALL"] + sorted([str(x).strip().upper() for x in raw_df[col_item].unique() if str(x).strip() != ""])
        sel_cat    = st.sidebar.selectbox("Category", cat_opts)

        # Filter Data
        df = raw_df.copy()
        if sel_month != "ALL":
            df = df[df[col_date].astype(str).str.contains(sel_month, case=False, na=False)]
        if sel_client != "ALL":
            df = df[df[col_client].astype(str).str.upper().str.strip() == sel_client]
        if sel_type != "ALL":
            df = df[df[col_type].astype(str).str.contains(sel_type, case=False, na=False)]
        if sel_cat != "ALL":
            df = df[df[col_item].astype(str).str.upper().str.strip() == sel_cat]

        # Numeric Conversions
        for c in [col_ord_qty, col_prod, col_rec, col_pend]:
            if c in df.columns:
                df[c] = pd.to_numeric(df[c], errors='coerce').fillna(0)

        # KPIs
        t_designs = len(df)
        t_qty     = int(df[col_ord_qty].sum()) if col_ord_qty in df.columns else 0
        t_prod    = int(df[col_prod].sum()) if col_prod in df.columns else 0
        t_rec     = int(df[col_rec].sum()) if col_rec in df.columns else 0
        t_pend    = int(df[col_pend].sum()) if col_pend in df.columns else 0

        c1, c2, c3, c4, c5 = st.columns(5)
        c1.metric("TOTAL DESIGNS", f"{t_designs:,}")
        c2.metric("TOTAL QTY (PCS)", f"{t_qty:,}")
        c3.metric("IN PRODUCTION", f"{t_prod:,}")
        c4.metric("RECEIVED / DONE", f"{t_rec:,}")
        c5.metric("TOTAL PENDING QTY", f"{t_pend:,}")

        st.markdown("---")

        # Monthly Fulfillment Breakdown Table
        st.subheader("📅 Client Fulfillment Breakdown (Monthly)")
        m_summary = []
        for m in fy_months:
            sub_m = raw_df[raw_df[col_date].astype(str).str.contains(m, case=False, na=False)]
            if sel_client != "ALL":
                sub_m = sub_m[sub_m[col_client].astype(str).str.upper().str.strip() == sel_client]
            if sel_type != "ALL":
                sub_m = sub_m[sub_m[col_type].astype(str).str.contains(sel_type, case=False, na=False)]
            if sel_cat != "ALL":
                sub_m = sub_m[sub_m[col_item].astype(str).str.upper().str.strip() == sel_cat]

            for c in [col_ord_qty, col_prod, col_rec, col_pend]:
                if c in sub_m.columns:
                    sub_m[c] = pd.to_numeric(sub_m[c], errors='coerce').fillna(0)

            m_summary.append({
                "Month": m,
                "ORDER QTY": int(sub_m[col_ord_qty].sum()) if col_ord_qty in sub_m.columns else 0,
                "IN PRODUCTION": int(sub_m[col_prod].sum()) if col_prod in sub_m.columns else 0,
                "RECEIVED": int(sub_m[col_rec].sum()) if col_rec in sub_m.columns else 0,
                "PENDING": int(sub_m[col_pend].sum()) if col_pend in sub_m.columns else 0
            })

        m_df = pd.DataFrame(m_summary)
        
        m_col1, m_col2 = st.columns([1, 1])
        with m_col1:
            st.dataframe(m_df, use_container_width=True)
        with m_col2:
            fig_donut = px.pie(
                names=["RECEIVED QTY", "PENDING QTY"],
                values=[t_rec, t_pend],
                title="ORDER FULFILLMENT RATIO (RECEIVED vs PENDING)",
                hole=0.45, color_discrete_sequence=["#059669", "#DC2626"]
            )
            st.plotly_chart(fig_donut, use_container_width=True)

    # -------------------------------------------------------------
    # 3. PRODUCTION PROCESS & VENDOR PERFORMANCE DASHBOARD
    # -------------------------------------------------------------
    elif selected_dashboard == "3. Production Process & Vendor Performance":
        st.title("🏭 Production Executive Process Dashboard")
        st.markdown("---")

        # Column Mapping (Col B: Date, Col C: Designer, Col F: Category, Col AA: Fabricator, Col AS: InProd, Col AT: Recvd, Col AU: Pending, Col AH: Delay Days)
        col_date    = raw_df.columns[1] if len(raw_df.columns) > 1 else "DATE"
        col_des     = raw_df.columns[2] if len(raw_df.columns) > 2 else "DESIGNER"
        col_item    = raw_df.columns[5] if len(raw_df.columns) > 5 else "CATEGORY"
        col_fab     = raw_df.columns[26] if len(raw_df.columns) > 26 else "FABRICATOR"
        col_delay   = raw_df.columns[33] if len(raw_df.columns) > 33 else "DELAY DAYS"
        
        col_inprod  = raw_df.columns[44] if len(raw_df.columns) > 44 else "INPRODUCTION"
        col_recvd   = raw_df.columns[45] if len(raw_df.columns) > 45 else "RECIEVED"
        col_pending = raw_df.columns[46] if len(raw_df.columns) > 46 else "PENDING"

        # Sidebar Filters
        sel_month = st.sidebar.selectbox("Select Month", ["ALL"] + fy_months)
        fab_opts  = ["ALL"] + sorted([str(x).strip().upper() for x in raw_df[col_fab].unique() if str(x).strip() != ""])
        sel_fab   = st.sidebar.selectbox("Fabricator", fab_opts)
        sel_st    = st.sidebar.selectbox("Status", ["ALL", "COMPLETED", "PENDING"])
        cat_opts  = ["ALL"] + sorted([str(x).strip().upper() for x in raw_df[col_item].unique() if str(x).strip() != ""])
        sel_cat   = st.sidebar.selectbox("Category", cat_opts)
        des_opts  = ["ALL"] + sorted([str(x).strip().upper() for x in raw_df[col_des].unique() if str(x).strip() != ""])
        sel_des   = st.sidebar.selectbox("Designer", des_opts)
        sel_risk  = st.sidebar.selectbox("Delay Risk", ["ALL", "ON-TIME", "OVERDUE (>0 DAYS)"])

        # Data Filter
        df = raw_df.copy()
        if sel_month != "ALL":
            df = df[df[col_date].astype(str).str.contains(sel_month, case=False, na=False)]
        if sel_fab != "ALL":
            df = df[df[col_fab].astype(str).str.upper().str.strip() == sel_fab]
        if sel_cat != "ALL":
            df = df[df[col_item].astype(str).str.upper().str.strip() == sel_cat]
        if sel_des != "ALL":
            df = df[df[col_des].astype(str).str.upper().str.strip() == sel_des]
        
        # Numeric Conversion
        for c in [col_inprod, col_recvd, col_pending, col_delay]:
            if c in df.columns:
                df[c] = pd.to_numeric(df[c], errors='coerce').fillna(0)

        if sel_st == "COMPLETED":
            df = df[df[col_pending] <= 0]
        elif sel_st == "PENDING":
            df = df[df[col_pending] > 0]

        if sel_risk == "ON-TIME":
            df = df[df[col_delay] <= 0]
        elif sel_risk == "OVERDUE (>0 DAYS)":
            df = df[df[col_delay] > 0]

        # KPIs
        t_design   = len(df)
        p_inprod   = int(df[col_inprod].sum()) if col_inprod in df.columns else 0
        p_recvd    = int(df[col_recvd].sum()) if col_recvd in df.columns else 0
        p_pending  = int(df[col_pending].sum()) if col_pending in df.columns else 0
        p_overdue  = int(df[df[col_delay] > 0][col_inprod].sum()) if col_delay in df.columns else 0
        
        avg_delay  = df[df[col_delay] > 0][col_delay].mean() if col_delay in df.columns and len(df[df[col_delay] > 0]) > 0 else 0.0
        ontime_pct = (len(df[df[col_delay] <= 0]) / t_design * 100) if t_design > 0 else 0.0

        p1, p2, p3, p4, p5, p6 = st.columns(6)
        p1.metric("TOTAL DESIGN", f"{t_design:,} Orders")
        p2.metric("INPRODUCTION PCS", f"{p_inprod:,} Pcs")
        p3.metric("RECIEVED PCS", f"{p_recvd:,} Pcs")
        p4.metric("PENDING PCS", f"{p_pending:,} Pcs")
        p5.metric("OVERDUE PCS", f"{p_overdue:,} Pcs")
        p6.metric("AVG OVERDUE DAYS", f"{avg_delay:.1f} Days")

        st.markdown("---")

        # Fabricator Wise Pending Load Chart + Table
        st.subheader("🧵 Fabricator/Vendor Wise Pending Load")
        fab_summary = df.groupby(col_fab)[col_pending].sum().reset_index()
        fab_summary.columns = ["Fabricator Name", "Pending Pcs"]
        fab_summary = fab_summary.sort_values(by="Pending Pcs", ascending=False)

        f_col1, f_col2 = st.columns([1, 1.2])
        with f_col1:
            st.dataframe(fab_summary, use_container_width=True)
        with f_col2:
            fig_fab = px.pie(
                fab_summary, names="Fabricator Name", values="Pending Pcs",
                title="FABRICATOR PENDING PCS SHARE", hole=0.4,
                color_discrete_sequence=px.colors.qualitative.Pastel
            )
            st.plotly_chart(fig_fab, use_container_width=True)

        # Monthly Fulfillment Trend Line Chart
        st.subheader("📈 Monthly Fulfillment Trend Analysis")
        m_trend = df.groupby(col_date)[[col_inprod, col_recvd, col_pending]].sum().reset_index()
        fig_line = px.line(
            m_trend, x=col_date, y=[col_inprod, col_recvd, col_pending],
            title="MONTHLY FULFILLMENT TREND ANALYSIS", markers=True
        )
        st.plotly_chart(fig_line, use_container_width=True)

except Exception as e:
    st.error(f"Error Loading Google Sheets Data: {e}")
