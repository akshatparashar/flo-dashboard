import html
import re
import traceback
from datetime import datetime, timedelta

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

# Har sheet ke Apps Script se bane dashboard tabs yahan se padhe jaate hain.
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

AUTO_REFRESH_SECONDS = 300          # dashboard har 5 minute me khud refresh hota hai
DATA_TTL = 240                      # cache isse pehle expire => har refresh par fresh data
TOTAL_LABELS = {"TOTAL", "GRAND TOTAL", "ALL FABRICATORS"}


class SheetError(Exception):
    """Google Sheet khulne / padhne ki problem."""


def _stretch_kwargs():
    try:
        major, minor = (int(p) for p in st.__version__.split(".")[:2])
    except Exception:
        return {"use_container_width": True}
    return {"width": "stretch"} if (major, minor) >= (1, 50) else {"use_container_width": True}

STRETCH = _stretch_kwargs()

PALETTE = ["#6366f1", "#10b981", "#f59e0b", "#ef4444", "#8b5cf6", "#06b6d4", "#ec4899", "#84cc16",
           "#f97316", "#14b8a6", "#a855f7", "#eab308"]
KPI_ACCENTS = ["#6366f1", "#10b981", "#f59e0b", "#ef4444", "#8b5cf6", "#06b6d4", "#ec4899", "#84cc16"]
PLOT_TEMPLATE = "plotly_white"
THEME = {"panel": "#ffffff", "text": "#0f172a", "muted": "#475569", "border": "#e2e8f0"}


# -----------------------------------------------------------------------------
# 2. THEME / CSS
# -----------------------------------------------------------------------------
def apply_theme():
    global PLOT_TEMPLATE
    if "dashboard_dark_mode" not in st.session_state:
        st.session_state.dashboard_dark_mode = False

    with st.sidebar:
        st.markdown("### 🎨 Preferences")
        st.toggle("Dark mode", key="dashboard_dark_mode", help="Dashboard appearance mode toggle")

    dark = st.session_state.dashboard_dark_mode
    if dark:
        app_bg, panel_bg, text, muted, border = "#0b1020", "#131a2e", "#e9eefc", "#a3b1d0", "#27324f"
        card_bg, chip_bg, accent = "#18213a", "#222d4a", "#818cf8"
        hero_grad = "#1e1b4b 0%, #312e81 55%, #0e7490 100%"
        PLOT_TEMPLATE = "plotly_dark"
    else:
        app_bg, panel_bg, text, muted, border = "#f4f6fb", "#ffffff", "#0f172a", "#475569", "#e2e8f0"
        card_bg, chip_bg, accent = "#f8fafc", "#eef2ff", "#4f46e5"
        hero_grad = "#4f46e5 0%, #7c3aed 55%, #0ea5e9 100%"
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
.stApp, [data-testid="stAppViewContainer"], [data-testid="stMain"] {{ background-color: var(--app-bg) !important; color: var(--text-color); font-family: "Inter", -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; }}
[data-testid="stHeader"] {{ background-color: transparent !important; }}
.block-container {{ padding-top: 2.4rem; padding-bottom: 3rem; max-width: 1650px; }}

.stApp p, .stApp li, .stApp h1, .stApp h2, .stApp h3, .stApp h4, .stApp h5, .stApp h6,
.stApp label, [data-testid="stWidgetLabel"] p, [data-testid="stMarkdownContainer"] {{ color: var(--text-color); }}
[data-testid="stCaptionContainer"], .stApp small {{ color: var(--muted-color) !important; }}
.stApp h3 {{ font-weight: 800; letter-spacing: -0.01em; }}

/* Sidebar */
[data-testid="stSidebar"] {{ background-color: var(--panel-bg) !important; border-right: 1px solid var(--border-color); }}
[data-testid="stSidebar"] h3 {{ font-size: .8rem; font-weight: 800; text-transform: uppercase; letter-spacing: 0.1em; color: var(--accent); margin-bottom: 0.5rem; }}
[data-testid="stSidebar"] label, [data-testid="stSidebar"] p {{ color: var(--text-color) !important; }}

/* Inputs */
div[data-baseweb="select"] > div, div[data-baseweb="input"] > div {{ background: var(--panel-bg) !important; color: var(--text-color) !important; border: 1px solid var(--border-color) !important; border-radius: 10px; }}
div[data-baseweb="select"] span, div[data-baseweb="select"] input {{ color: var(--text-color) !important; }}
div[data-baseweb="tag"] {{ background-color: var(--chip-bg) !important; border-radius: 6px !important; }}
div[data-baseweb="tag"] span {{ color: var(--text-color) !important; font-weight: 600; }}
div[data-baseweb="popover"] ul, div[data-baseweb="menu"] {{ background: var(--panel-bg) !important; }}
div[data-baseweb="popover"] li, div[data-baseweb="menu"] li {{ color: var(--text-color) !important; background: var(--panel-bg) !important; }}
div[data-baseweb="popover"] li:hover {{ background: var(--chip-bg) !important; }}
button[kind="secondary"], [data-testid="stBaseButton-secondary"] {{ background: var(--chip-bg) !important; color: var(--text-color) !important; border: 1px solid var(--border-color) !important; border-radius: 10px; font-weight: 700; }}
button[kind="secondary"]:hover, [data-testid="stBaseButton-secondary"]:hover {{ border-color: var(--accent) !important; color: var(--accent) !important; }}

/* Tabs */
[data-testid="stTabs"] [role="tablist"] {{ gap: 4px; border-bottom: 2px solid var(--border-color); }}
[data-testid="stTabs"] button {{ border-radius: 10px 10px 0 0; padding: 10px 20px; }}
[data-testid="stTabs"] button p {{ font-weight: 700; font-size: .92rem; color: var(--muted-color); }}
[data-testid="stTabs"] button[aria-selected="true"] {{ background: var(--chip-bg); }}
[data-testid="stTabs"] button[aria-selected="true"] p {{ color: var(--accent); }}

/* Charts */
[data-testid="stPlotlyChart"] {{ background: var(--panel-bg); border: 1px solid var(--border-color); border-radius: 16px; padding: 8px; box-shadow: 0 6px 20px rgba(15,23,42,.05); }}

