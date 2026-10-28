# -----------------------------------------------------------------------------
# 7. COMMON HELPERS (Sample + Fabricator dashboards)
# -----------------------------------------------------------------------------
PALETTE = ["#2563eb", "#059669", "#f59e0b", "#dc2626", "#7c3aed",
           "#0891b2", "#db2777", "#65a30d", "#ea580c", "#475569"]
px.defaults.color_discrete_sequence = PALETTE
STATUS_COLORS = {"APPROVED": "#059669", "REJECTED": "#dc2626", "HOLD": "#f59e0b", "PROCESS": "#2563eb"}
MONTH_ABBR = [m[:3].lower() for m in MONTHS]
BLANKS = {"", "nan", "none", "-", "—", "–", "n/a", "na", "#n/a", "#div/0!", "#ref!", "#value!", "#error!"}
ID_COL_RE = re.compile(r"^(s\.?\s*no\.?|sr\.?\s*no\.?|sl\.?\s*no\.?|serial.*|#|id|index)$", re.I)
TOTAL_RE = re.compile(r"^(grand\s*|sub\s*|net\s*)?total\b", re.I)
DASH_RE = re.compile(r"dashboard", re.I)


def is_number_like(s):
    t = re.sub(r"[,\s₹$€£%()\xa0]", "", str(s))
    if t in ("", "-", "."):
        return False
    try:
        float(t)
        return True
    except ValueError:
        return False


def num_nan(s):
    """Text -> float (blank / #DIV/0! = NaN)."""
    if not isinstance(s, pd.Series):
        s = pd.Series(s)
    text = s.astype(str).str.replace("\xa0", "", regex=False).str.strip()
    text = text.mask(text.str.lower().isin(BLANKS))
    neg = text.str.match(r"^\(.*\)$", na=False)
    cleaned = text.str.replace(",", "", regex=False).str.replace(r"[^0-9.\-]", "", regex=True)
    cleaned = cleaned.mask(neg, "-" + cleaned.str.replace("-", "", regex=False))
    out = pd.to_numeric(cleaned, errors="coerce")
    return pd.Series(np.asarray(out, dtype="float64"), index=s.index)


def date_series(s):
    s = s.astype(str).str.strip()
    s = s.mask(s.str.lower().isin(BLANKS))
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        res = pd.to_datetime(s, errors="coerce", dayfirst=True)
        miss = res.isna() & s.notna()
        if miss.any():
            res[miss] = pd.to_datetime(s[miss], errors="coerce", dayfirst=False)
    return res


def make_unique(names):
    seen, out = {}, []
    for i, n in enumerate(names):
        n = re.sub(r"\s+", " ", str(n)).strip() or f"Column {i + 1}"
        if n in seen:
            seen[n] += 1
            n = f"{n} ({seen[n]})"
        else:
            seen[n] = 1
        out.append(n)
    return out


def detect_header_row(values, scan=15):
    head = values[:scan]
    counts = [sum(1 for c in r if str(c).strip()) for r in head]
    if not counts or max(counts) == 0:
        return 0
    best = max(counts)
    for i, r in enumerate(head):
        filled = [str(c).strip() for c in r if str(c).strip()]
        if len(filled) >= max(2, 0.6 * best):
            if sum(is_number_like(c) for c in filled) / len(filled) < 0.4:
                return i
    return counts.index(best)


def split_table(values):
    """Sheet rows -> DataFrame (all text). Title rows upar aur TOTAL rows hata di jaati hain."""
    hdr = detect_header_row(values)
    body = values[hdr + 1:]
    width = max([len(values[hdr])] + [len(r) for r in body]) if body else len(values[hdr])
    header = make_unique(list(values[hdr]) + [""] * (width - len(values[hdr])))
    body = [list(r) + [""] * (width - len(r)) for r in body]
    df = pd.DataFrame(body, columns=header).astype(str).apply(lambda c: c.str.strip())
    df = df.loc[(df != "").any(axis=1)]
    df = df.loc[:, (df != "").any(axis=0)]
    non_id = [c for c in df.columns if not ID_COL_RE.match(c.strip())]
    if non_id:   # sirf S.No bhari hui (khali) rows hata do
        df = df.loc[(df[non_id] != "").any(axis=1)]

    def first_text(row):
        for v in row:
            if v and not is_number_like(v):
                return v
        return ""

    if len(df):
        is_total = df.apply(lambda r: bool(TOTAL_RE.match(first_text(r))), axis=1)
        df = df[~is_total]
    return df.reset_index(drop=True)


def norm_name(s):
    return re.sub(r"[^a-z0-9]", "", str(s).lower())


def find_tab(titles, wanted, exclude_re=None):
    nw = norm_name(wanted)
    pool = [t for t in titles if not (exclude_re and exclude_re.search(t))]
    for t in pool:
        if norm_name(t) == nw:
            return t
    for t in pool:
        if nw and nw in norm_name(t):
            return t
    return None


def month_name_of(x):
    t = str(x).strip().lower()[:3]
    return MONTHS[MONTH_ABBR.index(t)] if t in MONTH_ABBR else ""


def month_idx(m):
    return MONTHS.index(m) if m in MONTHS else 99


@st.cache_data(ttl=300, show_spinner="Loading sheet tabs...")
def list_tabs(sheet_id):
    return [(ws.title, ws.id) for ws in get_client().open_by_key(sheet_id).worksheets()]


@st.cache_data(ttl=300, show_spinner="Loading live data from Google Sheet...")
def load_tab_values(sheet_id, tab_title):
    return get_client().open_by_key(sheet_id).worksheet(tab_title).get_all_values()


def show_access_error(e):
    email = ""
    try:
        email = st.secrets["gcp_service_account"]["client_email"]
    except Exception:
        pass
    st.error("Could not open this Google Sheet. Share it (Viewer access is enough) with the service account"
             + (f": **{email}**" if email else " email from your Streamlit secrets.") + " and refresh.")
    st.caption(f"Technical detail: {type(e).__name__}: {e}")


