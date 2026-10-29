import html
import re
from datetime import datetime

import numpy as np
import pandas as pd
import plotly.express as px
import streamlit as st
import gspread
from google.oauth2.service_account import Credentials

# -----------------------------------------------------------------------------
# 1. PAGE SETUP & CONFIG
# -----------------------------------------------------------------------------
st.set_page_config(
    page_title="Executive Operations & Production Hub 2026-27",
    page_icon="📊",
    layout="wide",
)

SHEET_REGISTRY = {
    "Master Sheet": {
        "id": "1wBo0zF2wlqBzY5ZQaX5CPjCOedORwg_1Eh01vje5KFU",
        "type": "tracker",
        "dashboard_tabs": {
            "designer": "DESIGNER DASHBOARD",
            "production": "PRODUCTION PROCESS DASHBOARD",
            "client": "CLIENT DASHBOARD",
        },
    },
    "Sample Summary": {
        "id": "1EfQ08lXGL8YjtoaZ2ygJtNVaED7doDijo2jFvCuS7Kg",
        "type": "sample_summary",
        "gid": 1117754857,
        "dashboard_tab": "SAMPLE DASHBOARD",
    },
    "Fabricator Report": {
        "id": "1hP9Bkvu2F-qj4tXYhOCb4alfJOZZtAsMQNOjVQyWoo4",
        "type": "overview_fabricators",
        "gid": 318103522,
        "dashboard_tab": "FABRICATOR DASHBOARD",
    },
}

FY_START_YEAR = 2026
MONTHS = ["April", "May", "June", "July", "August", "September",
          "October", "November", "December", "January", "February", "March"]
FY_MONTH_LABELS = [
    f"{m}-{(FY_START_YEAR if i < 9 else FY_START_YEAR + 1) % 100:02d}" for i, m in enumerate(MONTHS)
]
LIVE_TTL = 60          
TOTAL_LABELS = {"TOTAL", "GRAND TOTAL", "ALL FABRICATORS"}


def _stretch_kwargs():
    try:
        major, minor = (int(p) for p in st.__version__.split(".")[:2])
    except Exception:
        return {"use_container_width": True}
    return {"width": "stretch"} if (major, minor) >= (1, 50) else {"use_container_width": True}

STRETCH = _stretch_kwargs()

PALETTE = ["#2563eb", "#059669", "#d97706", "#dc2626", "#7c3aed", "#0891b2", "#db2777", "#65a30d",
           "#ea580c", "#0d9488", "#9333ea", "#ca8a04"]
PLOT_TEMPLATE = "plotly_white"
THEME = {"panel": "#ffffff", "text": "#0f172a", "muted": "#475569", "border": "#cbd5e1"}


def apply_theme():
    global PLOT_TEMPLATE
    if "dashboard_dark_mode" not in st.session_state:
        st.session_state.dashboard_dark_mode = False

    with st.sidebar:
        st.markdown("### 🎨 Preferences")
        st.toggle("Dark mode", key="dashboard_dark_mode", help="Dashboard appearance mode toggle")

    dark = st.session_state.dashboard_dark_mode
    if dark:
        app_bg, panel_bg, text, muted, border = "#0b1220", "#111a2e", "#e8eef8", "#9fb0c8", "#26344d"
        card_bg, chip_bg, accent = "#162038", "#1f2d47", "#38bdf8"
        hero_grad = "#131e33 0%, #172a48 100%"
        PLOT_TEMPLATE = "plotly_dark"
    else:
        app_bg, panel_bg, text, muted, border = "#f1f5f9", "#ffffff", "#0f172a", "#475569", "#cbd5e1"
        card_bg, chip_bg, accent = "#f8fafc", "#e2e8f0", "#2563eb"
        hero_grad = "#ffffff 0%, #e8f0ff 100%"
        PLOT_TEMPLATE = "plotly_white"

    THEME.update(panel=panel_bg, text=text, muted=muted, border=border)
    px.defaults.template = PLOT_TEMPLATE
    px.defaults.color_discrete_sequence = PALETTE

    st.markdown(f"""
<style>
:root {{
    --app-bg: {app_bg}; --panel-bg: {panel_bg}; --card-bg: {card_bg}; --text-color: {text};
    --muted-color: {muted}; --border-color: {border}; --chip-bg: {chip_bg}; --accent: {accent};
    color-scheme: {'dark' if dark else 'light'};
}}
.stApp, [data-testid="stAppViewContainer"], [data-testid="stMain"] {{ background-color: var(--app-bg) !important; color: var(--text-color); font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; }}
[data-testid="stHeader"] {{ background-color: var(--app-bg) !important; }}
.block-container {{ padding-top: 2.6rem; padding-bottom: 2.8rem; max-width: 1650px; }}

.stApp p, .stApp li, .stApp h1, .stApp h2, .stApp h3, .stApp h4, .stApp h5, .stApp h6,
.stApp label, [data-testid="stWidgetLabel"] p, [data-testid="stMarkdownContainer"] {{ color: var(--text-color); }}
[data-testid="stCaptionContainer"], .stApp small {{ color: var(--muted-color) !important; }}

[data-testid="stSidebar"] {{ background-color: var(--panel-bg) !important; border-right: 1px solid var(--border-color); }}
[data-testid="stSidebar"] h3 {{ font-size: .83rem; font-weight: 750; text-transform: uppercase; letter-spacing: 0.08em; color: var(--muted-color); margin-bottom: 0.6rem; }}
[data-testid="stSidebar"] label, [data-testid="stSidebar"] p {{ color: var(--text-color) !important; }}

div[data-baseweb="select"] > div, div[data-baseweb="input"] > div {{ background: var(--panel-bg) !important; color: var(--text-color) !important; border: 1px solid var(--border-color) !important; border-radius: 8px; }}
div[data-baseweb="select"] span, div[data-baseweb="select"] input {{ color: var(--text-color) !important; }}
div[data-baseweb="popover"] ul, div[data-baseweb="menu"] {{ background: var(--panel-bg) !important; }}
div[data-baseweb="popover"] li, div[data-baseweb="menu"] li {{ color: var(--text-color) !important; background: var(--panel-bg) !important; }}
div[data-baseweb="popover"] li:hover {{ background: var(--chip-bg) !important; }}
button[kind="secondary"], [data-testid="stBaseButton-secondary"] {{ background: var(--chip-bg) !important; color: var(--text-color) !important; border: 1px solid var(--border-color) !important; }}

[data-testid="stMetric"] {{ background: var(--panel-bg); border: 1px solid var(--border-color); border-top: 3px solid var(--accent); padding: 14px 18px; border-radius: 12px; box-shadow: 0 4px 14px rgba(0,0,0,0.05); min-height: 108px; }}
[data-testid="stMetricLabel"] {{ color: var(--muted-color) !important; }}
[data-testid="stMetricLabel"] p {{ color: var(--muted-color) !important; font-size: .74rem; font-weight: 700; text-transform: uppercase; letter-spacing: .03em; white-space: normal; line-height: 1.25; }}
[data-testid="stMetricValue"], [data-testid="stMetricValue"] > div {{ color: var(--text-color) !important; font-weight: 800; font-size: 1.35rem; white-space: normal; overflow-wrap: anywhere; line-height: 1.2; }}
[data-testid="stMetricDelta"] {{ color: var(--accent) !important; font-weight: 700; }}

[data-testid="stTabs"] [role="tablist"] {{ position: sticky; top: 3.4rem; z-index: 99; background-color: var(--app-bg); padding: 4px 0; border-bottom: 2px solid var(--border-color); }}
[data-testid="stTabs"] button {{ border-radius: 8px 8px 0 0; padding: 10px 20px; }}
[data-testid="stTabs"] button p {{ font-weight: 700; font-size: .92rem; color: var(--muted-color); }}
[data-testid="stTabs"] button[aria-selected="true"] p {{ color: var(--accent); }}

[data-testid="stPlotlyChart"] {{ background: var(--panel-bg); border: 1px solid var(--border-color); border-radius: 12px; padding: 8px; }}

.tbl-wrap {{ overflow: auto; border: 1px solid var(--border-color); border-radius: 10px; background: var(--panel-bg); margin-bottom: 14px; }}
.dash-tbl {{ width: 100%; border-collapse: collapse; font-size: .82rem; color: var(--text-color); }}
.dash-tbl th {{ position: sticky; top: 0; z-index: 1; background: var(--chip-bg); color: var(--text-color); text-align: right; padding: 9px 12px; font-weight: 750; font-size: .72rem; text-transform: uppercase; letter-spacing: .03em; white-space: nowrap; border-bottom: 1px solid var(--border-color); }}
.dash-tbl td {{ padding: 7px 12px; text-align: right; border-bottom: 1px solid var(--border-color); white-space: nowrap; color: var(--text-color); }}
.dash-tbl th:first-child, .dash-tbl td:first-child {{ text-align: left; }}
.dash-tbl tbody tr:nth-child(even) td {{ background: var(--card-bg); }}
.dash-tbl tbody tr:hover td {{ background: var(--chip-bg); }}
.dash-tbl tr.tot td {{ font-weight: 800; background: var(--chip-bg); border-top: 2px solid var(--accent); }}
.dash-tbl tr.ref td {{ font-style: italic; color: var(--muted-color); }}

.dashboard-hero {{ background: linear-gradient(135deg, {hero_grad}); border: 1px solid var(--border-color); border-radius: 14px; padding: 18px 22px; margin-bottom: 18px; box-shadow: 0 4px 15px rgba(0,0,0,0.04); }}
.dashboard-hero h2 {{ margin: 0; font-size: 1.45rem; font-weight: 800; letter-spacing: -0.02em; color: var(--text-color); }}
.dashboard-hero p {{ color: var(--muted-color); margin: 3px 0 0 0; font-size: .88rem; }}
.section-badge {{ display: inline-flex; align-items: center; background: var(--chip-bg); color: var(--text-color); padding: 4px 12px; border-radius: 6px; font-size: 0.8rem; font-weight: 750; margin: 10px 0 8px 0; text-transform: uppercase; letter-spacing: .02em; }}
.filter-chips {{ display: flex; flex-wrap: wrap; gap: 6px; align-items: center; margin: 2px 0 14px 0; }}
.filter-chips .lead {{ color: var(--muted-color); font-size: .78rem; font-weight: 700; margin-right: 4px; }}
.filter-chips .chip {{ background: var(--chip-bg); border: 1px solid var(--border-color); color: var(--text-color); padding: 3px 11px; border-radius: 999px; font-size: .78rem; }}
</style>
""", unsafe_allow_html=True)


