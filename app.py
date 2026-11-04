import html
import re
import warnings

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
        "gid": 78218658,
        "data_tabs": ["SAMPLE SUMMARY", "SAMPLE SUMMARY 2026-27", "2026-27", "SAMPLE SHEET 2026-27"],
    },
    "Fabricator Report": {
        "id": "1hP9Bkvu2F-qj4tXYhOCb4alfJOZZtAsMQNOjVQyWoo4",
        "type": "overview_fabricators",
        "gid": 164418035,
        "summary_tabs": ["MONTHWISE SUMMARY", "MONTHWISE SUMMARY 2026-27"],
    },
}

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


@st.cache_data(ttl=300, show_spinner=False)
def list_tabs(sheet_id):
    return [ws.title for ws in _open_book(sheet_id).worksheets()]


@st.cache_data(ttl=300, show_spinner="Google Sheet se live data load ho raha hai...")
def load_tab_raw(sheet_id, tab_title):
    """Unformatted values: numbers as numbers, dates as serial numbers (no locale/format parsing errors)."""
    book = _open_book(sheet_id)
    resp = book.values_get(_a1_tab(tab_title), params={
        "valueRenderOption": "UNFORMATTED_VALUE",
        "dateTimeRenderOption": "SERIAL_NUMBER",
    })
    return resp.get("values", [])


@st.cache_data(ttl=300, show_spinner=False)
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


@st.cache_data(ttl=300, show_spinner="Sheet data load ho raha hai...")
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


