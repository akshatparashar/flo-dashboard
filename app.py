import html
import re
import warnings
from datetime import datetime, timezone

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
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
        # Data tab the sheet dashboards are built from (first match wins).
        "source_tabs": ["CONFIRMATION SHEET", "ORDER SHEET"],
        # The sheet's own dashboard tabs (used only by the Data Check tab).
        "dashboard_tabs": {
            "designer": "DESIGNER DASHBOARD",
            "production": "PRODUCTION PROCESS DASHBOARD",
            "client": "CLIENT DASHBOARD",
        },
    },
    "Sample Summary": {
        "id": "1EfQ08lXGL8YjtoaZ2ygJtNVaED7doDijo2jFvCuS7Kg",
        "type": "sample_summary",
        "gid": 78218658,   # fallback only (used if none of the tab names below exist)
        # Source (data) tab, first match wins. Same order as the Apps Script.
        "source_tabs": ["2026-27", "SAMPLE SHEET 2026-27", "Sheet1"],
        "dashboard_tab": "SAMPLE DASHBOARD",   # sheet's own dashboard (Data Check compares with it)
    },
    "Fabricator Report": {
        "id": "1hP9Bkvu2F-qj4tXYhOCb4alfJOZZtAsMQNOjVQyWoo4",
        "type": "overview_fabricators",
        "gid": 164418035,  # fallback only
        "source_tabs": ["MONTHWISE SUMMARY", "MONTHWISE SUMMARY 2026-27"],
        "dashboard_tab": "FABRICATOR DASHBOARD",
    },
}

# Google Sheet data is re-read at most once per this many seconds (live updates)
LIVE_TTL = 60

# Financial year shown on the dashboards (April 2026 – March 2027)
FY_START_YEAR = 2026
MONTHS = ["April", "May", "June", "July", "August", "September",
          "October", "November", "December", "January", "February", "March"]
MONTH_NUM = {m[:3].lower(): i for i, m in enumerate(
    ["January", "February", "March", "April", "May", "June", "July",
     "August", "September", "October", "November", "December"], start=1)}
MONTH_NAME_BY_NUM = {v: k for k, v in {
    "January": 1, "February": 2, "March": 3, "April": 4, "May": 5, "June": 6, "July": 7,
    "August": 8, "September": 9, "October": 10, "November": 11, "December": 12}.items()}
FY_MONTH_LABELS = [
    f"{m}-{(FY_START_YEAR if i < 9 else FY_START_YEAR + 1) % 100:02d}" for i, m in enumerate(MONTHS)
]

CATEGORIES_LIST = ["CO-ORD SET", "KURTA PANT", "TOP", "KURTA PANT DUPATTA", "DRESS", "KAFTAN", "KURTA"]
# Designers always listed on the Designer Dashboard (even with 0 volume), like the sheet.
KNOWN_DESIGNERS = ["ANAMIKA", "AYUSHI", "CHARU", "DEEPIKA", "JYOTI", "KEERTI",
                   "KRISHNA", "MANSI", "MUSKAN", "REKHA"]

# Source-tab columns used by the Master Sheet dashboards
MASTER_COLS = {
    "date_client": "B",   # order date -> month
    "designer": "C",
    "type": "D",          # NEW / REPEAT
    "category": "F",
    "qty": "J",           # order qty
    "client": "N",
    "fabricator": "AA",
    "date_prod": "AC",
    "delay": "AH",        # delay days (>0 overdue)
    "production": "AS",   # in production pcs
    "received": "AT",     # received pcs
    "pending": "AU",      # pending pcs
    "status": "AX",
}

def _stretch_kwargs():
    """Full-width kwarg that works on both old and new Streamlit versions."""
    try:
        major, minor = (int(p) for p in st.__version__.split(".")[:2])
    except Exception:
        return {"use_container_width": True}
    return {"width": "stretch"} if (major, minor) >= (1, 50) else {"use_container_width": True}


STRETCH = _stretch_kwargs()

PALETTE = ["#2563eb", "#059669", "#d97706", "#dc2626", "#7c3aed", "#0891b2", "#db2777", "#65a30d",
           "#ea580c", "#0d9488", "#9333ea", "#ca8a04"]
PLOT_TEMPLATE = "plotly_white"


def apply_theme():
    """Sidebar dark-mode toggle + global CSS."""
    global PLOT_TEMPLATE
    if "dashboard_dark_mode" not in st.session_state:
        st.session_state.dashboard_dark_mode = False

    with st.sidebar:
        st.markdown("### 🎨 Preferences")
        st.toggle("Dark mode", key="dashboard_dark_mode", help="Dashboard appearance mode toggle")

    dark = st.session_state.dashboard_dark_mode
    if dark:
        app_bg, panel_bg, text, muted, border = "#0a0f1d", "#12192b", "#eaf0f8", "#94a3b8", "#1e293b"
        card_bg, chip_bg, accent = "#162035", "#1e2c45", "#38bdf8"
        PLOT_TEMPLATE = "plotly_dark"
    else:
        app_bg, panel_bg, text, muted, border = "#f8fafc", "#ffffff", "#0f172a", "#64748b", "#e2e8f0"
        card_bg, chip_bg, accent = "#f1f5f9", "#e2e8f0", "#2563eb"
        PLOT_TEMPLATE = "plotly_white"

    px.defaults.template = PLOT_TEMPLATE
    px.defaults.color_discrete_sequence = PALETTE
    hero_grad = "#131e33 0%, #172a48 100%" if dark else "#ffffff 0%, #edf4ff 100%"

    st.markdown(f"""
<style>
:root {{
    --app-bg: {app_bg}; --panel-bg: {panel_bg}; --card-bg: {card_bg}; --text-color: {text};
    --muted-color: {muted}; --border-color: {border}; --chip-bg: {chip_bg}; --accent: {accent};
}}
.stApp {{ background-color: var(--app-bg); color: var(--text-color); font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; }}
.block-container {{ padding-top: 1.15rem; padding-bottom: 2.8rem; max-width: 1650px; }}
[data-testid="stSidebar"] {{ background-color: var(--panel-bg); border-right: 1px solid var(--border-color); }}
[data-testid="stSidebar"] h3 {{ font-size: .83rem; font-weight: 750; text-transform: uppercase; letter-spacing: 0.08em; color: var(--muted-color); margin-bottom: 0.6rem; }}
[data-testid="stSidebar"] label {{ font-size: .78rem !important; font-weight: 650 !important; color: var(--text-color) !important; margin-bottom: 3px; }}
.stMultiSelect [data-baseweb="select"] > div {{ border-radius: 8px; border: 1px solid var(--border-color); background: var(--panel-bg); min-height: 36px; }}
.stMultiSelect [data-baseweb="tag"] {{ background-color: var(--chip-bg) !important; border: 1px solid var(--border-color) !important; border-radius: 5px !important; padding: 1px 6px !important; margin: 2px !important; }}
.stMultiSelect [data-baseweb="tag"] span {{ color: var(--text-color) !important; font-size: 0.76rem !important; font-weight: 550 !important; }}
[data-testid="stMetric"] {{ background: var(--panel-bg); border: 1px solid var(--border-color); border-top: 3px solid var(--accent); padding: 14px 18px; border-radius: 12px; box-shadow: 0 4px 14px rgba(0,0,0,0.04); }}
[data-testid="stMetricLabel"] {{ color: var(--muted-color); font-size: .78rem; font-weight: 700; text-transform: uppercase; letter-spacing: .03em; }}
[data-testid="stMetricValue"] {{ color: var(--text-color); font-weight: 800; font-size: 1.45rem; }}
[data-testid="stTabs"] button {{ border-radius: 8px 8px 0 0; font-weight: 700; font-size: .92rem; padding: 10px 20px; }}
[data-testid="stPlotlyChart"] {{ background: var(--panel-bg); border: 1px solid var(--border-color); border-radius: 12px; padding: 8px; }}
[data-testid="stDataFrame"] {{ border: 1px solid var(--border-color); border-radius: 10px; overflow: hidden; }}
.dashboard-hero {{
    background: linear-gradient(135deg, {hero_grad});
    border: 1px solid var(--border-color); border-radius: 14px; padding: 18px 22px; margin-bottom: 18px;
    box-shadow: 0 4px 15px rgba(0,0,0,0.03);
}}
.dashboard-hero h2 {{ margin: 0; font-size: 1.45rem; font-weight: 800; letter-spacing: -0.02em; }}
.dashboard-hero p {{ color: var(--muted-color); margin: 3px 0 0 0; font-size: .88rem; }}
.section-badge {{ display: inline-flex; align-items: center; background: var(--chip-bg); padding: 4px 12px; border-radius: 6px; font-size: 0.8rem; font-weight: 750; margin: 10px 0 8px 0; text-transform: uppercase; letter-spacing: .02em; }}
</style>
""", unsafe_allow_html=True)


# -----------------------------------------------------------------------------
# 2. HELPER UTILITIES & DATA SANITIZATION
# -----------------------------------------------------------------------------
def col_to_idx(letter):
    n = 0
    for c in letter.upper():
        n = n * 26 + ord(c) - 64
    return n - 1


def norm_key(x):
    return re.sub(r"[^A-Z0-9]", "", str(x).upper())


def num(s):
    """Convert a Series (numbers or text like '1,234', '(50)', '12%', '5 Days') to float; blanks -> 0."""
    if not isinstance(s, pd.Series):
        s = pd.Series(s)
    out = pd.to_numeric(s, errors="coerce").astype(float)
    need = out.isna() & s.notna()
    if need.any():
        text = s[need].astype(str).str.replace("\xa0", "", regex=False).str.strip()
        neg = text.str.match(r"^\(.*\)$") | text.str.startswith("−")
        cleaned = text.str.replace(r"[^0-9.\-]", "", regex=True)
        cleaned = cleaned.where(cleaned.str.count(r"\.") <= 1, "")
        val = pd.to_numeric(cleaned, errors="coerce")
        val = val.where(~neg, -val.abs())
        out.loc[need] = val
    return out.fillna(0).astype(float)


def clean_delay_days(s):
    parsed = num(s)
    # Blank-date formulas (e.g. TODAY()-blank) produce huge numbers -> treat as 0
    return parsed.mask(parsed.abs() > 1000, 0)


def clean_text(s):
    t = s.astype("string").fillna("")
    t = t.str.replace("\xa0", " ", regex=False).str.replace(r"\s+", " ", regex=True).str.strip()
    t = t.mask(t.str.lower().isin(["nan", "none", "<na>", "#n/a", "#ref!", "#value!"]), "")
    return t.astype(str)


def _parse_one_date(v):
    for dayfirst in (True, False):
        try:
            d = pd.to_datetime(v, dayfirst=dayfirst, errors="coerce")
        except Exception:
            d = pd.NaT
        if pd.notna(d):
            return d
    return pd.NaT


def parse_dates(s):
    """Handles Google Sheets serial numbers (unformatted) and text dates (dd/mm/yyyy first)."""
    s = pd.Series(s)
    out = pd.Series(pd.NaT, index=s.index, dtype="datetime64[ns]")
    numeric = pd.to_numeric(s, errors="coerce")
    serial = numeric.between(20000, 80000)  # valid sheet serials ~1954..2119
    if serial.any():
        out.loc[serial] = pd.to_datetime(numeric[serial].astype(float), unit="D", origin="1899-12-30")
    text = s.astype(str).str.strip()
    rest = (~serial) & numeric.isna() & text.ne("") & ~text.str.lower().isin(["nan", "none", "<na>"])
    if rest.any():
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            out.loc[rest] = pd.to_datetime(text[rest].apply(_parse_one_date), errors="coerce")
    return out