/* KPI cards */
.kpi-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(210px, 1fr)); gap: 14px; margin: 8px 0 12px 0; }}
.kpi-card {{ background: linear-gradient(135deg, color-mix(in srgb, var(--kc) 10%, var(--panel-bg)), var(--panel-bg) 70%); border: 1px solid var(--border-color); border-left: 5px solid var(--kc); border-radius: 16px; padding: 15px 18px; box-shadow: 0 6px 20px rgba(15,23,42,.06); }}
.kpi-label {{ font-size: .7rem; font-weight: 800; letter-spacing: .07em; text-transform: uppercase; color: var(--muted-color); line-height: 1.3; }}
.kpi-value {{ font-size: 1.6rem; font-weight: 800; color: var(--text-color); margin-top: 5px; line-height: 1.15; overflow-wrap: anywhere; }}
.kpi-sub {{ margin-top: 4px; font-size: .75rem; font-weight: 700; color: var(--kc); }}

/* Tables */
.tbl-wrap {{ overflow: auto; border: 1px solid var(--border-color); border-radius: 14px; background: var(--panel-bg); margin-bottom: 14px; box-shadow: 0 6px 20px rgba(15,23,42,.05); }}
.dash-tbl {{ width: 100%; border-collapse: collapse; font-size: .82rem; color: var(--text-color); }}
.dash-tbl th {{ position: sticky; top: 0; z-index: 1; background: var(--chip-bg); color: var(--text-color); text-align: right; padding: 10px 12px; font-weight: 800; font-size: .7rem; text-transform: uppercase; letter-spacing: .04em; white-space: nowrap; border-bottom: 2px solid var(--accent); }}
.dash-tbl td {{ padding: 8px 12px; text-align: right; border-bottom: 1px solid var(--border-color); white-space: nowrap; color: var(--text-color); }}
.dash-tbl th:first-child, .dash-tbl td:first-child {{ text-align: left; font-weight: 600; }}
.dash-tbl tbody tr:nth-child(even) td {{ background: var(--card-bg); }}
.dash-tbl tbody tr:hover td {{ background: var(--chip-bg); }}
.dash-tbl tr.tot td {{ font-weight: 800; background: var(--chip-bg); border-top: 2px solid var(--accent); }}
.dash-tbl tr.ref td {{ font-style: italic; color: var(--muted-color); }}