def style_fig(fig, height=380):
    fig.update_layout(height=height, margin=dict(l=10, r=10, t=55, b=10), legend_title_text="",
                      font=dict(size=12), title_font_size=15)
    return fig


def fmt_val(x, kind="int"):
    if x is None or pd.isna(x):
        return "—"
    if kind == "pct":
        return f"{x:.1f}%"
    if kind == "days":
        return f"{x:.1f} d"
    return f"{x:,.0f}"


def render_insights(items):
    if items:
        cards = "".join(f'<div class="insight">{i}</div>' for i in items)
        st.markdown(f'<div class="insight-grid">{cards}</div>', unsafe_allow_html=True)


def section(title, sub=""):
    st.markdown(f'<div class="sec-title">{html.escape(title)}</div>' +
                (f'<div class="sec-sub">{html.escape(sub)}</div>' if sub else ""), unsafe_allow_html=True)


# ---------- KPI cards with month comparison ----------
def compute_kpis(defs, d, d_nm, sel_months, mode):
    """Returns (current values, comparison values or None, note)."""
    cur = {x["label"]: x["fn"](d) for x in defs}
    if not sel_months:
        return cur, None, ""
    sel = sorted(sel_months, key=month_idx)
    first, n = month_idx(sel[0]), len(sel)
    present = [m for m in MONTHS if m in set(d_nm["Month"])]
    if mode == "Previous month(s)":
        pm = MONTHS[max(0, first - n):first]
        if not pm:
            return cur, None, "April is the first month of the FY - nothing earlier to compare with."
        base = d_nm[d_nm["Month"].isin(pm)]
        prev = {x["label"]: x["fn"](base) for x in defs}
        return cur, prev, f"{', '.join(sel)} vs previous {', '.join(pm)}"
    em = [m for m in present if month_idx(m) < first]
    if not em:
        return cur, None, "No earlier month in the data to average."
    base = d_nm[d_nm["Month"].isin(em)]
    prev = {}
    for x in defs:
        v = x["fn"](base)
        prev[x["label"]] = v / len(em) * n if x["additive"] else v
    return cur, prev, f"{', '.join(sel)} vs average of earlier months ({em[0]} → {em[-1]})"


def kpi_cards(defs, cur, prev, cols=4):
    cards = []
    for x in defs:
        v, kind = cur[x["label"]], x["fmt"]
        dtxt, tone, sub = "&nbsp;", "flat", ""
        if prev is not None:
            p = prev[x["label"]]
            if kind == "pct":
                raw = v - p
                txt = f"{raw:+.1f} pp"
            elif p == 0:
                raw = v - p
                txt = "new" if v else "0%"
            else:
                raw = (v - p) / abs(p) * 100
                txt = f"{raw:+.1f}%"
            arrow = "▲" if raw > 0.05 else ("▼" if raw < -0.05 else "■")
            if abs(raw) < 0.05:
                tone = "flat"
            elif x["inverse"]:
                tone = "bad" if raw > 0 else "good"
            else:
                tone = "good" if raw > 0 else "bad"
            dtxt = f"{arrow} {txt}"
            sub = f"vs {fmt_val(p, kind)}"
        cards.append(
            f'<div class="kpi" style="--c:{x["color"]}"><div class="lbl">{html.escape(x["label"])}</div>'
            f'<div class="val">{fmt_val(v, kind)}</div><div class="dlt {tone}">{dtxt} <span class="sub">{sub}</span></div></div>')
    st.markdown(f'<div class="kpi-grid" style="grid-template-columns:repeat({cols},1fr)">{"".join(cards)}</div>',
                unsafe_allow_html=True)


def month_filter_block(months, k):
    """Month multiselect + compare mode. Returns (selected months, compare mode)."""
    sel = st.multiselect("📅 Month", months, key=k("m"))
    mode = "Previous month(s)"
    if sel:
        mode = st.radio("Compare with", ["Previous month(s)", "Average of earlier months"], key=k("cmp"))
    return sel, mode


def hero(title, subtitle, chips):
    chips_html = "".join(f'<span class="chip">{html.escape(c)}</span>' for c in chips)
    st.markdown(f'<div class="dashboard-hero"><h2>{html.escape(title)}</h2><p>{html.escape(subtitle)}</p>{chips_html}</div>',
                unsafe_allow_html=True)


# -----------------------------------------------------------------------------
# 8. SAMPLE DASHBOARD  (sheet: SAMPLE SUMMARY 2026-27, tab: 2026-27)
# -----------------------------------------------------------------------------
STATUS_ORDER = ["APPROVED", "REJECTED", "HOLD", "PROCESS"]
RISK_LABELS = ["On Time (≤0)", "Low (1-7 d)", "Medium (8-15 d)", "High (15+ d)"]
RISK_COLORS = ["#059669", "#f59e0b", "#ea580c", "#dc2626"]
DATE_PRIORITY = [r"sample\s*process\s*date", r"process\s*date", r"complete", r"recd|receiv", r"showcase"]


def status_group(s):
    u = str(s).upper().strip()
    if u.lower() in BLANKS:
        return "(BLANK)"
    for key, name in (("APPROV", "APPROVED"), ("REJECT", "REJECTED"), ("HOLD", "HOLD"), ("PROCESS", "PROCESS")):
        if key in u:
            return name
    return u


def find_col(df, pats):
    for pat in pats:
        for c in df.columns:
            if re.search(pat, c.lower()):
                return c
    return None


def date_candidates(df):
    out = []
    for c in df.columns:
        s = df[c].astype(str).str.strip()
        s = s[~s.str.lower().isin(BLANKS)]
        if s.empty or s.map(is_number_like).mean() >= 0.8 or s.str.contains(r"\d").mean() < 0.9:
            continue
        if date_series(s).notna().mean() >= 0.6:
            out.append(c)
    return out