# -----------------------------------------------------------------------------
# 2. DISPLAY HELPERS
# -----------------------------------------------------------------------------
def style_fig(fig, height=360):
    fig.update_layout(
        template=PLOT_TEMPLATE,
        height=height,
        paper_bgcolor=THEME["panel"],
        plot_bgcolor=THEME["panel"],
        margin=dict(l=12, r=12, t=50, b=10),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1, title_text=""),
        font=dict(size=11, color=THEME["text"]),
        title_font=dict(size=14, color=THEME["text"], family="-apple-system, sans-serif"),
    )
    fig.update_xaxes(gridcolor=THEME["border"], zerolinecolor=THEME["border"], linecolor=THEME["border"])
    fig.update_yaxes(gridcolor=THEME["border"], zerolinecolor=THEME["border"], linecolor=THEME["border"])
    return fig


def show_chart(fig, height=360):
    st.plotly_chart(style_fig(fig, height), theme=None, **STRETCH)


def badge(text):
    st.markdown(f'<div class="section-badge">{html.escape(text)}</div>', unsafe_allow_html=True)


def show_table(df, pct_cols=(), height=None):
    if df is None or df.empty:
        st.info("Is section ka data sheet me abhi nahi mila.")
        return
    num_cols = {c for c in df.columns if pd.api.types.is_numeric_dtype(df[c])}
    head = "".join(f"<th>{html.escape(str(c))}</th>" for c in df.columns)
    rows = []
    for _, r in df.iterrows():
        label = str(r.iloc[0]).strip().upper()
        cls = "tot" if label in TOTAL_LABELS else ("ref" if label.startswith("ALL OVER") else "")
        tds = []
        for c in df.columns:
            v = r[c]
            if c in num_cols:
                if c in pct_cols:
                    hue = max(0.0, min(float(v), 100.0)) * 1.4
                    style = "" if cls else f' style="background:hsla({hue:.0f},65%,45%,.22)"'
                    tds.append(f"<td{style}>{float(v):.1f}%</td>")
                else:
                    tds.append(f"<td>{float(v):,.0f}</td>")
            else:
                tds.append(f"<td>{html.escape(str(v))}</td>")
        rows.append(f'<tr class="{cls}">{"".join(tds)}</tr>')
    style = f' style="max-height:{int(height)}px"' if height else ""
    st.markdown(
        f'<div class="tbl-wrap"{style}><table class="dash-tbl"><thead><tr>{head}</tr></thead>'
        f'<tbody>{"".join(rows)}</tbody></table></div>',
        unsafe_allow_html=True,
    )


def body(df, drop_prefix=("⚠", "ALL OVER")):
    if df is None or df.empty:
        return df
    lab = df.iloc[:, 0].astype(str).str.strip().str.upper()
    keep = ~lab.isin(TOTAL_LABELS)
    for p in drop_prefix:
        keep &= ~lab.str.startswith(p)
    return df[keep]


def render_kpi_cards(kpis, per_row=4):
    for i in range(0, len(kpis), per_row):
        chunk = kpis[i:i + per_row]
        cols = st.columns(per_row)
        for col, (title, value, sub) in zip(cols, chunk):
            col.metric(title, value, delta=sub or None, delta_color="off")


def show_filter_chips_from_dict(filters_dict):
    chips = "".join(
        f'<span class="chip">{html.escape(label)}: <b>{html.escape(str(val))}</b></span>'
        for label, val in filters_dict.items())
    st.markdown(
        f'<div class="filter-chips"><span class="lead">🔎 Selected Live Filters:</span>{chips}</div>',
        unsafe_allow_html=True)


def hero(title, source_tab, extra=""):
    st.markdown(
        f"""<div class="dashboard-hero"><h2>{html.escape(title)}</h2>
        <p>Source Data: <b>{html.escape(source_tab)}</b> · Live Dynamic Calculation ·
        Loaded: {datetime.now().strftime('%d %b %Y, %H:%M')}{extra}</p></div>""",
        unsafe_allow_html=True)


# -----------------------------------------------------------------------------
# 3. GOOGLE SHEETS AUTH & DATA LOADERS
# -----------------------------------------------------------------------------
def show_access_error(e=None):
    email = ""
    try:
        email = st.secrets["gcp_service_account"]["client_email"]
    except Exception:
        pass
    st.error("Could not open this Google Sheet. Share it with service account: "
             + (f"**{email}**" if email else "email from secrets")
             + (f"\n\nDetails: `{e}`" if e else ""))


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


def _open_book(sheet_id):
    try:
        return get_client().open_by_key(sheet_id)
    except Exception as e:
        show_access_error(e)
        st.stop()


def _a1_tab(title):
    return "'" + str(title).replace("'", "''") + "'"


def norm_key(x):
    return re.sub(r"[^A-Z0-9]", "", str(x).upper())


def find_tab(tabs, wanted):
    w = norm_key(wanted)
    for t in tabs:
        if norm_key(t) == w:
            return t
    return None


