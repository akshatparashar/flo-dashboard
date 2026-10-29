import html
import re
import warnings
from datetime import datetime, timedelta

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
        "source_tabs": ["CONFIRMATION SHEET", "ORDER SHEET"],
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
        "summary_tabs": ["SAMPLE DASHBOARD", "DASHBOARD 2026-27"],
        "data_tabs": ["SAMPLE SUMMARY", "SAMPLE SUMMARY 2026-27", "2026-27"],
    },
    "Fabricator Report": {
        "id": "1hP9Bkvu2F-qj4tXYhOCb4alfJOZZtAsMQNOjVQyWoo4",
        "type": "overview_fabricators",
        "gid": 318103522,
        "summary_tabs": ["FABRICATOR DASHBOARD", "MONTHWISE SUMMARY"],
    },
}

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
KNOWN_DESIGNERS = ["ANAMIKA", "AYUSHI", "CHARU", "DEEPIKA", "JYOTI", "KEERTI",
                   "KRISHNA", "MANSI", "MUSKAN", "REKHA"]

MASTER_COLS = {
    "date_client": "B",
    "designer": "C",
    "type": "D",
    "category": "F",
    "qty": "J",
    "client": "N",
    "fabricator": "AA",
    "date_prod": "AC",
    "delay": "AH",
    "production": "AS",
    "received": "AT",
    "pending": "AU",
    "status": "AX",
}

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

def apply_theme():
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

/* Sticky Freeze Header and Filter Header */
[data-testid="stTabs"] [role="tablist"] {{
    position: sticky;
    top: 0;
    z-index: 999;
    background-color: var(--app-bg);
    padding-top: 5px;
    padding-bottom: 5px;
    border-bottom: 2px solid var(--border-color);
}}

.sticky-filter-row {{
    position: sticky;
    top: 45px;
    z-index: 998;
    background-color: var(--panel-bg);
    padding: 12px 16px;
    border-radius: 10px;
    border: 1px solid var(--border-color);
    box-shadow: 0 4px 10px rgba(0,0,0,0.05);
    margin-bottom: 15px;
}}

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
    s = pd.Series(s)
    out = pd.Series(pd.NaT, index=s.index, dtype="datetime64[ns]")
    numeric = pd.to_numeric(s, errors="coerce")
    serial = numeric.between(20000, 80000)
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
    if kind in ("orders", "int"):
        return f"{value:,.0f}"
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

def add_total_with_rate(df, label_col, rate_col, num_col, den_col, label="TOTAL"):
    """Total row jisme % column sum nahi balki (num / den * 100) se calculate hota hai."""
    out = add_total(df, label_col, label)
    last = out.index[-1]
    n, d = float(out.at[last, num_col]), float(out.at[last, den_col])
    out.at[last, rate_col] = (n / d * 100) if d else 0.0
    return out

def _highlight_total(row):
    is_total = str(row.iloc[0]).strip().upper() in ("TOTAL", "GRAND TOTAL")
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

def smart_multiselect(label, options, key):
    """'All' wala multiselect; options badalne par purani invalid selection apne aap hat jati hai."""
    valid = [x for x in st.session_state.get(key, ["All"]) if x in options] or ["All"]
    st.session_state[key] = valid
    return st.multiselect(label, options=options, key=key,
                          on_change=handle_smart_all_filter, args=(key,))

def picked(selection):
    """['All'] / [] -> None (no filter), warna selected list."""
    if not selection or "All" in selection:
        return None
    return list(selection)


# -----------------------------------------------------------------------------
# 3. GOOGLE SHEETS AUTHENTICATION & LOADERS
# -----------------------------------------------------------------------------
LIVE_TTL = 60  # seconds - Sample / Fabricator dashboards itne seconds me sheet se dobara data lete hain

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

@st.cache_data(ttl=300, show_spinner=False)
def list_tabs(sheet_id):
    return [ws.title for ws in _open_book(sheet_id).worksheets()]

@st.cache_data(ttl=300, show_spinner=False)
def list_tab_meta(sheet_id):
    return [(ws.title, ws.id) for ws in _open_book(sheet_id).worksheets()]

@st.cache_data(ttl=300, show_spinner="Google Sheet se live data load ho raha hai...")
def load_tab_raw(sheet_id, tab_title):
    book = _open_book(sheet_id)
    resp = book.values_get(_a1_tab(tab_title), params={
        "valueRenderOption": "UNFORMATTED_VALUE",
        "dateTimeRenderOption": "SERIAL_NUMBER",
    })
    return resp.get("values", [])

@st.cache_data(ttl=300, show_spinner=False)
def load_tab_formatted(sheet_id, tab_title):
    book = _open_book(sheet_id)
    resp = book.values_get(_a1_tab(tab_title))
    return resp.get("values", [])

@st.cache_data(ttl=LIVE_TTL, show_spinner="Google Sheet se live data load ho raha hai...")
def load_live_values(sheet_id, tab_title, formatted=False):
    book = _open_book(sheet_id)
    params = None if formatted else {
        "valueRenderOption": "UNFORMATTED_VALUE",
        "dateTimeRenderOption": "SERIAL_NUMBER",
    }
    resp = book.values_get(_a1_tab(tab_title), params=params)
    return resp.get("values", [])