def sample_frame(df, date_col):
    idx = df.index

    def txt(col, upper=True):
        s = df[col].astype(str).str.strip() if col else pd.Series("", index=idx)
        s = s.where(~s.str.lower().isin(BLANKS), "")
        return s.str.upper() if upper else s

    c_des = find_col(df, [r"designer"])
    c_fab = find_col(df, [r"fabricator"])
    c_sta = find_col(df, [r"^status", r"status"])
    c_qty = find_col(df, [r"sample\s*qty", r"\bqty\b", r"quantity"])
    c_del = find_col(df, [r"delay\s*days", r"^delay(?!.*reason)"])
    c_rea = find_col(df, [r"delay\s*reason"])
    c_ven = find_col(df, [r"vendor"])

    d = pd.DataFrame(index=idx)
    d["Designer"] = txt(c_des)
    d["Fabricator"] = txt(c_fab)
    d["Status"] = txt(c_sta).map(status_group)
    d["Vendor"] = txt(c_ven)
    d["Delay Reason"] = txt(c_rea)
    d["Qty"] = num_nan(df[c_qty]).fillna(0.0) if c_qty else pd.Series(1.0, index=idx)
    delay = num_nan(df[c_del]).fillna(0.0) if c_del else pd.Series(0.0, index=idx)
    d["Delay Days"] = delay.mask(delay.abs() > 3000, 0.0)          # sheet ke #formula garbage (-46,126) ko 0 maana
    d["Delay Risk"] = pd.cut(d["Delay Days"], bins=[-np.inf, 0, 7, 15, np.inf], labels=RISK_LABELS).astype(str)
    dt = date_series(df[date_col]) if date_col else pd.Series(pd.NaT, index=idx)
    d["Date"] = pd.to_datetime(dt, errors="coerce")
    d["Month"] = d["Date"].dt.month_name().fillna("")
    keep = (d["Designer"] != "") | (d["Fabricator"] != "") | (d["Status"] != "(BLANK)") | (d["Qty"] > 0)
    d = d[keep].copy()
    d["Designer"] = d["Designer"].replace("", "(BLANK)")
    d["Fabricator"] = d["Fabricator"].replace("", "(BLANK)")
    used = {"Designer": c_des, "Fabricator": c_fab, "Status": c_sta, "Qty": c_qty, "Delay days": c_del, "Date (for Month)": date_col}
    return d.reset_index(drop=True), used


def status_pivot(d, dim):
    pv = d.pivot_table(index=dim, columns="Status", values="Qty", aggfunc="sum", fill_value=0)
    cols = [s for s in STATUS_ORDER if s in pv.columns] + sorted(c for c in pv.columns if c not in STATUS_ORDER)
    pv = pv[cols]
    pv["TOTAL"] = pv.sum(axis=1)
    return pv


def status_cmap(statuses):
    others = [s for s in statuses if s not in STATUS_COLORS]
    cmap = dict(STATUS_COLORS)
    for i, s in enumerate(others):
        cmap[s] = ["#64748b", "#0891b2", "#db2777", "#65a30d"][i % 4]
    return cmap


def sample_kpi_defs():
    def st_qty(name):
        return lambda d: float(d.loc[d["Status"] == name, "Qty"].sum())

    def ratio(d):
        t = d["Qty"].sum()
        return float(d.loc[d["Status"] == "APPROVED", "Qty"].sum() / t * 100) if t else 0.0

    def avg_delay(d):
        x = d.loc[d["Delay Days"] > 0, "Delay Days"]
        return float(x.mean()) if len(x) else 0.0

    return [
        {"label": "Total Samples", "fn": lambda d: float(d["Qty"].sum()), "fmt": "int", "inverse": False, "additive": True, "color": "#2563eb"},
        {"label": "Approved", "fn": st_qty("APPROVED"), "fmt": "int", "inverse": False, "additive": True, "color": "#059669"},
        {"label": "Rejected", "fn": st_qty("REJECTED"), "fmt": "int", "inverse": True, "additive": True, "color": "#dc2626"},
        {"label": "On Hold", "fn": st_qty("HOLD"), "fmt": "int", "inverse": True, "additive": True, "color": "#f59e0b"},
        {"label": "On Process", "fn": st_qty("PROCESS"), "fmt": "int", "inverse": False, "additive": True, "color": "#0891b2"},
        {"label": "Approval Ratio", "fn": ratio, "fmt": "pct", "inverse": False, "additive": False, "color": "#16a34a"},
        {"label": "Overdue (>0 days)", "fn": lambda d: float(d.loc[d["Delay Days"] > 0, "Qty"].sum()), "fmt": "int",
         "inverse": True, "additive": True, "color": "#ea580c"},
        {"label": "Avg Delay Days", "fn": avg_delay, "fmt": "days", "inverse": True, "additive": False, "color": "#7c3aed"},
    ]