/* Hero / headings / chips */
.dashboard-hero {{ background: linear-gradient(120deg, {hero_grad}); border-radius: 18px; padding: 22px 26px; margin-bottom: 18px; box-shadow: 0 10px 30px rgba(79,70,229,.25); }}
.dashboard-hero h2 {{ margin: 0; font-size: 1.5rem; font-weight: 800; letter-spacing: -0.02em; color: #ffffff !important; }}
.dashboard-hero p {{ color: rgba(255,255,255,.88) !important; margin: 5px 0 0 0; font-size: .86rem; }}
.section-badge {{ display: flex; align-items: center; gap: 8px; color: var(--text-color); padding: 2px 0 2px 12px; border-left: 4px solid var(--accent); font-size: .86rem; font-weight: 800; margin: 18px 0 10px 0; text-transform: uppercase; letter-spacing: .05em; }}
.filter-title {{ font-size: .78rem; font-weight: 800; text-transform: uppercase; letter-spacing: .08em; color: var(--accent); margin: 6px 0 2px 0; }}
.filter-chips {{ display: flex; flex-wrap: wrap; gap: 6px; align-items: center; margin: 2px 0 12px 0; }}
.filter-chips .lead {{ color: var(--muted-color); font-size: .76rem; font-weight: 700; margin-right: 4px; }}
.filter-chips .chip {{ background: var(--chip-bg); border: 1px solid var(--border-color); color: var(--text-color); padding: 3px 11px; border-radius: 999px; font-size: .76rem; }}
</style>
""", unsafe_allow_html=True)


# -----------------------------------------------------------------------------
# 3. DISPLAY HELPERS
# -----------------------------------------------------------------------------
def style_fig(fig, height=360):
    fig.update_layout(
        template=PLOT_TEMPLATE,
        height=height,
        paper_bgcolor=THEME["panel"],
        plot_bgcolor=THEME["panel"],
        margin=dict(l=12, r=12, t=52, b=10),
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
        st.info("Is section ka data abhi nahi mila (ya filter me kuch match nahi hua).")
        return
    num_set = {c for c in df.columns if pd.api.types.is_numeric_dtype(df[c])}
    head = "".join(f"<th>{html.escape(str(c))}</th>" for c in df.columns)
    rows = []
    for _, r in df.iterrows():
        label = str(r.iloc[0]).strip().upper()
        cls = "tot" if label in TOTAL_LABELS else ("ref" if label.startswith("ALL OVER") else "")
        tds = []
        for c in df.columns:
            v = r[c]
            if c in num_set:
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


def render_kpi_cards(kpis):
    cards = []
    for i, (title, value, sub) in enumerate(kpis):
        color = KPI_ACCENTS[i % len(KPI_ACCENTS)]
        sub_html = f'<div class="kpi-sub">{html.escape(sub)}</div>' if sub else ""
        cards.append(
            f'<div class="kpi-card" style="--kc:{color}"><div class="kpi-label">{html.escape(title)}</div>'
            f'<div class="kpi-value">{html.escape(value)}</div>{sub_html}</div>')
    st.markdown(f'<div class="kpi-grid">{"".join(cards)}</div>', unsafe_allow_html=True)


def show_sheet_filters(grid, spec):
    """Sheet dashboard ke apne dropdown ki current value dikhata hai; ALL na ho to warning."""
    vals = [(label, _txt(_cell(grid, r, c)) or "ALL") for label, r, c in spec]
    chips = "".join(f'<span class="chip">{html.escape(l)}: <b>{html.escape(v)}</b></span>' for l, v in vals)
    st.markdown(
        f'<div class="filter-chips"><span class="lead">🔎 Google Sheet dashboard ke filters:</span>{chips}</div>',
        unsafe_allow_html=True)
    if any(v.upper() not in ("ALL", "ALL FABRICATORS") for _, v in vals):
        st.warning("Google Sheet dashboard me koi filter 'ALL' nahi hai, isliye neeche ka data pehle se filtered hai. "
                   "Poora data dekhne ke liye Sheet me sab dropdown 'ALL' kar dein.")


def hero(title, source, extra=""):
    now = datetime.now()
    nxt = now + timedelta(seconds=AUTO_REFRESH_SECONDS)
    st.markdown(
        f"""<div class="dashboard-hero"><h2>{html.escape(title)}</h2>
        <p>Source: <b>{html.escape(source)}</b> · Last updated {now.strftime('%d %b %Y, %H:%M:%S')} ·
        Next auto-refresh {nxt.strftime('%H:%M')} (har {AUTO_REFRESH_SECONDS // 60} min){extra}</p></div>""",
        unsafe_allow_html=True)


# -----------------------------------------------------------------------------
# 4. FILTER HELPERS
# -----------------------------------------------------------------------------
def handle_smart_all_filter(key):
    selected = st.session_state.get(key, [])
    prev_key = f"{key}_prev_state"
    prev = st.session_state.get(prev_key, ["All"])
    if not selected:
        st.session_state[key] = ["All"]
    elif "All" in selected and len(selected) > 1:
        if "All" in prev:
            st.session_state[key] = [x for x in selected if x != "All"]
        else:
            st.session_state[key] = ["All"]
    st.session_state[prev_key] = st.session_state[key]


def smart_multiselect(label, options, key):
    valid = [x for x in st.session_state.get(key, ["All"]) if x in options] or ["All"]
    st.session_state[key] = valid
    return st.multiselect(label, options=options, key=key,
                          on_change=handle_smart_all_filter, args=(key,))


def _reset_filters(keys):
    for k in keys:
        st.session_state[k] = ["All"]
        st.session_state[f"{k}_prev_state"] = ["All"]


def filter_panel(specs, prefix):
    """specs=[(field, label, options)] -> {field: [selected] or None}"""
    st.markdown('<div class="filter-title">🎛️ Filters</div>', unsafe_allow_html=True)
    cols = st.columns(len(specs) + 1)
    out, keys = {}, []
    for col, (field, label, options) in zip(cols, specs):
        key = f"{prefix}_{field}"
        keys.append(key)
        with col:
            sel = smart_multiselect(label, ["All"] + [o for o in options if o != "All"], key)
        out[field] = None if (not sel or "All" in sel) else list(sel)
    with cols[-1]:
        st.markdown("<div style='height:1.7rem'></div>", unsafe_allow_html=True)
        st.button("↺ Reset filters", key=f"{prefix}_reset", on_click=_reset_filters, args=(keys,))
    return out


def body(df, drop_prefix=("⚠", "ALL OVER")):
    """Total / reference rows hata kar sirf asli data rows."""
    if df is None or df.empty:
        return df
    lab = df.iloc[:, 0].astype(str).str.strip().str.upper()
    keep = ~lab.isin(TOTAL_LABELS)
    for p in drop_prefix:
        keep &= ~lab.str.startswith(p)
    return df[keep]


def pick_rows(df, selected):
    b = body(df)
    if b is None or b.empty:
        return b
    return b[b.iloc[:, 0].isin(selected)]


def retotal(b, rate=None, label="TOTAL"):
    """Data rows ke neeche naya TOTAL row. rate=(rate_col, numerator_col, denominator_col)."""
    if b is None or b.empty:
        return b
    tot = {b.columns[0]: label}
    for c in b.columns[1:]:
        tot[c] = float(b[c].sum()) if pd.api.types.is_numeric_dtype(b[c]) else ""
    if rate:
        rc, nc, dc = rate
        tot[rc] = (tot[nc] / tot[dc] * 100) if tot[dc] else 0.0
    return pd.concat([b, pd.DataFrame([tot])], ignore_index=True)


def month_keys(selected):
    """'April-26' ya 'April' dono tarah ke labels match karne ke liye."""
    keys = set(selected or [])
    keys |= {s.split("-")[0] for s in (selected or [])}
    return keys


def total_row(df):
    """Table ki TOTAL row (dict) ya {}."""
    if df is None or df.empty:
        return {}
    lab = df.iloc[:, 0].astype(str).str.strip().str.upper()
    t = df[lab.isin(TOTAL_LABELS)]
    return t.iloc[0].to_dict() if not t.empty else {}


def n0(x):
    return f"{float(x):,.0f}"


# -----------------------------------------------------------------------------
# 5. GOOGLE SHEETS AUTH & LOADERS  (cached functions kabhi st.stop / st.error nahi chalate)
# -----------------------------------------------------------------------------
def show_access_error(e=None):
    email = ""
    try:
        email = st.secrets["gcp_service_account"]["client_email"]
    except Exception:
        pass
    st.error("Google Sheet nahi khul paayi. Sheet ko is service account ke saath share karein: "
             + (f"**{email}**" if email else "(secrets me client_email)")
             + (f"\n\nDetails: `{e}`" if e else ""))


@st.cache_resource(show_spinner=False)
def get_client():
    if "gcp_service_account" not in st.secrets:
        raise SheetError("Google credentials missing hain. Streamlit Settings → Secrets me "
                         "[gcp_service_account] add karein.")
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
    except SheetError:
        raise
    except Exception as e:
        raise SheetError(str(e)) from e


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


@st.cache_data(ttl=DATA_TTL, show_spinner=False)
def list_tab_meta(sheet_id):
    return [(ws.title, ws.id) for ws in _open_book(sheet_id).worksheets()]


@st.cache_data(ttl=DATA_TTL, show_spinner="Google Sheet se live data load ho raha hai...")
def load_live_values(sheet_id, tab_title):
    book = _open_book(sheet_id)
    try:
        resp = book.values_get(_a1_tab(tab_title), params={
            "valueRenderOption": "UNFORMATTED_VALUE",
            "dateTimeRenderOption": "SERIAL_NUMBER",
        })
    except Exception as e:
        raise SheetError(f"'{tab_title}' tab padhne me error: {e}") from e
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
        st.error(f"Google Sheet me '{wanted}' tab nahi mila. Pehle Apps Script se dashboard "
                 "generate karein (Refresh Dashboard function run karein).")
        st.stop()
    grid = load_live_values(sheet_id, tab)
    if not grid:
        st.error(f"'{tab}' tab khaali hai. Apps Script se dashboard dobara generate karein.")
        st.stop()
    return tab, grid


# -----------------------------------------------------------------------------
# 6. GRID PARSING HELPERS (dashboard tabs ka fixed layout)
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
    """title_pat wala table: title ke next row me header, phir data rows (TOTAL tak)."""
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
    names = [_txt(_cell(grid, header_row, c)) or f"col{c}" for c in [label_col] + list(value_cols)]
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
# 7. MASTER SHEET DASHBOARDS
# -----------------------------------------------------------------------------
def designer_view(sheet_id, cfg):
    tab, g = get_dashboard_grid(sheet_id, cfg["dashboard_tabs"]["designer"])
    st.subheader("👨‍🎨 Designer Performance & Category Tracking")
    show_sheet_filters(g, [("Month", 3, 2), ("Designer", 3, 7), ("Order Type", 3, 12)])

    vol = read_table(g, r"DESIGNER VOLUME", [
        ("Designer Name", 0), ("New Orders (Pcs)", 2), ("Repeat Orders (Pcs)", 3),
        ("Total Volume (Pcs)", 4), ("Share %", 5), ("Total Design Count", 6)], pct=("Share %",))
    cat = read_table(g, r"CATEGORY WISE DESIGNER", [("Designer", 0)] + [(None, c) for c in range(1, 9)])

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

    names = list(body(vol)["Designer Name"]) if not vol.empty else []
    sel = filter_panel([("designer", "Designer", names), ("month", "Month (trend chart)", FY_MONTH_LABELS)], "des")

    vol_v, cat_v = vol, cat
    if sel["designer"]:
        b = pick_rows(vol, sel["designer"])
        total = b["Total Volume (Pcs)"].sum()
        b = b.assign(**{"Share %": (b["Total Volume (Pcs)"] / total * 100) if total else 0.0})
        vol_v = retotal(b)
        cat_v = retotal(pick_rows(cat, sel["designer"]))
        trend = trend[trend["Designer"].isin(sel["designer"])]
    if sel["month"]:
        trend = trend[trend["Month"].isin(sel["month"])]

    if sel["designer"] and vol_v is not None and not vol_v.empty:
        b = body(vol_v)
        top = b.loc[b["Total Volume (Pcs)"].idxmax()]
        kpis = [("TOTAL DESIGNS", n0(b["Total Design Count"].sum()), ""),
                ("TOTAL QUANTITY (PCS)", n0(b["Total Volume (Pcs)"].sum()), ""),
                ("NEW ORDER QTY", n0(b["New Orders (Pcs)"].sum()), ""),
                ("REPEAT ORDER QTY", n0(b["Repeat Orders (Pcs)"].sum()), ""),
                ("TOP PERFORMER", f"{top['Designer Name']} ({n0(top['Total Volume (Pcs)'])} Pcs)", "")]
    else:
        kpis = read_kpis(g, 5, 6)
    render_kpi_cards(kpis)

    badge("📊 Designer Volume & Share Breakdown")
    c1, c2 = st.columns([1.2, 1])
    with c1:
        show_table(vol_v, pct_cols=("Share %",))
    with c2:
        b = body(vol_v)
        if b is not None and not b.empty:
            m = b.melt(id_vars="Designer Name", value_vars=["New Orders (Pcs)", "Repeat Orders (Pcs)"],
                       var_name="Order Type", value_name="Qty")
            fig = px.bar(m, x="Designer Name", y="Qty", color="Order Type", barmode="group",
                         title="DESIGNER PERFORMANCE: NEW vs REPEAT ORDERS (PCS)",
                         color_discrete_sequence=["#10b981", "#8b5cf6"])
            fig.update_xaxes(title="", tickangle=-35)
            show_chart(fig, 380)

    badge("🧩 Category Wise Designer Breakdown (Pcs)")
    c3, c4 = st.columns([1.25, 1])
    with c3:
        show_table(cat_v)
    with c4:
        t2 = trend[trend["Pcs"] != 0]
        if not t2.empty:
            fig = px.bar(t2, x="Month", y="Pcs", color="Designer",
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
    show_sheet_filters(g, [("Month", 3, 2), ("Fabricator", 3, 6), ("Status", 3, 10),
                           ("Category", 3, 14), ("Designer", 3, 18), ("Delay Risk", 3, 22)])

    cat = read_table(g, r"CATEGORY-WISE PRODUCTION", [
        ("CATEGORY", 0), ("IN-PRODUCTION (AS)", 3), ("RECEIVED (AT)", 5), ("PENDING (AU)", 7)])
    mdf = read_table(g, r"MONTHLY FULFILLMENT TREND", [
        ("MONTH", 0), ("ORDERS", 3), ("IN-PRODUCTION (AS)", 5), ("RECEIVED (AT)", 7)])
    fab = read_pairs(g, 25, [26])
    if not fab.empty:
        fab.columns = ["FABRICATOR", "PENDING PCS"]
        fab = fab[fab["PENDING PCS"] > 0].sort_values("PENDING PCS", ascending=False)

    cat_names = list(body(cat)["CATEGORY"]) if not cat.empty else []
    fab_names = list(fab["FABRICATOR"]) if not fab.empty else []
    sel = filter_panel([("category", "Category", cat_names), ("month", "Month", FY_MONTH_LABELS),
                        ("fabricator", "Fabricator", fab_names)], "prod")

    cat_v, mdf_v, fab_v = cat, mdf, fab
    if sel["category"]:
        cat_v = retotal(pick_rows(cat, sel["category"]))
    if sel["month"]:
        keys = month_keys(sel["month"])
        b = body(mdf)
        mdf_v = retotal(b[b["MONTH"].isin(keys)])
    if sel["fabricator"] and not fab.empty:
        fab_v = fab[fab["FABRICATOR"].isin(sel["fabricator"])]

    if any(sel.values()):
        kpis = []
        if sel["category"] and cat_v is not None and not cat_v.empty:
            t = total_row(cat_v)
            kpis += [("IN-PRODUCTION PCS (AS) · categories", n0(t["IN-PRODUCTION (AS)"]), ""),
                     ("RECEIVED PCS (AT) · categories", n0(t["RECEIVED (AT)"]), ""),
                     ("PENDING PCS (AU) · categories", n0(t["PENDING (AU)"]), "")]
        if sel["month"] and mdf_v is not None and not mdf_v.empty:
            t = total_row(mdf_v)
            kpis += [("ORDERS · months", n0(t["ORDERS"]), ""),
                     ("IN-PRODUCTION PCS (AS) · months", n0(t["IN-PRODUCTION (AS)"]), ""),
                     ("RECEIVED PCS (AT) · months", n0(t["RECEIVED (AT)"]), "")]
        if sel["fabricator"] and not fab_v.empty:
            kpis += [("PENDING PCS · fabricators", n0(fab_v["PENDING PCS"].sum()), "")]
        if not kpis:
            kpis = read_kpis(g, 6, 7)
        else:
            st.caption("Filter active: KPI cards selected tables ke totals se bane hain.")
    else:
        kpis = read_kpis(g, 6, 7)
    badge("📊 Process Key Performance Indicators")
    render_kpi_cards(kpis)

    badge("📊 Category-wise Production Performance Breakdown")
    c1, c2 = st.columns([1, 1.35])
    with c1:
        show_table(cat_v)
    with c2:
        b = body(cat_v)
        if b is not None and not b.empty:
            chart_df = b.melt(id_vars="CATEGORY", var_name="Metric", value_name="PCS")
            fig = px.bar(chart_df, x="CATEGORY", y="PCS", color="Metric", barmode="group",
                         title="CATEGORY-WISE VOLUME COMPARISON",
                         color_discrete_sequence=["#6366f1", "#ef4444", "#f59e0b"])
            fig.update_xaxes(tickangle=-35, title="")
            show_chart(fig, 360)

    badge("🧵 Fabricator Pending PCS Share")
    if fab_v is not None and not fab_v.empty:
        f1, f2 = st.columns([1.35, 1])
        with f1:
            fig = px.pie(fab_v, names="FABRICATOR", values="PENDING PCS", hole=0.48,
                         title="FABRICATOR PENDING PCS SHARE")
            fig.update_traces(textposition="inside", textinfo="percent")
            show_chart(fig, 360)
        with f2:
            tbl = fab_v.copy()
            tbl["SHARE %"] = tbl["PENDING PCS"] / tbl["PENDING PCS"].sum() * 100
            tot = pd.DataFrame([{"FABRICATOR": "TOTAL", "PENDING PCS": tbl["PENDING PCS"].sum(), "SHARE %": 100.0}])
            show_table(pd.concat([tbl, tot], ignore_index=True), pct_cols=("SHARE %",))
    else:
        st.info("Selected filters ke liye fabricator pending data nahi hai.")

    badge("📅 Monthly Fulfillment Trend")
    m1, m2 = st.columns([1, 1.35])
    with m1:
        show_table(mdf_v, height=500)
    with m2:
        b = body(mdf_v)
        if b is not None and not b.empty:
            line_df = b.melt(id_vars="MONTH", value_vars=["IN-PRODUCTION (AS)", "RECEIVED (AT)"],
                             var_name="Metric", value_name="PCS")
            fig = px.line(line_df, x="MONTH", y="PCS", color="Metric", markers=True,
                          title="MONTHLY FULFILLMENT TREND ANALYSIS",
                          color_discrete_sequence=["#ef4444", "#6366f1"])
            fig.update_xaxes(tickangle=-35, title="")
            show_chart(fig, 460)


def client_view(sheet_id, cfg):
    tab, g = get_dashboard_grid(sheet_id, cfg["dashboard_tabs"]["client"])
    st.subheader("🏢 Executive Client Performance Dashboard")
    show_sheet_filters(g, [("Month", 3, 1), ("Client", 3, 5), ("Order Type", 3, 10), ("Category", 3, 13)])

    m = read_table(g, r"CLIENT FULFILLMENT BREAKDOWN", [
        ("MONTH", 0), ("ORDER QTY", 2), ("IN PRODUCTION", 3), ("RECEIVED", 4), ("PENDING", 5)])
    cat = read_table(g, r"CATEGORY WISE ORDER BREAKDOWN", [("MONTH", 0)] + [(None, c) for c in range(2, 10)])
    cat_cols = [c for c in cat.columns[1:] if str(c).upper() != "TOTAL"]

    sel = filter_panel([("month", "Month", FY_MONTH_LABELS), ("category", "Category", cat_cols)], "cli")

    m_v, cat_v = m, cat
    if sel["month"]:
        keys = month_keys(sel["month"])
        m_v = retotal(body(m)[lambda d: d["MONTH"].isin(keys)])
        cat_v = body(cat)[lambda d: d["MONTH"].isin(keys)]
    else:
        cat_v = body(cat)
    if sel["category"] and not cat_v.empty:
        cat_v = cat_v[["MONTH"] + sel["category"]].copy()
        cat_v["TOTAL"] = cat_v[sel["category"]].sum(axis=1)
    if sel["month"] or sel["category"]:
        cat_v = retotal(cat_v)
    else:
        cat_v = cat

    if any(sel.values()):
        kpis = []
        if sel["month"] and m_v is not None and not m_v.empty:
            t = total_row(m_v)
            kpis += [("TOTAL QTY (PCS)", n0(t["ORDER QTY"]), ""), ("IN PRODUCTION", n0(t["IN PRODUCTION"]), ""),
                     ("RECEIVED / DONE", n0(t["RECEIVED"]), ""), ("TOTAL PENDING QTY", n0(t["PENDING"]), "")]
        if cat_v is not None and not cat_v.empty:
            kpis += [("CATEGORY TOTAL (PCS)", n0(total_row(cat_v).get("TOTAL", 0)), "")]
        st.caption("Filter active: KPI cards selected tables ke totals se bane hain.")
    else:
        kpis = read_kpis(g, 5, 6, sub_row=7)
    render_kpi_cards(kpis)

    badge("📅 Client Fulfillment Breakdown (Monthly)")
    c1, c2, c3 = st.columns([1.25, 1, 1])
    with c1:
        show_table(m_v, height=500)
    b = body(m_v)
    with c2:
        pie_df = b[b["ORDER QTY"] > 0] if b is not None and not b.empty else pd.DataFrame()
        if not pie_df.empty:
            fig = px.pie(pie_df, names="MONTH", values="ORDER QTY", title="CLIENT MONTHLY ORDER TREND (PCS)")
            fig.update_traces(textposition="inside", textinfo="percent+label")
            show_chart(fig, 420)
        else:
            st.info("Selected filters ke liye order data nahi hai.")
    with c3:
        tot = total_row(m_v)
        if tot and (tot["RECEIVED"] + tot["PENDING"]) > 0:
            q = pd.DataFrame({"Status": ["RECEIVED QTY", "PENDING QTY"], "Qty": [tot["RECEIVED"], tot["PENDING"]]})
            fig = px.pie(q, names="Status", values="Qty", hole=.45,
                         title="ORDER FULFILLMENT RATIO (RECEIVED vs PENDING)",
                         color="Status", color_discrete_map={"RECEIVED QTY": "#10b981", "PENDING QTY": "#ef4444"})
            show_chart(fig, 420)
        else:
            st.info("Received / pending data nahi hai.")

    badge("🧩 Category Wise Order Breakdown (Pcs)")
    c4, c5 = st.columns([1.35, 1])
    with c4:
        show_table(cat_v, height=500)
    with c5:
        b = body(cat_v)
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
    st.markdown(
        f"""<div class="dashboard-hero"><h2>📊 {html.escape(sheet_name)} · Executive Dashboard 2026-27</h2>
        <p>Designer / Production / Client dashboard tabs se live data · Last updated
        {datetime.now().strftime('%d %b %Y, %H:%M:%S')} · Next auto-refresh
        {(datetime.now() + timedelta(seconds=AUTO_REFRESH_SECONDS)).strftime('%H:%M')}
        (har {AUTO_REFRESH_SECONDS // 60} min)</p></div>""",
        unsafe_allow_html=True)

    t1, t2, t3 = st.tabs(["👨‍🎨 Designer Dashboard", "🏭 Production Process Dashboard", "🏢 Client Dashboard"])
    with t1:
        designer_view(sheet_id, cfg)
    with t2:
        production_view(sheet_id, cfg)
    with t3:
        client_view(sheet_id, cfg)


# -----------------------------------------------------------------------------
# 8. SAMPLE SUMMARY
# -----------------------------------------------------------------------------
def render_sample_summary_dashboard(sheet_name, cfg):
    sheet_id = cfg["id"]
    tab, g = get_dashboard_grid(sheet_id, cfg["dashboard_tab"], cfg.get("gid"))
    hero("⚡ Executive Sample Performance & Designer Dashboard (2026-27)", tab)
    show_sheet_filters(g, [("Month", 4, 1), ("Designer", 4, 6), ("Status", 4, 11), ("Vendor", 4, 16)])

    df_m = read_table(g, r"MONTHLY SAMPLE BREAKDOWN", [
        ("MONTH", 0), ("APPROVED", 2), ("REJECTED", 3), ("HOLD", 4), ("PROCESS", 5),
        ("OTHER", 6), ("TOTAL", 7), ("APPR %", 8)], pct=("APPR %",))
    df_d = read_table(g, r"DESIGNER PERFORMANCE SCORECARD", [
        ("DESIGNER", 10), ("APPROVED", 11), ("REJECTED", 12), ("TOTAL", 13), ("APPR %", 14)], pct=("APPR %",))
    df_v = read_table(g, r"VENDOR PERFORMANCE SCORECARD", [
        ("VENDOR", 16), ("APPROVED", 18), ("REJECTED", 19), ("TOTAL", 20), ("APPR %", 21)], pct=("APPR %",))
    status_cols = ["APPROVED", "REJECTED", "HOLD", "PROCESS", "OTHER"]

    des_names = list(body(df_d)["DESIGNER"]) if not df_d.empty else []
    ven_names = list(body(df_v)["VENDOR"]) if not df_v.empty else []
    sel = filter_panel([("month", "Month", FY_MONTH_LABELS), ("designer", "Designer", des_names),
                        ("status", "Status", status_cols), ("vendor", "Vendor", ven_names)], "samp")

    # ---- apply filters
    m_v, d_v, v_v = df_m, df_d, df_v
    if sel["month"] or sel["status"]:
        b = body(df_m)
        if sel["month"]:
            b = b[b["MONTH"].isin(sel["month"])]
        cols = sel["status"] or status_cols
        b = b[["MONTH"] + cols].copy()
        b["TOTAL"] = b[cols].sum(axis=1)
        b["APPR %"] = np.where((b["TOTAL"] > 0) & ("APPROVED" in cols),
                               (b["APPROVED"] if "APPROVED" in cols else 0) / b["TOTAL"].replace(0, np.nan) * 100, 0.0)
        b["APPR %"] = b["APPR %"].fillna(0.0)
        m_v = retotal(b, rate=("APPR %", "APPROVED", "TOTAL") if "APPROVED" in cols else None)
        if "APPROVED" not in cols and m_v is not None and not m_v.empty:
            m_v.loc[m_v.index[-1], "APPR %"] = 0.0
    if sel["designer"]:
        d_v = retotal(pick_rows(df_d, sel["designer"]), rate=("APPR %", "APPROVED", "TOTAL"))
    if sel["vendor"]:
        v_v = retotal(pick_rows(df_v, sel["vendor"]), rate=("APPR %", "APPROVED", "TOTAL"))

    # ---- KPIs
    def top_of(d):
        b = body(d)
        return b.loc[b["APPROVED"].idxmax(), "DESIGNER"] if b is not None and not b.empty and b["APPROVED"].max() > 0 else "N/A"

    if sel["month"] or sel["status"]:
        t = total_row(m_v)
        tot = t.get("TOTAL", 0)
        kpis = [("TOTAL SAMPLES QTY", n0(tot) + " Samples", ""),
                ("APPROVED SAMPLES", n0(t.get("APPROVED", 0)) + " Pcs", ""),
                ("REJECTED SAMPLES", n0(t.get("REJECTED", 0)) + " Pcs", ""),
                ("ON HOLD SAMPLES", n0(t.get("HOLD", 0)) + " Pcs", ""),
                ("ON PROCESS", n0(t.get("PROCESS", 0)) + " Pcs", ""),
                ("APPROVAL RATIO %", f"{t.get('APPR %', 0):.1f}%", ""),
                ("🏆 TOP PERFORMER", top_of(d_v), "")]
    elif sel["designer"] or sel["vendor"]:
        src = d_v if sel["designer"] else v_v
        t = total_row(src)
        kpis = [("TOTAL SAMPLES QTY", n0(t.get("TOTAL", 0)) + " Samples", ""),
                ("APPROVED SAMPLES", n0(t.get("APPROVED", 0)) + " Pcs", ""),
                ("REJECTED SAMPLES", n0(t.get("REJECTED", 0)) + " Pcs", ""),
                ("APPROVAL RATIO %", f"{t.get('APPR %', 0):.1f}%", "")]
        if sel["designer"]:
            kpis.append(("🏆 TOP PERFORMER", top_of(d_v), ""))
    else:
        kpis = read_kpis(g, 7, 8)
    render_kpi_cards(kpis)
    if any(sel.values()):
        st.caption("Filter active: KPI cards selected tables ke totals se bane hain.")

    badge("📊 Executive Tables & Workflow Matrix")
    c_m, c_d, c_v = st.columns([1.4, 1, 1])
    with c_m:
        st.markdown("##### 📅 Monthly Sample Breakdown")
        show_table(m_v, pct_cols=("APPR %",))
        note = cell_text(g, r"Process Date")
        if note and not (sel["month"] or sel["status"]):
            (st.warning if note.startswith("⚠") else st.success)(note)
    with c_d:
        st.markdown("##### 👩‍🎨 Designer Scorecard")
        show_table(d_v, pct_cols=("APPR %",))
    with c_v:
        st.markdown("##### 🏭 Vendor Scorecard")
        show_table(v_v, pct_cols=("APPR %",))

    badge("📈 Visual Performance Trends")
    mo = body(m_v)
    g1, g2, g3 = st.columns(3)
    with g1:
        if mo is not None and not mo.empty:
            ycols = [c for c in status_cols if c in mo.columns]
            fig = px.bar(mo, x="MONTH", y=ycols, title="MONTHLY SAMPLE STATUS DISTRIBUTION", barmode="stack",
                         color_discrete_map={"APPROVED": "#10b981", "REJECTED": "#ef4444", "HOLD": "#f59e0b",
                                             "PROCESS": "#6366f1", "OTHER": "#94a3b8"})
            fig.update_xaxes(tickangle=-35, title="")
            fig.update_yaxes(title="")
            show_chart(fig, 350)
    with g2:
        if mo is not None and not mo.empty:
            ycols = [c for c in ["TOTAL", "APPROVED", "REJECTED"] if c in mo.columns]
            fig = px.line(mo, x="MONTH", y=ycols, markers=True, title="MONTHLY PROCESS VOLUME TREND",
                          color_discrete_map={"TOTAL": "#6366f1", "APPROVED": "#10b981", "REJECTED": "#ef4444"})
            fig.update_xaxes(tickangle=-35, title="")
            fig.update_yaxes(title="")
            show_chart(fig, 350)
    with g3:
        t = total_row(m_v)
        if t:
            pie = pd.DataFrame({"Status": [c for c in status_cols if c in m_v.columns],
                                "Count": [t[c] for c in status_cols if c in m_v.columns]})
            if pie["Count"].sum() > 0:
                fig = px.pie(pie, names="Status", values="Count", hole=0.45, title="OVERALL SAMPLE APPROVAL SHARE",
                             color="Status",
                             color_discrete_map={"APPROVED": "#10b981", "REJECTED": "#ef4444", "HOLD": "#f59e0b",
                                                 "PROCESS": "#6366f1", "OTHER": "#94a3b8"})
                show_chart(fig, 350)
            else:
                st.info("Selected filters ke liye data nahi hai.")


# -----------------------------------------------------------------------------
# 9. FABRICATOR REPORT
# -----------------------------------------------------------------------------
def render_fabricator_dashboard(sheet_name, cfg):
    sheet_id = cfg["id"]
    tab, g = get_dashboard_grid(sheet_id, cfg["dashboard_tab"], cfg.get("gid"))
    upd = _txt(_cell(g, 4, 17))
    hero("🏭 Fabricator Stock Position Dashboard (2026-27)", tab, f" · Sheet: {upd}" if upd else "")
    show_sheet_filters(g, [("Fabricator", 4, 1), ("Month", 4, 6)])

    mt = read_table(g, r"MONTHLY POSITION OF STOCK", [
        ("MONTH", 0), ("FABRIC ISSUE (MTR)", 2), ("PCS UNDER PRODUCTION", 3), ("RCVD", 4),
        ("REMAINING", 5), ("MONTHLY INCOMING", 6), ("RCVD %", 7)], pct=("RCVD %",))
    sc = read_table(g, r"FABRICATOR SCORECARD", [
        ("FABRICATOR", 9), ("FABRIC ISSUE (MTR)", 11), ("PCS UNDER PRODUCTION", 12), ("RCVD", 13),
        ("REMAINING", 14), ("MONTHLY INCOMING", 15), ("RCVD %", 16)], pct=("RCVD %",), stop_total=False)
    mx = read_table(g, r"MATRIX", [("FABRICATOR", 0)] + [(None, c) for c in range(2, 15)])
    rate = ("RCVD %", "RCVD", "PCS UNDER PRODUCTION")

    fab_names = list(body(sc)["FABRICATOR"]) if not sc.empty else []
    sel = filter_panel([("fabricator", "Fabricator", fab_names), ("month", "Month", FY_MONTH_LABELS)], "fab")

    mt_v, sc_v, mx_v = mt, sc, mx
    if sel["month"]:
        mt_v = retotal(body(mt)[lambda d: d["MONTH"].isin(sel["month"])], rate=rate)
        shorts = [s.split("-")[0][:3] for s in sel["month"]]
        if not mx.empty:
            b = body(mx)
            keep = ["FABRICATOR"] + [c for c in b.columns[1:] if str(c) in shorts]
            b = b[keep].copy()
            b["TOTAL"] = b[keep[1:]].sum(axis=1) if len(keep) > 1 else 0.0
            mx_v = b
    if sel["fabricator"]:
        sc_v = retotal(pick_rows(sc, sel["fabricator"]), rate=rate)
        if not mx_v.empty:
            mx_v = body(mx_v)[lambda d: d["FABRICATOR"].isin(sel["fabricator"])]
    if (sel["month"] or sel["fabricator"]) and mx_v is not None and not mx_v.empty:
        mx_v = retotal(body(mx_v), label="ALL FABRICATORS")

    # ---- KPIs
    def kpi_from(t, scorecard=None):
        rcvd_pct = t["RCVD"] / t["PCS UNDER PRODUCTION"] * 100 if t["PCS UNDER PRODUCTION"] else 0.0
        out = [("FABRIC ISSUED (MTR)", n0(t["FABRIC ISSUE (MTR)"]) + " mtr", ""),
               ("PCS UNDER PRODUCTION", n0(t["PCS UNDER PRODUCTION"]) + " Pcs", ""),
               ("RCVD (RECEIVED)", n0(t["RCVD"]) + " Pcs", ""),
               ("REMAINING", n0(t["REMAINING"]) + " Pcs", ""),
               ("MONTHLY INCOMING", n0(t["MONTHLY INCOMING"]) + " Pcs", ""),
               ("RECEIVED %", f"{rcvd_pct:.1f}%", "")]
        if scorecard is not None and not scorecard.empty:
            out.append(("🏆 TOP RECEIVER", scorecard.loc[scorecard["RCVD"].idxmax(), "FABRICATOR"]
                        if scorecard["RCVD"].max() > 0 else "N/A", ""))
            out.append(("⚠ MOST PENDING", scorecard.loc[scorecard["REMAINING"].idxmax(), "FABRICATOR"]
                        if scorecard["REMAINING"].max() > 0 else "N/A", ""))
        return out

    if sel["fabricator"] and sc_v is not None and not sc_v.empty:
        render_kpi_cards(kpi_from(total_row(sc_v), body(sc_v)))
        st.caption("Filter active: KPI cards selected fabricators ke scorecard (poore saal) se bane hain.")
    elif sel["month"] and mt_v is not None and not mt_v.empty:
        render_kpi_cards(kpi_from(total_row(mt_v)))
        st.caption("Filter active: KPI cards selected months ke totals se bane hain.")
    else:
        render_kpi_cards(read_kpis(g, 7, 8))

    t1, t2 = st.tabs(["📊 Fabricator Dashboard", "📋 Month × Fabricator Matrix"])
    with t1:
        badge("📅 Monthly Position Of Stock")
        c1, c2 = st.columns([1.25, 1])
        with c1:
            show_table(mt_v, pct_cols=("RCVD %",), height=500)
        mb = body(mt_v)
        with c2:
            if mb is not None and not mb.empty:
                fig = px.bar(mb, x="MONTH", y=["PCS UNDER PRODUCTION", "RCVD", "REMAINING"], barmode="group",
                             title="MONTHLY: PRODUCTION vs RCVD vs REMAINING",
                             color_discrete_sequence=["#6366f1", "#10b981", "#ef4444"])
                fig.update_xaxes(tickangle=-35, title="")
                fig.update_yaxes(title="Pcs")
                show_chart(fig, 460)
        if mb is not None and not mb.empty:
            fig = px.line(mb, x="MONTH", y=["FABRIC ISSUE (MTR)", "MONTHLY INCOMING"], markers=True,
                          title="MONTHLY FABRIC ISSUE & INCOMING TREND",
                          color_discrete_sequence=["#6366f1", "#f59e0b"])
            fig.update_xaxes(tickangle=-35, title="")
            fig.update_yaxes(title="")
            show_chart(fig, 340)

        badge("🏭 Fabricator Scorecard")
        if sel["month"]:
            st.caption("Scorecard poore saal ka hai (Month filter yahan lagu nahi hota).")
        s1, s2 = st.columns([1.5, 1])
        with s1:
            show_table(sc_v, pct_cols=("RCVD %",))
        sb = body(sc_v)
        with s2:
            if sb is not None and not sb.empty:
                fig = px.bar(sb, y="FABRICATOR", x=["RCVD", "REMAINING"], orientation="h", barmode="stack",
                             title="FABRICATOR WISE: RCVD vs REMAINING",
                             color_discrete_sequence=["#10b981", "#ef4444"])
                fig.update_yaxes(title="", autorange="reversed")
                fig.update_xaxes(title="Pcs")
                show_chart(fig, 400)
        if sb is not None and not sb.empty:
            fig = px.area(sb, x="FABRICATOR", y="RCVD %", title="FABRICATOR WISE: RECEIVED %",
                          color_discrete_sequence=["#6366f1"])
            fig.update_yaxes(range=[0, 100], ticksuffix="%", title="")
            fig.update_xaxes(title="", tickangle=-35)
            show_chart(fig, 340)

        check = cell_text(g, r"ALL OVER table|ALL OVER nahi")
        if check and not sel["fabricator"]:
            if check.startswith("✅"):
                st.success(check)
            elif check.startswith("⚠"):
                st.warning(check)
            else:
                st.info(check)

    with t2:
        title = cell_text(g, r"MATRIX") or "MONTH × FABRICATOR MATRIX"
        badge(f"🧮 {title}")
        show_table(mx_v)


# -----------------------------------------------------------------------------
# 10. MAIN ROUTER (auto-refresh fragment + crash-proof)
# -----------------------------------------------------------------------------
def render_selected(selected):
    cfg = SHEET_REGISTRY[selected]
    kind = cfg.get("type", "tracker")
    try:
        if kind == "tracker":
            render_tracker(selected, cfg)
        elif kind == "overview_fabricators":
            render_fabricator_dashboard(selected, cfg)
        elif kind == "sample_summary":
            render_sample_summary_dashboard(selected, cfg)
    except SheetError as e:
        show_access_error(e)
    except Exception as e:                      # page hamesha khulta rahe
        if type(e).__name__ in ("StopException", "RerunException", "RerunData"):
            raise
        st.error(f"Dashboard load karte waqt error aaya: {e}")
        with st.expander("Technical details"):
            st.code(traceback.format_exc())


_FRAGMENT = getattr(st, "fragment", None)
if _FRAGMENT is not None:
    try:
        render_live = _FRAGMENT(run_every=AUTO_REFRESH_SECONDS)(render_selected)
    except TypeError:                           # purane Streamlit me run_every nahi hota
        render_live = render_selected
else:
    render_live = render_selected


def main():
    apply_theme()
    with st.sidebar:
        st.markdown("### 🗂️ Workspace Selection")
        selected = st.selectbox("Active Google Sheet", list(SHEET_REGISTRY.keys()), key="ws_choice")
        st.markdown("### 🔄 Data Sync")
        st.caption(f"Auto-refresh: har {AUTO_REFRESH_SECONDS // 60} minute")
        if st.button("🔄 Refresh now", key="refresh_now"):
            st.cache_data.clear()
            st.rerun()
        if render_live is render_selected:
            st.caption("Auto-refresh ke liye Streamlit ≥ 1.37 chahiye; tab tak 'Refresh now' use karein.")
    render_live(selected)


if __name__ == "__main__":
    main()