@st.cache_data(ttl=300, show_spinner=False)
def list_tab_meta(sheet_id):
    return [(ws.title, ws.id) for ws in _open_book(sheet_id).worksheets()]


@st.cache_data(ttl=LIVE_TTL, show_spinner="Google Sheet se live raw data load ho raha hai...")
def load_raw_data_frame(sheet_id, wanted_tab="ORDER SHEET"):
    book = _open_book(sheet_id)
    meta = list_tab_meta(sheet_id)
    titles = [t for t, _ in meta]
    tab = find_tab(titles, wanted_tab) or find_tab(titles, "CONFIRMATION SHEET") or titles[0]
    
    resp = book.values_get(_a1_tab(tab), params={
        "valueRenderOption": "UNFORMATTED_VALUE",
        "dateTimeRenderOption": "FORMATTED_STRING",
    })
    values = resp.get("values", [])
    if not values or len(values) < 5:
        st.error(f"'{tab}' me sufficient data nahi mil raha hai.")
        st.stop()
    
    # Data Row 5 (index 4) se start hota hai
    headers = [str(c).strip() if c else f"Col_{i}" for i, c in enumerate(values[4])]
    data = values[5:]
    
    # Padding rows
    max_len = max(len(headers), max(len(r) for r in data) if data else 0)
    data_padded = [r + [""] * (max_len - len(r)) for r in data]
    
    df = pd.DataFrame(data_padded)
    # 0-indexed column position safety mapping
    return tab, df


@st.cache_data(ttl=LIVE_TTL, show_spinner="Dashboard Grid Load ho raha hai...")
def load_live_values(sheet_id, tab_title):
    book = _open_book(sheet_id)
    resp = book.values_get(_a1_tab(tab_title), params={
        "valueRenderOption": "UNFORMATTED_VALUE",
        "dateTimeRenderOption": "SERIAL_NUMBER",
    })
    return resp.get("values", [])


def get_dashboard_grid(sheet_id, wanted, gid=None):
    meta = list_tab_meta(sheet_id)
    titles = [t for t, _ in meta]
    tab = find_tab(titles, wanted)
    if tab is None and gid is not None:
        for t, i in meta:
            if str(i) == str(gid) and "DASHBOARD" in t.upper():
                tab = t
    if tab is None:
        st.error(f"Google Sheet me '{wanted}' tab nahi mila.")
        st.stop()
    grid = load_live_values(sheet_id, tab)
    return tab, grid


# -----------------------------------------------------------------------------
# 4. GRID HELPER FUNCTIONS (Sample & Fabricator Dashboards ke liye)
# -----------------------------------------------------------------------------
def _cell(grid, r, c):
    if r < 0 or r >= len(grid):
        return ""
    row = grid[r]
    if c < 0 or c >= len(row):
        return ""
    return row[c]


def _to_float(v):
    if v is None or isinstance(v, bool):
        return 0.0
    if isinstance(v, (int, float)):
        return float(v) if np.isfinite(v) else 0.0
    t = str(v).replace("\xa0", " ").strip().replace(",", "")
    if re.fullmatch(r"\(\d+(\.\d+)?\)", t):
        return -float(t[1:-1])
    if re.fullmatch(r"[-+]?(\d+(\.\d*)?|\.\d+)", t):
        return float(t)
    return 0.0


def _txt(v):
    if v is None:
        return ""
    if isinstance(v, float) and v.is_integer():
        v = int(v)
    return re.sub(r"\s+", " ", str(v).replace("\xa0", " ")).strip()


def _fmt_value(v):
    if isinstance(v, bool):
        return str(v)
    if isinstance(v, (int, float)):
        return f"{v:,.0f}"
    t = _txt(v)
    return t if t else "—"


def find_cell(grid, pattern, max_col=24, max_row=400):
    rx = re.compile(pattern, re.I)
    for r in range(min(len(grid), max_row)):
        row = grid[r]
        for c in range(min(len(row), max_col)):
            v = row[c]
            if isinstance(v, str) and rx.search(v):
                return r, c
    return None


def cell_text(grid, pattern):
    pos = find_cell(grid, pattern)
    return _txt(_cell(grid, *pos)) if pos else ""


def read_kpis(grid, title_row, value_row, sub_row=None):
    out = []
    trow = grid[title_row] if title_row < len(grid) else []
    for c, v in enumerate(trow):
        title = _txt(v)
        if title and c < 24:
            val = _fmt_value(_cell(grid, value_row, c))
            sub = _txt(_cell(grid, sub_row, c)) if sub_row is not None else ""
            out.append((title.replace("RECIEVED", "RECEIVED"), val, sub))
    return out


def read_table(grid, title_pat, cols, pct=(), label_col=None, stop_total=True):
    names = [n for n, _ in cols]
    pos = find_cell(grid, title_pat)
    if not pos:
        return pd.DataFrame(columns=[n or f"col{i}" for i, n in enumerate(names)])
    hr = pos[0] + 1
    resolved = [((n if n else _txt(_cell(grid, hr, c))), c) for n, c in cols]
    lc = label_col if label_col is not None else resolved[0][1]
    rows, r = [], hr + 1
    while r < len(grid) and len(rows) < 300:
        label = _txt(_cell(grid, r, lc))
        if not label:
            break
        rec = []
        for name, c in resolved:
            if c == lc:
                rec.append(label)
            else:
                val = _to_float(_cell(grid, r, c))
                rec.append(val * 100 if name in pct else val)
        rows.append(rec)
        if stop_total and label.upper() in TOTAL_LABELS:
            break
        r += 1
    return pd.DataFrame(rows, columns=[n for n, _ in resolved])


def read_pairs(grid, label_col, value_cols, start_row=1, header_row=0):
    names = [_txt(_cell(grid, header_row, c)) for c in [label_col] + list(value_cols)]
    rows, r = [], start_row
    while r < len(grid):
        label = _txt(_cell(grid, r, label_col))
        if not label:
            break
        rows.append([label] + [_to_float(_cell(grid, r, c)) for c in value_cols])
        r += 1
    return pd.DataFrame(rows, columns=names)


def melt_cols(df, exclude=("TOTAL",)):
    value_cols = [c for c in df.columns[1:] if str(c).upper() not in exclude]
    return df.melt(id_vars=df.columns[0], value_vars=value_cols, var_name="Category", value_name="Pcs")


# -----------------------------------------------------------------------------
# 5. DYNAMIC MASTER SHEET VIEWS (DIRECT LIVE CALCULATIONS FROM ORDER SHEET)
# -----------------------------------------------------------------------------

def parse_order_date_to_month(val):
    if not val or pd.isna(val):
        return ""
    val_str = str(val).strip()
    for m in MONTHS:
        if m.lower() in val_str.lower():
            return m
    try:
        dt = pd.to_datetime(val_str, errors='coerce')
        if not pd.isna(dt):
            return dt.strftime('%B')
    except Exception:
        pass
    return ""

