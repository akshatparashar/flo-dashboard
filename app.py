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

# Har sheet ke Apps Script dwara bane dashboard tabs yahan se padhe jaate hain.
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
LIVE_TTL = 60          # seconds: itne seconds baad sheet se naya data aata hai
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

/* Text colours (Streamlit base theme se independent) */
.stApp p, .stApp li, .stApp h1, .stApp h2, .stApp h3, .stApp h4, .stApp h5, .stApp h6,
.stApp label, [data-testid="stWidgetLabel"] p, [data-testid="stMarkdownContainer"] {{ color: var(--text-color); }}
[data-testid="stCaptionContainer"], .stApp small {{ color: var(--muted-color) !important; }}

/* Sidebar */
[data-testid="stSidebar"] {{ background-color: var(--panel-bg) !important; border-right: 1px solid var(--border-color); }}
[data-testid="stSidebar"] h3 {{ font-size: .83rem; font-weight: 750; text-transform: uppercase; letter-spacing: 0.08em; color: var(--muted-color); margin-bottom: 0.6rem; }}
[data-testid="stSidebar"] label, [data-testid="stSidebar"] p {{ color: var(--text-color) !important; }}

/* Inputs / dropdowns */
div[data-baseweb="select"] > div, div[data-baseweb="input"] > div {{ background: var(--panel-bg) !important; color: var(--text-color) !important; border: 1px solid var(--border-color) !important; border-radius: 8px; }}
div[data-baseweb="select"] span, div[data-baseweb="select"] input {{ color: var(--text-color) !important; }}
div[data-baseweb="popover"] ul, div[data-baseweb="menu"] {{ background: var(--panel-bg) !important; }}
div[data-baseweb="popover"] li, div[data-baseweb="menu"] li {{ color: var(--text-color) !important; background: var(--panel-bg) !important; }}
div[data-baseweb="popover"] li:hover {{ background: var(--chip-bg) !important; }}
button[kind="secondary"], [data-testid="stBaseButton-secondary"] {{ background: var(--chip-bg) !important; color: var(--text-color) !important; border: 1px solid var(--border-color) !important; }}

/* KPI metric cards */
[data-testid="stMetric"] {{ background: var(--panel-bg); border: 1px solid var(--border-color); border-top: 3px solid var(--accent); padding: 14px 18px; border-radius: 12px; box-shadow: 0 4px 14px rgba(0,0,0,0.05); min-height: 108px; }}
[data-testid="stMetricLabel"] {{ color: var(--muted-color) !important; }}
[data-testid="stMetricLabel"] p {{ color: var(--muted-color) !important; font-size: .74rem; font-weight: 700; text-transform: uppercase; letter-spacing: .03em; white-space: normal; line-height: 1.25; }}
[data-testid="stMetricValue"], [data-testid="stMetricValue"] > div {{ color: var(--text-color) !important; font-weight: 800; font-size: 1.35rem; white-space: normal; overflow-wrap: anywhere; line-height: 1.2; }}
[data-testid="stMetricDelta"] {{ color: var(--accent) !important; font-weight: 700; }}

/* Tabs */
[data-testid="stTabs"] [role="tablist"] {{ position: sticky; top: 3.4rem; z-index: 99; background-color: var(--app-bg); padding: 4px 0; border-bottom: 2px solid var(--border-color); }}
[data-testid="stTabs"] button {{ border-radius: 8px 8px 0 0; padding: 10px 20px; }}
[data-testid="stTabs"] button p {{ font-weight: 700; font-size: .92rem; color: var(--muted-color); }}
[data-testid="stTabs"] button[aria-selected="true"] p {{ color: var(--accent); }}

/* Charts */
[data-testid="stPlotlyChart"] {{ background: var(--panel-bg); border: 1px solid var(--border-color); border-radius: 12px; padding: 8px; }}

/* Custom HTML tables */
.tbl-wrap {{ overflow: auto; border: 1px solid var(--border-color); border-radius: 10px; background: var(--panel-bg); margin-bottom: 14px; }}
.dash-tbl {{ width: 100%; border-collapse: collapse; font-size: .82rem; color: var(--text-color); }}
.dash-tbl th {{ position: sticky; top: 0; z-index: 1; background: var(--chip-bg); color: var(--text-color); text-align: right; padding: 9px 12px; font-weight: 750; font-size: .72rem; text-transform: uppercase; letter-spacing: .03em; white-space: nowrap; border-bottom: 1px solid var(--border-color); }}
.dash-tbl td {{ padding: 7px 12px; text-align: right; border-bottom: 1px solid var(--border-color); white-space: nowrap; color: var(--text-color); }}
.dash-tbl th:first-child, .dash-tbl td:first-child {{ text-align: left; }}
.dash-tbl tbody tr:nth-child(even) td {{ background: var(--card-bg); }}
.dash-tbl tbody tr:hover td {{ background: var(--chip-bg); }}
.dash-tbl tr.tot td {{ font-weight: 800; background: var(--chip-bg); border-top: 2px solid var(--accent); }}
.dash-tbl tr.ref td {{ font-style: italic; color: var(--muted-color); }}