def month_label(dts):
    lab = pd.Series("(NO DATE)", index=dts.index, dtype=object)
    valid = dts.notna()
    lab[valid] = [f"{MONTH_NAME_BY_NUM[d.month]}-{d.year % 100:02d}" for d in dts[valid]]
    return lab


def month_sort_key(label):
    m = re.match(r"\s*([A-Za-z]+)[\s\-']*(\d{2,4})?", str(label))
    if not m:
        return (9999, 99)
    mon = MONTH_NUM.get(m.group(1)[:3].lower(), 99)
    yr = int(m.group(2)) if m.group(2) else 0
    if 0 < yr < 100:
        yr += 2000
    return (yr if yr else 9998, mon)


def fmt(x):
    return f"{x:,.0f}"


def fmt_kpi(value, kind):
    if kind == "orders":
        return f"{value:,.0f} Orders"
    if kind == "pcs":
        return f"{value:,.0f} Pcs"
    if kind == "days":
        return f"{value:.1f} Days"
    if kind == "pct":
        return f"{value:.1f}%"
    if kind == "text":
        return str(value)
    return f"{value:,.0f}"


def metrics(items):
    cols = st.columns(len(items))
    for c, (label, value) in zip(cols, items):
        c.metric(label, value)


def render_kpis(kpis, per_row=4):
    """kpis: list of (label, sheet_label, value, kind)."""
    for i in range(0, len(kpis), per_row):
        chunk = kpis[i:i + per_row]
        metrics([(k[0], fmt_kpi(k[2], k[3])) for k in chunk])


def style_fig(fig, height=360):
    fig.update_layout(
        template=PLOT_TEMPLATE,
        height=height,
        margin=dict(l=12, r=12, t=50, b=10),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1, title_text=""),
        font=dict(size=11),
        title_font=dict(size=14, family="-apple-system, sans-serif"),
    )
    return fig


def badge(text):
    st.markdown(f'<div class="section-badge">{html.escape(text)}</div>', unsafe_allow_html=True)


def add_total(df, label_col, label="TOTAL"):
    tot = {c: (df[c].sum() if pd.api.types.is_numeric_dtype(df[c]) else "") for c in df.columns}
    tot[label_col] = label
    return pd.concat([df, pd.DataFrame([tot])], ignore_index=True)


def _highlight_total(row):
    is_total = str(row.iloc[0]).strip().upper() in ("TOTAL", "GRAND TOTAL", "ALL FABRICATORS")
    style = "font-weight: 700; background-color: rgba(37, 99, 235, 0.14)" if is_total else ""
    return [style] * len(row)


def show_table(df, pct_cols=(), dec_cols=(), height=None):
    fmt_map = {}
    for c in df.columns:
        if c in pct_cols:
            fmt_map[c] = "{:.1f}%"
        elif c in dec_cols:
            fmt_map[c] = "{:,.2f}"
        elif pd.api.types.is_numeric_dtype(df[c]):
            fmt_map[c] = "{:,.0f}"
    styler = df.style.format(fmt_map).apply(_highlight_total, axis=1)
    kwargs = {**STRETCH, "hide_index": True}
    if height:
        kwargs["height"] = height
    st.dataframe(styler, **kwargs)


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


# -----------------------------------------------------------------------------
# 3. GOOGLE SHEETS AUTHENTICATION & LOADERS
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


@st.cache_data(ttl=LIVE_TTL, show_spinner=False)
def list_tabs(sheet_id):
    return [ws.title for ws in _open_book(sheet_id).worksheets()]


@st.cache_data(ttl=LIVE_TTL, show_spinner="Google Sheet se live data load ho raha hai...")
def load_tab_raw(sheet_id, tab_title):
    """Unformatted values: numbers as numbers, dates as serial numbers (no locale/format parsing errors)."""
    book = _open_book(sheet_id)
    resp = book.values_get(_a1_tab(tab_title), params={
        "valueRenderOption": "UNFORMATTED_VALUE",
        "dateTimeRenderOption": "SERIAL_NUMBER",
    })
    return resp.get("values", [])


@st.cache_data(ttl=LIVE_TTL, show_spinner=False)
def load_tab_formatted(sheet_id, tab_title):
    """Values exactly as displayed in the sheet (used to read the sheet's own dashboard KPIs)."""
    book = _open_book(sheet_id)
    resp = book.values_get(_a1_tab(tab_title))
    return resp.get("values", [])


def find_tab(tabs, wanted):
    w = norm_key(wanted)
    for t in tabs:
        if norm_key(t) == w:
            return t
    return None


@st.cache_data(ttl=LIVE_TTL, show_spinner="Sheet data load ho raha hai...")
def load_worksheet_smart(sheet_id, cfg, signature_text=None):
    """Safely retrieves worksheet by GID, Title or Content Signature."""
    book = _open_book(sheet_id)
    worksheets = book.worksheets()
    target_gid = cfg.get("gid")
    ws_target = None

    if target_gid is not None:
        for ws in worksheets:
            if str(ws.id) == str(target_gid):
                ws_target = ws
                break

    if ws_target is None:
        cand_titles = cfg.get("summary_tabs", []) + cfg.get("data_tabs", [])
        for pref in cand_titles:
            pref_norm = re.sub(r"[^a-z0-9]", "", str(pref).lower())
            for ws in worksheets:
                ws_norm = re.sub(r"[^a-z0-9]", "", str(ws.title).lower())
                if pref_norm in ws_norm or ws_norm in pref_norm:
                    ws_target = ws
                    break
            if ws_target:
                break

    if ws_target is None and signature_text:
        sig_low = signature_text.lower()
        for ws in worksheets:
            v = ws.get_all_values()
            if any(sig_low in str(c).lower() for r in v[:15] for c in r):
                ws_target = ws
                break

    if ws_target is None:
        ws_target = worksheets[0] if worksheets else None
    if ws_target is None:
        return "", []
    return ws_target.title, ws_target.get_all_values()


# -----------------------------------------------------------------------------
# 4. MASTER SHEET – DATA PREPARATION
# -----------------------------------------------------------------------------
CATEGORY_ALIASES = {norm_key(c): c for c in CATEGORIES_LIST}
CATEGORY_ALIASES.update({
    "COORD": "CO-ORD SET", "COORDSETS": "CO-ORD SET", "CORDSET": "CO-ORD SET",
    "KURTAPANTS": "KURTA PANT", "KURTAPANTSET": "KURTA PANT",
    "TOPS": "TOP",
    "KURTAPANTDUPPATA": "KURTA PANT DUPATTA", "KURTAPANTSDUPATTA": "KURTA PANT DUPATTA",
    "KURTAPANTDUPATTASET": "KURTA PANT DUPATTA",
    "DRESSES": "DRESS", "KAFTANS": "KAFTAN", "KURTAS": "KURTA",
})


def canon_category(v):
    v = str(v).strip()
    if not v:
        return ""
    return CATEGORY_ALIASES.get(norm_key(v), v.upper())


def build_raw(values):
    """Returns data rows (index = actual sheet row number) and the first data row number."""
    needed_width = col_to_idx("AX") + 1

    def is_row_no(v):
        t = str(v).strip()
        return bool(re.fullmatch(r"\d+(\.0+)?", t)) and float(t) > 0

    first = None
    for i, r in enumerate(values):
        if i < 2 or not r:          # row 1 = title, row 2 = totals row
            continue
        if is_row_no(r[0]) and len(r) > 1 and str(r[1]).strip():
            first = i
            break
    if first is None:
        first = next((i for i, r in enumerate(values) if i >= 2 and r and is_row_no(r[0])),
                     min(4, len(values)))

    rows = values[first:]
    if not rows:
        return pd.DataFrame(), first + 1
    width = max([len(r) for r in rows] + [needed_width])
    df = pd.DataFrame([list(r) + [""] * (width - len(r)) for r in rows],
                      index=range(first + 1, first + 1 + len(rows)))

    b = df[col_to_idx("B")].astype(str).str.strip()
    j_val = num(df[col_to_idx("J")])
    first_cells = df[[0, 1, 2]].apply(lambda c: c.map(norm_key))
    is_total_row = first_cells.isin(["TOTAL", "GRANDTOTAL"]).any(axis=1)
    keep = ((b != "") | (j_val != 0)) & ~is_total_row
    return df[keep], first + 1


def prepare(raw):
    def col(key):
        i = col_to_idx(MASTER_COLS[key])
        if i in raw.columns:
            return raw[i]
        return pd.Series([""] * len(raw), index=raw.index, dtype=object)

    d = pd.DataFrame(index=raw.index)
    d.index.name = "sheet_row"
    d["date_client"] = parse_dates(col("date_client"))
    d["date_prod"] = parse_dates(col("date_prod"))
    d["designer"] = clean_text(col("designer")).str.upper().replace("", "(NOT ASSIGNED)")

    t = clean_text(col("type")).str.upper()
    d["type_raw"] = t
    d["order_type"] = np.select(
        [t.eq("NEW"), t.eq("REPEAT"), t.str.contains("REPEAT"), t.str.contains("NEW")],
        ["NEW", "REPEAT", "REPEAT", "NEW"], default="OTHER")

    d["category"] = clean_text(col("category")).map(canon_category).replace("", "(NO CATEGORY)")
    d["qty"] = num(col("qty"))
    d["client"] = clean_text(col("client")).str.upper().replace("", "(NO CLIENT)")
    d["fabricator"] = clean_text(col("fabricator")).str.upper().replace("", "(NOT ASSIGNED)")
    d["delay"] = clean_delay_days(col("delay"))
    d["production"] = num(col("production"))
    d["received"] = num(col("received"))
    d["pending"] = num(col("pending"))
    d["status"] = clean_text(col("status")).str.upper().replace("", "(BLANK)")
    d["month"] = month_label(d["date_client"])
    return d


def month_list(d):
    """12 FY months always, plus any other month labels that actually carry data (e.g. (NO DATE))."""
    active = d[(d["qty"] != 0) | (d["production"] != 0)]
    extra = [m for m in active["month"].unique() if m not in FY_MONTH_LABELS]
    return FY_MONTH_LABELS + sorted(extra, key=month_sort_key)


def opt_list(d, col, known=(), first=()):
    present = {v for v in d[col].unique() if v}
    rest = sorted((present | set(known)) - set(first))
    return ["All"] + list(first) + rest


def filter_data(d, f):
    x = d
    for field in ["month", "designer", "client", "fabricator", "status", "category", "order_type"]:
        v = f.get(field, "All")
        if v != "All":
            x = x[x[field] == v]
    risk = f.get("risk", "All")
    if risk.startswith("Overdue"):
        x = x[x["delay"] > 0]
    elif risk.startswith("On-time"):
        x = x[x["delay"] <= 0]
    return x


def filter_row(spec, key_prefix):
    cols = st.columns(len(spec))
    out = {}
    for c, (field, label, options) in zip(cols, spec):
        out[field] = c.selectbox(label, options, key=f"{key_prefix}_{field}")
    return out


