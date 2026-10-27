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

# 1. Google Sheets Robust Live Data Fetching
@st.cache_data(ttl=300)
def load_sheet_data():
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    credentials = Credentials.from_service_account_info(
        st.secrets["gcp_service_account"],
        scopes=scope
    )
    client = gspread.authorize(credentials)
    
    sheet_key = "1wBo0zF2wlqBzY5ZQaX5CPjCOedORwg_1Eh01vje5KFU"
    spreadsheet = client.open_by_key(sheet_key)
    
    # Try getting "CONFIRMATION SHEET" or "ORDER SHEET" or First Sheet
    try:
        ws = spreadsheet.worksheet("CONFIRMATION SHEET")
    except:
        try:
            ws = spreadsheet.worksheet("ORDER SHEET")
        except:
            ws = spreadsheet.get_worksheet(0)
            
    raw_data = ws.get_all_values()
    
    # Header is at Row 5 (Index 4) in your sheet
    if len(raw_data) > 4:
        header = raw_data[4]
        data = raw_data[5:]
    else:
        header = raw_data[0]
        data = raw_data[1:]
        
    df = pd.DataFrame(data, columns=[str(h).strip() for h in header])
    return df

try:
    raw_df = load_sheet_data()
    
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

    fy_months = ["April", "May", "June", "July", "August", "September", "October", "November", "December", "January", "February", "March"]

    # Safely Identify Columns by Index to match Google Apps Script
    col_date = raw_df.columns[1] if len(raw_df.columns) > 1 else "ORDER DATE"
    col_des  = raw_df.columns[2] if len(raw_df.columns) > 2 else "DESIGNER'S NAME"
    col_type = raw_df.columns[3] if len(raw_df.columns) > 3 else "ORDER TYPE"
    col_item = raw_df.columns[5] if len(raw_df.columns) > 5 else "CATEGORY"
    col_qty  = raw_df.columns[9] if len(raw_df.columns) > 9 else "NO. OF PC'S"
    col_client = raw_df.columns[13] if len(raw_df.columns) > 13 else "CLIENT NAME"
    col_fab  = raw_df.columns[20] if len(raw_df.columns) > 20 else "FABRICATOR'S"
    col_delay= raw_df.columns[33] if len(raw_df.columns) > 33 else "Delay Days By Fabricator"
    
    col_inprod  = raw_df.columns[44] if len(raw_df.columns) > 44 else "IN PRODUCTION"
    col_recvd   = raw_df.columns[45] if len(raw_df.columns) > 45 else "RECEIVED"
    col_pending = raw_df.columns[46] if len(raw_df.columns) > 46 else "PENDING"

    # -------------------------------------------------------------
    # 1. DESIGNER PERFORMANCE & CATEGORY TRACKING DASHBOARD
    # -------------------------------------------------------------
    if selected_dashboard == "1. Designer Performance & Category Tracking":
        st.title("👨‍🎨 Executive Designer Performance & Category Tracking Dashboard")
        st.markdown("---")

        sel_month = st.sidebar.selectbox("Select Month", ["ALL"] + fy_months)
        des_list = ["ALL"] + sorted([str(x).strip().upper() for x in raw_df[col_des].unique() if str(x).strip() not in ["", "DESIGNER", "DESIGNER'S NAME"]])
        sel_des = st.sidebar.selectbox("Select Designer", des_list)
        sel_type = st.sidebar.selectbox("Order Type", ["ALL", "NEW", "REPEAT"])

        df = raw_df.copy()
        if sel_month != "ALL":
            df = df[df[col_date].astype(str).str.contains(sel_month, case=False, na=False)]
        if sel_des != "ALL":
            df = df[df[col_des].astype(str).str.upper().str.strip() == sel_des]
        if sel_type != "ALL":
            df = df[df[col_type].astype(str).str.contains(sel_type, case=False, na=False)]

        df[col_qty] = pd.to_numeric(df[col_qty], errors='coerce').fillna(0)

        total_designs = len(df)
        total_qty = int(df[col_qty].sum())
        new_qty = int(df[df[col_type].astype(str).str.contains("NEW", case=False, na=False)][col_qty].sum())
        repeat_qty = int(df[df[col_type].astype(str).str.contains("REPEAT", case=False, na=False)][col_qty].sum())
        
        des_grouped = df.groupby(col_des)[col_qty].sum()
        top_performer = f"{des_grouped.idxmax()} ({int(des_grouped.max()):,} Pcs)" if not des_grouped.empty and des_grouped.max() > 0 else "N/A"

        k1, k2, k3, k4, k5 = st.columns(5)
        k1.metric("TOTAL DESIGNS", f"{total_designs:,}")
        k2.metric("TOTAL QUANTITY (PCS)", f"{total_qty:,}")
        k3.metric("NEW ORDER QTY", f"{new_qty:,}")
        k4.metric("REPEAT ORDER QTY", f"{repeat_qty:,}")
        k5.metric("TOP PERFORMER", top_performer)

        st.markdown("---")
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

    # -------------------------------------------------------------
    # 2. CLIENT PERFORMANCE & FULFILLMENT DASHBOARD
    # -------------------------------------------------------------
    elif selected_dashboard == "2. Client Performance & Fulfillment":
        st.title("🏢 Executive Client Performance & Category Dashboard")
        st.markdown("---")

        sel_month = st.sidebar.selectbox("Select Month", ["ALL"] + fy_months)
        client_opts = ["ALL"] + sorted([str(x).strip().upper() for x in raw_df[col_client].unique() if str(x).strip() not in ["", "CLIENT NAME"]])
        sel_client = st.sidebar.selectbox("Select Client Name", client_opts)
        sel_type = st.sidebar.selectbox("Order Type", ["ALL", "NEW", "REPEAT"])

        df = raw_df.copy()
        if sel_month != "ALL":
            df = df[df[col_date].astype(str).str.contains(sel_month, case=False, na=False)]
        if sel_client != "ALL":
            df = df[df[col_client].astype(str).str.upper().str.strip() == sel_client]
        if sel_type != "ALL":
            df = df[df[col_type].astype(str).str.contains(sel_type, case=False, na=False)]

        for c in [col_qty, col_inprod, col_recvd, col_pending]:
            if c in df.columns:
                df[c] = pd.to_numeric(df[c], errors='coerce').fillna(0)

        t_designs = len(df)
        t_qty = int(df[col_qty].sum()) if col_qty in df.columns else 0
        t_prod = int(df[col_inprod].sum()) if col_inprod in df.columns else 0
        t_rec = int(df[col_recvd].sum()) if col_recvd in df.columns else 0
        t_pend = int(df[col_pending].sum()) if col_pending in df.columns else 0

        c1, c2, c3, c4, c5 = st.columns(5)
        c1.metric("TOTAL DESIGNS", f"{t_designs:,}")
        c2.metric("TOTAL QTY (PCS)", f"{t_qty:,}")
        c3.metric("IN PRODUCTION", f"{t_prod:,}")
        c4.metric("RECEIVED / DONE", f"{t_rec:,}")
        c5.metric("TOTAL PENDING QTY", f"{t_pend:,}")

        st.markdown("---")
        st.subheader("📅 Client Fulfillment Breakdown (Monthly)")
        
        m_summary = []
        for m in fy_months:
            sub_m = raw_df[raw_df[col_date].astype(str).str.contains(m, case=False, na=False)]
            if sel_client != "ALL":
                sub_m = sub_m[sub_m[col_client].astype(str).str.upper().str.strip() == sel_client]
            if sel_type != "ALL":
                sub_m = sub_m[sub_m[col_type].astype(str).str.contains(sel_type, case=False, na=False)]

            for c in [col_qty, col_inprod, col_recvd, col_pending]:
                if c in sub_m.columns:
                    sub_m[c] = pd.to_numeric(sub_m[c], errors='coerce').fillna(0)

            m_summary.append({
                "Month": m,
                "ORDER QTY": int(sub_m[col_qty].sum()) if col_qty in sub_m.columns else 0,
                "IN PRODUCTION": int(sub_m[col_inprod].sum()) if col_inprod in sub_m.columns else 0,
                "RECEIVED": int(sub_m[col_recvd].sum()) if col_recvd in sub_m.columns else 0,
                "PENDING": int(sub_m[col_pending].sum()) if col_pending in sub_m.columns else 0
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

        sel_month = st.sidebar.selectbox("Select Month", ["ALL"] + fy_months)
        fab_opts = ["ALL"] + sorted([str(x).strip().upper() for x in raw_df[col_fab].unique() if str(x).strip() not in ["", "FABRICATOR'S"]])
        sel_fab = st.sidebar.selectbox("Fabricator", fab_opts)

        df = raw_df.copy()
        if sel_month != "ALL":
            df = df[df[col_date].astype(str).str.contains(sel_month, case=False, na=False)]
        if sel_fab != "ALL":
            df = df[df[col_fab].astype(str).str.upper().str.strip() == sel_fab]

        for c in [col_inprod, col_recvd, col_pending, col_delay]:
            if c in df.columns:
                df[c] = pd.to_numeric(df[c], errors='coerce').fillna(0)

        t_design = len(df)
        p_inprod = int(df[col_inprod].sum()) if col_inprod in df.columns else 0
        p_recvd = int(df[col_recvd].sum()) if col_recvd in df.columns else 0
        p_pending = int(df[col_pending].sum()) if col_pending in df.columns else 0
        p_overdue = int(df[df[col_delay] > 0][col_inprod].sum()) if col_delay in df.columns else 0

        p1, p2, p3, p4, p5 = st.columns(5)
        p1.metric("TOTAL DESIGN", f"{t_design:,} Orders")
        p2.metric("INPRODUCTION PCS", f"{p_inprod:,} Pcs")
        p3.metric("RECIEVED PCS", f"{p_recvd:,} Pcs")
        p4.metric("PENDING PCS", f"{p_pending:,} Pcs")
        p5.metric("OVERDUE PCS", f"{p_overdue:,} Pcs")

        st.markdown("---")
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

except Exception as e:
    st.error(f"Error Loading Google Sheets Data: {e}")