/* Hero, badges, chips */
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
    """Theme-aware HTML table (dark/light dono me sahi colors)."""
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
    """Total / reference rows hata kar sirf asli data rows (charts ke liye)."""
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


def show_filter_chips(grid, spec):
    chips = "".join(
        f'<span class="chip">{html.escape(label)}: <b>{html.escape(_txt(_cell(grid, r, c)) or "ALL")}</b></span>'
        for label, r, c in spec)
    st.markdown(
        f'<div class="filter-chips"><span class="lead">🔎 Sheet dashboard ke current filters:</span>{chips}</div>',
        unsafe_allow_html=True)


def hero(title, source_tab, extra=""):
    st.markdown(
        f"""<div class="dashboard-hero"><h2>{html.escape(title)}</h2>
        <p>Source: Google Sheet tab <b>{html.escape(source_tab)}</b> · Live sync (har {LIVE_TTL} sec) ·
        Loaded: {datetime.now().strftime('%d %b %Y, %H:%M')}{extra}</p></div>""",
        unsafe_allow_html=True)


# -----------------------------------------------------------------------------
# 3. GOOGLE SHEETS AUTH & LOADERS
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


@st.cache_data(ttl=LIVE_TTL, show_spinner="Google Sheet se live data load ho raha hai...")
def load_live_values(sheet_id, tab_title):
    book = _open_book(sheet_id)
    resp = book.values_get(_a1_tab(tab_title), params={
        "valueRenderOption": "UNFORMATTED_VALUE",
        "dateTimeRenderOption": "SERIAL_NUMBER",
    })
    return resp.get("values", [])


def get_dashboard_grid(sheet_id, wanted, gid=None):
    """Sheet ka dashboard tab dhoondh kar uska computed grid lautata hai."""
    meta = list_tab_meta(sheet_id)
    titles = [t for t, _ in meta]
    tab = find_tab(titles, wanted)
    if tab is None and gid is not None:
        for t, i in meta:
            if str(i) == str(gid) and "DASHBOARD" in t.upper():
                tab = t
    if tab is None:
        st.error(f"Google Sheet me '{wanted}' tab nahi mila. Pehle Apps Script se dashboard "
                 "generate karein (Refresh / create dashboard function run karein).")
        st.stop()
    grid = load_live_values(sheet_id, tab)
    if not grid:
        st.error(f"'{tab}' tab khaali hai. Apps Script se dashboard dobara generate karein.")
        st.stop()
    return tab, grid


# -----------------------------------------------------------------------------
# 4. GRID PARSING HELPERS (dashboard tabs ka fixed layout)
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
    """KPI cards: title_row ke har non-empty cell ke neeche wali value row se value."""
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
    """
    title_pat se table ka title dhoondta hai; uske next row me header, phir data rows
    (label khaali hone par ya TOTAL row ke baad ruk jata hai).
    cols = [(column_name or None(=sheet header), col_index_0_based), ...]
    """
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
    """Hidden chart-helper areas (e.g. Z:AA) ko DataFrame me padhta hai."""
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
# 5. MASTER SHEET  (DESIGNER / PRODUCTION / CLIENT dashboard tabs)
# -----------------------------------------------------------------------------
def designer_view(sheet_id, cfg):
    tab, g = get_dashboard_grid(sheet_id, cfg["dashboard_tabs"]["designer"])
    st.subheader("👨‍🎨 Executive Designer Performance & Category Tracking Dashboard")
    st.caption(f"Source tab: {tab}")
    show_filter_chips(g, [("Month", 3, 2), ("Designer", 3, 7), ("Order Type", 3, 12)])
    render_kpi_cards(read_kpis(g, 5, 6), per_row=5)

    st.markdown("---")
    badge("📊 Designer Volume & Share Breakdown")
    df = read_table(g, r"DESIGNER VOLUME", [
        ("Designer Name", 0), ("New Orders (Pcs)", 2), ("Repeat Orders (Pcs)", 3),
        ("Total Volume (Pcs)", 4), ("Share %", 5), ("Total Design Count", 6)], pct=("Share %",))
    c1, c2 = st.columns([1.2, 1])
    with c1:
        show_table(df, pct_cols=("Share %",))
    with c2:
        b = body(df)
        if b is not None and not b.empty:
            m = b.melt(id_vars="Designer Name", value_vars=["New Orders (Pcs)", "Repeat Orders (Pcs)"],
                       var_name="Order Type", value_name="Qty")
            fig = px.bar(m, x="Designer Name", y="Qty", color="Order Type", barmode="group",
                         title="DESIGNER PERFORMANCE: NEW vs REPEAT ORDERS (PCS)",
                         color_discrete_sequence=["#059669", "#7C3AED"])
            fig.update_xaxes(title="", tickangle=-35)
            show_chart(fig, 380)

    st.markdown("---")
    badge("🧩 Category Wise Designer Breakdown (Pcs)")
    cat = read_table(g, r"CATEGORY WISE DESIGNER", [("Designer", 0)] + [(None, c) for c in range(1, 9)])
    c3, c4 = st.columns([1.25, 1])
    with c3:
        show_table(cat)
    with c4:
        # hidden trend helper: AA = month, AB.. = designers
        hdr = g[0] if g else []
        dcols = []
        for c in range(27, len(hdr)):
            n = _txt(hdr[c])
            if not n:
                break
            dcols.append((n, c))
        recs = []
        for r in range(1, 13):
            mname = _txt(_cell(g, r, 26))
            if not mname:
                break
            label = FY_MONTH_LABELS[MONTHS.index(mname)] if mname in MONTHS else mname
            for n, c in dcols:
                recs.append({"Month": label, "Designer": n, "Pcs": _to_float(_cell(g, r, c))})
        trend = pd.DataFrame(recs, columns=["Month", "Designer", "Pcs"])
        trend = trend[trend["Pcs"] != 0]
        if not trend.empty:
            fig = px.bar(trend, x="Month", y="Pcs", color="Designer",
                         title="MONTHLY DESIGNER PERFORMANCE TREND (PCS)",
                         category_orders={"Month": FY_MONTH_LABELS})
            fig.update_layout(barmode="stack")
            fig.update_xaxes(tickangle=-35, title="")
            show_chart(fig, 380)
        else:
            st.info("Selected filters ke liye monthly data nahi hai.")