def prepare_master_data(df_raw):
    """Word Docs Column Specifications ke aadhar par Master Data cleaning[cite: 3, 6, 7]."""
    df = pd.DataFrame()
    
    # Column B (index 1): Order Date[cite: 3, 6, 7]
    date_series = df_raw.iloc[:, 1] if df_raw.shape[1] > 1 else pd.Series()
    df['Month'] = date_series.apply(parse_order_date_to_month)
    
    # Column C (index 2): Designer Name (for Production Dashboard)[cite: 6]
    df['Designer_C'] = df_raw.iloc[:, 2].astype(str).str.strip().str.upper() if df_raw.shape[1] > 2 else ""
    
    # Column D (index 3): Order Type (NEW / REPEAT)[cite: 3, 7]
    df['Order_Type'] = df_raw.iloc[:, 3].astype(str).str.strip().str.upper() if df_raw.shape[1] > 3 else ""
    
    # Column F (index 5): Category[cite: 3, 6, 7]
    df['Category'] = df_raw.iloc[:, 5].astype(str).str.strip().str.upper() if df_raw.shape[1] > 5 else ""
    
    # Column J (index 9): Order Quantity (Pcs)[cite: 3, 7]
    df['Order_Qty'] = pd.to_numeric(df_raw.iloc[:, 9], errors='coerce').fillna(0) if df_raw.shape[1] > 9 else 0
    
    # Column N (index 13): Designer Name (Designer Dashboard) / Client Name[cite: 3, 7]
    df['Designer_N'] = df_raw.iloc[:, 13].astype(str).str.strip().str.upper() if df_raw.shape[1] > 13 else ""
    df['Client_Name'] = df_raw.iloc[:, 13].astype(str).str.strip() if df_raw.shape[1] > 13 else ""
    
    # Column AA (index 26): Fabricator Name[cite: 6]
    df['Fabricator'] = df_raw.iloc[:, 26].astype(str).str.strip().str.upper() if df_raw.shape[1] > 26 else ""
    
    # Column AH (index 33): Delay Days[cite: 6]
    df['Delay_Days'] = pd.to_numeric(df_raw.iloc[:, 33], errors='coerce').fillna(0) if df_raw.shape[1] > 33 else 0
    
    # Column AS (index 44): In Production Qty[cite: 6, 7]
    df['In_Production'] = pd.to_numeric(df_raw.iloc[:, 44], errors='coerce').fillna(0) if df_raw.shape[1] > 44 else 0
    
    # Column AT (index 45): Received Qty[cite: 6, 7]
    df['Received'] = pd.to_numeric(df_raw.iloc[:, 45], errors='coerce').fillna(0) if df_raw.shape[1] > 45 else 0
    
    # Column AU (index 46): Pending Qty[cite: 6, 7]
    df['Pending'] = pd.to_numeric(df_raw.iloc[:, 46], errors='coerce').fillna(0) if df_raw.shape[1] > 46 else 0
    
    # Column AX (index 49): Status[cite: 7]
    df['Status'] = df_raw.iloc[:, 49].astype(str).str.strip().str.upper() if df_raw.shape[1] > 49 else ""
    
    return df


def designer_view(sheet_id, cfg):
    tab_name, df_raw = load_raw_data_frame(sheet_id, "ORDER SHEET")
    df = prepare_master_data(df_raw)
    
    # Dynamic Designer Names from Column N[cite: 3]
    valid_designers = sorted([d for d in df['Designer_N'].unique() if d and d not in ["DESIGNER", "DESIGNER NAME", "DESIGNER'S NAME", "NAME"]])
    
    # Interactive Sidebar Filters for Live Calculation
    with st.sidebar:
        st.markdown("### 🔍 Designer Live Filters")
        sel_month = st.selectbox("Month", ["ALL"] + MONTHS, key="des_m")
        sel_designer = st.selectbox("Designer", ["ALL"] + valid_designers, key="des_d")
        sel_type = st.selectbox("Order Type", ["ALL", "NEW", "REPEAT"], key="des_t")
        sel_cat = st.selectbox("Category", ["ALL", "CO-ORD SET", "KURTA PANT", "TOP", "KURTA PANT DUPATTA", "DRESS", "KAFTAN", "KURTA"], key="des_c")
    
    filters_selected = {"Month": sel_month, "Designer": sel_designer, "Order Type": sel_type, "Category": sel_cat}
    
    # Filtering DataFrame dynamically
    df_filtered = df[(df['Designer_N'] != "")].copy()
    if sel_month != "ALL":
        df_filtered = df_filtered[df_filtered['Month'].str.lower() == sel_month.lower()]
    if sel_designer != "ALL":
        df_filtered = df_filtered[df_filtered['Designer_N'] == sel_designer]
    if sel_type != "ALL":
        df_filtered = df_filtered[df_filtered['Order_Type'].str.contains(sel_type, case=False, na=False)]
    if sel_cat != "ALL":
        df_filtered = df_filtered[df_filtered['Category'] == sel_cat]
        
    st.subheader("👩‍🎨 Executive Designer Performance & Category Tracking Dashboard")
    st.caption(f"Calculated Live from: {tab_name}")
    show_filter_chips_from_dict(filters_selected)
    
    # KPI Calculations[cite: 3]
    tot_designs = len(df_filtered)
    tot_qty = df_filtered['Order_Qty'].sum()
    new_qty = df_filtered[df_filtered['Order_Type'].str.contains("NEW", na=False)]['Order_Qty'].sum()
    repeat_qty = df_filtered[df_filtered['Order_Type'].str.contains("REPEAT", na=False)]['Order_Qty'].sum()
    
    # Top Performer calculation[cite: 3]
    des_grp = df_filtered.groupby('Designer_N')['Order_Qty'].sum()
    top_performer = f"{des_grp.idxmax()} ({des_grp.max():,.0f} Pcs)" if not des_grp.empty and des_grp.max() > 0 else "N/A"
    
    kpis = [
        ("TOTAL DESIGNS", f"{tot_designs:,.0f}", ""),
        ("TOTAL QUANTITY (PCS)", f"{tot_qty:,.0f}", ""),
        ("NEW ORDER QTY", f"{new_qty:,.0f}", ""),
        ("REPEAT ORDER QTY", f"{repeat_qty:,.0f}", ""),
        ("🏆 TOP PERFORMER", top_performer, "")
    ]
    render_kpi_cards(kpis, per_row=5)

    st.markdown("---")
    badge("👩‍🎨 Designer Volume & Share Breakdown")
    
    # Table 1: Designer Volume & Share Breakdown[cite: 3]
    des_list_to_show = valid_designers if sel_designer == "ALL" else [sel_designer]
    tbl1_rows = []
    for d_name in des_list_to_show:
        d_df = df_filtered[df_filtered['Designer_N'] == d_name]
        d_new = d_df[d_df['Order_Type'].str.contains("NEW", na=False)]['Order_Qty'].sum()
        d_repeat = d_df[d_df['Order_Type'].str.contains("REPEAT", na=False)]['Order_Qty'].sum()
        d_vol = d_new + d_repeat
        d_count = len(d_df)
        tbl1_rows.append({
            "Designer Name": d_name,
            "New Orders (Pcs)": d_new,
            "Repeat Orders (Pcs)": d_repeat,
            "Total Volume (Pcs)": d_vol,
            "Share %": 0.0,
            "Design Count": d_count
        })
    df_tbl1 = pd.DataFrame(tbl1_rows)
    tot_vol_all = df_tbl1['Total Volume (Pcs)'].sum()
    if tot_vol_all > 0:
        df_tbl1['Share %'] = (df_tbl1['Total Volume (Pcs)'] / tot_vol_all) * 100
        
    tot_row = pd.DataFrame([{
        "Designer Name": "TOTAL",
        "New Orders (Pcs)": df_tbl1['New Orders (Pcs)'].sum(),
        "Repeat Orders (Pcs)": df_tbl1['Repeat Orders (Pcs)'].sum(),
        "Total Volume (Pcs)": tot_vol_all,
        "Share %": 100.0,
        "Design Count": df_tbl1['Design Count'].sum()
    }])
    df_tbl1_full = pd.concat([df_tbl1, tot_row], ignore_index=True)
    
    c1, c2 = st.columns([1.2, 1])
    with c1:
        show_table(df_tbl1_full, pct_cols=("Share %",))
    with c2:
        b = body(df_tbl1_full)
        if b is not None and not b.empty:
            m = b.melt(id_vars="Designer Name", value_vars=["New Orders (Pcs)", "Repeat Orders (Pcs)"],
                       var_name="Order Type", value_name="Qty")
            fig = px.bar(m, x="Designer Name", y="Qty", color="Order Type", barmode="group",
                         title="DESIGNER PERFORMANCE: NEW vs REPEAT ORDERS (PCS)",
                         color_discrete_sequence=["#059669", "#7C3AED"])
            fig.update_xaxes(title="", tickangle=-35)
            show_chart(fig, 380)

    st.markdown("---")
    badge("👗 Category Wise Designer Breakdown (Pcs)")
    
    # Table 2: Category Wise Designer Matrix[cite: 3]
    categories = ["CO-ORD SET", "KURTA PANT", "TOP", "KURTA PANT DUPATTA", "DRESS", "KAFTAN", "KURTA"]
    cat_rows = []
    for d_name in des_list_to_show:
        d_df = df_filtered[df_filtered['Designer_N'] == d_name]
        row_dict = {"Designer": d_name}
        row_tot = 0
        for cat in categories:
            val = d_df[d_df['Category'] == cat]['Order_Qty'].sum()
            row_dict[cat] = val
            row_tot += val
        row_dict["TOTAL"] = row_tot
        cat_rows.append(row_dict)
    
    df_cat = pd.DataFrame(cat_rows)
    tot_cat_dict = {"Designer": "TOTAL"}
    for cat in categories + ["TOTAL"]:
        tot_cat_dict[cat] = df_cat[cat].sum() if not df_cat.empty else 0
    df_cat_full = pd.concat([df_cat, pd.DataFrame([tot_cat_dict])], ignore_index=True)
    
    c3, c4 = st.columns([1.25, 1])
    with c3:
        show_table(df_cat_full)
    with c4:
        # Monthly Performance Trend Calculation
        trend_records = []
        for m_name in MONTHS:
            m_df = df_filtered[df_filtered['Month'].str.lower() == m_name.lower()]
            for d_name in des_list_to_show:
                pcs = m_df[m_df['Designer_N'] == d_name]['Order_Qty'].sum()
                if pcs > 0:
                    trend_records.append({"Month": m_name, "Designer": d_name, "Pcs": pcs})
        trend_df = pd.DataFrame(trend_records)
        if not trend_df.empty:
            fig = px.bar(trend_df, x="Month", y="Pcs", color="Designer",
                         title="MONTHLY DESIGNER PERFORMANCE TREND (PCS)",
                         category_orders={"Month": MONTHS})
            fig.update_layout(barmode="stack")
            fig.update_xaxes(tickangle=-35, title="")
            show_chart(fig, 380)
        else:
            st.info("Selected filters ke liye monthly data nahi hai.")