def sample_insights(d, d_nm, cur, prev):
    items = []
    total = d["Qty"].sum()
    if total <= 0:
        return items
    pv = status_pivot(d, "Designer").sort_values("TOTAL", ascending=False)
    t = pv.iloc[0]
    items.append(f"🎨 Top designer <b>{html.escape(str(pv.index[0]))}</b> – {t['TOTAL']:,.0f} samples ({t['TOTAL'] / total * 100:.1f}% of total).")
    if "APPROVED" in pv.columns:
        big = pv[pv["TOTAL"] >= max(5, total * 0.02)]
        if len(big) >= 2:
            r = (big["APPROVED"] / big["TOTAL"] * 100).sort_values(ascending=False)
            items.append(f"✅ Best approval ratio: <b>{html.escape(str(r.index[0]))}</b> ({r.iloc[0]:.1f}%); "
                         f"lowest: <b>{html.escape(str(r.index[-1]))}</b> ({r.iloc[-1]:.1f}%).")
    if "REJECTED" in d["Status"].values:
        fp = status_pivot(d[d["Fabricator"] != "(BLANK)"], "Fabricator")
        if "REJECTED" in fp.columns and len(fp) and fp["REJECTED"].max() > 0:
            f = fp["REJECTED"].idxmax()
            items.append(f"❌ Most rejections come from <b>{html.escape(str(f))}</b> ({fp.loc[f, 'REJECTED']:,.0f} pcs).")
    hold = d.loc[d["Status"] == "HOLD", "Qty"].sum()
    proc = d.loc[d["Status"] == "PROCESS", "Qty"].sum()
    if hold or proc:
        items.append(f"⏳ <b>{hold:,.0f}</b> samples on hold and <b>{proc:,.0f}</b> still in process.")
    od = d.loc[d["Delay Days"] > 0, "Qty"].sum()
    if od > 0:
        items.append(f"🚨 <b>{od:,.0f}</b> samples are overdue ({od / total * 100:.1f}%).")
    mt = d_nm[d_nm["Month"] != ""].groupby("Month")["Qty"].sum()
    if len(mt):
        items.append(f"📅 Busiest month: <b>{html.escape(mt.idxmax())}</b> ({mt.max():,.0f} samples).")
    if prev is not None:
        for lbl in ("Total Samples", "Approved", "Rejected"):
            if prev.get(lbl):
                ch = (cur[lbl] - prev[lbl]) / abs(prev[lbl]) * 100
                items.append(f"{'▲' if ch > 0 else '▼'} {lbl} <b>{ch:+.1f}%</b> vs comparison period.")
    return items


def sample_dashboard(d_all, used, ctx):
    k = lambda s: f"{ctx['key']}_{s}"
    keys = {"multi": [], "single": []}
    with st.sidebar:
        st.markdown("### 🔎 Filters")
        months = [m for m in MONTHS if m in set(d_all["Month"])]
        sel_months, mode = month_filter_block(months, k)
        f_des = st.multiselect("🎨 Designer", sorted(d_all["Designer"].unique()), key=k("d"))
        stat_opts = [s for s in STATUS_ORDER if s in set(d_all["Status"])] + sorted(set(d_all["Status"]) - set(STATUS_ORDER))
        f_sta = st.multiselect("📌 Status", stat_opts, key=k("s"))
        f_fab = st.multiselect("🧵 Fabricator", sorted(d_all["Fabricator"].unique()), key=k("f"))
        f_risk = st.selectbox("⏰ Delay Risk", ["ALL"] + RISK_LABELS, key=k("r"))
        keys["multi"] = [k("m"), k("d"), k("s"), k("f")]
        keys["single"] = [(k("r"), "ALL")]

        def _reset():
            for kk in keys["multi"]:
                st.session_state[kk] = []
            for kk, v in keys["single"]:
                st.session_state[kk] = v

        st.button("↺ Reset filters", on_click=_reset, key=k("reset"))
        if st.button("🔄 Refresh data", key=k("refresh")):
            st.cache_data.clear()
            st.rerun()

    d_nm = d_all
    for col, vals in (("Designer", f_des), ("Status", f_sta), ("Fabricator", f_fab)):
        if vals:
            d_nm = d_nm[d_nm[col].isin(vals)]
    if f_risk != "ALL":
        d_nm = d_nm[d_nm["Delay Risk"] == f_risk]
    d = d_nm[d_nm["Month"].isin(sel_months)] if sel_months else d_nm

    hero(f"🧪 {ctx['title']}", "Executive sample performance & process dashboard 2026-27",
         [f"Tab: {ctx['tab']}", f"{d['Qty'].sum():,.0f} samples in view", f"{len(d):,} rows"] +
         ([f"Months: {', '.join(sorted(sel_months, key=month_idx))}"] if sel_months else []))
    if d.empty:
        st.warning("No rows match the selected filters.")
        st.stop()

    t1, t2 = st.tabs(["📊 Overview", "📋 Tables & Data"])
    with t1:
        defs = sample_kpi_defs()
        cur, prev, note = compute_kpis(defs, d, d_nm, sel_months, mode)
        if sel_months:
            st.caption("📊 " + (note or "") + "  ·  green = better, red = worse")
        else:
            st.caption("💡 Select a month in the sidebar to see how each KPI changed vs previous month(s).")
        kpi_cards(defs[:4], cur, prev)
        kpi_cards(defs[4:], cur, prev)

        section("💡 Key insights")
        render_insights(sample_insights(d, d_nm, cur, prev))

        cmap = status_cmap(sorted(set(d_nm["Status"])))
        has_month = (d_nm["Month"] != "").any()
        if has_month:
            section("Monthly sample status", "All months are shown (month filter ignored here) so the trend stays visible.")
            mp = status_pivot(d_nm[d_nm["Month"] != ""], "Month")
            mp = mp.reindex([m for m in MONTHS if m in mp.index])
            tbl = mp.reset_index()
            tbl.loc[len(tbl)] = ["TOTAL"] + [mp[c].sum() for c in mp.columns]
            a, b = st.columns([1, 1.25])
            with a:
                st.dataframe(tbl, use_container_width=True, hide_index=True, height=35 * (len(tbl) + 1) + 3)
            with b:
                long = mp.drop(columns="TOTAL").reset_index().melt(id_vars="Month", var_name="Status", value_name="Samples")
                fig = px.bar(long, x="Month", y="Samples", color="Status", barmode="stack", color_discrete_map=cmap,
                             category_orders={"Month": MONTHS}, title="Monthly sample status distribution")
                st.plotly_chart(style_fig(fig, 380), use_container_width=True)
            a, b = st.columns([1.5, 1])
            with a:
                tr = mp.reset_index().melt(id_vars="Month", var_name="Status", value_name="Samples")
                fig = px.line(tr, x="Month", y="Samples", color="Status", markers=True, color_discrete_map={**cmap, "TOTAL": "#0f172a"},
                              category_orders={"Month": MONTHS}, title="Monthly sample volume trend")
                st.plotly_chart(style_fig(fig, 380), use_container_width=True)
            with b:
                sg = d.groupby("Status")["Qty"].sum().reset_index()
                fig = px.pie(sg[sg["Qty"] > 0], names="Status", values="Qty", hole=0.55, color="Status",
                             color_discrete_map=cmap, title="Status share")
                st.plotly_chart(style_fig(fig, 380), use_container_width=True)

        section("Designer & Fabricator performance")
        a, b = st.columns(2)
        dp = status_pivot(d, "Designer").sort_values("TOTAL", ascending=False)
        with a:
            long = dp.head(10).drop(columns="TOTAL").reset_index().melt(id_vars="Designer", var_name="Status", value_name="Samples")
            fig = px.bar(long, x="Designer", y="Samples", color="Status", barmode="stack", color_discrete_map=cmap,
                         title="Designer-wise samples by status (top 10)")
            st.plotly_chart(style_fig(fig), use_container_width=True)
        with b:
            fp = status_pivot(d[d["Fabricator"] != "(BLANK)"], "Fabricator").sort_values("TOTAL", ascending=False) \
                if (d["Fabricator"] != "(BLANK)").any() else pd.DataFrame()
            if len(fp):
                long = fp.head(10).drop(columns="TOTAL").reset_index().melt(id_vars="Fabricator", var_name="Status", value_name="Samples")
                fig = px.bar(long, x="Fabricator", y="Samples", color="Status", barmode="stack", color_discrete_map=cmap,
                             title="Fabricator-wise samples by status (top 10)")
                st.plotly_chart(style_fig(fig), use_container_width=True)
        a, b = st.columns(2)
        with a:
            if "APPROVED" in dp.columns:
                ar = dp[dp["TOTAL"] > 0].head(12).copy()
                ar["Approval %"] = (ar["APPROVED"] / ar["TOTAL"] * 100).round(1)
                ar = ar.sort_values("Approval %").reset_index()
                fig = px.bar(ar, x="Approval %", y="Designer", orientation="h", text_auto=".1f",
                             color="Approval %", color_continuous_scale=["#dc2626", "#f59e0b", "#059669"], range_color=[0, 100],
                             title="Approval ratio by designer (top 12 by volume)")
                st.plotly_chart(style_fig(fig), use_container_width=True)
        with b:
            rk = d.groupby("Delay Risk")["Qty"].sum().reindex(RISK_LABELS).fillna(0).reset_index()
            fig = px.bar(rk, x="Delay Risk", y="Qty", text_auto=".3s", color="Delay Risk",
                         color_discrete_map=dict(zip(RISK_LABELS, RISK_COLORS)), title="Samples by delay risk")
            fig.update_layout(showlegend=False)
            st.plotly_chart(style_fig(fig), use_container_width=True)

    with t2:
        section("Designer-wise summary")
        dtab = status_pivot(d, "Designer").sort_values("TOTAL", ascending=False)
        if "APPROVED" in dtab.columns:
            dtab["Approval %"] = (dtab["APPROVED"] / dtab["TOTAL"].where(dtab["TOTAL"] > 0) * 100).round(1)
        st.dataframe(dtab.reset_index(), use_container_width=True, hide_index=True)
        section("Fabricator-wise summary")
        ftab = status_pivot(d, "Fabricator").sort_values("TOTAL", ascending=False)
        if "APPROVED" in ftab.columns:
            ftab["Approval %"] = (ftab["APPROVED"] / ftab["TOTAL"].where(ftab["TOTAL"] > 0) * 100).round(1)
        st.dataframe(ftab.reset_index(), use_container_width=True, hide_index=True)
        section("Filtered data")
        show = d.drop(columns=["Date"]).assign(**{"Date": d["Date"].dt.strftime("%d-%m-%Y")})
        st.dataframe(show, use_container_width=True, hide_index=True, height=360)
        st.download_button("⬇️ Download filtered data (CSV)", show.to_csv(index=False).encode("utf-8"),
                           file_name="sample_data.csv", mime="text/csv", key=k("dl"))
        with st.expander("Columns used from the sheet"):
            st.dataframe(pd.DataFrame([{"Meaning": a, "Sheet column": b or "— not found —"} for a, b in used.items()]),
                         use_container_width=True, hide_index=True)