def production_view(sheet_id, cfg):
    tab, g = get_dashboard_grid(sheet_id, cfg["dashboard_tabs"]["production"])
    st.subheader("🏭 Production Executive Process Dashboard")
    st.caption(f"Source tab: {tab}")
    show_filter_chips(g, [("Month", 3, 2), ("Fabricator", 3, 6), ("Status", 3, 10),
                          ("Category", 3, 14), ("Designer", 3, 18), ("Delay Risk", 3, 22)])
    badge("📊 Process Key Performance Indicators")
    render_kpi_cards(read_kpis(g, 6, 7), per_row=4)

    st.markdown("---")
    badge("📊 Category-wise Production Performance Breakdown")
    cat = read_table(g, r"CATEGORY-WISE PRODUCTION", [
        ("CATEGORY", 0), ("IN-PRODUCTION (AS)", 3), ("RECEIVED (AT)", 5), ("PENDING (AU)", 7)])
    c1, c2 = st.columns([1, 1.35])
    with c1:
        show_table(cat)
    with c2:
        b = body(cat)
        if b is not None and not b.empty:
            chart_df = b.melt(id_vars="CATEGORY", var_name="Metric", value_name="PCS")
            fig = px.bar(chart_df, x="CATEGORY", y="PCS", color="Metric", barmode="group",
                         title="CATEGORY-WISE VOLUME COMPARISON",
                         color_discrete_sequence=["#2563eb", "#ef4444", "#f59e0b"])
            fig.update_xaxes(tickangle=-35, title="")
            show_chart(fig, 360)

    badge("🧵 Fabricator Pending PCS Share")
    fab = read_pairs(g, 25, [26])                      # hidden helper Z:AA
    if not fab.empty:
        fab.columns = ["FABRICATOR", "PENDING PCS"]
        fab = fab[fab["PENDING PCS"] > 0].sort_values("PENDING PCS", ascending=False)
    if not fab.empty:
        f1, f2 = st.columns([1.35, 1])
        with f1:
            fig = px.pie(fab, names="FABRICATOR", values="PENDING PCS", hole=0.48,
                         title="FABRICATOR PENDING PCS SHARE")
            fig.update_traces(textposition="inside", textinfo="percent")
            show_chart(fig, 360)
        with f2:
            tbl = fab.copy()
            tbl["SHARE %"] = tbl["PENDING PCS"] / tbl["PENDING PCS"].sum() * 100
            tot = pd.DataFrame([{"FABRICATOR": "TOTAL", "PENDING PCS": tbl["PENDING PCS"].sum(), "SHARE %": 100.0}])
            show_table(pd.concat([tbl, tot], ignore_index=True), pct_cols=("SHARE %",))
    else:
        st.info("Selected filters ke liye fabricator pending data nahi hai.")

    badge("📅 Monthly Fulfillment Trend")
    mdf = read_table(g, r"MONTHLY FULFILLMENT TREND", [
        ("MONTH", 0), ("ORDERS", 3), ("IN-PRODUCTION (AS)", 5), ("RECEIVED (AT)", 7)])
    m1, m2 = st.columns([1, 1.35])
    with m1:
        show_table(mdf, height=500)
    with m2:
        b = body(mdf)
        if b is not None and not b.empty:
            line_df = b.melt(id_vars="MONTH", value_vars=["IN-PRODUCTION (AS)", "RECEIVED (AT)"],
                             var_name="Metric", value_name="PCS")
            fig = px.line(line_df, x="MONTH", y="PCS", color="Metric", markers=True,
                          title="MONTHLY FULFILLMENT TREND ANALYSIS",
                          color_discrete_sequence=["#ef4444", "#2563eb"])
            fig.update_xaxes(tickangle=-35, title="")
            show_chart(fig, 460)