# --- KPI definitions: (display label, label used on the sheet dashboard, value, format) ---
def designer_kpis(x):
    return [
        ("TOTAL DESIGNS", "TOTAL DESIGNS", int((x["qty"] > 0).sum()), "int"),
        ("TOTAL QUANTITY (PCS)", "TOTAL QUANTITY (PCS)", x["qty"].sum(), "int"),
        ("NEW ORDER QTY", "NEW ORDER QTY", x.loc[x["order_type"] == "NEW", "qty"].sum(), "int"),
        ("REPEAT ORDER QTY", "REPEAT ORDER QTY", x.loc[x["order_type"] == "REPEAT", "qty"].sum(), "int"),
    ]


def client_kpis(x):
    return [
        ("TOTAL DESIGNS", "TOTAL DESIGNS", int((x["qty"] > 0).sum()), "int"),
        ("TOTAL QTY (PCS)", "TOTAL QTY (PCS)", x["qty"].sum(), "int"),
        ("IN PRODUCTION", "IN PRODUCTION", x["production"].sum(), "int"),
        ("RECEIVED / DONE", "RECEIVED / DONE", x["received"].sum(), "int"),
        ("TOTAL PENDING QTY", "TOTAL PENDING QTY", x["pending"].sum(), "int"),
        ("REPEAT ORDERS (PCS)", "REPEAT ORDERS (PCS)", x.loc[x["order_type"] == "REPEAT", "qty"].sum(), "int"),
        ("NEW ORDERS (PCS)", "NEW ORDERS (PCS)", x.loc[x["order_type"] == "NEW", "qty"].sum(), "int"),
        ("CATEGORY TOTAL (PCS)", "CATEGORY TOTAL (PCS)", x.loc[x["category"].isin(CATEGORIES_LIST), "qty"].sum(), "int"),
    ]


def production_kpis(x):
    base = x[x["production"] > 0]                 # an "order" = a design that is in production
    overdue = base[base["delay"] > 0]
    ontime = base[base["delay"] <= 0]
    n = len(base)
    return [
        ("TOTAL DESIGN", "TOTAL DESIGN", n, "orders"),
        ("INPRODUCTION PCS (AS)", "INPRODUCTION PCS (AS)", x["production"].sum(), "pcs"),
        ("RECEIVED PCS (AT)", "RECIEVED PCS (AT)", x["received"].sum(), "pcs"),
        ("PENDING PCS (AU)", "PENDING PCS (AU)", x["pending"].sum(), "pcs"),
        ("OVERDUE PCS (AH > 0)", "OVERDUE PCS (AH > 0)", overdue["production"].sum(), "pcs"),
        ("AVG OVERDUE DAYS", "AVG OVERDUE DAYS", overdue["delay"].mean() if len(overdue) else 0.0, "days"),
        ("ON-TIME DELIVERY %", "ON-TIME DELIVERY %", (len(ontime) / n * 100) if n else 0.0, "pct"),
        ("ON-TIME PCS (AH <= 0)", "ON-TIME PCS (AH <= 0)", ontime["production"].sum(), "pcs"),
    ]


# -----------------------------------------------------------------------------
# 5. MASTER SHEET – DASHBOARDS
# -----------------------------------------------------------------------------
def designer_dashboard(d_all, key):
    st.subheader("👨‍🎨 Executive Designer Performance & Category Tracking Dashboard")
    badge("🔎 Interactive Designer Dashboard Filters")
    f = filter_row([
        ("month", "Select Month", ["All"] + month_list(d_all)),
        ("designer", "Select Designer", opt_list(d_all, "designer", known=KNOWN_DESIGNERS)),
        ("order_type", "Order Type", opt_list(d_all, "order_type", first=("NEW", "REPEAT"))),
    ], f"{key}_des")
    x = filter_data(d_all, f)

    # Designer rows: fixed list (like the sheet) + any designer with volume
    if f["designer"] != "All":
        designers = [f["designer"]]
    else:
        with_vol = {v for v in d_all.loc[d_all["qty"] > 0, "designer"].unique()}
        designers = sorted((set(KNOWN_DESIGNERS) | with_vol) - {"(NOT ASSIGNED)"})
        if "(NOT ASSIGNED)" in with_vol:
            designers.append("(NOT ASSIGNED)")

    total_qty = x["qty"].sum()
    rows = []
    for des in designers:
        sub = x[x["designer"] == des]
        vol = sub["qty"].sum()
        rows.append({
            "Designer Name": des,
            "New Orders (Pcs)": sub.loc[sub["order_type"] == "NEW", "qty"].sum(),
            "Repeat Orders (Pcs)": sub.loc[sub["order_type"] == "REPEAT", "qty"].sum(),
            "Total Volume (Pcs)": vol,
            "Share %": (vol / total_qty * 100) if total_qty else 0.0,
            "Total Design Count": int((sub["qty"] > 0).sum()),
        })
    g = pd.DataFrame(rows, columns=["Designer Name", "New Orders (Pcs)", "Repeat Orders (Pcs)",
                                    "Total Volume (Pcs)", "Share %", "Total Design Count"])

    kpis = designer_kpis(x)
    if not g.empty and g["Total Volume (Pcs)"].max() > 0:
        top = g.loc[g["Total Volume (Pcs)"].idxmax()]
        top_txt = f"{top['Designer Name']} ({fmt(top['Total Volume (Pcs)'])} Pcs)"
    else:
        top_txt = "—"
    metrics([(k[0], fmt_kpi(k[2], k[3])) for k in kpis] + [("TOP PERFORMER", top_txt)])

    st.markdown("---")
    badge("📊 Designer Volume & Share Breakdown")
    c1, c2 = st.columns([1.2, 1])
    with c1:
        show_table(add_total(g, "Designer Name"), pct_cols=("Share %",))
    with c2:
        melted = g.melt(id_vars="Designer Name", value_vars=["New Orders (Pcs)", "Repeat Orders (Pcs)"],
                        var_name="Order Type", value_name="Qty")
        fig = px.bar(melted, x="Designer Name", y="Qty", color="Order Type", barmode="group",
                     title="DESIGNER PERFORMANCE: NEW vs REPEAT ORDERS (PCS)",
                     color_discrete_sequence=["#059669", "#7C3AED"])
        fig.update_xaxes(title="", tickangle=-35)
        st.plotly_chart(style_fig(fig, 380), **STRETCH)

    st.markdown("---")
    badge("🧩 Category Wise Designer Breakdown (Pcs)")
    pv = x.groupby(["designer", "category"])["qty"].sum().unstack(fill_value=0)
    other_cats = [c for c in pv.columns if c not in CATEGORIES_LIST and pv[c].sum() != 0]
    cats = CATEGORIES_LIST + other_cats
    pv = pv.reindex(index=designers, columns=cats, fill_value=0)
    pv["TOTAL"] = pv[cats].sum(axis=1)
    cat_df = pv.reset_index().rename(columns={"designer": "Designer", "index": "Designer"})
    cat_df.columns = ["Designer"] + list(cat_df.columns[1:])

    c3, c4 = st.columns([1.25, 1])
    with c3:
        show_table(add_total(cat_df, "Designer"))
    with c4:
        months = month_list(d_all)
        trend = x[x["qty"] != 0].groupby(["month", "designer"], as_index=False)["qty"].sum()
        if not trend.empty:
            fig = px.bar(trend, x="month", y="qty", color="designer",
                         title="MONTHLY DESIGNER PERFORMANCE TREND (PCS)",
                         category_orders={"month": months},
                         labels={"month": "Month", "qty": "Pcs", "designer": "Designer"})
            fig.update_layout(barmode="stack")
            fig.update_xaxes(tickangle=-35)
            st.plotly_chart(style_fig(fig, 380), **STRETCH)
        else:
            st.info("Selected filters ke liye monthly data nahi hai.")


def client_dashboard(d_all, key):
    st.subheader("🏢 Executive Client Performance Dashboard")
    badge("🔎 Interactive Client Dashboard Filters")
    f = filter_row([
        ("month", "Month", ["All"] + month_list(d_all)),
        ("client", "Client Name", opt_list(d_all, "client")),
        ("order_type", "Order Type", opt_list(d_all, "order_type", first=("NEW", "REPEAT"))),
        ("category", "Category", opt_list(d_all, "category", first=tuple(CATEGORIES_LIST))),
    ], f"{key}_cli")
    x = filter_data(d_all, f)

    render_kpis(client_kpis(x), per_row=4)

    st.markdown("---")
    months = month_list(d_all)
    badge("📅 Client Fulfillment Breakdown (Monthly)")
    m = x.groupby("month")[["qty", "production", "received", "pending"]].sum().reindex(months, fill_value=0)
    m = m.reset_index().rename(columns={"index": "MONTH", "month": "MONTH", "qty": "ORDER QTY",
                                        "production": "IN PRODUCTION", "received": "RECEIVED",
                                        "pending": "PENDING"})
    m.columns = ["MONTH", "ORDER QTY", "IN PRODUCTION", "RECEIVED", "PENDING"]

    c1, c2, c3 = st.columns([1.25, 1, 1])
    with c1:
        show_table(add_total(m, "MONTH"), height=500)
    with c2:
        pie_df = m[m["ORDER QTY"] > 0]
        if not pie_df.empty:
            fig = px.pie(pie_df, names="MONTH", values="ORDER QTY", title="CLIENT MONTHLY ORDER TREND (PCS)",
                         category_orders={"MONTH": months})
            fig.update_traces(textposition="inside", textinfo="percent+label")
            st.plotly_chart(style_fig(fig, 420), **STRETCH)
        else:
            st.info("Selected filters ke liye order data nahi hai.")
    with c3:
        rec, pen = x["received"].sum(), x["pending"].sum()
        if rec + pen > 0:
            q = pd.DataFrame({"Status": ["RECEIVED QTY", "PENDING QTY"], "Qty": [rec, pen]})
            fig = px.pie(q, names="Status", values="Qty", hole=.45,
                         title="ORDER FULFILLMENT RATIO (RECEIVED vs PENDING)",
                         color="Status", color_discrete_map={"RECEIVED QTY": "#dc2626", "PENDING QTY": "#f59e0b"})
            st.plotly_chart(style_fig(fig, 420), **STRETCH)
        else:
            st.info("Received / pending data nahi hai.")

    st.markdown("---")
    badge("🧩 Category Wise Order Breakdown (Pcs)")
    pv = x.groupby(["month", "category"])["qty"].sum().unstack(fill_value=0)
    other_cats = [c for c in pv.columns if c not in CATEGORIES_LIST and pv[c].sum() != 0]
    cats = CATEGORIES_LIST + other_cats
    pv = pv.reindex(index=months, columns=cats, fill_value=0)
    pv["TOTAL"] = pv[cats].sum(axis=1)
    cat_df = pv.reset_index()
    cat_df.columns = ["MONTH"] + list(cat_df.columns[1:])

    c4, c5 = st.columns([1.35, 1])
    with c4:
        show_table(add_total(cat_df, "MONTH"), height=500)
    with c5:
        long = cat_df.melt(id_vars="MONTH", value_vars=cats, var_name="Category", value_name="Pcs")
        long = long[long["Pcs"] != 0]
        if not long.empty:
            fig = px.bar(long, x="MONTH", y="Pcs", color="Category", title="CATEGORY DISTRIBUTION BY MONTH",
                         category_orders={"MONTH": months, "Category": cats})
            fig.update_layout(barmode="stack")
            fig.update_xaxes(tickangle=-35, title="")
            st.plotly_chart(style_fig(fig, 460), **STRETCH)
        else:
            st.info("Selected filters ke liye category data nahi hai.")