def find_tab(tabs, wanted):
    w = norm_key(wanted)
    for t in tabs:
        if norm_key(t) == w:
            return t
    return None


# -----------------------------------------------------------------------------
# 4. MASTER SHEET – DATA PREPARATION (UNTOUCHED)
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
    needed_width = col_to_idx("AX") + 1

    def is_row_no(v):
        t = str(v).strip()
        return bool(re.fullmatch(r"\d+(\.0+)?", t)) and float(t) > 0

    first = None
    for i, r in enumerate(values):
        if i < 3 or not r:
            continue
        if is_row_no(r[0]) and len(r) > 1 and str(r[1]).strip():
            first = i
            break

    if first is None:
        first = 4

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

def filter_row_sticky(spec, key_prefix):
    st.markdown('<div class="sticky-filter-row">', unsafe_allow_html=True)
    cols = st.columns(len(spec))
    out = {}
    for c, (field, label, options) in zip(cols, spec):
        out[field] = c.selectbox(f"🔍 {label}", options, key=f"{key_prefix}_{field}")
    st.markdown('</div>', unsafe_allow_html=True)
    return out

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
    base = x[x["production"] > 0]
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
# 5. MASTER SHEET – DASHBOARDS (UNTOUCHED)
# -----------------------------------------------------------------------------
def designer_dashboard(d_all, key):
    st.subheader("👨‍🎨 Executive Designer Performance & Category Tracking Dashboard")
    f = filter_row_sticky([
        ("month", "Select Month", ["All"] + month_list(d_all)),
        ("designer", "Select Designer", opt_list(d_all, "designer", known=KNOWN_DESIGNERS)),
        ("order_type", "Order Type", opt_list(d_all, "order_type", first=("NEW", "REPEAT"))),
    ], f"{key}_des")
    x = filter_data(d_all, f)

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
    f = filter_row_sticky([
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
    f = filter_row_sticky([
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


def data_check(sheet_id, cfg, tabs, src_tab, first_row, totals_row, d_all):
    st.subheader("✅ Data Check – Streamlit vs Google Sheet")
    st.caption(f"Source tab: **{src_tab}** · data from sheet row {first_row} · {len(d_all):,} rows loaded "
               f"· {int((d_all['qty'] > 0).sum()):,} designs with qty > 0")

    badge("Data quality notes")
    notes = []
    active = d_all[d_all["qty"] != 0]
    no_date = active[active["month"] == "(NO DATE)"]
    if len(no_date):
        notes.append(f"{len(no_date)} rows with qty but no valid order date in column B "
                     f"({fmt(no_date['qty'].sum())} pcs)")
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

    src_tab = default

    with st.sidebar:
        st.markdown("### 📄 Master Sheet Actions")
        st.caption(f"Active Tab: **{src_tab}**")
        if st.button("🔄 Refresh Data", key=f"{sheet_id}_ref"):
            st.cache_data.clear()
            st.rerun()

    values = load_tab_raw(sheet_id, src_tab)
    if not values:
        st.error(f"Tab '{src_tab}' empty hai.")
        st.stop()

    raw, first_row = build_raw(values)
    if raw.empty:
        st.error(f"Tab '{src_tab}' me data rows nahi mile.")
        st.stop()
    totals_row = values[1] if len(values) > 1 else []
    d_all = prepare(raw)

    st.markdown(
        f"""<div class="dashboard-hero"><h2>📊 {html.escape(sheet_name)} · Executive Dashboard 2026-27</h2>
        <p>Source Tab: <b>{html.escape(src_tab)}</b> · {len(d_all):,} rows (data starting from row {first_row}) · auto-refresh active</p></div>""",
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
# 6. COMMON CELL HELPERS (Sample + Fabricator engines)
# -----------------------------------------------------------------------------
def _cell(grid, r, c):
    """grid[r][c] safely (Sheets API short rows/cols trim kar deta hai)."""
    if r < 0 or r >= len(grid):
        return ""
    row = grid[r]
    if c < 0 or c >= len(row):
        return ""
    return row[c]

def _to_float(v):
    """Sheet formula IFERROR(VALUE(TRIM(x)),0) jaisa behaviour."""
    if v is None or isinstance(v, bool):
        return 0.0
    if isinstance(v, (int, float)):
        return float(v) if np.isfinite(v) else 0.0
    t = str(v).replace("\xa0", " ").strip().replace(",", "")
    if not t:
        return 0.0
    if re.fullmatch(r"\(\d+(\.\d+)?\)", t):
        return -float(t[1:-1])
    if re.fullmatch(r"[-+]?(\d+(\.\d*)?|\.\d+)", t):
        return float(t)
    return 0.0

def _txt(v):
    """Sheet TRIM() jaisa: extra spaces hata kar clean text."""
    if v is None:
        return ""
    if isinstance(v, float) and v.is_integer():
        v = int(v)
    return re.sub(r"\s+", " ", str(v).replace("\xa0", " ")).strip()

_NUMERIC_RE = re.compile(r"[-+]?(\d+(\.\d*)?|\.\d+)([eE][-+]?\d+)?")


# -----------------------------------------------------------------------------
# 7. FABRICATOR ENGINE  (source: "MONTHWISE SUMMARY"  ->  same logic as Apps Script)
# -----------------------------------------------------------------------------
FAB_METRICS = ["Fabric Issue (mtr)", "Pcs Under Production", "RCVD", "Remaining", "Monthly Incoming"]
FAB_DISPLAY = {
    "Fabric Issue (mtr)": "FABRIC ISSUE (MTR)",
    "Pcs Under Production": "PCS UNDER PRODUCTION",
    "RCVD": "RCVD",
    "Remaining": "REMAINING",
    "Monthly Incoming": "MONTHLY INCOMING",
}
FAB_MONTH_SHORT = ["Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec", "Jan", "Feb", "Mar"]
FAB_SUMMARY_TAB = "MONTHWISE SUMMARY"
FAB_SKIP_TABS = {"FABRICATORDASHBOARD", "FABDASHDATA"}


def detect_fab_blocks(disp, raw):
    """
    Apps Script detectBlocks_ ka Python version:
    'Position Of Stock ...' title -> same column me 'Month' header -> 'Apr...' se 12 mahine,
    uske right me 5 columns (Fabric Issue, Under Production, RCVD, Remaining, Incoming).
    """
    blocks, used = [], {}
    for r in range(len(disp)):
        for c in range(len(disp[r])):
            t = str(disp[r][c]).strip()
            m = re.match(r"^position\s+of\s+stock\s*(.*)$", t, re.I)
            if not m:
                continue

            hdr = -1
            for rr in range(r, min(r + 6, len(disp) - 1) + 1):
                if re.fullmatch(r"month", str(_cell(disp, rr, c)).strip(), re.I):
                    hdr = rr
                    break
            if hdr < 0:
                continue

            first = -1
            for rr in range(hdr + 1, min(hdr + 6, len(disp) - 1) + 1):
                if re.match(r"^apr", str(_cell(disp, rr, c)).strip(), re.I):
                    first = rr
                    break
            if first < 0:
                continue

            raw_name = re.sub(r"[()]", "", m.group(1)).strip().upper()
            is_all = bool(re.search(r"ALL\s*OVER", raw_name))
            name = "ALL OVER" if is_all else (raw_name or "BLOCK")
            if name in used:
                used[name] += 1
                name = f"{name} ({used[name]})"
            else:
                used[name] = 1

            blocks.append({"name": name, "is_all": is_all, "first": first, "col": c})

    rows = []
    for b in blocks:
        for mi in range(12):
            vals = [_to_float(_cell(raw, b["first"] + mi, b["col"] + f)) for f in range(1, 6)]
            rows.append([b["name"], mi + 1] + vals)
    return pd.DataFrame(rows, columns=["Fabricator", "MONTH_NO"] + FAB_METRICS)


@st.cache_data(ttl=LIVE_TTL, show_spinner="Fabricator sheet se live data load ho raha hai...")
def load_fabricator_data(sheet_id, gid):
    meta = list_tab_meta(sheet_id)
    titles = [t for t, _ in meta]

    candidates = []
    exact = find_tab(titles, FAB_SUMMARY_TAB)
    if exact:
        candidates.append(exact)
    for t in titles:
        if re.search(r"monthwise|monthly\s*summary", t, re.I) and t not in candidates:
            candidates.append(t)
    if gid is not None:
        for t, i in meta:
            if str(i) == str(gid) and t not in candidates:
                candidates.append(t)
    for t in titles:
        if t not in candidates:
            candidates.append(t)

    for tab in candidates:
        if norm_key(tab) in FAB_SKIP_TABS:
            continue
        disp = load_live_values(sheet_id, tab, True)
        if not disp:
            continue
        raw = load_live_values(sheet_id, tab, False)
        df = detect_fab_blocks(disp, raw)
        if not df.empty:
            return tab, df
    return "", pd.DataFrame(columns=["Fabricator", "MONTH_NO"] + FAB_METRICS)


def fab_apply(df, fabs=None, month_nos=None):
    """fabs=None => ALL FABRICATORS (ALL OVER row exclude, jaise sheet me '<>ALL OVER')."""
    x = df[df["Fabricator"].isin(fabs)] if fabs else df[df["Fabricator"] != "ALL OVER"]
    if month_nos:
        x = x[x["MONTH_NO"].isin(month_nos)]
    return x


def fab_month_table(df, fabs):
    x = fab_apply(df, fabs, None)
    g = x.groupby("MONTH_NO")[FAB_METRICS].sum().reindex(range(1, 13), fill_value=0)
    t = g.reset_index(drop=True).astype(float)
    t.insert(0, "MONTH", FY_MONTH_LABELS)
    t = t.rename(columns=FAB_DISPLAY)
    t["RCVD %"] = np.where(t["PCS UNDER PRODUCTION"] > 0,
                           t["RCVD"] / t["PCS UNDER PRODUCTION"] * 100, 0.0)
    return t


def fab_scorecard(df, order, month_nos):
    x = fab_apply(df, None, month_nos)
    g = x.groupby("Fabricator")[FAB_METRICS].sum().reindex(order, fill_value=0).astype(float)
    t = g.reset_index().rename(columns={"Fabricator": "FABRICATOR"}).rename(columns=FAB_DISPLAY)
    t["RCVD %"] = np.where(t["PCS UNDER PRODUCTION"] > 0,
                           t["RCVD"] / t["PCS UNDER PRODUCTION"] * 100, 0.0)
    return t


def fab_matrix(df, order, metric):
    x = df[df["Fabricator"] != "ALL OVER"]
    g = x.groupby(["Fabricator", "MONTH_NO"])[metric].sum().unstack(fill_value=0)
    g = g.reindex(index=order, columns=range(1, 13), fill_value=0).astype(float)
    g.columns = FAB_MONTH_SHORT
    g["TOTAL"] = g.sum(axis=1)
    return g.reset_index().rename(columns={"Fabricator": "FABRICATOR"})


def render_fabricator_dashboard(sheet_name, cfg):
    sheet_id = cfg["id"]
    tab_title, df = load_fabricator_data(sheet_id, cfg.get("gid"))

    with st.sidebar:
        st.markdown("### 📄 Fabricator Sheet Actions")
        st.caption(f"Active Tab: **{tab_title or '—'}**")
        st.caption(f"Auto-sync: har {LIVE_TTL} sec me sheet se naya data")
        if st.button("🔄 Refresh Data", key="fab_ref"):
            st.cache_data.clear()
            st.rerun()

    if df.empty:
        st.error("Fabricator sheet me koi 'Position Of Stock ...' table nahi mili "
                 "(Month header aur 'Apr' se shuru hone wali rows chahiye). "
                 "Sheet ka structure check karein.")
        st.stop()

    fab_order = list(dict.fromkeys(df.loc[df["Fabricator"] != "ALL OVER", "Fabricator"]))
    has_all = bool((df["Fabricator"] == "ALL OVER").any())
    if not fab_order:
        st.error("Sirf 'ALL OVER' table mili, individual fabricator tables nahi mile.")
        st.stop()

    # ---------------- Filters (Apps Script: Fabricator / Month / Metric) ----------------
    st.markdown('<div class="sticky-filter-row">', unsafe_allow_html=True)
    f1, f2, f3 = st.columns(3)
    with f1:
        fab_opts = ["All"] + fab_order + (["ALL OVER"] if has_all else [])
        sel_fabs = smart_multiselect("🔍 Fabricator", fab_opts, "f_fab")
    with f2:
        sel_months = smart_multiselect("🔍 Month", ["All"] + FY_MONTH_LABELS, "f_month")
    with f3:
        metric = st.selectbox("🔍 Matrix Metric", FAB_METRICS, index=FAB_METRICS.index("RCVD"), key="f_metric")
    st.markdown('</div>', unsafe_allow_html=True)

    fabs = picked(sel_fabs)
    month_sel = picked(sel_months)
    month_nos = [FY_MONTH_LABELS.index(m) + 1 for m in month_sel] if month_sel else None

    st.markdown(
        f"""<div class="dashboard-hero">
        <h2>🏭 FABRICATOR STOCK POSITION DASHBOARD (2026-27)</h2>
        <p>Active Source: <b>{html.escape(tab_title)}</b> · Live sync from Google Sheet ·
        Updated: {datetime.now().strftime('%d %b %Y, %H:%M')}</p>
        </div>""",
        unsafe_allow_html=True,
    )

    # ---------------- KPIs ----------------
    xk = fab_apply(df, fabs, month_nos)
    tot = xk[FAB_METRICS].sum()
    issue, prod, rcvd, rem, inc = (float(tot[m]) for m in FAB_METRICS)
    rcvd_pct = (rcvd / prod * 100) if prod > 0 else 0.0

    sc = fab_scorecard(df, fab_order, month_nos)
    top_rcvd = sc.loc[sc["RCVD"].idxmax(), "FABRICATOR"] if sc["RCVD"].max() > 0 else "N/A"
    top_pend = sc.loc[sc["REMAINING"].idxmax(), "FABRICATOR"] if sc["REMAINING"].max() > 0 else "N/A"

    metrics([
        ("FABRIC ISSUED (MTR)", f"{issue:,.0f} mtr"),
        ("PCS UNDER PRODUCTION", f"{prod:,.0f} Pcs"),
        ("RCVD (RECEIVED)", f"{rcvd:,.0f} Pcs"),
        ("REMAINING", f"{rem:,.0f} Pcs"),
    ])
    metrics([
        ("MONTHLY INCOMING", f"{inc:,.0f} Pcs"),
        ("RECEIVED %", f"{rcvd_pct:.1f}%"),
        ("🏆 TOP RECEIVER", str(top_rcvd)),
        ("⚠ MOST PENDING", str(top_pend)),
    ])

    st.markdown("---")
    t1, t2 = st.tabs(["📊 Fabricator Dashboard", "📋 Month × Fabricator Matrix"])

    with t1:
        mt = fab_month_table(df, fabs)
        badge("📅 Monthly Position Of Stock")
        c1, c2 = st.columns([1.25, 1])
        with c1:
            show_table(add_total_with_rate(mt, "MONTH", "RCVD %", "RCVD", "PCS UNDER PRODUCTION"),
                       pct_cols=("RCVD %",), height=500)
        with c2:
            fig = px.bar(mt, x="MONTH", y=["PCS UNDER PRODUCTION", "RCVD", "REMAINING"], barmode="group",
                         title="MONTHLY: PRODUCTION vs RCVD vs REMAINING",
                         color_discrete_sequence=["#2563eb", "#059669", "#dc2626"])
            fig.update_xaxes(tickangle=-35, title="")
            fig.update_yaxes(title="Pcs")
            st.plotly_chart(style_fig(fig, 460), **STRETCH)

        fig = px.line(mt, x="MONTH", y=["FABRIC ISSUE (MTR)", "MONTHLY INCOMING"], markers=True,
                      title="MONTHLY FABRIC ISSUE & INCOMING TREND",
                      color_discrete_sequence=["#2563eb", "#d97706"])
        fig.update_xaxes(tickangle=-35, title="")
        fig.update_yaxes(title="")
        st.plotly_chart(style_fig(fig, 340), **STRETCH)

        st.markdown("---")
        badge("🏭 Fabricator Scorecard")
        st.caption("Scorecard sabhi fabricators dikhata hai (sirf Month filter lagta hai) — Google Sheet dashboard jaisa.")
        table = add_total_with_rate(sc, "FABRICATOR", "RCVD %", "RCVD", "PCS UNDER PRODUCTION")

        all_row = None
        if has_all:
            xa = df[df["Fabricator"] == "ALL OVER"]
            if month_nos:
                xa = xa[xa["MONTH_NO"].isin(month_nos)]
            sums = xa[FAB_METRICS].sum()
            all_row = {"FABRICATOR": "ALL OVER (SHEET)"}
            for m in FAB_METRICS:
                all_row[FAB_DISPLAY[m]] = float(sums[m])
            p = all_row["PCS UNDER PRODUCTION"]
            all_row["RCVD %"] = (all_row["RCVD"] / p * 100) if p > 0 else 0.0
            table = pd.concat([table, pd.DataFrame([all_row])], ignore_index=True)

        s1, s2 = st.columns([1.5, 1])
        with s1:
            show_table(table, pct_cols=("RCVD %",))
        with s2:
            fig = px.bar(sc, y="FABRICATOR", x=["RCVD", "REMAINING"], orientation="h", barmode="stack",
                         title="FABRICATOR WISE: RCVD vs REMAINING",
                         color_discrete_sequence=["#059669", "#dc2626"])
            fig.update_yaxes(title="", autorange="reversed")
            fig.update_xaxes(title="Pcs")
            st.plotly_chart(style_fig(fig, 400), **STRETCH)

        fig = px.area(sc, x="FABRICATOR", y="RCVD %", title="FABRICATOR WISE: RECEIVED %",
                      color_discrete_sequence=["#3b82f6"])
        fig.update_yaxes(range=[0, 100], ticksuffix="%", title="")
        fig.update_xaxes(title="", tickangle=-35)
        st.plotly_chart(style_fig(fig, 340), **STRETCH)

        # Cross-check (sheet ki data-check line jaisa)
        if has_all:
            diff = sum(abs(float(table.loc[table["FABRICATOR"] == "TOTAL", FAB_DISPLAY[m]].iloc[0]) - all_row[FAB_DISPLAY[m]])
                       for m in FAB_METRICS)
            if diff < 1:
                st.success("✅ Fabricators ka total sheet ke ALL OVER table se match karta hai")
            else:
                st.warning(f"⚠ Fabricators ka total ALL OVER table se alag hai (difference = {diff:,.0f}) "
                           "- koi fabricator table summary me missing ho sakta hai")
        else:
            st.info("ℹ Sheet me ALL OVER table nahi mila, isliye cross-check nahi ho paya")

    with t2:
        badge(f"🧮 Month × Fabricator Matrix — Metric: {metric}")
        mx = fab_matrix(df, fab_order, metric)
        show_table(add_total(mx, "FABRICATOR", "ALL FABRICATORS"))
        with st.expander("🔍 Detected tables (raw parsed data)"):
            st.dataframe(df, **STRETCH, hide_index=True)


# -----------------------------------------------------------------------------
# 8. SAMPLE SUMMARY ENGINE  (source tab columns: B Vendor, F Qty, H Date, L Status, N Designer)
# -----------------------------------------------------------------------------
SAMPLE_SOURCE_TABS = ["2026-27", "SAMPLE SHEET 2026-27", "SAMPLE SUMMARY 2026-27", "SAMPLE SUMMARY", "Sheet1"]
SAMPLE_MAX_ROW = 2500                      # Apps Script rows 2..2500 padhta hai
SAMPLE_COL = {"vendor": 1, "qty": 5, "date": 7, "status": 11, "designer": 13}   # B, F, H, L, N (0-based)
SAMPLE_STATUSES = ["APPROVED", "REJECTED", "HOLD", "ON PROCESS", "OTHER"]
FY_MONTH_NOS = [4, 5, 6, 7, 8, 9, 10, 11, 12, 1, 2, 3]
_MONTH_STR = "janfebmaraprmayjunjulaugsepoctnovdec"


def sample_month_no(v):
    """Apps Script ke MONTH_NO ARRAYFORMULA ka exact Python version."""
    if v is None or isinstance(v, bool):
        return 0
    if isinstance(v, (int, float)):
        try:
            return (datetime(1899, 12, 30) + timedelta(days=float(v))).month
        except (OverflowError, ValueError):
            return 0
    t = str(v).strip()
    if not t:
        return 0
    nrm = re.sub(r"[ .,\-]+", "/", re.sub(r"\s+", " ", t.lower()))
    m = re.fullmatch(r"[0-9]{1,2}/([0-9]{1,2})/[0-9]{2,4}", nrm)
    if m:
        return int(m.group(1))
    m = re.fullmatch(r"([0-9]{1,2})/[0-9]{4}", nrm)
    if m:
        return int(m.group(1))
    m = re.fullmatch(r"[0-9]{4}/([0-9]{1,2})/[0-9]{1,2}", nrm)
    if m:
        return int(m.group(1))
    m = re.search(r"(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)", nrm)
    if m:
        return (_MONTH_STR.find(m.group(1)) + 1 + 2) // 3
    return 0


def sample_status_class(v):
    s = _txt(v).upper()
    if not s:
        return "NONE"
    if "REJECT" in s:
        return "REJECTED"
    if "APPROV" in s:
        return "APPROVED"
    if "HOLD" in s:
        return "HOLD"
    if "PROCESS" in s:
        return "ON PROCESS"
    return "OTHER"


def pick_sample_tab(sheet_id, gid):
    meta = list_tab_meta(sheet_id)
    titles = [t for t, _ in meta]
    for cand in SAMPLE_SOURCE_TABS:
        t = find_tab(titles, cand)
        if t:
            return t
    if gid is not None:
        for t, i in meta:
            if str(i) == str(gid) and "DASHBOARD" not in t.upper():
                return t
    for t in titles:
        if "DASHBOARD" not in t.upper():
            return t
    return titles[0] if titles else None


def build_sample_df(values):
    body = values[1:SAMPLE_MAX_ROW]          # sheet rows 2..2500
    beyond = sum(1 for r in values[SAMPLE_MAX_ROW:] if any(str(c).strip() for c in r))

    recs, designers, vendors = [], [], []
    seen_d, seen_v = set(), set()

    def uniq(raw_val, seen, out, skip):
        v = _txt(raw_val)
        if v and not _NUMERIC_RE.fullmatch(v) and v.upper() not in skip and v.upper() not in seen:
            seen.add(v.upper())
            out.append(v)

    for r in body:
        des_raw = _cell([r], 0, SAMPLE_COL["designer"])
        ven_raw = _cell([r], 0, SAMPLE_COL["vendor"])
        uniq(des_raw, seen_d, designers, {"DESIGNER NAME", "DESIGNER"})
        uniq(ven_raw, seen_v, vendors, {"VENDOR NAME", "VENDOR"})

        des = _txt(des_raw) or "(BLANK)"
        ven = _txt(ven_raw) or "(BLANK)"
        status = sample_status_class(_cell([r], 0, SAMPLE_COL["status"]))
        recs.append({
            "qty": _to_float(_cell([r], 0, SAMPLE_COL["qty"])),
            "month_no": sample_month_no(_cell([r], 0, SAMPLE_COL["date"])),
            "status": status,
            "grp": "OTHER" if status == "NONE" else status,
            "designer": des,
            "designer_key": des.upper(),
            "vendor": ven,
            "vendor_key": ven.upper(),
        })

    cols = ["qty", "month_no", "status", "grp", "designer", "designer_key", "vendor", "vendor_key"]
    return pd.DataFrame(recs, columns=cols), designers, vendors, beyond


@st.cache_data(ttl=LIVE_TTL, show_spinner="Sample sheet se live data load ho raha hai...")
def load_sample_source(sheet_id, gid):
    tab = pick_sample_tab(sheet_id, gid)
    if not tab:
        return "", []
    return tab, load_live_values(sheet_id, tab, False)


def sample_filter(df, months=None, des=None, stat=None, ven=None):
    x = df
    if months:
        x = x[x["month_no"].isin(months)]
    if des:
        x = x[x["designer_key"].isin([d.upper() for d in des])]
    if stat:
        x = x[x["status"].isin(stat)]
    if ven:
        x = x[x["vendor_key"].isin([v.upper() for v in ven])]
    return x


def _status_row(label, s):
    v = {k: float(s.loc[s["grp"] == k, "qty"].sum()) for k in SAMPLE_STATUSES}
    total = sum(v.values())
    return {
        "MONTH": label,
        "APPROVED": v["APPROVED"], "REJECTED": v["REJECTED"], "HOLD": v["HOLD"],
        "PROCESS": v["ON PROCESS"], "OTHER": v["OTHER"],
        "TOTAL": total,
        "APPR %": (v["APPROVED"] / total * 100) if total else 0.0,
    }


def sample_monthly_table(x):
    rows = [_status_row(lbl, x[x["month_no"] == mno]) for lbl, mno in zip(FY_MONTH_LABELS, FY_MONTH_NOS)]
    no_date = _status_row("⚠ NO / UNREADABLE DATE", x[~x["month_no"].isin(FY_MONTH_NOS)])
    return pd.DataFrame(rows), no_date


def sample_group_table(x, names, key_col, label):
    rows = []
    for name in names:
        s = x[x[key_col] == name.upper()]
        appr = float(s.loc[s["status"] == "APPROVED", "qty"].sum())
        rej = float(s.loc[s["status"] == "REJECTED", "qty"].sum())
        tot = float(s["qty"].sum())
        rows.append({label: name, "APPROVED": appr, "REJECTED": rej, "TOTAL": tot,
                     "APPR %": (appr / tot * 100) if tot else 0.0})
    return pd.DataFrame(rows, columns=[label, "APPROVED", "REJECTED", "TOTAL", "APPR %"])


def render_sample_summary_dashboard(sheet_name, cfg):
    sheet_id = cfg["id"]
    tab_title, values = load_sample_source(sheet_id, cfg.get("gid"))

    with st.sidebar:
        st.markdown("### 📄 Sample Sheet Actions")
        st.caption(f"Active Tab: **{tab_title or '—'}**")
        st.caption(f"Auto-sync: har {LIVE_TTL} sec me sheet se naya data")
        if st.button("🔄 Refresh Data", key="samp_ref"):
            st.cache_data.clear()
            st.rerun()

    if not values:
        st.error("Sample sheet ka source tab khaali hai ya mila nahi.")
        st.stop()

    d_all, designers, vendors, beyond = build_sample_df(values)
    if d_all.empty:
        st.error("Source tab me data rows nahi mile.")
        st.stop()
    if beyond:
        st.warning(f"Sheet me row {SAMPLE_MAX_ROW} ke baad bhi {beyond} data rows hain — "
                   "Google Sheet dashboard bhi sirf row 2500 tak padhta hai, isliye wo yahan include nahi hain.")

    # ---------------- Filters (Apps Script: Month / Designer / Status / Vendor) ----------------
    st.markdown('<div class="sticky-filter-row">', unsafe_allow_html=True)
    f1, f2, f3, f4 = st.columns(4)
    with f1:
        sel_m = smart_multiselect("🔍 Month", ["All"] + FY_MONTH_LABELS, "s_month")
    with f2:
        sel_d = smart_multiselect("🔍 Designer", ["All"] + designers, "s_des")
    with f3:
        sel_s = smart_multiselect("🔍 Status", ["All", "APPROVED", "REJECTED", "HOLD", "ON PROCESS"], "s_stat")
    with f4:
        sel_v = smart_multiselect("🔍 Vendor", ["All"] + vendors, "s_ven")
    st.markdown('</div>', unsafe_allow_html=True)

    m_lbl = picked(sel_m)
    months = [MONTH_NUM[l.split("-")[0][:3].lower()] for l in m_lbl] if m_lbl else None
    des, stat, ven = picked(sel_d), picked(sel_s), picked(sel_v)

    st.markdown(
        f"""<div class="dashboard-hero">
        <h2>⚡ EXECUTIVE SAMPLE PERFORMANCE & DESIGNER DASHBOARD (2026-27)</h2>
        <p>Active Source: <b>{html.escape(tab_title)}</b> · Live sync from Google Sheet ·
        {len(d_all):,} rows · Updated: {datetime.now().strftime('%d %b %Y, %H:%M')}</p>
        </div>""",
        unsafe_allow_html=True,
    )

    # Sheet logic: monthly table -> sab filters; designer table -> designer filter skip;
    # vendor table -> vendor filter skip.
    x_all = sample_filter(d_all, months, des, stat, ven)
    x_des = sample_filter(d_all, months, None, stat, ven)
    x_ven = sample_filter(d_all, months, des, stat, None)

    df_m, no_date = sample_monthly_table(x_all)
    df_des = sample_group_table(x_des, designers, "designer_key", "DESIGNER")
    df_ven = sample_group_table(x_ven, vendors, "vendor_key", "VENDOR")

    q = lambda s: float(x_all.loc[x_all["status"] == s, "qty"].sum())
    tot_s = float(x_all["qty"].sum())
    app_s, rej_s, hld_s, prc_s = q("APPROVED"), q("REJECTED"), q("HOLD"), q("ON PROCESS")
    ratio = (app_s / tot_s * 100) if tot_s > 0 else 0.0
    top = "N/A"
    if not df_des.empty and df_des["APPROVED"].max() > 0:
        top = df_des.loc[df_des["APPROVED"].idxmax(), "DESIGNER"]

    metrics([
        ("TOTAL SAMPLES QTY", fmt(tot_s) + " Samples"),
        ("APPROVED SAMPLES", fmt(app_s) + " Pcs"),
        ("REJECTED SAMPLES", fmt(rej_s) + " Pcs"),
        ("ON HOLD SAMPLES", fmt(hld_s) + " Pcs"),
    ])
    metrics([
        ("ON PROCESS", fmt(prc_s) + " Pcs"),
        ("APPROVAL RATIO %", f"{ratio:.1f}%"),
        ("🏆 TOP PERFORMER", str(top)),
    ])

    st.markdown("---")
    badge("📊 EXECUTIVE TABLES & WORKFLOW MATRIX")
    c_m, c_d, c_v = st.columns([1.35, 1, 1])

    with c_m:
        st.markdown("##### 📅 MONTHLY SAMPLE BREAKDOWN")
        show_df = df_m
        if no_date["TOTAL"] > 0:
            show_df = pd.concat([df_m, pd.DataFrame([no_date])], ignore_index=True)
        show_table(add_total_with_rate(show_df, "MONTH", "APPR %", "APPROVED", "TOTAL"), pct_cols=("APPR %",))
        if no_date["TOTAL"] > 0:
            st.warning(f"⚠ {fmt(no_date['TOTAL'])} samples ki Process Date (Col H) khaali ya unreadable hai")
        else:
            st.success("✅ Sab samples ki Process Date sahi padhi gayi")

    with c_d:
        st.markdown("##### 👩‍🎨 DESIGNER PERFORMANCE SCORECARD")
        if df_des.empty:
            st.info("Designer data nahi mila.")
        else:
            show_table(add_total_with_rate(df_des, "DESIGNER", "APPR %", "APPROVED", "TOTAL"), pct_cols=("APPR %",))
            st.caption("Designer filter is table par lagu nahi hota (sheet jaisa).")

    with c_v:
        st.markdown("##### 🏭 VENDOR PERFORMANCE SCORECARD")
        if df_ven.empty:
            st.info("Vendor data nahi mila.")
        else:
            show_table(add_total_with_rate(df_ven, "VENDOR", "APPR %", "APPROVED", "TOTAL"), pct_cols=("APPR %",))
            st.caption("Vendor filter is table par lagu nahi hota (sheet jaisa).")

    st.markdown("---")
    badge("📈 VISUAL PERFORMANCE TRENDS")
    g1, g2, g3 = st.columns(3)
    with g1:
        fig1 = px.bar(df_m, x="MONTH", y=["APPROVED", "REJECTED", "HOLD", "PROCESS", "OTHER"],
                      title="MONTHLY SAMPLE STATUS DISTRIBUTION", barmode="stack",
                      color_discrete_sequence=["#059669", "#DC2626", "#D97706", "#2563EB", "#94A3B8"])
        fig1.update_xaxes(tickangle=-35, title="")
        fig1.update_yaxes(title="")
        st.plotly_chart(style_fig(fig1, 350), **STRETCH)
    with g2:
        fig2 = px.line(df_m, x="MONTH", y=["TOTAL", "APPROVED", "REJECTED"], markers=True,
                       title="MONTHLY PROCESS VOLUME TREND",
                       color_discrete_sequence=["#2563eb", "#059669", "#DC2626"])
        fig2.update_xaxes(tickangle=-35, title="")
        fig2.update_yaxes(title="")
        st.plotly_chart(style_fig(fig2, 350), **STRETCH)
    with g3:
        all_tot = {k: float(x_all.loc[x_all["grp"] == k, "qty"].sum()) for k in SAMPLE_STATUSES}
        pie = pd.DataFrame({"Status": list(all_tot.keys()), "Count": list(all_tot.values())})
        if pie["Count"].sum() > 0:
            fig3 = px.pie(pie, names="Status", values="Count", title="OVERALL SAMPLE APPROVAL SHARE", hole=0.45,
                          color="Status",
                          color_discrete_map={"APPROVED": "#059669", "REJECTED": "#DC2626", "HOLD": "#D97706",
                                              "ON PROCESS": "#2563EB", "OTHER": "#94A3B8"})
            st.plotly_chart(style_fig(fig3, 350), **STRETCH)
        else:
            st.info("Selected filters ke liye data nahi hai.")

    blank_des = float(x_des.loc[x_des["designer"] == "(BLANK)", "qty"].sum())
    blank_ven = float(x_ven.loc[x_ven["vendor"] == "(BLANK)", "qty"].sum())
    if blank_des or blank_ven:
        st.caption(f"ℹ Blank designer wali qty: {fmt(blank_des)} · Blank vendor wali qty: {fmt(blank_ven)} "
                   "(ye scorecards me list nahi hoti, par KPI / monthly total me judti hai).")


# -----------------------------------------------------------------------------
# 9. MAIN ROUTER
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