def production_view(sheet_id, cfg):
    tab_name, df_raw = load_raw_data_frame(sheet_id, "ORDER SHEET")
    df = prepare_master_data(df_raw)
    
    # Unique Filter Lists for Production Dashboard[cite: 6]
    valid_fabs = sorted([f for f in df['Fabricator'].unique() if f and f not in ["FABRICATOR", "FABRICATOR'S", "NAME"]])
    valid_des = sorted([d for d in df['Designer_C'].unique() if d and d not in ["DESIGNER", "DESIGNER'S NAME", "NAME"]])
    
    with st.sidebar:
        st.markdown("### 🔍 Production Live Filters")
        sel_month = st.selectbox("Month", ["ALL"] + MONTHS, key="prod_m")
        sel_fab = st.selectbox("Fabricator", ["ALL"] + valid_fabs, key="prod_f")
        sel_st = st.selectbox("Status", ["ALL", "COMPLETED", "PENDING"], key="prod_s")
        sel_cat = st.selectbox("Category", ["ALL", "CO-ORD SET", "KURTA PANT", "TOP", "KURTA PANT DUPATTA", "DRESS", "KAFTAN", "KURTA"], key="prod_c")
        sel_des = st.selectbox("Designer", ["ALL"] + valid_des, key="prod_d")
        sel_risk = st.selectbox("Delay Risk", ["ALL", "ON-TIME", "OVERDUE (>0 DAYS)"], key="prod_r")
        
    filters_selected = {
        "Month": sel_month, "Fabricator": sel_fab, "Status": sel_st,
        "Category": sel_cat, "Designer": sel_des, "Delay Risk": sel_risk
    }
    
    # Filter Data dynamically[cite: 6]
    df_filtered = df[(df['Fabricator'] != "")].copy()
    if sel_month != "ALL":
        df_filtered = df_filtered[df_filtered['Month'].str.lower() == sel_month.lower()]
    if sel_fab != "ALL":
        df_filtered = df_filtered[df_filtered['Fabricator'] == sel_fab]
    if sel_st != "ALL":
        if sel_st == "COMPLETED":
            df_filtered = df_filtered[df_filtered['Pending'] <= 0]
        else:
            df_filtered = df_filtered[df_filtered['Pending'] > 0]
    if sel_cat != "ALL":
        df_filtered = df_filtered[df_filtered['Category'] == sel_cat]
    if sel_des != "ALL":
        df_filtered = df_filtered[df_filtered['Designer_C'] == sel_des]
    if sel_risk != "ALL":
        if sel_risk == "ON-TIME":
            df_filtered = df_filtered[df_filtered['Delay_Days'] <= 0]
        else:
            df_filtered = df_filtered[df_filtered['Delay_Days'] > 0]
            
    st.subheader("🏭 Production Executive Process Dashboard")
    st.caption(f"Calculated Live from: {tab_name}")
    show_filter_chips_from_dict(filters_selected)
    
    # Production KPIs[cite: 6]
    tot_designs = len(df_filtered)
    in_prod_pcs = df_filtered['In_Production'].sum()
    rcvd_pcs = df_filtered['Received'].sum()
    pending_pcs = df_filtered['Pending'].sum()
    overdue_pcs = df_filtered[df_filtered['Delay_Days'] > 0]['In_Production'].sum()
    
    overdue_df = df_filtered[df_filtered['Delay_Days'] > 0]
    avg_overdue_days = overdue_df['Delay_Days'].mean() if not overdue_df.empty else 0.0
    
    ontime_count = len(df_filtered[df_filtered['Delay_Days'] <= 0])
    ontime_pct = (ontime_count / tot_designs * 100) if tot_designs > 0 else 0.0
    ontime_pcs = df_filtered[df_filtered['Delay_Days'] <= 0]['In_Production'].sum()
    
    kpis = [
        ("TOTAL DESIGN", f"{tot_designs:,.0f} Orders", ""),
        ("INPRODUCTION PCS (AS)", f"{in_prod_pcs:,.0f} Pcs", ""),
        ("RECIEVED PCS (AT)", f"{rcvd_pcs:,.0f} Pcs", ""),
        ("PENDING PCS (AU)", f"{pending_pcs:,.0f} Pcs", ""),
        ("OVERDUE PCS (AH > 0)", f"{overdue_pcs:,.0f} Pcs", ""),
        ("AVG OVERDUE DAYS", f"{avg_overdue_days:.1f} Days", ""),
        ("ON-TIME DELIVERY %", f"{ontime_pct:.1f}%", ""),
        ("ON-TIME PCS (AH <= 0)", f"{ontime_pcs:,.0f} Pcs", "")
    ]
    badge("📊 Process Key Performance Indicators")
    render_kpi_cards(kpis, per_row=4)

    st.markdown("---")
    badge("📊 Category-wise Production Performance Breakdown")
    
    # Table 1: Category Breakdown[cite: 6]
    categories = ["CO-ORD SET", "KURTA PANT", "TOP", "KURTA PANT DUPATTA", "DRESS", "KAFTAN", "KURTA"]
    cat_rows = []
    for c_name in categories:
        c_df = df_filtered[df_filtered['Category'] == c_name]
        cat_rows.append({
            "CATEGORY": c_name,
            "INPRODUCTION (AS)": c_df['In_Production'].sum(),
            "RECIEVED (AT)": c_df['Received'].sum(),
            "PENDING (AU)": c_df['Pending'].sum()
        })
    df_cat = pd.DataFrame(cat_rows)
    tot_cat_row = pd.DataFrame([{
        "CATEGORY": "TOTAL",
        "INPRODUCTION (AS)": df_cat['INPRODUCTION (AS)'].sum(),
        "RECIEVED (AT)": df_cat['RECIEVED (AT)'].sum(),
        "PENDING (AU)": df_cat['PENDING (AU)'].sum()
    }])
    df_cat_full = pd.concat([df_cat, tot_cat_row], ignore_index=True)
    
    c1, c2 = st.columns([1, 1.35])
    with c1:
        show_table(df_cat_full)
    with c2:
        b = body(df_cat_full)
        if b is not None and not b.empty:
            chart_df = b.melt(id_vars="CATEGORY", var_name="Metric", value_name="PCS")
            fig = px.bar(chart_df, x="CATEGORY", y="PCS", color="Metric", barmode="group",
                         title="CATEGORY-WISE VOLUME COMPARISON",
                         color_discrete_sequence=["#2563eb", "#059669", "#f59e0b"])
            fig.update_xaxes(tickangle=-35, title="")
            show_chart(fig, 360)

    badge("🧵 Fabricator Pending PCS Share")
    # Fabricator Pending Pcs Calculation[cite: 6]
    fab_grp = df_filtered.groupby('Fabricator')['Pending'].sum().reset_index()
    fab_grp.columns = ["FABRICATOR", "PENDING PCS"]
    fab_grp = fab_grp[fab_grp["PENDING PCS"] > 0].sort_values("PENDING PCS", ascending=False)
    
    if not fab_grp.empty:
        f1, f2 = st.columns([1.35, 1])
        with f1:
            fig = px.pie(fab_grp, names="FABRICATOR", values="PENDING PCS", hole=0.4,
                         title="FABRICATOR PENDING PCS SHARE")
            fig.update_traces(textposition="inside", textinfo="percent")
            show_chart(fig, 360)
        with f2:
            tbl = fab_grp.copy()
            tbl["SHARE %"] = tbl["PENDING PCS"] / tbl["PENDING PCS"].sum() * 100
            tot = pd.DataFrame([{"FABRICATOR": "TOTAL", "PENDING PCS": tbl["PENDING PCS"].sum(), "SHARE %": 100.0}])
            show_table(pd.concat([tbl, tot], ignore_index=True), pct_cols=("SHARE %",))
    else:
        st.info("Selected filters ke liye fabricator pending data nahi hai.")

    badge("📅 Monthly Fulfillment Trend")
    # Table 2: Monthly Fulfillment Trend[cite: 6]
    m_rows = []
    for m_name in MONTHS:
        m_df = df_filtered[df_filtered['Month'].str.lower() == m_name.lower()]
        m_rows.append({
            "MONTH": m_name,
            "ORDERS": len(m_df),
            "RCVD (AS)": m_df['Received'].sum(),
            "PENDING (AT)": m_df['Pending'].sum()
        })
    df_m = pd.DataFrame(m_rows)
    tot_m_row = pd.DataFrame([{
        "MONTH": "TOTAL",
        "ORDERS": df_m['ORDERS'].sum(),
        "RCVD (AS)": df_m['RCVD (AS)'].sum(),
        "PENDING (AT)": df_m['PENDING (AT)'].sum()
    }])
    df_m_full = pd.concat([df_m, tot_m_row], ignore_index=True)
    
    m1, m2 = st.columns([1, 1.35])
    with m1:
        show_table(df_m_full, height=500)
    with m2:
        b = body(df_m_full)
        if b is not None and not b.empty:
            line_df = b.melt(id_vars="MONTH", value_vars=["RCVD (AS)", "PENDING (AT)"],
                             var_name="Metric", value_name="PCS")
            fig = px.line(line_df, x="MONTH", y="PCS", color="Metric", markers=True,
                          title="MONTHLY FULFILLMENT TREND ANALYSIS",
                          color_discrete_sequence=["#059669", "#dc2626"])
            fig.update_xaxes(tickangle=-35, title="")
            show_chart(fig, 460)