def render_samples(sheet_name, cfg):
    sid = cfg["id"]
    try:
        titles = [t for t, _ in list_tabs(sid)]
    except Exception as e:
        show_access_error(e)
        st.stop()
    default = None
    for w in cfg.get("data_tabs", []):
        default = find_tab(titles, w, DASH_RE) or default
    with st.sidebar:
        with st.expander("⚙️ Settings"):
            tab = st.selectbox("Data tab", titles, index=titles.index(default) if default in titles else 0, key=f"sdt_{sid}")
    try:
        values = load_tab_values(sid, tab)
    except Exception as e:
        show_access_error(e)
        st.stop()
    if not values or not any(str(c).strip() for r in values for c in r):
        st.warning(f"The tab '{tab}' is empty. Pick the data tab under ⚙️ Settings in the sidebar.")
        st.stop()
    df = split_table(values)
    if df.empty:
        st.warning("Header found but no data rows below it.")
        st.stop()
    cands = date_candidates(df)
    pref = next((c for pat in DATE_PRIORITY for c in cands if re.search(pat, c.lower())), cands[0] if cands else None)
    with st.sidebar:
        with st.expander("⚙️ Settings"):
            date_col = st.selectbox("Month is based on", ["(none)"] + cands, index=(cands.index(pref) + 1) if pref else 0,
                                    key=f"sdc_{sid}")
    d_all, used = sample_frame(df, None if date_col == "(none)" else date_col)
    if d_all.empty:
        st.warning("No sample rows found in this tab.")
        st.stop()
    sample_dashboard(d_all, used, {"key": f"{sid}_{tab}", "title": sheet_name, "tab": tab})