def production_dashboard(d_all, key):
    st.subheader("🏭 Production Executive Process Dashboard")
    badge("🔎 Interactive Dashboard Filters")
    f = filter_row([
        ("month", "Month", ["All"] + month_list(d_all)),
        ("fabricator", "Fabricator", opt_list(d_all, "fabricator")),
        ("status", "Status", opt_list(d_all, "status")),
        ("category", "Category", opt_list(d_all, "category", first=tuple(CATEGORIES_LIST))),
        ("designer", "Designer", opt_list(d_all, "designer", known=KNOWN_DESIGNERS)),
        ("risk", "Delay Risk", ["All", "Overdue (>0 days)", "On-time (≤0 days)"]),
    ], f"{key}_prod")
    x = filter_data(d_all, f)

    badge("📊 Process Key Performance Indicators")
    render_kpis(production_kpis(x), per_row=4)

    st.markdown("---")
    badge("📊 Category-wise Production Performance Breakdown")
    cat = x.groupby("category")[["production", "received", "pending"]].sum()
    other_cats = [c for c in cat.index if c not in CATEGORIES_LIST and cat.loc[c].abs().sum() != 0]
    cat = cat.reindex(CATEGORIES_LIST + other_cats, fill_value=0).reset_index()
    cat.columns = ["CATEGORY", "IN-PRODUCTION (AS)", "RECEIVED (AT)", "PENDING (AU)"]

    c1, c2 = st.columns([1, 1.35])
    with c1:
        show_table(add_total(cat, "CATEGORY"))
    with c2:
        chart_df = cat.melt(id_vars="CATEGORY", value_vars=["IN-PRODUCTION (AS)", "RECEIVED (AT)", "PENDING (AU)"],
                            var_name="Metric", value_name="PCS")
        fig = px.bar(chart_df, x="CATEGORY", y="PCS", color="Metric", barmode="group",
                     title="CATEGORY-WISE VOLUME COMPARISON",
                     color_discrete_sequence=["#2563eb", "#ef4444", "#f59e0b"])
        fig.update_xaxes(tickangle=-35, title="")
        st.plotly_chart(style_fig(fig, 360), **STRETCH)

    badge("🧵 Fabricator Pending PCS Share")
    fab = x.groupby("fabricator", as_index=False)["pending"].sum()
    fab = fab[fab["pending"] > 0].sort_values("pending", ascending=False)
    if not fab.empty:
        f1, f2 = st.columns([1.35, 1])
        with f1:
            fig = px.pie(fab, names="fabricator", values="pending", hole=0.48, title="FABRICATOR PENDING PCS SHARE")
            fig.update_traces(textposition="inside", textinfo="percent")
            st.plotly_chart(style_fig(fig, 360), **STRETCH)
        with f2:
            tbl = fab.rename(columns={"fabricator": "FABRICATOR", "pending": "PENDING PCS"})
            tbl["SHARE %"] = tbl["PENDING PCS"] / tbl["PENDING PCS"].sum() * 100
            show_table(add_total(tbl, "FABRICATOR"), pct_cols=("SHARE %",))
    else:
        st.info("Selected filters ke liye fabricator pending data nahi hai.")

    badge("📅 Monthly Fulfillment Trend")
    months = month_list(d_all)
    grp = x.groupby("month")
    mdf = pd.DataFrame({
        "ORDERS": grp["production"].apply(lambda s: int((s > 0).sum())),
        "IN-PRODUCTION (AS)": grp["production"].sum(),
        "RECEIVED (AT)": grp["received"].sum(),
        "PENDING (AU)": grp["pending"].sum(),
    }).reindex(months, fill_value=0).reset_index()
    mdf.columns = ["MONTH", "ORDERS", "IN-PRODUCTION (AS)", "RECEIVED (AT)", "PENDING (AU)"]

    m1, m2 = st.columns([1, 1.35])
    with m1:
        show_table(add_total(mdf, "MONTH"), height=500)
    with m2:
        line_df = mdf.melt(id_vars="MONTH", value_vars=["IN-PRODUCTION (AS)", "RECEIVED (AT)", "PENDING (AU)"],
                           var_name="Metric", value_name="PCS")
        fig = px.line(line_df, x="MONTH", y="PCS", color="Metric", markers=True,
                      title="MONTHLY FULFILLMENT TREND ANALYSIS",
                      category_orders={"MONTH": months},
                      color_discrete_sequence=["#ef4444", "#f59e0b", "#2563eb"])
        fig.update_xaxes(tickangle=-35, title="")
        st.plotly_chart(style_fig(fig, 460), **STRETCH)


# -----------------------------------------------------------------------------
# 6. MASTER SHEET – DATA CHECK (app vs sheet)
# -----------------------------------------------------------------------------
def find_sheet_kpis(values, labels):
    """Finds each KPI label on a dashboard tab and reads the value in the row below it."""
    wanted = {norm_key(lbl) for lbl in labels}
    out = {}
    for r, row in enumerate(values):
        for c, cell in enumerate(row):
            k = norm_key(cell)
            if k in wanted and k not in out and r + 1 < len(values):
                nxt = values[r + 1]
                for cc in range(c, min(c + 3, len(nxt))):
                    if str(nxt[cc]).strip():
                        out[k] = float(num(pd.Series([nxt[cc]])).iloc[0])
                        break
    return out


def compare_block(sheet_id, tabs, tab_name, kpis, max_rows=None):
    tab = find_tab(tabs, tab_name)
    if not tab:
        st.caption(f"Tab '{tab_name}' sheet me nahi mila.")
        return
    try:
        vals = load_tab_formatted(sheet_id, tab)
    except Exception as e:
        st.caption(f"'{tab_name}' read nahi ho paya: {e}")
        return
    found = find_sheet_kpis(vals[:max_rows] if max_rows else vals, [k[1] for k in kpis])
    rows = []
    for label, sheet_label, value, kind in kpis:
        sv = found.get(norm_key(sheet_label))
        tol = 0.06 if kind in ("pct", "days") else 0.5
        if sv is None:
            status, diff = "⚠️ label not found", np.nan
        else:
            diff = float(value) - sv
            status = "✅ match" if abs(diff) <= tol else "❌ mismatch"
        rows.append({"KPI": label, "Sheet dashboard": sv if sv is not None else np.nan,
                     "Streamlit app": float(value), "Diff": diff, "Status": status})
    df = pd.DataFrame(rows)
    st.dataframe(df.style.format({"Sheet dashboard": "{:,.1f}", "Streamlit app": "{:,.1f}", "Diff": "{:,.1f}"}),
                 **STRETCH, hide_index=True)


def data_check(sheet_id, cfg, tabs, src_tab, first_row, totals_row, d_all):
    st.subheader("✅ Data Check – Streamlit vs Google Sheet")
    st.caption(f"Source tab: **{src_tab}** · data from sheet row {first_row} · {len(d_all):,} rows loaded "
               f"· {int((d_all['qty'] > 0).sum()):,} designs with qty > 0")

    badge("1 · Sheet dashboard tabs vs app (all filters = ALL)")
    st.caption("Sheet dashboard ke dropdown filters ALL par hone chahiye, warna numbers alag dikhenge.")
    dash = cfg.get("dashboard_tabs", {})
    st.markdown("**Client Dashboard**")
    compare_block(sheet_id, tabs, dash.get("client", "CLIENT DASHBOARD"), client_kpis(d_all))
    st.markdown("**Production Process Dashboard**")
    compare_block(sheet_id, tabs, dash.get("production", "PRODUCTION PROCESS DASHBOARD"), production_kpis(d_all))
    st.markdown("**Designer Dashboard**")
    compare_block(sheet_id, tabs, dash.get("designer", "DESIGNER DASHBOARD"), designer_kpis(d_all))

    badge("2 · Source tab row-2 totals vs app")
    items = [("Total Qty (J)", "J", d_all["qty"].sum()),
             ("In Production (AS)", "AS", d_all["production"].sum()),
             ("Received (AT)", "AT", d_all["received"].sum()),
             ("Pending (AU)", "AU", d_all["pending"].sum())]
    rows = []
    for label, letter, mine in items:
        idx = col_to_idx(letter)
        cell = totals_row[idx] if idx < len(totals_row) else ""
        sheet_val = float(num(pd.Series([cell])).iloc[0])
        rows.append({"Column": label, "Sheet row-2 total": sheet_val, "Dashboard": float(mine),
                     "Diff": float(mine) - sheet_val})
    st.dataframe(pd.DataFrame(rows).style.format({"Sheet row-2 total": "{:,.0f}", "Dashboard": "{:,.0f}",
                                                  "Diff": "{:,.0f}"}),
                 **STRETCH, hide_index=True)

    badge("3 · Data quality notes")
    notes = []
    active = d_all[d_all["qty"] != 0]
    no_date = active[active["month"] == "(NO DATE)"]
    if len(no_date):
        notes.append(f"{len(no_date)} rows with qty but no valid order date in column B "
                     f"({fmt(no_date['qty'].sum())} pcs) – rows: {', '.join(map(str, no_date.index[:25]))}")
    out_fy = active[(active["month"] != "(NO DATE)") & ~active["month"].isin(FY_MONTH_LABELS)]
    if len(out_fy):
        notes.append(f"{len(out_fy)} rows dated outside FY {FY_START_YEAR}-{(FY_START_YEAR + 1) % 100:02d} "
                     f"({fmt(out_fy['qty'].sum())} pcs) – months: {', '.join(sorted(out_fy['month'].unique(), key=month_sort_key))}")
    unk = active[~active["category"].isin(CATEGORIES_LIST)]
    if len(unk):
        notes.append(f"{len(unk)} rows with a category outside the 7 standard ones "
                     f"({fmt(unk['qty'].sum())} pcs): {', '.join(sorted(unk['category'].unique()))}")
    oth = active[active["order_type"] == "OTHER"]
    if len(oth):
        notes.append(f"{len(oth)} rows where column D is neither NEW nor REPEAT ({fmt(oth['qty'].sum())} pcs)")
    nod = active[active["designer"] == "(NOT ASSIGNED)"]
    if len(nod):
        notes.append(f"{len(nod)} rows with blank designer ({fmt(nod['qty'].sum())} pcs)")
    if notes:
        for n in notes:
            st.warning(n)
    else:
        st.success("Koi data quality issue nahi mila.")

    with st.expander("🔍 Parsed rows (first 300)"):
        st.dataframe(d_all.head(300).reset_index(), **STRETCH, hide_index=True)