def client_view(sheet_id, cfg):
    tab_name, df_raw = load_raw_data_frame(sheet_id, "CONFIRMATION SHEET")
    df = prepare_master_data(df_raw)
    
    valid_clients = sorted([c for c in df['Client_Name'].unique() if c and c.upper() not in ["CLIENT", "CLIENT NAME", "NAME"]])
    
    with st.sidebar:
        st.markdown("### 🔍 Client Live Filters")
        sel_month = st.selectbox("Month", ["ALL"] + MONTHS, key="cli_m")
        sel_client = st.selectbox("Client Name", ["ALL"] + valid_clients, key="cli_c")
        sel_type = st.selectbox("Order Type", ["ALL", "NEW", "REPEAT"], key="cli_t")
        sel_cat = st.selectbox("Category", ["ALL", "CO-ORD SET", "KURTA PANT", "TOP", "KURTA PANT DUPATTA", "DRESS", "KAFTAN", "KURTA"], key="cli_cat")
        
    filters_selected = {"Month": sel_month, "Client": sel_client, "Order Type": sel_type, "Category": sel_cat}
    
    # Filter Data dynamically[cite: 7]
    df_filtered = df[(df['Client_Name'] != "")].copy()
    if sel_month != "ALL":
        df_filtered = df_filtered[df_filtered['Month'].str.lower() == sel_month.lower()]
    if sel_client != "ALL":
        df_filtered = df_filtered[df_filtered['Client_Name'] == sel_client]
    if sel_type != "ALL":
        df_filtered = df_filtered[df_filtered['Order_Type'].str.contains(sel_type, case=False, na=False)]
    if sel_cat != "ALL":
        df_filtered = df_filtered[df_filtered['Category'] == sel_cat]
        
    st.subheader("🏢 Executive Client Performance Dashboard")
    st.caption(f"Calculated Live from: {tab_name}")
    show_filter_chips_from_dict(filters_selected)
    
    # Client KPIs[cite: 7]
    tot_designs = len(df_filtered)
    tot_qty = df_filtered['Order_Qty'].sum()
    in_prod = df_filtered['In_Production'].sum()
    rec_qty = df_filtered['Received'].sum()
    
    pending_df = df_filtered[(df_filtered['Status'] < "DONE") & (df_filtered['Pending'] > 0)]
    pending_qty = pending_df['Pending'].sum()
    
    repeat_pcs = df_filtered[df_filtered['Order_Type'].str.contains("REPEAT", na=False)]['Order_Qty'].sum()
    new_pcs = df_filtered[df_filtered['Order_Type'].str.contains("NEW", na=False)]['Order_Qty'].sum()
    cat_tot = tot_qty
    
    kpis = [
        ("TOTAL DESIGNS", f"{tot_designs:,.0f}", ""),
        ("TOTAL QTY (PCS)", f"{tot_qty:,.0f}", ""),
        ("IN PRODUCTION", f"{in_prod:,.0f}", ""),
        ("RECEIVED / DONE", f"{rec_qty:,.0f}", ""),
        ("TOTAL PENDING QTY", f"{pending_qty:,.0f}", ""),
        ("REPEAT ORDERS (PCS)", f"{repeat_pcs:,.0f}", ""),
        ("NEW ORDERS (PCS)", f"{new_pcs:,.0f}", ""),
        ("CATEGORY TOTAL (PCS)", f"{cat_tot:,.0f}", "")
    ]
    render_kpi_cards(kpis, per_row=4)

    st.markdown("---")
    badge("📅 Client Fulfillment Breakdown (Monthly)")
    
    # Section A: Monthly Fulfillment Table[cite: 7]
    m_rows = []
    for m_name in MONTHS:
        m_df = df_filtered[df_filtered['Month'].str.lower() == m_name.lower()]
        p_m_df = m_df[(m_df['Status'] < "DONE") & (m_df['Pending'] > 0)]
        m_rows.append({
            "MONTH": m_name,
            "ORDER QTY": m_df['Order_Qty'].sum(),
            "IN PRODUCTION": m_df['In_Production'].sum(),
            "RECEIVED": m_df['Received'].sum(),
            "PENDING": p_m_df['Pending'].sum()
        })
    df_m = pd.DataFrame(m_rows)
    tot_m_row = pd.DataFrame([{
        "MONTH": "TOTAL",
        "ORDER QTY": df_m['ORDER QTY'].sum(),
        "IN PRODUCTION": df_m['IN PRODUCTION'].sum(),
        "RECEIVED": df_m['RECEIVED'].sum(),
        "PENDING": df_m['PENDING'].sum()
    }])
    df_m_full = pd.concat([df_m, tot_m_row], ignore_index=True)
    
    c1, c2, c3 = st.columns([1.25, 1, 1])
    with c1:
        show_table(df_m_full, height=500)
    b = body(df_m_full)
    with c2:
        pie_df = b[b["ORDER QTY"] > 0] if b is not None and not b.empty else pd.DataFrame()
        if not pie_df.empty:
            fig = px.pie(pie_df, names="MONTH", values="ORDER QTY", title="CLIENT MONTHLY ORDER TREND (PCS)")
            fig.update_traces(textposition="inside", textinfo="percent+label")
            show_chart(fig, 420)
        else:
            st.info("Selected filters ke liye order data nahi hai.")
    with c3:
        tot_rec = df_m['RECEIVED'].sum()
        tot_pen = df_m['PENDING'].sum()
        if (tot_rec + tot_pen) > 0:
            q = pd.DataFrame({"Status": ["RECEIVED QTY", "PENDING QTY"], "Qty": [tot_rec, tot_pen]})
            fig = px.pie(q, names="Status", values="Qty", hole=.45,
                         title="ORDER FULFILLMENT RATIO (RECEIVED vs PENDING)",
                         color="Status", color_discrete_map={"RECEIVED QTY": "#059669", "PENDING QTY": "#dc2626"})
            show_chart(fig, 420)
        else:
            st.info("Received / pending data nahi hai.")

    st.markdown("---")
    badge("👗 Category Wise Order Breakdown (Pcs)")
    
    # Section B: Category Wise Order Matrix[cite: 7]
    categories = ["CO-ORD SET", "KURTA PANT", "TOP", "KURTA PANT DUPATTA", "DRESS", "KAFTAN", "KURTA"]
    cat_rows = []
    for m_name in MONTHS:
        m_df = df_filtered[df_filtered['Month'].str.lower() == m_name.lower()]
        row_dict = {"MONTH": m_name}
        row_tot = 0
        for cat in categories:
            val = m_df[m_df['Category'] == cat]['Order_Qty'].sum()
            row_dict[cat] = val
            row_tot += val
        row_dict["TOTAL"] = row_tot
        cat_rows.append(row_dict)
        
    df_cat = pd.DataFrame(cat_rows)
    tot_cat_dict = {"MONTH": "TOTAL"}
    for cat in categories + ["TOTAL"]:
        tot_cat_dict[cat] = df_cat[cat].sum() if not df_cat.empty else 0
    df_cat_full = pd.concat([df_cat, pd.DataFrame([tot_cat_dict])], ignore_index=True)
    
    c4, c5 = st.columns([1.35, 1])
    with c4:
        show_table(df_cat_full, height=500)
    with c5:
        b = body(df_cat_full)
        if b is not None and not b.empty:
            long = melt_cols(b)
            long = long[long["Pcs"] != 0]
            if not long.empty:
                fig = px.bar(long, x="MONTH", y="Pcs", color="Category", title="CATEGORY DISTRIBUTION BY MONTH",
                             category_orders={"MONTH": MONTHS})
                fig.update_layout(barmode="stack")
                fig.update_xaxes(tickangle=-35, title="")
                show_chart(fig, 460)
            else:
                st.info("Selected filters ke liye category data nahi hai.")