# -----------------------------------------------------------------------------
# 9. FABRICATOR DASHBOARD  (sheet: FABRICATOR REPORT SHEET 2026-27, tab: MONTHWISE SUMMARY)
# -----------------------------------------------------------------------------
FI, PU, RC, RM, INC = "Fabric Issue (mtr)", "Pcs Under Production", "Received", "Remaining", "Monthly Incoming"
FAB_METRICS = [FI, PU, RC, RM, INC]


def map_metric(h):
    t = str(h).lower()
    if "incoming" in t:
        return INC
    if "issue" in t:
        return FI
    if "under" in t or "production" in t:
        return PU
    if "rcvd" in t or "receiv" in t:
        return RC
    if "remain" in t or "pending" in t or "balance" in t:
        return RM
    return None


def parse_monthwise(values):
    """'Position Of Stock <NAME>' blocks (side by side / stacked) -> long DataFrame."""
    if not values:
        return pd.DataFrame()
    w = max(len(r) for r in values)
    grid = [[str(c).strip() for c in r] + [""] * (w - len(r)) for r in values]
    n = len(grid)
    recs = []
    for r in range(n):
        for c in range(w):
            if grid[r][c].lower() != "month":
                continue
            j, heads = c, []
            while j < w and grid[r][j]:
                heads.append(grid[r][j])
                j += 1
            metrics_map = {c + 1 + i: map_metric(h) for i, h in enumerate(heads[1:])}
            if not any(metrics_map.values()):
                continue
            title = ""
            for rr in range(r - 1, max(-1, r - 4), -1):
                if grid[rr][c]:
                    title = grid[rr][c]
                    break
            name = re.sub(r"^position\s+of\s+stock\s*", "", title, flags=re.I).strip() or f"Block {len(recs) + 1}"
            overall = bool(re.search(r"all\s*over", name, re.I))
            blanks = 0
            for rr in range(r + 1, min(n, r + 40)):
                lab = grid[rr][c]
                if not lab:
                    blanks += 1
                    if blanks > 3:
                        break
                    continue
                blanks = 0
                if TOTAL_RE.match(lab):
                    break
                m = month_name_of(lab)
                if not m:
                    break
                rec = {"Fabricator": name, "Month": m, "Overall": overall}
                for col, metric in metrics_map.items():
                    if metric:
                        rec[metric] = float(num_nan(pd.Series([grid[rr][col]])).fillna(0.0).iloc[0])
                recs.append(rec)
    if not recs:
        return pd.DataFrame()
    df = pd.DataFrame(recs)
    for m in FAB_METRICS:
        if m not in df.columns:
            df[m] = 0.0
        df[m] = df[m].fillna(0.0)
    return df


def fab_kpi_defs():
    def pct(d):
        p = d[PU].sum()
        return float(d[RC].sum() / p * 100) if p else 0.0

    def active(d):
        x = d[(d[FI] + d[PU] + d[RC] + d[INC]) > 0]
        return float(x["Fabricator"].nunique())

    return [
        {"label": "Fabric Issued (mtr)", "fn": lambda d: float(d[FI].sum()), "fmt": "int", "inverse": False, "additive": True, "color": "#2563eb"},
        {"label": "Pcs Under Production", "fn": lambda d: float(d[PU].sum()), "fmt": "int", "inverse": False, "additive": True, "color": "#7c3aed"},
        {"label": "Received", "fn": lambda d: float(d[RC].sum()), "fmt": "int", "inverse": False, "additive": True, "color": "#059669"},
        {"label": "Remaining", "fn": lambda d: float(d[RM].sum()), "fmt": "int", "inverse": True, "additive": True, "color": "#dc2626"},
        {"label": "Received %", "fn": pct, "fmt": "pct", "inverse": False, "additive": False, "color": "#16a34a"},
        {"label": "Monthly Incoming", "fn": lambda d: float(d[INC].sum()), "fmt": "int", "inverse": False, "additive": True, "color": "#0891b2"},
        {"label": "Active Fabricators", "fn": active, "fmt": "int", "inverse": False, "additive": False, "color": "#f59e0b"},
    ]


def fab_summary(d):
    g = d.groupby("Fabricator")[FAB_METRICS].sum().reset_index()
    g["Received %"] = (g[RC] / g[PU].where(g[PU] > 0) * 100).round(1)
    return g.sort_values(PU, ascending=False).reset_index(drop=True)


def fab_insights(d, d_nm, cur, prev):
    items = []
    g = fab_summary(d)
    if len(g) and g[PU].sum() > 0:
        t = g.iloc[0]
        items.append(f"🧵 <b>{html.escape(str(t['Fabricator']))}</b> has the most pcs under production: {t[PU]:,.0f} "
                     f"({t[PU] / g[PU].sum() * 100:.1f}% of all).")
    if len(g) and g[RM].sum() > 0:
        t = g.sort_values(RM, ascending=False).iloc[0]
        items.append(f"⏳ Highest remaining: <b>{html.escape(str(t['Fabricator']))}</b> – {t[RM]:,.0f} pcs "
                     f"({t[RM] / g[RM].sum() * 100:.1f}% of all remaining).")
    gg = g[g[PU] > 0].dropna(subset=["Received %"])
    if len(gg) >= 2:
        lo, hi = gg.sort_values("Received %").iloc[0], gg.sort_values("Received %").iloc[-1]
        items.append(f"✅ Best received %: <b>{html.escape(str(hi['Fabricator']))}</b> ({hi['Received %']:.1f}%); "
                     f"lowest: <b>{html.escape(str(lo['Fabricator']))}</b> ({lo['Received %']:.1f}%).")
    mt = d_nm.groupby("Month")[PU].sum()
    if len(mt) and mt.max() > 0:
        items.append(f"📅 Busiest month: <b>{html.escape(mt.idxmax())}</b> ({mt.max():,.0f} pcs under production).")
    if prev is not None:
        for lbl in ("Pcs Under Production", "Received", "Remaining"):
            if prev.get(lbl):
                ch = (cur[lbl] - prev[lbl]) / abs(prev[lbl]) * 100
                items.append(f"{'▲' if ch > 0 else '▼'} {lbl} <b>{ch:+.1f}%</b> vs comparison period.")
    return items