def render_tracker(sheet_name, cfg):
    sheet_id = cfg["id"]
    tabs = list_tabs(sheet_id)
    if not tabs:
        st.error("Sheet me koi tab nahi mila.")
        st.stop()

    default = None
    for cand in cfg.get("source_tabs", []):
        default = find_tab(tabs, cand)
        if default:
            break
    if default is None:
        default = next((t for t in tabs if "DASHBOARD" not in t.upper()), tabs[0])

    with st.sidebar:
        st.markdown("### 📄 Master Data Source")
        src_tab = st.selectbox("Data tab", tabs, index=tabs.index(default), key=f"{sheet_id}_src_tab",
                               help="Jis tab se dashboards bante hain (order data). Data Check tab se verify karein.")
        if st.button("🔄 Refresh Data", key=f"{sheet_id}_ref"):
            st.cache_data.clear()
            st.rerun()

    values = load_tab_raw(sheet_id, src_tab)
    if not values:
        st.error(f"Tab '{src_tab}' empty hai.")
        st.stop()

    raw, first_row = build_raw(values)
    if raw.empty:
        st.error(f"Tab '{src_tab}' me data rows nahi mile (column A me serial number aur column B me date expected hai).")
        st.stop()
    totals_row = values[1] if len(values) > 1 else []
    d_all = prepare(raw)

    st.markdown(
        f"""<div class="dashboard-hero"><h2>📊 {html.escape(sheet_name)} · Executive Dashboard 2026-27</h2>
        <p>Source Tab: <b>{html.escape(src_tab)}</b> · {len(d_all):,} rows (data from sheet row {first_row}) · data re-syncs from the sheet every {LIVE_TTL} sec</p></div>""",
        unsafe_allow_html=True,
    )

    key = sheet_id[:8]
    t1, t2, t3, t4 = st.tabs(["👨‍🎨 Designer Dashboard", "🏭 Production Process Dashboard",
                              "🏢 Client Dashboard", "✅ Data Check"])
    with t1:
        designer_dashboard(d_all, key)
    with t2:
        production_dashboard(d_all, key)
    with t3:
        client_dashboard(d_all, key)
    with t4:
        data_check(sheet_id, cfg, tabs, src_tab, first_row, totals_row, d_all)


# -----------------------------------------------------------------------------
# 7. SHARED HELPERS FOR "SAMPLE" & "FABRICATOR" DASHBOARDS
# -----------------------------------------------------------------------------
try:
    from zoneinfo import ZoneInfo
except Exception:  # pragma: no cover
    ZoneInfo = None

APP_TZ = "Asia/Kolkata"


def now_label():
    try:
        return datetime.now(ZoneInfo(APP_TZ)).strftime("%d %b %Y, %I:%M:%S %p")
    except Exception:
        return datetime.now(timezone.utc).strftime("%d %b %Y, %H:%M:%S UTC")


def idx_to_col(i):
    s, i = "", i + 1
    while i:
        i, r = divmod(i - 1, 26)
        s = chr(65 + r) + s
    return s


def to_num(v):
    """Single cell -> float (numbers stay numbers, '1,234' / '(50)' / '12%' are cleaned, junk -> 0)."""
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        return float(v)
    return float(num(pd.Series([v])).iloc[0])


def _is_number_text(v):
    return bool(re.fullmatch(r"[-+]?(\d[\d,]*\.?\d*|\.\d+)", str(v).strip()))


@st.cache_data(ttl=LIVE_TTL, show_spinner=False)
def list_tabs_meta(sheet_id):
    return [(ws.title, ws.id) for ws in _open_book(sheet_id).worksheets()]


@st.cache_data(ttl=LIVE_TTL, show_spinner="Google Sheet se live data load ho raha hai...")
def fetch_grid(sheet_id, tab_title, formatted=False):
    """Whole tab as a grid.
    formatted=False -> real values (numbers = numbers, dates = serial numbers) -> used for calculations
    formatted=True  -> text exactly as shown in the sheet -> used only to locate titles/headers."""
    book = _open_book(sheet_id)
    params = None if formatted else {"valueRenderOption": "UNFORMATTED_VALUE",
                                     "dateTimeRenderOption": "SERIAL_NUMBER"}
    resp = book.values_get(_a1_tab(tab_title), params=params)
    return {"values": resp.get("values", []), "synced": now_label()}


def pick_default_tab(meta, names, gid=None, name_regex=None):
    titles = [t for t, _ in meta]
    for n in names:
        t = find_tab(titles, n)
        if t:
            return t
    if name_regex:
        for t in titles:
            if re.search(name_regex, t, re.I):
                return t
    if gid is not None:
        for t, g in meta:
            if str(g) == str(gid):
                return t
    for t in titles:
        if "DASHBOARD" not in t.upper():
            return t
    return titles[0]


def sidebar_source_picker(cfg, key, name_regex=None):
    meta = list_tabs_meta(cfg["id"])
    if not meta:
        st.error("Sheet me koi tab nahi mila.")
        return None
    titles = [t for t, _ in meta]
    default = pick_default_tab(meta, cfg.get("source_tabs", []), cfg.get("gid"), name_regex)
    with st.sidebar:
        st.markdown("### 📄 Data Source")
        tab = st.selectbox("Data tab", titles, index=titles.index(default), key=key,
                           help="Jis tab se dashboard banta hai. Galat tab dikhe to yahan se badlein.")
        if st.button("🔄 Refresh data now", key=f"{key}_refresh"):
            st.cache_data.clear()
            st.rerun()
    return tab


def run_live(render_fn, *args):
    """Runs the dashboard; if auto-refresh is ON it re-runs by itself (Streamlit fragments)."""
    secs = st.session_state.get("live_secs", 0)
    runner = render_fn
    if secs and hasattr(st, "fragment"):
        try:
            runner = st.fragment(run_every=int(secs))(render_fn)
        except Exception:
            runner = render_fn
    runner(*args)


def hero(icon, title, subtitle_html, synced):
    st.markdown(
        f"""<div class="dashboard-hero"><h2>{icon} {html.escape(title)}</h2>
        <p>{subtitle_html} · <span style="background:var(--chip-bg);padding:2px 9px;border-radius:20px;font-size:.78rem;font-weight:650;">
        🕒 Synced {html.escape(synced)}</span></p></div>""",
        unsafe_allow_html=True,
    )


def multi(container, label, options, key, placeholder="All"):
    """Multiselect where 'nothing selected' = ALL. Drops stale selections safely."""
    options = list(options)
    st.session_state[key] = [v for v in st.session_state.get(key, []) if v in options]
    try:
        return container.multiselect(label, options, key=key, placeholder=placeholder)
    except TypeError:
        return container.multiselect(label, options, key=key)


def _reset_filters(defaults):
    for k, v in defaults.items():
        st.session_state[k] = v


def with_total(df, label_col, pct=None, label="TOTAL"):
    """Appends a TOTAL row. pct=(pct_col, numerator_col, denominator_col) is recomputed, never summed."""
    if df.empty:
        return df
    skip = {label_col} | ({pct[0]} if pct else set())
    row = {label_col: label}
    for c in df.columns:
        if c not in skip and pd.api.types.is_numeric_dtype(df[c]):
            row[c] = df[c].sum()
    if pct:
        den = row.get(pct[2], 0)
        row[pct[0]] = (row.get(pct[1], 0) / den * 100) if den else 0.0
    return pd.concat([df, pd.DataFrame([row])], ignore_index=True)


def table_with_download(df, name, **kw):
    show_table(df, **kw)
    st.download_button("⬇️ Download CSV", df.to_csv(index=False).encode("utf-8-sig"),
                       file_name=f"{name}.csv", mime="text/csv", key=f"dl_{name}")


def safe_div_pct(a, b):
    return (a / b * 100) if b else 0.0


# -----------------------------------------------------------------------------
# 8. SAMPLE SUMMARY DASHBOARD  (mirrors the "SAMPLE DASHBOARD" Apps Script)
#    Source tab columns:  B = Vendor | F = Qty | H = Process Date | L = Status | N = Designer
#    Row 1 = header, data from row 2.
# -----------------------------------------------------------------------------
SAMPLE_STATUSES = ["Approved", "Rejected", "On Hold", "In Process", "Other"]
SAMPLE_COLORS = {"Approved": "#059669", "Rejected": "#dc2626", "On Hold": "#f59e0b",
                 "In Process": "#2563eb", "Other": "#94a3b8"}
SAMPLE_COLS = {"vendor": "B", "qty": "F", "date": "H", "status": "L", "designer": "N"}
FY_MONTH_NOS = [4, 5, 6, 7, 8, 9, 10, 11, 12, 1, 2, 3]
MONTHNO_TO_LABEL = dict(zip(FY_MONTH_NOS, FY_MONTH_LABELS))
MON3 = ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"]


def _month_from_text(t):
    t = re.sub(r"[ .,\-]+", "/", str(t).strip().lower())
    for pat in (r"^\d{1,2}/(\d{1,2})/\d{2,4}$",      # dd/mm/yyyy
                r"^(\d{1,2})/\d{4}$",                  # mm/yyyy
                r"^\d{4}/(\d{1,2})/\d{1,2}$"):         # yyyy/mm/dd
        m = re.match(pat, t)
        if m:
            return int(m.group(1))
    m = re.search(r"(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)", t)   # "Apr-26", "April 2026"
    return MON3.index(m.group(1)) + 1 if m else 0


def month_numbers(s):
    """Process-date column -> month number 1..12 (0 = blank / unreadable). Same rules as the sheet script."""
    s = pd.Series(s).fillna("")
    out = pd.Series(0, index=s.index, dtype="int64")
    numeric = pd.to_numeric(s, errors="coerce")
    isnum = numeric.notna() & numeric.between(1, 100000)
    if isnum.any():
        dts = pd.to_datetime(numeric[isnum].astype(float), unit="D", origin="1899-12-30", errors="coerce")
        out.loc[isnum] = dts.dt.month.fillna(0).astype("int64").to_numpy()
    txt = (~isnum) & numeric.isna() & s.astype(str).str.strip().ne("")
    if txt.any():
        out.loc[txt] = s[txt].map(_month_from_text).astype("int64").to_numpy()
    return out.where(out.between(1, 12), 0)


def classify_status(s):
    t = clean_text(s).str.upper()
    vals = np.select(
        [t.eq(""), t.str.contains("REJECT"), t.str.contains("APPROV"), t.str.contains("HOLD"), t.str.contains("PROCESS")],
        ["Other", "Rejected", "Approved", "On Hold", "In Process"], default="Other")
    return pd.Series(vals, index=t.index)


def canon_series(raw, skip_words):
    """Case-insensitive name cleanup: 'abc' / 'ABC ' -> one spelling. Blank -> (BLANK), numbers/headers -> (OTHER)."""
    skip = {w.upper() for w in skip_words}
    mapping = {}
    for v in raw:
        if v and not _is_number_text(v) and v.upper() not in skip:
            mapping.setdefault(v.upper(), v)
    return raw.map(lambda v: mapping.get(v.upper(), "(BLANK)" if v == "" else "(OTHER)"))


def build_samples(values):
    if len(values) < 2:
        return pd.DataFrame(), []
    header = list(values[0])
    rows = values[1:]
    width = max([len(r) for r in rows] + [col_to_idx("N") + 1])
    df = pd.DataFrame([list(r) + [""] * (width - len(r)) for r in rows], index=range(2, 2 + len(rows)))

    def col(key):
        return df[col_to_idx(SAMPLE_COLS[key])]

    d = pd.DataFrame(index=df.index)
    d.index.name = "sheet_row"
    d["qty"] = num(col("qty"))
    vendor_raw, designer_raw = clean_text(col("vendor")), clean_text(col("designer"))
    status_raw = clean_text(col("status"))
    d["vendor"] = canon_series(vendor_raw, ("VENDOR NAME", "VENDOR"))
    d["designer"] = canon_series(designer_raw, ("DESIGNER NAME", "DESIGNER"))
    d["month_no"] = month_numbers(col("date"))
    d["month"] = d["month_no"].map(MONTHNO_TO_LABEL).fillna("(NO DATE)")
    d["status"] = classify_status(col("status"))
    d["qty_raw"] = col("qty").astype(str).str.strip()
    d["date_raw"] = col("date").astype(str).str.strip()
    d["status_raw"] = status_raw
    keep = (vendor_raw != "") | (designer_raw != "") | (status_raw != "") | (d["qty"] != 0)
    return d[keep], header