def render_tracker(sheet_name, cfg):
    sheet_id = cfg["id"]
    with st.sidebar:
        st.markdown("### 📄 Master Sheet Actions")
        for k, v in cfg["dashboard_tabs"].items():
            st.caption(f"{k.title()}: **{v}**")
        st.caption(f"Auto-sync: har {LIVE_TTL} sec")
        if st.button("🔄 Refresh Data", key=f"{sheet_id}_ref"):
            st.cache_data.clear()
            st.rerun()

    st.markdown(
        f"""<div class="dashboard-hero"><h2>📊 {html.escape(sheet_name)} · Executive Dashboard 2026-27</h2>
        <p>Google Sheet ke Raw Data Tabs se Dynamic Calculations ·
        Loaded: {datetime.now().strftime('%d %b %Y, %H:%M')}</p></div>""",
        unsafe_allow_html=True)

    t1, t2, t3 = st.tabs(["👩‍🎨 Designer Dashboard", "🏭 Production Process Dashboard", "🏢 Client Dashboard"])
    with t1:
        designer_view(sheet_id, cfg)
    with t2:
        production_view(sheet_id, cfg)
    with t3:
        client_view(sheet_id, cfg)


# -----------------------------------------------------------------------------
# 6. SAMPLE SUMMARY (EXACT SAME & UNTOUCHED)
# -----------------------------------------------------------------------------
def render_sample_summary_dashboard(sheet_name, cfg):
    sheet_id = cfg["id"]
    tab, g = get_dashboard_grid(sheet_id, cfg["dashboard_tab"], cfg.get("gid"))

    with st.sidebar:
        st.markdown("### 📄 Sample Sheet Actions")
        st.caption(f"Active Tab: **{tab}**")
        st.caption(f"Auto-sync: har {LIVE_TTL} sec")
        if st.button("🔄 Refresh Data", key="samp_ref"):
            st.cache_data.clear()
            st.rerun()

    hero("⚡ EXECUTIVE SAMPLE PERFORMANCE & DESIGNER DASHBOARD (2026-27)", tab)
    show_filter_chips(g, [("Month", 4, 1), ("Designer", 4, 6), ("Status", 4, 11), ("Vendor", 4, 16)])
    render_kpi_cards(read_kpis(g, 7, 8), per_row=4)

    st.markdown("---")
    badge("📊 EXECUTIVE TABLES & WORKFLOW MATRIX")
    c_m, c_d, c_v = st.columns([1.4, 1, 1])
    with c_m:
        st.markdown("##### 📅 MONTHLY SAMPLE BREAKDOWN")
        df_m = read_table(g, r"MONTHLY SAMPLE BREAKDOWN", [
            ("MONTH", 0), ("APPROVED", 2), ("REJECTED", 3), ("HOLD", 4), ("PROCESS", 5),
            ("OTHER", 6), ("TOTAL", 7), ("APPR %", 8)], pct=("APPR %",))
        show_table(df_m, pct_cols=("APPR %",))
        note = cell_text(g, r"Process Date")
        if note:
            (st.warning if note.startswith("⚠") else st.success)(note)
    with c_d:
        st.markdown("##### 👩‍🎨 DESIGNER PERFORMANCE SCORECARD")
        df_d = read_table(g, r"DESIGNER PERFORMANCE SCORECARD", [
            ("DESIGNER", 10), ("APPROVED", 11), ("REJECTED", 12), ("TOTAL", 13), ("APPR %", 14)], pct=("APPR %",))
        show_table(df_d, pct_cols=("APPR %",))
    with c_v:
        st.markdown("##### 🏭 VENDOR PERFORMANCE SCORECARD")
        df_v = read_table(g, r"VENDOR PERFORMANCE SCORECARD", [
            ("VENDOR", 16), ("APPROVED", 18), ("REJECTED", 19), ("TOTAL", 20), ("APPR %", 21)], pct=("APPR %",))
        show_table(df_v, pct_cols=("APPR %",))

    st.markdown("---")
    badge("📈 VISUAL PERFORMANCE TRENDS")
    months_only = body(df_m)
    g1, g2, g3 = st.columns(3)
    with g1:
        if months_only is not None and not months_only.empty:
            fig = px.bar(months_only, x="MONTH", y=["APPROVED", "REJECTED", "HOLD", "PROCESS", "OTHER"],
                         title="MONTHLY SAMPLE STATUS DISTRIBUTION", barmode="stack",
                         color_discrete_sequence=["#059669", "#DC2626", "#D97706", "#2563EB", "#94A3B8"])
            fig.update_xaxes(tickangle=-35, title="")
            fig.update_yaxes(title="")
            show_chart(fig, 350)
    with g2:
        if months_only is not None and not months_only.empty:
            fig = px.line(months_only, x="MONTH", y=["TOTAL", "APPROVED", "REJECTED"], markers=True,
                          title="MONTHLY PROCESS VOLUME TREND",
                          color_discrete_sequence=["#2563eb", "#059669", "#DC2626"])
            fig.update_xaxes(tickangle=-35, title="")
            fig.update_yaxes(title="")
            show_chart(fig, 350)
    with g3:
        pie = read_pairs(g, 25, [26])                  
        if not pie.empty and pie.iloc[:, 1].sum() > 0:
            pie.columns = ["Status", "Count"]
            fig = px.pie(pie, names="Status", values="Count", hole=0.45, title="OVERALL SAMPLE APPROVAL SHARE",
                         color="Status",
                         color_discrete_map={"APPROVED": "#059669", "REJECTED": "#DC2626", "HOLD": "#D97706",
                                             "ON PROCESS": "#2563EB", "OTHER": "#94A3B8"})
            show_chart(fig, 350)
        else:
            st.info("Selected filters ke liye data nahi hai.")