def fabricator_dashboard(df_all, overall, ctx):
    k = lambda s: f"{ctx['key']}_{s}"
    with st.sidebar:
        st.markdown("### 🔎 Filters")
        months = [m for m in MONTHS if m in set(df_all["Month"])]
        sel_months, mode = month_filter_block(months, k)
        f_fab = st.multiselect("🧵 Fabricator", sorted(df_all["Fabricator"].unique()), key=k("f"))

        def _reset():
            st.session_state[k("m")] = []
            st.session_state[k("f")] = []

        st.button("↺ Reset filters", on_click=_reset, key=k("reset"))
        if st.button("🔄 Refresh data", key=k("refresh")):
            st.cache_data.clear()
            st.rerun()

    d_nm = df_all[df_all["Fabricator"].isin(f_fab)] if f_fab else df_all
    d = d_nm[d_nm["Month"].isin(sel_months)] if sel_months else d_nm

    hero(f"🧵 {ctx['title']}", "Fabricator-wise stock position, production & receiving",
         [f"Tab: {ctx['tab']}", f"{d['Fabricator'].nunique()} fabricators", f"{len(months)} active months"] +
         ([f"Months: {', '.join(sorted(sel_months, key=month_idx))}"] if sel_months else []))
    if d.empty:
        st.warning("No rows match the selected filters.")
        st.stop()

    t1, t2 = st.tabs(["📊 Overview", "📋 Tables & Data"])
    with t1:
        defs = fab_kpi_defs()
        cur, prev, note = compute_kpis(defs, d, d_nm, sel_months, mode)
        if sel_months:
            st.caption("📊 " + (note or "") + "  ·  green = better, red = worse")
        else:
            st.caption("💡 Select a month in the sidebar to see how each KPI changed vs previous month(s).")
        kpi_cards(defs[:4], cur, prev)
        kpi_cards(defs[4:], cur, prev)

        section("💡 Key insights")
        render_insights(fab_insights(d, d_nm, cur, prev))

        section("Monthly trend", "All months are shown (month filter ignored here) so the trend stays visible.")
        mt = d_nm.groupby("Month")[FAB_METRICS].sum().reindex([m for m in MONTHS if m in set(d_nm["Month"])]).reset_index()
        a, b = st.columns(2)
        with a:
            long = mt.melt(id_vars="Month", value_vars=[PU, RC, RM], var_name="Measure", value_name="Pcs")
            fig = px.bar(long, x="Month", y="Pcs", color="Measure", barmode="group", category_orders={"Month": MONTHS},
                         color_discrete_map={PU: "#7c3aed", RC: "#059669", RM: "#dc2626"}, title="Pcs: under production vs received vs remaining")
            st.plotly_chart(style_fig(fig), use_container_width=True)
        with b:
            long = mt.melt(id_vars="Month", value_vars=[FI, INC], var_name="Measure", value_name="Value")
            fig = px.line(long, x="Month", y="Value", color="Measure", markers=True, category_orders={"Month": MONTHS},
                          title="Fabric issued (mtr) & monthly incoming")
            st.plotly_chart(style_fig(fig), use_container_width=True)

        section("Fabricator-wise")
        g = fab_summary(d)
        a, b = st.columns(2)
        with a:
            top = g.head(15)
            long = top.melt(id_vars="Fabricator", value_vars=[RC, RM], var_name="Measure", value_name="Pcs")
            fig = px.bar(long, x="Fabricator", y="Pcs", color="Measure", barmode="stack",
                         color_discrete_map={RC: "#059669", RM: "#dc2626"}, title="Received vs remaining (top 15)")
            st.plotly_chart(style_fig(fig), use_container_width=True)
        with b:
            rp = g[g[PU] > 0].sort_values("Received %")
            if len(rp):
                fig = px.bar(rp, x="Received %", y="Fabricator", orientation="h", text_auto=".1f", color="Received %",
                             color_continuous_scale=["#dc2626", "#f59e0b", "#059669"], range_color=[0, 100],
                             title="Received % by fabricator")
                st.plotly_chart(style_fig(fig, 80 + 34 * len(rp) if len(rp) > 8 else 380), use_container_width=True)
        a, b = st.columns([1.4, 1])
        with a:
            meas = st.selectbox("Heatmap measure", FAB_METRICS, key=k("hm"))
            pv = d_nm.pivot_table(index="Fabricator", columns="Month", values=meas, aggfunc="sum", fill_value=0)
            pv = pv[[m for m in MONTHS if m in pv.columns]]
            pv = pv[pv.sum(axis=1) > 0]
            if pv.shape[0] and pv.shape[1]:
                fig = px.imshow(pv, text_auto=".3s", aspect="auto", color_continuous_scale="Blues", title=f"Fabricator × Month · {meas}")
                st.plotly_chart(style_fig(fig, 80 + 34 * len(pv) if len(pv) > 8 else 380), use_container_width=True)
        with b:
            sh = g[g[FI] > 0]
            if len(sh):
                fig = px.pie(sh, names="Fabricator", values=FI, hole=0.55, title="Share of fabric issued (mtr)")
                st.plotly_chart(style_fig(fig, 420), use_container_width=True)

    with t2:
        section("Fabricator-wise summary")
        g = fab_summary(d)
        tot = {"Fabricator": "TOTAL", **{m: g[m].sum() for m in FAB_METRICS}}
        tot["Received %"] = round(tot[RC] / tot[PU] * 100, 1) if tot[PU] else None
        st.dataframe(pd.concat([g, pd.DataFrame([tot])], ignore_index=True), use_container_width=True, hide_index=True)

        section("Month-wise summary")
        mt = d_nm.groupby("Month")[FAB_METRICS].sum().reindex([m for m in MONTHS if m in set(d_nm["Month"])])
        mt["Received %"] = (mt[RC] / mt[PU].where(mt[PU] > 0) * 100).round(1)
        for c in (PU, RC, RM):
            mt[f"{c} MoM %"] = (mt[c].pct_change() * 100).replace([np.inf, -np.inf], np.nan).round(1)
        st.dataframe(mt.reset_index(), use_container_width=True, hide_index=True)

        section("Fabricator × Month data")
        show = d.drop(columns=["Overall"]).sort_values(["Fabricator", "Month"], key=lambda s: s.map(month_idx) if s.name == "Month" else s)
        st.dataframe(show, use_container_width=True, hide_index=True, height=340)
        st.download_button("⬇️ Download data (CSV)", show.to_csv(index=False).encode("utf-8"),
                           file_name="fabricator_monthwise.csv", mime="text/csv", key=k("dl"))

        if overall is not None and len(overall):
            with st.expander("✅ Data check vs 'Position Of Stock (ALL OVER)' block"):
                rows = []
                for m in FAB_METRICS:
                    a, b = float(df_all[m].sum()), float(overall[m].sum())
                    rows.append({"Measure": m, "Sum of fabricators": a, "ALL OVER block": b, "Diff": a - b})
                st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
                st.caption("Diff should be 0. A difference means some fabricator block is missing from the overall block or vice-versa.")