def sample_filter(d, f, skip=()):
    x = d
    for field, col_name in (("month", "month"), ("designer", "designer"), ("status", "status"), ("vendor", "vendor")):
        if f.get(field) and field not in skip:
            x = x[x[col_name].isin(f[field])]
    return x


def status_table(x, group_col, index_values):
    if x.empty:
        p = pd.DataFrame(0.0, index=index_values, columns=SAMPLE_STATUSES)
    else:
        p = (x.groupby([group_col, "status"])["qty"].sum().unstack(fill_value=0)
             .reindex(index=index_values, columns=SAMPLE_STATUSES, fill_value=0).astype(float))
    p["Total"] = p[SAMPLE_STATUSES].sum(axis=1)
    p["Approval %"] = np.where(p["Total"] > 0, p["Approved"] / p["Total"].replace(0, np.nan) * 100, 0.0)
    return p


def sample_monthly(x):
    p = status_table(x, "month", FY_MONTH_LABELS + ["(NO DATE)"])
    if p.loc["(NO DATE)", "Total"] == 0:
        p = p.drop(index="(NO DATE)")
    p.index.name = "Month"
    return p.reset_index()


def sample_entity_table(x, group_col, names, label):
    p = status_table(x, group_col, list(names) + ["(BLANK)", "(OTHER)"])
    p = p[(p["Total"] != 0) | ~p.index.isin(["(BLANK)", "(OTHER)"])]
    p = p.sort_values("Total", ascending=False)
    p.index.name = label
    return p.reset_index()


def entity_chart(tbl, label, title):
    t = tbl[tbl["Total"] > 0].head(20)
    if t.empty:
        st.info("Selected filters ke liye data nahi hai.")
        return
    long = t.melt(id_vars=label, value_vars=SAMPLE_STATUSES, var_name="Status", value_name="Pcs")
    fig = px.bar(long, y=label, x="Pcs", color="Status", orientation="h", title=title,
                 color_discrete_map=SAMPLE_COLORS,
                 category_orders={label: list(t[label])[::-1], "Status": SAMPLE_STATUSES})
    fig.update_yaxes(title="")
    st.plotly_chart(style_fig(fig, max(320, 28 * len(t) + 120)), **STRETCH)


def render_sample_summary_dashboard(sheet_name, cfg):
    tab = sidebar_source_picker(cfg, f"{cfg['id']}_smp_tab")
    if tab:
        run_live(_sample_body, sheet_name, cfg, tab)


def _sample_body(sheet_name, cfg, tab):
    sheet_id = cfg["id"]
    pack = fetch_grid(sheet_id, tab)
    d, header = build_samples(pack["values"])
    hero("🔬", f"{sheet_name} · Sample Performance & Designer Dashboard",
         f"Source tab: <b>{html.escape(tab)}</b> · {len(d):,} rows · FY {FY_START_YEAR}-{(FY_START_YEAR + 1) % 100:02d}",
         pack["synced"])
    if d.empty:
        st.warning("Is tab me data nahi mila. Expected: row 1 = header, row 2 se data "
                   "(Vendor = B, Qty = F, Process Date = H, Status = L, Designer = N). "
                   "Sidebar se sahi 'Data tab' select karein.")
        return

    # header sanity check
    hints = {"vendor": "vendor", "qty": "qty|quant|sample", "date": "date", "status": "status", "designer": "designer"}
    hits = 0
    for k, pat in hints.items():
        i = col_to_idx(SAMPLE_COLS[k])
        if i < len(header) and re.search(pat, str(header[i]), re.I):
            hits += 1
    if hits < 2:
        st.warning("⚠️ Is tab ka header expected columns (B Vendor, F Qty, H Date, L Status, N Designer) se match nahi karta - "
                   "kya aapne sahi 'Data tab' select kiya hai? Details ke liye Data Check tab dekhein.")

    designer_names = [n for n in d["designer"].unique() if not n.startswith("(")]
    vendor_names = [n for n in d["vendor"].unique() if not n.startswith("(")]

    # ---------------- filters ----------------
    keys = {"month": "smp_month", "designer": "smp_designer", "status": "smp_status", "vendor": "smp_vendor"}
    with st.expander("🔎 Filters  (kuch select na karein = ALL)", expanded=True):
        c = st.columns([1.1, 1.2, 1.1, 1.2, 0.55])
        f = {
            "month": multi(c[0], "Month", FY_MONTH_LABELS, keys["month"], "All months"),
            "designer": multi(c[1], "Designer", designer_names, keys["designer"], "All designers"),
            "status": multi(c[2], "Status", SAMPLE_STATUSES, keys["status"], "All status"),
            "vendor": multi(c[3], "Vendor", vendor_names, keys["vendor"], "All vendors"),
        }
        c[4].markdown("<div style='height:1.7rem'></div>", unsafe_allow_html=True)
        c[4].button("↺ Reset", key="smp_reset", on_click=_reset_filters, args=({k: [] for k in keys.values()},))

    x = sample_filter(d, f)
    x_nd = sample_filter(d, f, skip=("designer",))     # designer comparison ignores the designer filter
    x_nv = sample_filter(d, f, skip=("vendor",))       # vendor comparison ignores the vendor filter

    # ---------------- KPIs ----------------
    by = x.groupby("status")["qty"].sum()
    tot = float(x["qty"].sum())
    app, rej, hld, prc, oth = (float(by.get(s, 0.0)) for s in SAMPLE_STATUSES)
    ratio = safe_div_pct(app, tot)

    des_tbl = sample_entity_table(x_nd, "designer", designer_names, "Designer")
    real = des_tbl[~des_tbl["Designer"].str.startswith("(")]
    if not real.empty and real["Approved"].max() > 0:
        top = real.loc[real["Approved"].idxmax()]
        top_txt = f"{top['Designer']} ({fmt(top['Approved'])} Pcs)"
    else:
        top_txt = "N/A"

    metrics([("Total Samples", f"{fmt(tot)} Pcs"), ("Approved", f"{fmt(app)} Pcs"), ("Rejected", f"{fmt(rej)} Pcs"),
             ("On Hold", f"{fmt(hld)} Pcs"), ("In Process", f"{fmt(prc)} Pcs"), ("Approval Ratio", f"{ratio:.1f}%")])
    metrics([("🏆 Top Performer (Approved)", top_txt), ("Rejection Rate", f"{safe_div_pct(rej, tot):.1f}%"),
             ("Open Pipeline (Hold + Process)", f"{fmt(hld + prc)} Pcs"), ("Other / Blank Status", f"{fmt(oth)} Pcs")])
    st.markdown("---")

    t_over, t_month, t_des, t_ven, t_chk = st.tabs(
        ["📊 Overview", "📅 Monthly Breakdown", "👩‍🎨 Designer Scorecard", "🏭 Vendor Scorecard", "✅ Data Check"])

    mt = sample_monthly(x)

    with t_over:
        if tot == 0:
            st.info("Selected filters ke liye koi sample data nahi hai.")
        else:
            c1, c2 = st.columns([1.55, 1])
            with c1:
                long = mt.melt(id_vars="Month", value_vars=SAMPLE_STATUSES, var_name="Status", value_name="Pcs")
                fig = px.bar(long, x="Month", y="Pcs", color="Status", barmode="stack",
                             title="MONTHLY SAMPLE STATUS DISTRIBUTION (PCS)", color_discrete_map=SAMPLE_COLORS,
                             category_orders={"Month": list(mt["Month"]), "Status": SAMPLE_STATUSES})
                fig.update_xaxes(tickangle=-35, title="")
                st.plotly_chart(style_fig(fig, 380), **STRETCH)
            with c2:
                share = pd.DataFrame({"Status": SAMPLE_STATUSES, "Pcs": [app, rej, hld, prc, oth]})
                share = share[share["Pcs"] > 0]
                fig = px.pie(share, names="Status", values="Pcs", hole=0.5, title="OVERALL SAMPLE STATUS SHARE",
                             color="Status", color_discrete_map=SAMPLE_COLORS)
                fig.update_traces(textinfo="percent+label", textposition="inside")
                st.plotly_chart(style_fig(fig, 380), **STRETCH)
            trend = mt.melt(id_vars="Month", value_vars=["Total", "Approved", "Rejected"], var_name="Series", value_name="Pcs")
            fig = px.line(trend, x="Month", y="Pcs", color="Series", markers=True,
                          title="MONTHLY PROCESS VOLUME TREND",
                          color_discrete_map={"Total": "#7c3aed", "Approved": "#059669", "Rejected": "#dc2626"},
                          category_orders={"Month": list(mt["Month"])})
            fig.update_xaxes(tickangle=-35, title="")
            st.plotly_chart(style_fig(fig, 340), **STRETCH)

    with t_month:
        badge("📅 Monthly Sample Breakdown (Process Date = column H)")
        shown = with_total(mt, "Month", pct=("Approval %", "Approved", "Total"))
        table_with_download(shown, "sample_monthly", pct_cols=("Approval %",), height=560)
        nd = mt.loc[mt["Month"] == "(NO DATE)", "Total"].sum()
        if nd > 0:
            st.warning(f"⚠ {fmt(nd)} samples ki Process Date (Col H) khaali ya unreadable hai - table me '(NO DATE)' row dekhein.")
        else:
            st.success("✅ Sab samples ki Process Date sahi padhi gayi.")

    with t_des:
        badge("👩‍🎨 Designer Performance Scorecard")
        st.caption("Designer filter yahan apply nahi hota taaki sab designers ki tulna ho sake; Month / Status / Vendor filter apply hote hain.")
        c1, c2 = st.columns([1.25, 1])
        with c1:
            table_with_download(with_total(des_tbl, "Designer", pct=("Approval %", "Approved", "Total")),
                                "sample_designer", pct_cols=("Approval %",), height=520)
        with c2:
            entity_chart(des_tbl, "Designer", "DESIGNER-WISE STATUS (PCS)")

    with t_ven:
        badge("🏭 Vendor Performance Scorecard")
        st.caption("Vendor filter yahan apply nahi hota taaki sab vendors ki tulna ho sake; Month / Status / Designer filter apply hote hain.")
        ven_tbl = sample_entity_table(x_nv, "vendor", vendor_names, "Vendor")
        c1, c2 = st.columns([1.25, 1])
        with c1:
            table_with_download(with_total(ven_tbl, "Vendor", pct=("Approval %", "Approved", "Total")),
                                "sample_vendor", pct_cols=("Approval %",), height=520)
        with c2:
            entity_chart(ven_tbl, "Vendor", "VENDOR-WISE STATUS (PCS)")

    with t_chk:
        _sample_data_check(sheet_id, cfg, tab, d, header)