# -----------------------------------------------------------------------------
# 7. FABRICATOR REPORT (EXACT SAME & UNTOUCHED)
# -----------------------------------------------------------------------------
def render_fabricator_dashboard(sheet_name, cfg):
    sheet_id = cfg["id"]
    tab, g = get_dashboard_grid(sheet_id, cfg["dashboard_tab"], cfg.get("gid"))

    with st.sidebar:
        st.markdown("### 📄 Fabricator Sheet Actions")
        st.caption(f"Active Tab: **{tab}**")
        st.caption(f"Auto-sync: har {LIVE_TTL} sec")
        if st.button("🔄 Refresh Data", key="fab_ref"):
            st.cache_data.clear()
            st.rerun()

    upd = _txt(_cell(g, 4, 17))
    hero("🏭 FABRICATOR STOCK POSITION DASHBOARD (2026-27)", tab, f" · Sheet: {upd}" if upd else "")
    show_filter_chips(g, [("Fabricator", 4, 1), ("Month", 4, 6), ("Metric", 4, 11)])
    render_kpi_cards(read_kpis(g, 7, 8), per_row=4)

    st.markdown("---")
    t1, t2 = st.tabs(["📊 Fabricator Dashboard", "📋 Month × Fabricator Matrix"])

    with t1:
        badge("📅 Monthly Position Of Stock")
        mt = read_table(g, r"MONTHLY POSITION OF STOCK", [
            ("MONTH", 0), ("FABRIC ISSUE (MTR)", 2), ("PCS UNDER PRODUCTION", 3), ("RCVD", 4),
            ("REMAINING", 5), ("MONTHLY INCOMING", 6), ("RCVD %", 7)], pct=("RCVD %",))
        c1, c2 = st.columns([1.25, 1])
        with c1:
            show_table(mt, pct_cols=("RCVD %",), height=500)
        mb = body(mt)
        with c2:
            if mb is not None and not mb.empty:
                fig = px.bar(mb, x="MONTH", y=["PCS UNDER PRODUCTION", "RCVD", "REMAINING"], barmode="group",
                             title="MONTHLY: PRODUCTION vs RCVD vs REMAINING",
                             color_discrete_sequence=["#2563eb", "#059669", "#dc2626"])
                fig.update_xaxes(tickangle=-35, title="")
                fig.update_yaxes(title="Pcs")
                show_chart(fig, 460)
        if mb is not None and not mb.empty:
            fig = px.line(mb, x="MONTH", y=["FABRIC ISSUE (MTR)", "MONTHLY INCOMING"], markers=True,
                          title="MONTHLY FABRIC ISSUE & INCOMING TREND",
                          color_discrete_sequence=["#2563eb", "#d97706"])
            fig.update_xaxes(tickangle=-35, title="")
            fig.update_yaxes(title="")
            show_chart(fig, 340)

        st.markdown("---")
        badge("🏭 Fabricator Scorecard")
        sc = read_table(g, r"FABRICATOR SCORECARD", [
            ("FABRICATOR", 9), ("FABRIC ISSUE (MTR)", 11), ("PCS UNDER PRODUCTION", 12), ("RCVD", 13),
            ("REMAINING", 14), ("MONTHLY INCOMING", 15), ("RCVD %", 16)], pct=("RCVD %",), stop_total=False)
        s1, s2 = st.columns([1.5, 1])
        with s1:
            show_table(sc, pct_cols=("RCVD %",))
        sb = body(sc)
        with s2:
            if sb is not None and not sb.empty:
                fig = px.bar(sb, y="FABRICATOR", x=["RCVD", "REMAINING"], orientation="h", barmode="stack",
                             title="FABRICATOR WISE: RCVD vs REMAINING",
                             color_discrete_sequence=["#059669", "#dc2626"])
                fig.update_yaxes(title="", autorange="reversed")
                fig.update_xaxes(title="Pcs")
                show_chart(fig, 400)
        if sb is not None and not sb.empty:
            fig = px.area(sb, x="FABRICATOR", y="RCVD %", title="FABRICATOR WISE: RECEIVED %",
                          color_discrete_sequence=["#3b82f6"])
            fig.update_yaxes(range=[0, 100], ticksuffix="%", title="")
            fig.update_xaxes(title="", tickangle=-35)
            show_chart(fig, 340)

        check = cell_text(g, r"ALL OVER table|ALL OVER nahi")
        if check:
            if check.startswith("✅"):
                st.success(check)
            elif check.startswith("⚠"):
                st.warning(check)
            else:
                st.info(check)

    with t2:
        title = cell_text(g, r"MATRIX") or "MONTH × FABRICATOR MATRIX"
        badge(f"🧮 {title}")
        mx = read_table(g, r"MATRIX", [("FABRICATOR", 0)] + [(None, c) for c in range(2, 15)])
        show_table(mx)


# -----------------------------------------------------------------------------
# 8. MAIN ROUTER
# -----------------------------------------------------------------------------
def main():
    apply_theme()
    with st.sidebar:
        st.markdown("### 🗂️ Workspace Selection")
        selected = st.selectbox("Active Google Sheet", list(SHEET_REGISTRY.keys()), key="ws_choice")

    cfg = SHEET_REGISTRY[selected]
    kind = cfg.get("type", "tracker")
    if kind == "tracker":
        render_tracker(selected, cfg)
    elif kind == "overview_fabricators":
        render_fabricator_dashboard(selected, cfg)
    elif kind == "sample_summary":
        render_sample_summary_dashboard(selected, cfg)


if __name__ == "__main__":
    main()