def client_view(sheet_id, cfg):
    tab, g = get_dashboard_grid(sheet_id, cfg["dashboard_tabs"]["client"])
    st.subheader("🏢 Executive Client Performance Dashboard")
    st.caption(f"Source tab: {tab}")
    show_filter_chips(g, [("Month", 3, 1), ("Client", 3, 5), ("Order Type", 3, 10), ("Category", 3, 13)])
    render_kpi_cards(read_kpis(g, 5, 6, sub_row=7), per_row=4)

    st.markdown("---")
    badge("📅 Client Fulfillment Breakdown (Monthly)")
    m = read_table(g, r"CLIENT FULFILLMENT BREAKDOWN", [
        ("MONTH", 0), ("ORDER QTY", 2), ("IN PRODUCTION", 3), ("RECEIVED", 4), ("PENDING", 5)])
    c1, c2, c3 = st.columns([1.25, 1, 1])
    with c1:
        show_table(m, height=500)
    b = body(m)
    with c2:
        pie_df = b[b["ORDER QTY"] > 0] if b is not None and not b.empty else pd.DataFrame()
        if not pie_df.empty:
            fig = px.pie(pie_df, names="MONTH", values="ORDER QTY", title="CLIENT MONTHLY ORDER TREND (PCS)")
            fig.update_traces(textposition="inside", textinfo="percent+label")
            show_chart(fig, 420)
        else:
            st.info("Selected filters ke liye order data nahi hai.")
    with c3:
        tot = m[m["MONTH"].str.upper().isin(TOTAL_LABELS)] if not m.empty else pd.DataFrame()
        if not tot.empty and (tot["RECEIVED"].iloc[0] + tot["PENDING"].iloc[0]) > 0:
            q = pd.DataFrame({"Status": ["RECEIVED QTY", "PENDING QTY"],
                              "Qty": [tot["RECEIVED"].iloc[0], tot["PENDING"].iloc[0]]})
            fig = px.pie(q, names="Status", values="Qty", hole=.45,
                         title="ORDER FULFILLMENT RATIO (RECEIVED vs PENDING)",
                         color="Status", color_discrete_map={"RECEIVED QTY": "#059669", "PENDING QTY": "#dc2626"})
            show_chart(fig, 420)
        else:
            st.info("Received / pending data nahi hai.")

    st.markdown("---")
    badge("🧩 Category Wise Order Breakdown (Pcs)")
    cat = read_table(g, r"CATEGORY WISE ORDER BREAKDOWN", [("MONTH", 0)] + [(None, c) for c in range(2, 10)])
    c4, c5 = st.columns([1.35, 1])
    with c4:
        show_table(cat, height=500)
    with c5:
        b = body(cat)
        if b is not None and not b.empty:
            long = melt_cols(b)
            long = long[long["Pcs"] != 0]
            if not long.empty:
                fig = px.bar(long, x="MONTH", y="Pcs", color="Category", title="CATEGORY DISTRIBUTION BY MONTH",
                             category_orders={"MONTH": list(b["MONTH"])})
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
        <p>Google Sheet ke Designer / Production / Client dashboard tabs se live data ·
        Loaded: {datetime.now().strftime('%d %b %Y, %H:%M')}</p></div>""",
        unsafe_allow_html=True)

    t1, t2, t3 = st.tabs(["👨‍🎨 Designer Dashboard", "🏭 Production Process Dashboard", "🏢 Client Dashboard"])
    with t1:
        designer_view(sheet_id, cfg)
    with t2:
        production_view(sheet_id, cfg)
    with t3:
        client_view(sheet_id, cfg)


# -----------------------------------------------------------------------------
# 6. SAMPLE SUMMARY  (SAMPLE DASHBOARD tab)
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
        pie = read_pairs(g, 25, [26])                  # hidden helper Z:AA (STATUS / SAMPLES)
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
# 7. FABRICATOR REPORT  (FABRICATOR DASHBOARD tab)
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