def _sample_data_check(sheet_id, cfg, tab, d, header):
    st.subheader("✅ Data Check")
    st.caption(f"Tab **{tab}** · {len(d):,} data rows (row 2 se) · total qty **{fmt(d['qty'].sum())}** Pcs")

    badge("1 · Kaun sa column kis kaam me aa raha hai")
    rows = []
    for key, label in (("vendor", "Vendor"), ("qty", "Sample Qty"), ("date", "Process Date → Month"),
                       ("status", "Status → Approved/Rejected/Hold/In Process"), ("designer", "Designer")):
        letter = SAMPLE_COLS[key]
        i = col_to_idx(letter)
        rows.append({"Column": letter, "Used for": label, "Header in sheet": str(header[i]) if i < len(header) else "(missing)"})
    st.dataframe(pd.DataFrame(rows), **STRETCH, hide_index=True)

    badge("2 · Sheet ke apne SAMPLE DASHBOARD se match (sab filters = ALL)")
    by = d.groupby("status")["qty"].sum()
    tot = float(d["qty"].sum())
    kp = [("Total Samples Qty", "TOTAL SAMPLES QTY", tot, "pcs"),
          ("Approved", "APPROVED SAMPLES", float(by.get("Approved", 0)), "pcs"),
          ("Rejected", "REJECTED SAMPLES", float(by.get("Rejected", 0)), "pcs"),
          ("On Hold", "ON HOLD SAMPLES", float(by.get("On Hold", 0)), "pcs"),
          ("On Process", "ON PROCESS", float(by.get("In Process", 0)), "pcs"),
          ("Approval Ratio %", "APPROVAL RATIO %", safe_div_pct(float(by.get("Approved", 0)), tot), "pct")]
    compare_block(sheet_id, [t for t, _ in list_tabs_meta(sheet_id)], cfg.get("dashboard_tab", "SAMPLE DASHBOARD"), kp, max_rows=12)

    badge("3 · Data quality notes")
    notes = []
    active = d[d["qty"] != 0]
    nd = active[active["month_no"] == 0]
    if len(nd):
        notes.append(f"{len(nd)} rows me qty hai par Process Date (col H) khaali/unreadable hai ({fmt(nd['qty'].sum())} pcs) - "
                     f"sheet rows: {', '.join(map(str, nd.index[:25]))}")
    bad_q = d[(d["qty_raw"] != "") & (d["qty"] == 0) & ~d["qty_raw"].str.match(r"^[\s\-–0.,()]*$")]
    if len(bad_q):
        notes.append(f"{len(bad_q)} rows me Qty (col F) number nahi hai, isliye 0 gina gaya - rows: {', '.join(map(str, bad_q.index[:25]))}")
    oth = active[active["status"] == "Other"]
    if len(oth):
        notes.append(f"{len(oth)} rows ka Status (col L) blank ya unknown hai ({fmt(oth['qty'].sum())} pcs) - 'Other' me gine gaye")
    nbd = active[active["designer"].isin(["(BLANK)", "(OTHER)"])]
    if len(nbd):
        notes.append(f"{len(nbd)} rows me Designer (col N) blank hai ({fmt(nbd['qty'].sum())} pcs)")
    nbv = active[active["vendor"].isin(["(BLANK)", "(OTHER)"])]
    if len(nbv):
        notes.append(f"{len(nbv)} rows me Vendor (col B) blank hai ({fmt(nbv['qty'].sum())} pcs)")
    if notes:
        for n in notes:
            st.warning(n)
    else:
        st.success("Koi data quality issue nahi mila.")

    with st.expander("ℹ️ Numbers kaise calculate hote hain"):
        st.markdown(
            "- **Qty** = column F (text jaise `1,200` ya `(50)` bhi number me badal jata hai; number na bane to 0)\n"
            "- **Month** = Process Date (col H) ka mahina - serial date, `dd/mm/yyyy`, `mm/yyyy`, `yyyy/mm/dd` ya `Apr-26` jaise text, sab padhe jate hain\n"
            "- **Status** (col L): text me `REJECT` → Rejected, `APPROV` → Approved, `HOLD` → On Hold, `PROCESS` → In Process; blank/baaki → Other\n"
            "- **Approval %** = Approved ÷ Total (Total me Other bhi shamil)\n"
            "- Designer / Vendor naam capital-small ya extra space se alag nahi gine jate")
    with st.expander("🔍 Parsed rows (first 300)"):
        st.dataframe(d.head(300).reset_index(), **STRETCH, hide_index=True)


# -----------------------------------------------------------------------------
# 9. FABRICATOR DASHBOARD  (mirrors the "FABRICATOR DASHBOARD" Apps Script)
#    Source tab: MONTHWISE SUMMARY -> blocks titled "Position Of Stock <NAME>"
#    Each block: header row "Month", then 12 rows April..March, 5 value columns to the right of Month:
#    Fabric Issue (mtr) | Pcs Under Production | RCVD | Remaining | Monthly Incoming
# -----------------------------------------------------------------------------
FAB_METRICS = ["Fabric Issue (mtr)", "Pcs Under Production", "RCVD (Pcs)", "Remaining (Pcs)", "Monthly Incoming (Pcs)"]
FY_MONTH_SHORT = [m[:3] for m in MONTHS]


def detect_fab_blocks(disp):
    blocks, used = [], {}
    for r, row in enumerate(disp):
        for c, cell in enumerate(row):
            m = re.match(r"^position\s+of\s+stock\s*(.*)$", str(cell).strip(), re.I)
            if not m:
                continue
            hdr = -1
            for rr in range(r, min(r + 7, len(disp))):
                if c < len(disp[rr]) and re.fullmatch(r"month", str(disp[rr][c]).strip(), re.I):
                    hdr = rr
                    break
            if hdr < 0:
                continue
            first = -1
            for rr in range(hdr + 1, min(hdr + 7, len(disp))):
                if c < len(disp[rr]) and re.match(r"apr", str(disp[rr][c]).strip(), re.I):
                    first = rr
                    break
            if first < 0:
                continue
            raw = re.sub(r"[()]", "", m.group(1)).strip().upper()
            raw = re.sub(r"^[\s:\-–]+", "", raw).strip()
            is_all = bool(re.search(r"ALL\s*OVER", raw))
            name = "ALL OVER" if is_all else (raw or "BLOCK")
            if name in used:
                used[name] += 1
                name = f"{name} ({used[name]})"
            else:
                used[name] = 1
            blocks.append({"name": name, "is_all": is_all, "title_row": r, "first_row": first, "col": c,
                           "title": str(cell).strip()})
    return blocks


def _cell(grid, r, c):
    if r < len(grid) and c < len(grid[r]):
        return grid[r][c]
    return ""


def build_fab_data(disp, raw):
    blocks = detect_fab_blocks(disp)
    recs = []
    for b in blocks:
        for k in range(12):
            vals = [to_num(_cell(raw, b["first_row"] + k, b["col"] + f)) for f in range(1, 6)]
            rec = {"Fabricator": b["name"], "is_all": b["is_all"], "Month": FY_MONTH_LABELS[k]}
            rec.update(dict(zip(FAB_METRICS, vals)))
            recs.append(rec)
    return blocks, pd.DataFrame(recs)


def render_fabricator_dashboard(sheet_name, cfg):
    tab = sidebar_source_picker(cfg, f"{cfg['id']}_fab_tab", name_regex=r"monthwise|monthly\s*summary")
    if tab:
        run_live(_fab_body, sheet_name, cfg, tab)