def compare_block(sheet_id, tabs, tab_name, kpis):
    tab = find_tab(tabs, tab_name)
    if not tab:
        st.caption(f"Tab '{tab_name}' sheet me nahi mila.")
        return
    try:
        vals = load_tab_formatted(sheet_id, tab)
    except Exception as e:
        st.caption(f"'{tab_name}' read nahi ho paya: {e}")
        return
    found = find_sheet_kpis(vals, [k[1] for k in kpis])
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
        <p>Source Tab: <b>{html.escape(src_tab)}</b> · {len(d_all):,} rows (data from sheet row {first_row}) · auto-refresh every 5 min</p></div>""",
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
# 7. FABRICATOR ENGINE
# -----------------------------------------------------------------------------
def parse_fabricator_summary_grid(values):
    records = []
    if not values:
        return pd.DataFrame()

    for r_idx, row in enumerate(values):
        for c_idx, cell in enumerate(row):
            cell_str = str(cell).strip()
            if re.search(r"position\s*of\s*stock", cell_str, re.I):
                fab_name = re.sub(r"position\s*of\s*stock\s*[:\-]?", "", cell_str, flags=re.I).strip()
                fab_name = re.sub(r"^[(\[]|[)\]]$", "", fab_name).strip()
                if "ALL OVER" in fab_name.upper():
                    fab_name = "ALL OVER (CONSOLIDATED)"
                if not fab_name:
                    fab_name = "UNKNOWN"

                header_row_idx = None
                for scan_r in range(r_idx + 1, min(r_idx + 6, len(values))):
                    scan_row = values[scan_r]
                    for offset in range(0, 3):
                        check_c = c_idx + offset
                        if check_c < len(scan_row) and re.search(r"month", str(scan_row[check_c]), re.I):
                            header_row_idx = scan_r
                            break
                    if header_row_idx is not None:
                        break
                if header_row_idx is None:
                    continue

                h_row = values[header_row_idx]
                col_map = {}
                for offset in range(0, 8):
                    curr_col = c_idx + offset
                    if curr_col < len(h_row):
                        h_val = str(h_row[curr_col]).strip().lower()
                        if "month" in h_val and "month" not in col_map:
                            col_map["month"] = curr_col
                        elif ("fabric" in h_val or "issue" in h_val or "mtr" in h_val) and "fabric_issue" not in col_map:
                            col_map["fabric_issue"] = curr_col
                        elif ("under" in h_val or "production" in h_val or "pcs" in h_val) and "production" not in col_map:
                            col_map["production"] = curr_col
                        elif ("rcvd" in h_val or "received" in h_val) and "received" not in col_map:
                            col_map["received"] = curr_col
                        elif ("remain" in h_val or "pending" in h_val) and "remaining" not in col_map:
                            col_map["remaining"] = curr_col
                        elif "incoming" in h_val and "incoming" not in col_map:
                            col_map["incoming"] = curr_col

                month_col = col_map.get("month", c_idx)
                for data_r in range(header_row_idx + 1, len(values)):
                    d_row = values[data_r]
                    if month_col >= len(d_row):
                        break
                    m_val = str(d_row[month_col]).strip()
                    if not m_val:
                        continue
                    if re.search(r"^total\b", m_val, re.I) or re.search(r"position\s*of\s*stock", m_val, re.I):
                        break
                    if not re.search(r"(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)", m_val, re.I):
                        continue

                    def get_val(k):
                        idx = col_map.get(k)
                        if idx is not None and idx < len(d_row):
                            return float(num(pd.Series([d_row[idx]])).iloc[0])
                        return 0.0

                    issue_val = get_val("fabric_issue")
                    prod_val = get_val("production")
                    rcvd_val = get_val("received")
                    rem_val = get_val("remaining")
                    inc_val = get_val("incoming")

                    if prod_val == 0 and issue_val == 0:
                        status = "No Orders"
                    elif rem_val == 0 and prod_val > 0:
                        status = "Completed (100%)"
                    elif rcvd_val > 0 and rem_val > 0:
                        status = "In Progress"
                    elif rcvd_val == 0 and prod_val > 0:
                        status = "Pending / Not Started"
                    else:
                        status = "In Progress" if rem_val > 0 else "Completed (100%)"

                    records.append({
                        "Fabricator": fab_name,
                        "Month": m_val,
                        "Fabric Issue (mtr)": issue_val,
                        "Pcs Under Production": int(prod_val),
                        "RCVD (Pcs)": int(rcvd_val),
                        "Remaining (Pcs)": int(rem_val),
                        "Monthly Incoming (Pcs)": int(inc_val),
                        "Production Status": status,
                    })

    df = pd.DataFrame(records)
    if not df.empty:
        df["_order"] = df["Month"].apply(month_sort_key)
        df = df.sort_values(["_order", "Fabricator"]).drop(columns=["_order"])
    return df


def render_fabricator_dashboard(sheet_name, cfg):
    tab_title, raw_values = load_worksheet_smart(cfg["id"], cfg, signature_text="position of stock")
    df_parsed = parse_fabricator_summary_grid(raw_values)

    if df_parsed.empty:
        st.error(f"Tab '{tab_title}' me fabricator block structure detect nahi hua. Make sure sheet me 'Position Of Stock' blocks hain.")
        st.stop()

    is_cons = df_parsed["Fabricator"].str.contains("ALL OVER", case=False, na=False)
    df_consolidated = df_parsed[is_cons].copy()
    df_vendors = df_parsed[~is_cons].copy()
    df_work = df_vendors if not df_vendors.empty else df_consolidated

    with st.sidebar:
        st.markdown("### 🔍 Fabricator Filters")
        fab_opts = ["All"] + sorted(df_work["Fabricator"].unique())
        if "f_fab" not in st.session_state:
            st.session_state["f_fab"] = ["All"]
        sel_fabs = st.multiselect("Fabricator Name", options=fab_opts, key="f_fab",
                                  on_change=handle_smart_all_filter, args=("f_fab",))

        month_opts = ["All"] + list(dict.fromkeys(df_work["Month"].tolist()))
        if "f_month" not in st.session_state:
            st.session_state["f_month"] = ["All"]
        sel_months = st.multiselect("Month", options=month_opts, key="f_month",
                                    on_change=handle_smart_all_filter, args=("f_month",))

        all_stat = ["Completed (100%)", "In Progress", "Pending / Not Started", "No Orders"]
        status_opts = ["All"] + [s for s in all_stat if s in df_work["Production Status"].values]
        if "f_stat" not in st.session_state:
            st.session_state["f_stat"] = ["All"]
        sel_status = st.multiselect("Production Status", options=status_opts, key="f_stat",
                                    on_change=handle_smart_all_filter, args=("f_stat",))

        hide_zero = st.checkbox("Hide Zero Production Months", value=True)
        if st.button("🔄 Refresh Data", key="fab_ref"):
            st.cache_data.clear()
            st.rerun()

    filtered = df_work.copy()
    if "All" not in sel_fabs and sel_fabs:
        filtered = filtered[filtered["Fabricator"].isin(sel_fabs)]
    if "All" not in sel_months and sel_months:
        filtered = filtered[filtered["Month"].isin(sel_months)]
    if "All" not in sel_status and sel_status:
        filtered = filtered[filtered["Production Status"].isin(sel_status)]
    if hide_zero:
        filtered = filtered[(filtered["Pcs Under Production"] > 0) | (filtered["Fabric Issue (mtr)"] > 0)]

    st.markdown(
        f"""<div class="dashboard-hero">
        <h2>🧵 {html.escape(sheet_name)} · Executive Operations Dashboard</h2>
        <p>Active Source: <b>{html.escape(tab_title)}</b> · {filtered['Fabricator'].nunique():,} Fabricator(s) Filtered · Live Sync 2026-27</p>
        </div>""",
        unsafe_allow_html=True,
    )

    if filtered.empty:
        st.warning("Selected filters ke saath koi record match nahi hua. Kripya sidebar filter reset karein.")
        st.stop()

    tot_fab = filtered["Fabric Issue (mtr)"].sum()
    tot_prod = filtered["Pcs Under Production"].sum()
    tot_rcvd = filtered["RCVD (Pcs)"].sum()
    tot_rem = filtered["Remaining (Pcs)"].sum()
    ful_rate = (tot_rcvd / tot_prod * 100) if tot_prod > 0 else 0.0

    k1, k2, k3, k4, k5 = st.columns(5)
    k1.metric("Fabric Issued", f"{tot_fab:,.1f} Mtr")
    k2.metric("Under Production", fmt(tot_prod) + " Pcs")
    k3.metric("Received (RCVD)", fmt(tot_rcvd) + " Pcs")
    k4.metric("Pending Backlog", fmt(tot_rem) + " Pcs")
    k5.metric("Fulfillment Rate", f"{ful_rate:.1f}%")
    st.markdown("---")

    t1, t2 = st.tabs(["📊 Monthly Trend & Production Pipeline", "👥 Vendor Scorecard & Backlog Deep-Dive"])

    with t1:
        badge("📈 Monthly Performance Trends")
        c1, c2 = st.columns([1.35, 1])
        with c1:
            m_agg = filtered.groupby("Month", as_index=False).agg(
                {"Pcs Under Production": "sum", "RCVD (Pcs)": "sum", "Remaining (Pcs)": "sum"})
            m_agg["_o"] = m_agg["Month"].apply(month_sort_key)
            m_agg = m_agg.sort_values("_o").drop(columns=["_o"])
            fig_bar = go.Figure()
            fig_bar.add_trace(go.Bar(name="Under Production", x=m_agg["Month"], y=m_agg["Pcs Under Production"], marker_color="#2563eb"))
            fig_bar.add_trace(go.Bar(name="Received (RCVD)", x=m_agg["Month"], y=m_agg["RCVD (Pcs)"], marker_color="#059669"))
            fig_bar.add_trace(go.Bar(name="Pending Backlog", x=m_agg["Month"], y=m_agg["Remaining (Pcs)"], marker_color="#dc2626"))
            fig_bar.update_layout(title="Monthly Production vs Delivery vs Backlog (Pcs)", barmode="group", xaxis_title="Month")
            st.plotly_chart(style_fig(fig_bar, 350), **STRETCH)
        with c2:
            status_df = filtered["Production Status"].value_counts().reset_index()
            status_df.columns = ["Status", "Count"]
            color_map = {"Completed (100%)": "#059669", "In Progress": "#f59e0b",
                         "Pending / Not Started": "#dc2626", "No Orders": "#94a3b8"}
            fig_pie = px.pie(status_df, names="Status", values="Count", title="Order Status Distribution",
                             hole=0.48, color="Status", color_discrete_map=color_map)
            st.plotly_chart(style_fig(fig_pie, 350), **STRETCH)

        st.markdown("#### 📋 Month-by-Month Production Breakdown Matrix")
        m_display = filtered[["Fabricator", "Month", "Fabric Issue (mtr)", "Pcs Under Production", "RCVD (Pcs)",
                              "Remaining (Pcs)", "Monthly Incoming (Pcs)", "Production Status"]].copy()
        show_table(m_display, dec_cols=("Fabric Issue (mtr)",))

    with t2:
        badge("👥 Vendor Comparative Analytics")
        v1, v2 = st.columns([1.3, 1])
        fab_summary = filtered.groupby("Fabricator", as_index=False).agg({
            "Fabric Issue (mtr)": "sum", "Pcs Under Production": "sum", "RCVD (Pcs)": "sum",
            "Remaining (Pcs)": "sum", "Monthly Incoming (Pcs)": "sum",
        }).sort_values("Pcs Under Production", ascending=False)

        with v1:
            fig_vbar = go.Figure()
            fig_vbar.add_trace(go.Bar(name="Received Pcs", x=fab_summary["Fabricator"], y=fab_summary["RCVD (Pcs)"], marker_color="#059669"))
            fig_vbar.add_trace(go.Bar(name="Remaining Backlog", x=fab_summary["Fabricator"], y=fab_summary["Remaining (Pcs)"], marker_color="#dc2626"))
            fig_vbar.update_layout(title="Fabricator Completed vs Pending Backlog", barmode="stack")
            st.plotly_chart(style_fig(fig_vbar, 340), **STRETCH)
        with v2:
            fig_vpie = px.pie(fab_summary, names="Fabricator", values="Pcs Under Production",
                              title="Fabricator Production Share", hole=0.45)
            st.plotly_chart(style_fig(fig_vpie, 340), **STRETCH)

        st.markdown("#### 📋 Fabricator Performance Scorecard with Grand Totals")
        fab_summary["Fulfillment %"] = np.where(fab_summary["Pcs Under Production"] > 0,
                                                fab_summary["RCVD (Pcs)"] / fab_summary["Pcs Under Production"].replace(0, np.nan) * 100, 0.0)
        fab_summary["Avg Mtr/Pc"] = np.where(fab_summary["Pcs Under Production"] > 0,
                                             fab_summary["Fabric Issue (mtr)"] / fab_summary["Pcs Under Production"].replace(0, np.nan), 0.0)
        tp = fab_summary["Pcs Under Production"].sum()
        tot_row = pd.DataFrame([{
            "Fabricator": "GRAND TOTAL",
            "Fabric Issue (mtr)": fab_summary["Fabric Issue (mtr)"].sum(),
            "Pcs Under Production": tp,
            "RCVD (Pcs)": fab_summary["RCVD (Pcs)"].sum(),
            "Remaining (Pcs)": fab_summary["Remaining (Pcs)"].sum(),
            "Monthly Incoming (Pcs)": fab_summary["Monthly Incoming (Pcs)"].sum(),
            "Fulfillment %": (fab_summary["RCVD (Pcs)"].sum() / tp * 100) if tp > 0 else 0.0,
            "Avg Mtr/Pc": (fab_summary["Fabric Issue (mtr)"].sum() / tp) if tp > 0 else 0.0,
        }])
        show_table(pd.concat([fab_summary, tot_row], ignore_index=True),
                   pct_cols=("Fulfillment %",), dec_cols=("Fabric Issue (mtr)", "Avg Mtr/Pc"))

        if not df_consolidated.empty:
            with st.expander("🏛️ Consolidated Position Of Stock (ALL OVER Reference Table)"):
                c_tbl = df_consolidated[["Month", "Fabric Issue (mtr)", "Pcs Under Production", "RCVD (Pcs)",
                                         "Remaining (Pcs)", "Monthly Incoming (Pcs)"]]
                st.dataframe(c_tbl, **STRETCH, hide_index=True)


# -----------------------------------------------------------------------------
# 8. SAMPLE SUMMARY ENGINE
# -----------------------------------------------------------------------------
def parse_sample_summary_sheet(values):
    data = {
        "total_samples": 0, "approved": 0, "rejected": 0, "hold": 0,
        "on_process": 0, "approval_ratio": 0.0, "overdue_pcs": 0, "avg_delay": 0.0,
        "monthly_breakdown": [],
    }
    if not values:
        return data

    for r_idx, row in enumerate(values):
        joined = " ".join(str(c).upper() for c in row)
        if "TOTAL SAMPLES" in joined and "APPROVED" in joined:
            for check_r in range(r_idx + 1, min(r_idx + 4, len(values))):
                non_empty = [str(c).strip() for c in values[check_r] if str(c).strip()]
                nums = [float(num(pd.Series([v])).iloc[0]) for v in non_empty]
                if len(nums) >= 4 and sum(nums[:4]) > 0:
                    data["total_samples"], data["approved"], data["rejected"], data["hold"] = map(int, nums[:4])
                    if len(nums) >= 5: data["on_process"] = int(nums[4])
                    if len(nums) >= 6: data["approval_ratio"] = float(nums[5])
                    if len(nums) >= 7: data["overdue_pcs"] = int(nums[6])
                    if len(nums) >= 8: data["avg_delay"] = float(nums[7])
                    break

    for r_idx, row in enumerate(values):
        joined = " ".join(str(c).upper() for c in row)
        if "MONTH" in joined and ("APPROVED" in joined or "REJECTED" in joined):
            h_row = [str(c).strip().lower() for c in row]
            col_map = {}
            for col_i, h_val in enumerate(h_row):
                if "month" in h_val and "month" not in col_map: col_map["month"] = col_i
                elif "approved" in h_val and "approved" not in col_map: col_map["approved"] = col_i
                elif "rejected" in h_val and "rejected" not in col_map: col_map["rejected"] = col_i
                elif "hold" in h_val and "hold" not in col_map: col_map["hold"] = col_i
                elif "process" in h_val and "process" not in col_map: col_map["process"] = col_i
                elif "total" in h_val and "total" not in col_map: col_map["total"] = col_i

            m_col = col_map.get("month", 0)
            for d_idx in range(r_idx + 1, min(r_idx + 25, len(values))):
                d_row = values[d_idx]
                if m_col >= len(d_row): break
                m_name = str(d_row[m_col]).strip()
                if not m_name: continue
                if re.search(r"^total\b", m_name, re.I): break
                if not re.search(r"(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)", m_name, re.I): continue

                def get_num_at(k):
                    idx = col_map.get(k)
                    if idx is not None and idx < len(d_row):
                        return int(num(pd.Series([d_row[idx]])).iloc[0])
                    return 0

                app_val, rej_val = get_num_at("approved"), get_num_at("rejected")
                hld_val, prc_val = get_num_at("hold"), get_num_at("process")
                tot_val = get_num_at("total") or (app_val + rej_val + hld_val + prc_val)
                data["monthly_breakdown"].append({"Month": m_name, "Approved": app_val, "Rejected": rej_val,
                                                  "Hold": hld_val, "Process": prc_val, "Total": tot_val})

    if data["total_samples"] == 0 and data["monthly_breakdown"]:
        m_df = pd.DataFrame(data["monthly_breakdown"])
        if m_df["Total"].sum() > 0:
            data["approved"] = int(m_df["Approved"].sum())
            data["rejected"] = int(m_df["Rejected"].sum())
            data["hold"] = int(m_df["Hold"].sum())
            data["on_process"] = int(m_df["Process"].sum())
            data["total_samples"] = int(m_df["Total"].sum())
            if data["total_samples"] > 0:
                data["approval_ratio"] = data["approved"] / data["total_samples"] * 100
    return data


def render_sample_summary_dashboard(sheet_name, cfg):
    tab_title, raw_values = load_worksheet_smart(cfg["id"], cfg, signature_text="total samples")
    parsed = parse_sample_summary_sheet(raw_values)

    with st.sidebar:
        st.markdown("### 🔍 Sample Dashboard Filters")
        m_list = [m["Month"] for m in parsed["monthly_breakdown"]] or FY_MONTH_LABELS
        if "s_month" not in st.session_state:
            st.session_state["s_month"] = ["All"]
        sel_months = st.multiselect("Month", options=["All"] + m_list, key="s_month",
                                    on_change=handle_smart_all_filter, args=("s_month",))
        if "s_stat" not in st.session_state:
            st.session_state["s_stat"] = ["All"]
        sel_status = st.multiselect("Status Filter", options=["All", "Approved", "Rejected", "On Hold", "In Process"],
                                    key="s_stat", on_change=handle_smart_all_filter, args=("s_stat",))
        if st.button("🔄 Refresh Data", key="samp_ref"):
            st.cache_data.clear()
            st.rerun()

    st.markdown(
        f"""<div class="dashboard-hero">
        <h2>🔬 {html.escape(sheet_name)} · Executive Process & QA Hub</h2>
        <p>Active Source: <b>{html.escape(tab_title)}</b> · Real-Time Sampling & QA Workflow Monitoring 2026-27</p>
        </div>""",
        unsafe_allow_html=True,
    )

    df_m = pd.DataFrame(parsed["monthly_breakdown"]) if parsed["monthly_breakdown"] else \
        pd.DataFrame(columns=["Month", "Approved", "Rejected", "Hold", "Process", "Total"])
    if not df_m.empty and "All" not in sel_months and sel_months:
        df_m = df_m[df_m["Month"].isin(sel_months)]

    has_monthly = not df_m.empty and df_m["Total"].sum() > 0
    tot_s = df_m["Total"].sum() if has_monthly else parsed["total_samples"]
    app_s = df_m["Approved"].sum() if has_monthly else parsed["approved"]
    rej_s = df_m["Rejected"].sum() if has_monthly else parsed["rejected"]
    hld_s = df_m["Hold"].sum() if has_monthly else parsed["hold"]
    prc_s = df_m["Process"].sum() if has_monthly else parsed["on_process"]
    ratio = (app_s / tot_s * 100) if tot_s > 0 else parsed["approval_ratio"]

    k = st.columns(6)
    k[0].metric("Total Samples", fmt(tot_s) + " Pcs")
    k[1].metric("Approved", fmt(app_s) + " Pcs")
    k[2].metric("Approval Ratio", f"{ratio:.1f}%")
    k[3].metric("Rejected", fmt(rej_s) + " Pcs")
    k[4].metric("On Hold", fmt(hld_s) + " Pcs")
    k[5].metric("In Process", fmt(prc_s) + " Pcs")
    st.markdown("---")

    t1, t2 = st.tabs(["📊 Sample Pipeline & Approval Health", "📋 Monthly Breakdown & Workflow Matrix"])
    color_map = {"Approved": "#059669", "Rejected": "#dc2626", "On Hold": "#f59e0b", "In Process": "#2563eb"}
    with t1:
        badge("📊 Sample Funnel & Approval Ratio")
        status_summary = pd.DataFrame({"Status": ["Approved", "Rejected", "On Hold", "In Process"],
                                       "Count": [app_s, rej_s, hld_s, prc_s]})
        if "All" not in sel_status and sel_status:
            status_summary = status_summary[status_summary["Status"].isin(sel_status)]
        c1, c2 = st.columns([1.3, 1])
        with c1:
            fig_bar = px.bar(status_summary, x="Status", y="Count", color="Status", text="Count",
                             title="Sampling Outcomes & Volume (Pcs)", color_discrete_map=color_map)
            st.plotly_chart(style_fig(fig_bar, 340), **STRETCH)
        with c2:
            fig_pie = px.pie(status_summary, names="Status", values="Count", title="Sampling Outcome Share",
                             hole=0.48, color="Status", color_discrete_map=color_map)
            st.plotly_chart(style_fig(fig_pie, 340), **STRETCH)

        st.markdown("#### 📋 Sampling QA Process Health Summary")
        st.dataframe(pd.DataFrame([{
            "Category": "All Samples", "Total Inward": tot_s, "Approved (Passed)": app_s, "Rejected": rej_s,
            "Hold": hld_s, "Active In Process": prc_s, "Pass Ratio (%)": f"{ratio:.1f}%",
        }]), **STRETCH, hide_index=True)

    with t2:
        badge("📅 Monthly Detailed Progression")
        if not df_m.empty:
            df_display = df_m.copy()
            df_display["Approval %"] = np.where(df_display["Total"] > 0,
                                                df_display["Approved"] / df_display["Total"].replace(0, np.nan) * 100, 0.0)
            tot = df_display["Total"].sum()
            df_display = pd.concat([df_display, pd.DataFrame([{
                "Month": "GRAND TOTAL", "Approved": df_display["Approved"].sum(), "Rejected": df_display["Rejected"].sum(),
                "Hold": df_display["Hold"].sum(), "Process": df_display["Process"].sum(), "Total": tot,
                "Approval %": (df_display["Approved"].sum() / tot * 100) if tot > 0 else 0.0,
            }])], ignore_index=True)
            show_table(df_display, pct_cols=("Approval %",))
        else:
            st.info("Monthly progression table sheet me blank hai. Headline summary statistics display ho rahe hain.")

        with st.expander("📄 View Source Sheet Raw Matrix"):
            if raw_values:
                width = max(len(r) for r in raw_values)
                st.dataframe(pd.DataFrame([r + [""] * (width - len(r)) for r in raw_values]),
                             **STRETCH, hide_index=True)


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