def render_fabricators(sheet_name, cfg):
    sid = cfg["id"]
    try:
        titles = [t for t, _ in list_tabs(sid)]
    except Exception as e:
        show_access_error(e)
        st.stop()
    default = None
    for w in cfg.get("summary_tabs", []):
        default = find_tab(titles, w) or default
    with st.sidebar:
        with st.expander("⚙️ Settings"):
            tab = st.selectbox("Summary tab", titles, index=titles.index(default) if default in titles else 0, key=f"fdt_{sid}")
    try:
        values = load_tab_values(sid, tab)
    except Exception as e:
        show_access_error(e)
        st.stop()
    long = parse_monthwise(values)
    if long.empty:
        st.error("No 'Position Of Stock ...' blocks (with a 'Month' header row) were found in this tab. "
                 "Pick the correct tab under ⚙️ Settings.")
        st.stop()
    overall = long[long["Overall"]]
    fabs = long[~long["Overall"]].copy()
    activity = fabs[FAB_METRICS].abs().sum(axis=1)
    fabs = fabs[activity.groupby(fabs["Fabricator"]).transform("sum") > 0]           # poori tarah khali fabricators hatao
    active_months = fabs.groupby("Month")[FAB_METRICS].apply(lambda x: x.abs().to_numpy().sum()) if len(fabs) else pd.Series(dtype=float)
    fabs = fabs[fabs["Month"].isin(active_months[active_months > 0].index)]          # future (khali) months hatao
    if fabs.empty:
        st.warning("All fabricator blocks are empty.")
        st.stop()
    fabricator_dashboard(fabs.reset_index(drop=True), overall, {"key": f"{sid}_{tab}", "title": sheet_name, "tab": tab})


# -----------------------------------------------------------------------------
# 10. MAIN APP  (sheet dropdown -> matching dashboard)
# -----------------------------------------------------------------------------
def render_tracker(sheet_name, sheet_id):
    """Master order-tracker dashboard (original logic)."""
    raw, totals_row, tab_name, first_data_row = load_sheet(sheet_id)
    d_all = prepare(raw)

    with st.sidebar:
        st.markdown("### 🔎 Filters")
        months_present = [m for m in MONTHS if m in set(d_all["month_client"].dropna())]
        sel_months = st.multiselect("Order month (Col B)", months_present)
        sel_designers = st.multiselect("Designer", sorted(x for x in d_all["designer"].unique() if x))
        sel_clients = st.multiselect("Client", sorted(x for x in d_all["client"].unique() if x))
        sel_fabs = st.multiselect("Fabricator", sorted(x for x in d_all["fabricator"].unique() if x))
        if st.button("🔄 Data refresh karo"):
            st.cache_data.clear()
            st.rerun()

    d = d_all.copy()
    if sel_months:
        d = d[d["month_client"].isin(sel_months)]
    if sel_designers:
        d = d[d["designer"].isin(sel_designers)]
    if sel_clients:
        d = d[d["client"].isin(sel_clients)]
    if sel_fabs:
        d = d[d["fabricator"].isin(sel_fabs)]

    st.markdown(
        f"""<div class="dashboard-hero"><h2>📊 Executive Multi-Dashboard 2026-27</h2>
        <p>Google Sheet: <b>{html.escape(sheet_name)}</b> · Tab: <b>{html.escape(tab_name)}</b> · {len(d):,} rows (data row {first_data_row} se)</p></div>""",
        unsafe_allow_html=True)

    if d.empty:
        st.warning("Is filter me koi data nahi mila.")
        st.stop()

    t1, t2, t3, t4 = st.tabs(["Overview", "Designer", "Client", "Production"])
    with t1:
        overview(d)
    with t2:
        designer_dashboard(d)
    with t3:
        client_dashboard(d)
    with t4:
        production_dashboard(d)

    with st.expander("✅ Data check (sheet totals se match)"):
        data_check(totals_row, d_all)


def main():
    with st.sidebar:
        st.markdown("### 📚 Select Dashboard")
        selected = st.selectbox("Google Sheet", list(SHEET_REGISTRY.keys()), key="sheet_choice")
        cfg = SHEET_REGISTRY[selected]

    kind = cfg.get("type", "tracker")
    if kind == "tracker":
        render_tracker(selected, cfg["id"])
    elif kind == "samples":
        render_samples(selected, cfg)
    else:
        render_fabricators(selected, cfg)


if __name__ == "__main__":
    main()