def _fab_body(sheet_name, cfg, tab):
    sheet_id = cfg["id"]
    disp = fetch_grid(sheet_id, tab, True)["values"]
    pack = fetch_grid(sheet_id, tab)
    blocks, df = build_fab_data(disp, pack["values"])
    hero("🏭", f"{sheet_name} · Fabricator Stock Position Dashboard",
         f"Source tab: <b>{html.escape(tab)}</b> · {sum(not b['is_all'] for b in blocks)} fabricator block(s) · FY {FY_START_YEAR}-{(FY_START_YEAR + 1) % 100:02d}",
         pack["synced"])
    if df.empty:
        st.error("Is tab me 'Position Of Stock ...' wale tables nahi mile (title ke neeche 'Month' header aur 'April' se shuru "
                 "12 rows chahiye). Sidebar se sahi 'Data tab' select karein.")
        return

    all_over = df[df["is_all"]]
    fabs_df = df[~df["is_all"]]
    base = fabs_df if not fabs_df.empty else all_over
    fab_names = list(dict.fromkeys(base["Fabricator"]))

    # ---------------- filters ----------------
    keys = {"fab": "fab_names", "month": "fab_month"}
    default_metric = "RCVD (Pcs)"
    st.session_state.setdefault("fab_metric", default_metric)
    with st.expander("🔎 Filters  (kuch select na karein = ALL)", expanded=True):
        c = st.columns([1.4, 1.3, 1.1, 0.55])
        sel_fab = multi(c[0], "Fabricator", fab_names, keys["fab"], "All fabricators")
        sel_month = multi(c[1], "Month", FY_MONTH_LABELS, keys["month"], "All months")
        metric = c[2].selectbox("Matrix / Heatmap metric", FAB_METRICS, key="fab_metric")
        c[3].markdown("<div style='height:1.7rem'></div>", unsafe_allow_html=True)
        c[3].button("↺ Reset", key="fab_reset", on_click=_reset_filters,
                    args=({keys["fab"]: [], keys["month"]: [], "fab_metric": default_metric},))

    def flt(frame, fabs=True, months=True):
        y = frame
        if fabs and sel_fab:
            y = y[y["Fabricator"].isin(sel_fab)]
        if months and sel_month:
            y = y[y["Month"].isin(sel_month)]
        return y

    x = flt(base)                                  # KPIs, matrix
    x_by_month = flt(base, months=False)           # monthly table/charts ignore the month filter
    x_by_fab = flt(base, fabs=False)               # scorecard compares all fabricators
    ao_f = flt(all_over, fabs=False)

    # ---------------- KPIs ----------------
    tot = x[FAB_METRICS].sum()
    recv_pct = safe_div_pct(tot["RCVD (Pcs)"], tot["Pcs Under Production"])
    g = x.groupby("Fabricator")[FAB_METRICS].sum()

    def top_of(col):
        if len(g) and g[col].max() > 0:
            return f"{g[col].idxmax()} ({fmt(g[col].max())} Pcs)"
        return "N/A"

    metrics([("Fabric Issued", f"{tot['Fabric Issue (mtr)']:,.0f} mtr"),
             ("Pcs Under Production", f"{fmt(tot['Pcs Under Production'])} Pcs"),
             ("RCVD (Received)", f"{fmt(tot['RCVD (Pcs)'])} Pcs"),
             ("Remaining", f"{fmt(tot['Remaining (Pcs)'])} Pcs"),
             ("Monthly Incoming", f"{fmt(tot['Monthly Incoming (Pcs)'])} Pcs"),
             ("Received %", f"{recv_pct:.1f}%")])
    metrics([("🏆 Top Receiver", top_of("RCVD (Pcs)")), ("⚠ Most Pending", top_of("Remaining (Pcs)"))])
    st.markdown("---")

    # ---------------- tables ----------------
    mm = x_by_month.groupby("Month")[FAB_METRICS].sum().reindex(FY_MONTH_LABELS, fill_value=0).astype(float)
    mm["RCVD %"] = np.where(mm["Pcs Under Production"] > 0,
                            mm["RCVD (Pcs)"] / mm["Pcs Under Production"].replace(0, np.nan) * 100, 0.0)
    mm.index.name = "Month"
    monthly = mm.reset_index()

    sc = x_by_fab.groupby("Fabricator", sort=False)[FAB_METRICS].sum().astype(float)
    sc["RCVD %"] = np.where(sc["Pcs Under Production"] > 0,
                            sc["RCVD (Pcs)"] / sc["Pcs Under Production"].replace(0, np.nan) * 100, 0.0)
    sc.index.name = "Fabricator"
    score = sc.reset_index()

    t_over, t_fab, t_month, t_mat, t_chk = st.tabs(
        ["📊 Overview", "🏭 Fabricator Scorecard", "📅 Monthly Position", "🧮 Month × Fabricator", "✅ Data Check"])

    with t_over:
        if tot[FAB_METRICS].abs().sum() == 0:
            st.info("Selected filters ke liye koi data nahi hai.")
        c1, c2 = st.columns([1.35, 1])
        with c1:
            fig = go.Figure()
            for col_name, color in (("Pcs Under Production", "#2563eb"), ("RCVD (Pcs)", "#059669"), ("Remaining (Pcs)", "#dc2626")):
                fig.add_trace(go.Bar(name=col_name, x=FY_MONTH_LABELS, y=mm[col_name], marker_color=color))
            fig.update_layout(barmode="group", title="MONTHLY: PRODUCTION vs RCVD vs REMAINING (PCS)")
            fig.update_xaxes(tickangle=-35)
            st.plotly_chart(style_fig(fig, 380), **STRETCH)
        with c2:
            fig = go.Figure()
            fig.add_trace(go.Scatter(x=FY_MONTH_LABELS, y=mm["Fabric Issue (mtr)"], name="Fabric Issue (mtr)",
                                     mode="lines+markers", line=dict(color="#7c3aed")))
            fig.add_trace(go.Scatter(x=FY_MONTH_LABELS, y=mm["Monthly Incoming (Pcs)"], name="Monthly Incoming (Pcs)",
                                     mode="lines+markers", line=dict(color="#d97706"), yaxis="y2"))
            fig.update_layout(title="FABRIC ISSUE & MONTHLY INCOMING TREND",
                              yaxis=dict(title="Mtr"),
                              yaxis2=dict(title="Pcs", overlaying="y", side="right", showgrid=False))
            fig.update_xaxes(tickangle=-35)
            st.plotly_chart(style_fig(fig, 380), **STRETCH)
        c3, c4 = st.columns([1.35, 1])
        with c3:
            fig = go.Figure()
            order = score.sort_values("RCVD (Pcs)")
            fig.add_trace(go.Bar(name="RCVD", y=order["Fabricator"], x=order["RCVD (Pcs)"], orientation="h", marker_color="#059669"))
            fig.add_trace(go.Bar(name="Remaining", y=order["Fabricator"], x=order["Remaining (Pcs)"], orientation="h", marker_color="#dc2626"))
            fig.update_layout(barmode="stack", title="FABRICATOR WISE: RCVD vs REMAINING (PCS)")
            st.plotly_chart(style_fig(fig, max(320, 30 * len(order) + 120)), **STRETCH)
        with c4:
            order = score.sort_values("RCVD %")
            fig = px.bar(order, x="RCVD %", y="Fabricator", orientation="h", text_auto=".1f",
                         color="RCVD %", color_continuous_scale="RdYlGn", range_color=[0, 100],
                         title="FABRICATOR WISE: RECEIVED %")
            fig.update_layout(coloraxis_showscale=False)
            fig.update_yaxes(title="")
            st.plotly_chart(style_fig(fig, max(320, 30 * len(order) + 120)), **STRETCH)
        st.caption("Month filter sirf KPIs aur fabricator charts par lagta hai; Fabricator filter KPIs aur monthly charts par.")

    with t_fab:
        badge("🏭 Fabricator Scorecard")
        st.caption("Fabricator filter yahan apply nahi hota (sab ki tulna); Month filter apply hota hai.")
        shown = with_total(score, "Fabricator", pct=("RCVD %", "RCVD (Pcs)", "Pcs Under Production"))
        if not ao_f.empty:
            ao_sum = ao_f[FAB_METRICS].sum()
            ao_row = {"Fabricator": "ALL OVER (SHEET)", **{k: float(ao_sum[k]) for k in FAB_METRICS},
                      "RCVD %": safe_div_pct(ao_sum["RCVD (Pcs)"], ao_sum["Pcs Under Production"])}
            shown = pd.concat([shown, pd.DataFrame([ao_row])], ignore_index=True)
        table_with_download(shown, "fabricator_scorecard", pct_cols=("RCVD %",), dec_cols=("Fabric Issue (mtr)",), height=460)
        if not ao_f.empty:
            diff = float((score[FAB_METRICS].sum() - ao_f[FAB_METRICS].sum()).abs().sum())
            if diff < 1:
                st.success("✅ Fabricators ka total sheet ke ALL OVER table se match karta hai.")
            else:
                st.warning(f"⚠ Fabricators ka total ALL OVER table se alag hai (difference = {diff:,.0f}) - "
                           "koi fabricator table summary me missing ho sakta hai.")
        else:
            st.info("ℹ Sheet me ALL OVER table nahi mila, isliye cross-check nahi ho paya.")

    with t_month:
        badge("📅 Monthly Position Of Stock")
        st.caption("Fabricator filter apply hota hai; Month filter yahan apply nahi hota (poora saal dikhta hai).")
        table_with_download(with_total(monthly, "Month", pct=("RCVD %", "RCVD (Pcs)", "Pcs Under Production")),
                            "fabricator_monthly", pct_cols=("RCVD %",), dec_cols=("Fabric Issue (mtr)",), height=520)

    with t_mat:
        badge(f"🧮 Month × Fabricator Matrix - {metric}")
        xm = flt(base, months=False)
        if xm.empty:
            st.info("Selected filters ke liye data nahi hai.")
        else:
            mat = (xm.groupby(["Fabricator", "Month"])[metric].sum().unstack(fill_value=0)
                   .reindex(index=[n for n in fab_names if n in set(xm["Fabricator"])], columns=FY_MONTH_LABELS, fill_value=0))
            mat.columns = FY_MONTH_SHORT
            fig = px.imshow(mat, text_auto=",.0f", aspect="auto", color_continuous_scale="Blues",
                            title=f"HEATMAP - {metric}", labels=dict(x="Month", y="Fabricator", color=metric))
            st.plotly_chart(style_fig(fig, max(300, 34 * len(mat) + 140)), **STRETCH)
            tbl = mat.copy()
            tbl["TOTAL"] = tbl.sum(axis=1)
            tbl.index.name = "Fabricator"
            tbl = tbl.reset_index()
            tbl = with_total(tbl, "Fabricator", label="ALL FABRICATORS")
            dec = ("TOTAL", *FY_MONTH_SHORT) if metric.startswith("Fabric") else ()
            table_with_download(tbl, "fabricator_matrix", dec_cols=dec)

    with t_chk:
        _fab_data_check(sheet_id, cfg, tab, blocks, df, base, all_over)


def _fab_data_check(sheet_id, cfg, tab, blocks, df, base, all_over):
    st.subheader("✅ Data Check")
    st.caption(f"Tab **{tab}** · {len(blocks)} 'Position Of Stock' block(s) mile")

    badge("1 · Detect hue tables")
    rows = [{"Fabricator": b["name"], "Title cell": f"{idx_to_col(b['col'])}{b['title_row'] + 1}",
             "April row": b["first_row"] + 1,
             "Value columns": f"{idx_to_col(b['col'] + 1)}:{idx_to_col(b['col'] + 5)}",
             "Type": "ALL OVER (reference)" if b["is_all"] else "Fabricator"} for b in blocks]
    st.dataframe(pd.DataFrame(rows), **STRETCH, hide_index=True)

    badge("2 · Sheet ke apne FABRICATOR DASHBOARD se match (sab filters = ALL)")
    t = base[FAB_METRICS].sum()
    kp = [("Fabric Issued (mtr)", "FABRIC ISSUED (MTR)", float(t["Fabric Issue (mtr)"]), "int"),
          ("Pcs Under Production", "PCS UNDER PRODUCTION", float(t["Pcs Under Production"]), "int"),
          ("RCVD", "RCVD (RECEIVED)", float(t["RCVD (Pcs)"]), "int"),
          ("Remaining", "REMAINING", float(t["Remaining (Pcs)"]), "int"),
          ("Monthly Incoming", "MONTHLY INCOMING", float(t["Monthly Incoming (Pcs)"]), "int"),
          ("Received %", "RECEIVED %", safe_div_pct(float(t["RCVD (Pcs)"]), float(t["Pcs Under Production"])), "pct")]
    compare_block(sheet_id, [x for x, _ in list_tabs_meta(sheet_id)], cfg.get("dashboard_tab", "FABRICATOR DASHBOARD"), kp, max_rows=12)

    badge("3 · Fabricators total vs ALL OVER table")
    if all_over.empty or base.equals(all_over):
        st.info("Sheet me alag se ALL OVER table nahi mila.")
    else:
        a = all_over[FAB_METRICS].sum()
        cmp_df = pd.DataFrame({"Metric": FAB_METRICS, "Fabricators total": [float(t[m]) for m in FAB_METRICS],
                               "ALL OVER table": [float(a[m]) for m in FAB_METRICS]})
        cmp_df["Diff"] = cmp_df["Fabricators total"] - cmp_df["ALL OVER table"]
        cmp_df["Status"] = np.where(cmp_df["Diff"].abs() < 1, "✅ match", "❌ mismatch")
        st.dataframe(cmp_df.style.format({"Fabricators total": "{:,.1f}", "ALL OVER table": "{:,.1f}", "Diff": "{:,.1f}"}),
                     **STRETCH, hide_index=True)

    with st.expander("ℹ️ Numbers kaise calculate hote hain"):
        st.markdown(
            "- Sheet me **'Position Of Stock <naam>'** title dhoondha jata hai; uske neeche **Month** header aur **April** se 12 rows li jati hain (April → March)\n"
            "- Month column ke seedhe daayein 5 columns: **Fabric Issue (mtr), Pcs Under Production, RCVD, Remaining, Monthly Incoming**\n"
            "- Cell text jaise `1,200` ya blank/error ho to number me badal jata hai (error/blank = 0)\n"
            "- **Received %** = RCVD ÷ Pcs Under Production\n"
            "- **ALL OVER** table sirf cross-check ke liye hai, KPIs me double count nahi hota")
    with st.expander("🔍 Parsed data"):
        st.dataframe(df.drop(columns=["is_all"]), **STRETCH, hide_index=True)


# -----------------------------------------------------------------------------
# 10. MAIN ROUTER
# -----------------------------------------------------------------------------
LIVE_OPTIONS = {"Off": 0, "Every 1 min": 60, "Every 2 min": 120, "Every 5 min": 300}


def main():
    apply_theme()
    with st.sidebar:
        st.markdown("### 🗂️ Workspace Selection")
        selected = st.selectbox("Active Google Sheet", list(SHEET_REGISTRY.keys()), key="ws_choice")
        st.markdown("### ⏱️ Live Updates")
        choice = st.selectbox("Auto-refresh (Sample & Fabricator)", list(LIVE_OPTIONS.keys()), index=2, key="live_choice",
                              help="Google Sheet me change hone par dashboard itne time me khud update ho jayega. "
                                   "Master Sheet ke liye sidebar ka Refresh button use karein ya page reload karein.")
        st.session_state["live_secs"] = LIVE_OPTIONS[choice]

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
