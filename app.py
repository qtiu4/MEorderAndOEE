"""OEE / Time Loss / Waste dashboard — reads the ME Order Google Sheet live."""
import base64
from datetime import datetime, timedelta, timezone
from html import escape
from pathlib import Path

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

import data as D

ASSETS = Path(__file__).parent / "assets"
LOGO = ASSETS / "oee logo.png"
LOGO_SMALL = ASSETS / "makorn_logo_small.png"
st.set_page_config(page_title="OEE Dashboard · Mahanakorn", page_icon=str(LOGO) if LOGO.exists() else "🏭",
                   layout="wide")

# ------------------------------------------------------------------ cockpit theme (dark navy)
NAVY_PANEL = "#121d45"
TEXT = "#e6ecff"
MUTED = "#8f9bc4"
GRID = "rgba(143,155,196,0.14)"
CYAN, GOLD, TEAL, VIOLET, PINK, BLUE, RED, SLATE = (
    "#38bdf8", "#f5a623", "#2dd4bf", "#a78bfa", "#f472b6", "#3b82f6", "#f87171", "#64748b")
FONT = "Prompt, 'Segoe UI', sans-serif"

# Fixed colours: a machine keeps its colour on every chart, whatever the filter.
MACHINE_COLORS = {"IL1": CYAN, "IL2": GOLD, "IL3": TEAL, "DT": VIOLET, "DT1": PINK, "DT2": BLUE}
GROUP_COLORS = {"A": CYAN, "P": GOLD, D.PLANNED: SLATE}
METRIC_COLORS = {"OEE": CYAN, "A": GOLD, "P": TEAL, "Q": VIOLET}
METRIC_NAMES = {"OEE": "OEE", "A": "Availability", "P": "Performance", "Q": "Quality"}
BAR_SCALE = [[0, "#1d4ed8"], [1, "#38bdf8"]]          # blue → cyan, like the reference bars
TH_TZ = timezone(timedelta(hours=7))
TH_MONTHS = ["ม.ค.", "ก.พ.", "มี.ค.", "เม.ย.", "พ.ค.", "มิ.ย.", "ก.ค.", "ส.ค.", "ก.ย.", "ต.ค.", "พ.ย.", "ธ.ค."]

COCKPIT_CSS = f"""
<style>
@import url('https://fonts.googleapis.com/css2?family=Prompt:wght@300;400;500;600;700&display=swap');
html, body, .stApp, [class*="st-"], button, input, textarea {{font-family:{FONT}}}
.stApp{{background:
  radial-gradient(1200px 600px at 85% -10%,rgba(56,189,248,.10),transparent 60%),
  radial-gradient(900px 500px at -10% 10%,rgba(167,139,250,.10),transparent 60%),
  linear-gradient(180deg,#0c1533 0%,#15204c 55%,#1a2558 100%) fixed}}
[data-testid="stHeader"]{{background:transparent}}
[data-testid="stSidebar"]{{background:linear-gradient(180deg,#0a1230,#111b42);border-right:1px solid rgba(120,150,255,.12)}}
[data-testid="stSidebar"] img{{border-radius:12px}}
.block-container{{padding-top:1.6rem}}
h1,h2,h3,h4{{color:{TEXT};font-weight:600}}
/* tabs */
.stTabs [data-baseweb="tab-list"]{{gap:6px;border-bottom:1px solid rgba(120,150,255,.15)}}
.stTabs [data-baseweb="tab"]{{background:rgba(18,29,69,.7);border:1px solid rgba(120,150,255,.14);
  border-bottom:none;border-radius:10px 10px 0 0;padding:8px 18px;color:{MUTED}}}
.stTabs [aria-selected="true"]{{background:#1b2a63;color:#fff}}
.stTabs [data-baseweb="tab-highlight"]{{background:{CYAN}}}
/* chart + table panels */
[data-testid="stPlotlyChart"],[data-testid="stDataFrame"]{{background:linear-gradient(180deg,#14204d,{NAVY_PANEL});
  border:1px solid rgba(120,150,255,.14);border-radius:12px;padding:10px 12px 4px;
  box-shadow:0 10px 30px rgba(3,8,30,.45),inset 0 1px 0 rgba(255,255,255,.04)}}
/* header bar */
.cp-head{{display:flex;align-items:center;gap:18px;padding:16px 22px;margin-bottom:14px;border-radius:14px;
  background:linear-gradient(90deg,#14204d 0%,#1b2a63 60%,#14204d 100%);
  border:1px solid rgba(120,150,255,.16);box-shadow:0 10px 30px rgba(3,8,30,.45)}}
.cp-logo{{background:#fff;border-radius:10px;padding:6px 8px;height:58px;display:flex;align-items:center}}
.cp-logo img{{height:46px}}
.cp-title{{font-size:1.9rem;font-weight:700;color:#fff;line-height:1.1;letter-spacing:.3px}}
.cp-sub{{color:{MUTED};font-size:.9rem;margin-top:4px}}
.cp-date{{margin-left:auto;text-align:right;color:#fff;font-weight:600;font-size:1.05rem}}
.cp-date small{{display:block;color:{MUTED};font-weight:400;font-size:.78rem;margin-top:2px}}
/* KPI tiles */
.kpi-grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:14px;margin:4px 0 16px}}
.kpi{{position:relative;overflow:hidden;border-radius:12px;padding:16px 18px 14px;min-height:112px;
  background:linear-gradient(160deg,#18265a 0%,{NAVY_PANEL} 100%);
  border:1px solid rgba(120,150,255,.14);box-shadow:0 10px 26px rgba(3,8,30,.45),inset 0 1px 0 rgba(255,255,255,.05)}}
.kpi:before{{content:"";position:absolute;left:0;top:14px;bottom:14px;width:3px;border-radius:3px;background:var(--c);
  box-shadow:0 0 12px var(--c)}}
.kpi .ico{{position:absolute;right:14px;top:14px;width:38px;height:38px;color:var(--c);opacity:.28}}
.kpi .lbl{{font-size:.88rem;font-weight:500;color:#dbe3ff}}
.kpi .val{{font-size:2.05rem;font-weight:700;color:var(--c);line-height:1.15;margin-top:8px;
  text-shadow:0 0 18px var(--glow)}}
.kpi .sub{{font-size:.78rem;color:{MUTED};margin-top:4px}}
.sec{{color:#fff;font-weight:600;font-size:1.1rem;margin:6px 0 8px;display:flex;align-items:center;gap:8px}}
.sec:before{{content:"";width:8px;height:8px;border-radius:2px;background:{CYAN};box-shadow:0 0 10px {CYAN}}}
</style>
"""
st.markdown(COCKPIT_CSS, unsafe_allow_html=True)

# Simple line icons (drawn here, 24×24 viewBox) used as faint watermarks on the KPI tiles.
_ICON_PATHS = {
    "gauge": '<path d="M4 17a8 8 0 1 1 16 0"/><path d="M12 17l4-5"/><circle cx="12" cy="17" r="1.2"/>',
    "clock": '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>',
    "bolt": '<path d="M13 3L5 14h6l-1 7 8-11h-6z"/>',
    "check": '<circle cx="12" cy="12" r="9"/><path d="M8 12.5l2.7 2.7L16 9.8"/>',
    "pause": '<circle cx="12" cy="12" r="9"/><path d="M10 9v6M14 9v6"/>',
    "box": '<path d="M3 8l9-5 9 5v8l-9 5-9-5z"/><path d="M3 8l9 5 9-5M12 13v8"/>',
    "trash": '<path d="M4 7h16M9 7V4h6v3M6 7l1 13h10l1-13"/>',
    "ruler": '<path d="M3 16L16 3l5 5L8 21z"/><path d="M7 12l2 2M10 9l2 2M13 6l2 2"/>',
    "alert": '<path d="M12 3l10 18H2z"/><path d="M12 10v5M12 18v.5"/>',
}
METRIC_ICONS = {"OEE": "gauge", "A": "clock", "P": "bolt", "Q": "check"}


def _icon(name):
    p = _ICON_PATHS.get(name, _ICON_PATHS["gauge"])
    return (f'<svg class="ico" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" '
            f'stroke-linecap="round" stroke-linejoin="round">{p}</svg>')


def _rgba(hex_color, a):
    h = hex_color.lstrip("#")
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    return f"rgba({r},{g},{b},{a})"


def kpi_cards(items, container=st):
    """items: (label, value, sub, hex colour[, icon name]) -> one row of cockpit tiles."""
    cards = []
    for item in items:
        label, value, sub, color = item[:4]
        icon = item[4] if len(item) > 4 else "gauge"
        sub_html = f'<div class="sub">{escape(sub)}</div>' if sub else ""
        cards.append(f'<div class="kpi" style="--c:{color};--glow:{_rgba(color, .35)}">{_icon(icon)}'
                     f'<div class="lbl">{escape(label)}</div><div class="val">{escape(value)}</div>'
                     f'{sub_html}</div>')
    container.markdown(f'<div class="kpi-grid">{"".join(cards)}</div>', unsafe_allow_html=True)


def section(title, container=st):
    container.markdown(f'<div class="sec">{escape(title)}</div>', unsafe_allow_html=True)


def header_bar(subtitle, loaded_at):
    logo_html = ""
    src = LOGO_SMALL if LOGO_SMALL.exists() else LOGO
    if src.exists():
        mime = "png" if src.suffix == ".png" else "jpeg"
        b64 = base64.b64encode(src.read_bytes()).decode()
        logo_html = f'<div class="cp-logo"><img src="data:image/{mime};base64,{b64}"></div>'
    now = datetime.now(TH_TZ)
    today = f"{now.day} {TH_MONTHS[now.month - 1]} {now.year + 543}"
    st.markdown(f'<div class="cp-head">{logo_html}<div><div class="cp-title"> OEE (Overall Equipment Effectiveness) </div>'
                f'<div class="cp-sub">{escape(subtitle)}</div></div>'
                f'<div class="cp-date">{today}<small>อัปเดตข้อมูล {escape(loaded_at)}</small></div></div>',
                unsafe_allow_html=True)


# ------------------------------------------------------------------ data
@st.cache_data(ttl=600, show_spinner="กำลังดึงข้อมูลจาก Google Sheets…")
def load_events():
    try:
        secrets = dict(st.secrets)
    except Exception:  # noqa: BLE001 - no secrets configured
        secrets = {}
    sheet_id = secrets.get("sheet_id", D.DEFAULT_SHEET_ID)
    if "gcp_service_account" in secrets:
        raw = D.load_service_account(sheet_id, dict(secrets["gcp_service_account"]))
    else:
        raw = D.load_public_xlsx(sheet_id)
    return (D.build_events(raw), D.build_total(raw), D.build_orders(raw), D.build_wip(raw),
            datetime.now(TH_TZ).strftime("%d/%m/%Y %H:%M"))


def machine_color_map(machines):
    extra = [TEAL, RED, PINK, VIOLET]
    out, i = {}, 0
    for m in sorted(machines):
        if m in MACHINE_COLORS:
            out[m] = MACHINE_COLORS[m]
        else:
            out[m] = extra[i % len(extra)]
            i += 1
    return out


def style(fig, height=360, pct_axis=False):
    fig.update_layout(height=height, margin=dict(l=8, r=12, t=52, b=36),
                      paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                      font=dict(family=FONT, color="#c3cdf0", size=12),
                      title=dict(x=0, xanchor="left", y=0.97, yanchor="top",
                                 font=dict(size=15, color="#ffffff", family=FONT)),
                      legend=dict(orientation="h", yanchor="top", y=-0.16, x=0, xanchor="left", title=None,
                                  bgcolor="rgba(0,0,0,0)", font=dict(color="#c3cdf0")),
                      hoverlabel=dict(bgcolor="#0b1430", bordercolor="#2b3a78", font=dict(color="#fff", family=FONT)),
                      hovermode="x unified", bargap=0.28)
    fig.update_xaxes(title=None, showgrid=False, linecolor="rgba(143,155,196,.25)", tickfont=dict(color=MUTED))
    fig.update_yaxes(title=None, gridcolor=GRID, zeroline=False, linecolor="rgba(0,0,0,0)",
                     tickfont=dict(color=MUTED))
    if pct_axis:
        fig.update_yaxes(tickformat=".0%")
    return fig


def avg_line(fig, value, label, color="#e6ecff", horizontal=True):
    """Dashed reference line (average / target) like the cockpit reference."""
    if value is None or pd.isna(value):
        return fig
    kw = dict(line_dash="dash", line_width=1.4, line_color=_rgba(color, .7) if color.startswith("#") else color,
              annotation_text=label, annotation_font=dict(color=color, size=11))
    if horizontal:
        fig.add_hline(y=value, annotation_position="top left", **kw)
    else:
        fig.add_vline(x=value, annotation_position="top right", **kw)
    return fig


def area_trace(x, y, name, color, hover):
    """Line with markers and a fading area fill under it."""
    base = dict(x=x, y=y, name=name, mode="lines+markers", fill="tozeroy",
                line=dict(color=color, width=2.6, shape="spline", smoothing=0.6),
                marker=dict(size=7, color=color, line=dict(color="#0f1a3d", width=1.5)),
                hovertemplate=hover)
    try:
        return go.Scatter(**base, fillgradient=dict(
            type="vertical", colorscale=[[0, _rgba(color, 0)], [1, _rgba(color, .38)]]))
    except (ValueError, TypeError):  # older plotly without fillgradient
        return go.Scatter(**base, fillcolor=_rgba(color, .16))


def gradient_bars(fig, values):
    """Colour single-series bars blue→cyan by value (gradient look)."""
    fig.update_traces(marker=dict(color=list(values), colorscale=BAR_SCALE, showscale=False, line=dict(width=0)))
    return fig


def donut(labels, values, colors, title, center_text, hover):
    fig = go.Figure(go.Pie(labels=labels, values=values, hole=0.66, sort=False, direction="clockwise",
                           marker=dict(colors=colors, line=dict(color=NAVY_PANEL, width=3)),
                           textinfo="percent", textfont=dict(color="#fff", size=12),
                           hovertemplate=hover))
    fig.update_layout(title=dict(text=title),
                      annotations=[dict(text=center_text, x=0.5, y=0.5, showarrow=False,
                                        font=dict(size=20, color="#fff", family=FONT))])
    style(fig, height=360)
    fig.update_layout(hovermode="closest", legend=dict(y=-0.05))
    return fig


def show_chart(container, fig):
    """Full-width chart on both newer (width=) and older (use_container_width=) Streamlit."""
    cfg = {"displaylogo": False}
    try:
        container.plotly_chart(fig, width="stretch", config=cfg)
    except TypeError:
        container.plotly_chart(fig, use_container_width=True, config=cfg)


def fmt_pct(v):
    return "–" if pd.isna(v) else f"{v:.1%}"


try:
    events, total_sheet, orders, wip, loaded_at = load_events()
except Exception as e:  # noqa: BLE001
    st.error("ดึงข้อมูลจาก Google Sheets ไม่ได้ ตรวจว่าแชร์ชีตแล้ว หรือใส่ service account ใน Secrets แล้ว")
    st.exception(e)
    st.stop()

# ------------------------------------------------------------------ sidebar filters
with st.sidebar:
    if LOGO.exists():
        st.image(str(LOGO), width=170)
    st.header("ตัวกรอง")
    # Ignore impossible months (e.g. a date typed as 24/10/68 that Sheets stored as 1968).
    months = sorted(m for m in events["month"].dropna().unique() if pd.Timestamp(m).year >= 2000)
    month_labels = [pd.Timestamp(m).strftime("%b %Y") for m in months]
    default_start = max(0, len(months) - 12)

    # Month range: two plain dropdowns (no slider, no callbacks).
    st.markdown("**ช่วงเดือน**")
    col_from, col_to = st.columns(2)
    m_from = col_from.selectbox("ตั้งแต่", month_labels, index=default_start, key="month_from")
    m_to = col_to.selectbox("ถึง", month_labels, index=len(month_labels) - 1, key="month_to")
    if month_labels.index(m_from) > month_labels.index(m_to):  # picked backwards -> swap
        m_from, m_to = m_to, m_from
    i_from, i_to = month_labels.index(m_from), month_labels.index(m_to)
    sel_months = months[i_from:i_to + 1]

    exclude = st.toggle("ไม่รวม SF ที่ขึ้นต้นด้วย IS", value=True,
                        help="ตรงกับวิธีคิด OEE ในชีต OEE_Monthly")
    pool = events[~events["excluded"]] if exclude else events
    all_machines = sorted(m for m in pool["machine"].unique() if m)
    sel_machines = st.multiselect("เครื่องจักร", all_machines, default=all_machines)

    st.divider()
    st.caption(f"ข้อมูลล่าสุด: {loaded_at} (อัปเดตอัตโนมัติทุก 10 นาที)")
    if st.button("ดึงข้อมูลใหม่ตอนนี้"):
        load_events.clear()
        st.rerun()

ev = pool[pool["month"].isin(sel_months) & pool["machine"].isin(sel_machines)]
if ev.empty:
    st.warning("ไม่มีข้อมูลในช่วงที่เลือก")
    st.stop()
cmap = machine_color_map(ev["machine"].unique())

header_bar(f"ประสิทธิผลโดยรวมของเครื่องจักร · Mahanakorn Electric Wire · {m_from} – {m_to} · {', '.join(sel_machines)}", loaded_at)

tab_oee, tab_total, tab_loss, tab_waste, tab_order, tab_data = st.tabs(
    ["OEE แยกเครื่อง", "OEE รวมรายเดือน", "Time Loss", "Waste", "ติดตามออเดอร์", "ตารางข้อมูล"])

# ------------------------------------------------------------------ OEE
with tab_oee:
    tot = D.oee_total(ev)
    last_m = max(sel_months)
    prev_m = (pd.Timestamp(last_m) - pd.offsets.MonthBegin(1))
    cur = D.oee_total(ev[ev["month"] == last_m]) if (ev["month"] == last_m).any() else None
    prv_ev = pool[(pool["month"] == prev_m) & pool["machine"].isin(sel_machines)]
    prv = D.oee_total(prv_ev) if not prv_ev.empty else None

    section("ภาพรวมช่วงที่เลือก")
    lm = f"{pd.Timestamp(last_m):%b %Y}"
    kpi_cards([(METRIC_NAMES[k], fmt_pct(tot[k]),
                (f"{lm}: {fmt_pct(cur[k])}" if cur is not None else "")
                + (f" · เดือนก่อน {fmt_pct(prv[k])}" if prv is not None else ""),
                METRIC_COLORS[k], METRIC_ICONS[k]) for k in ["OEE", "A", "P", "Q"]])

    by_mm = D.oee_table(ev, ["month", "machine"])
    by_m = D.oee_table(ev, ["month"]).assign(machine="รวม")

    metric = st.radio("ตัวชี้วัด", ["OEE", "A", "P", "Q"], horizontal=True, format_func=METRIC_NAMES.get)
    c1, c2 = st.columns([3, 2])
    fig = go.Figure(area_trace(by_m["month"], by_m[metric], "รวมทุกเครื่อง", METRIC_COLORS[metric], "%{y:.1%}"))
    avg_line(fig, tot[metric], f"เฉลี่ย {fmt_pct(tot[metric])}", GOLD if metric != "A" else CYAN)
    fig.update_layout(title=dict(text=f"{METRIC_NAMES[metric]} รวม รายเดือน"), showlegend=False)
    show_chart(c1, style(fig, pct_axis=True))

    fig = px.line(by_mm, x="month", y=metric, color="machine", markers=True,
                  color_discrete_map=cmap, title=f"{METRIC_NAMES[metric]} แยกเครื่อง")
    fig.update_traces(hovertemplate="%{y:.1%}", line=dict(width=2.2), marker=dict(size=6))
    show_chart(c2, style(fig, pct_axis=True))

    c1, c2 = st.columns(2)
    by_mach = D.oee_table(ev, ["machine"])
    melt = by_mach.melt(id_vars="machine", value_vars=["A", "P", "Q", "OEE"], var_name="ตัวชี้วัด", value_name="ค่า")
    fig = px.bar(melt, x="ตัวชี้วัด", y="ค่า", color="machine", barmode="group",
                 color_discrete_map=cmap, title="A / P / Q / OEE แยกเครื่อง (ทั้งช่วง)", text_auto=".0%")
    fig.update_traces(hovertemplate="%{y:.1%}", marker_line_width=0, textfont=dict(color="#fff", size=11))
    show_chart(c1, style(fig, pct_axis=True))

    lossbars = by_m[["month", "planned_hr", "a_hr", "run_time"]].rename(
        columns={"planned_hr": "หยุดตามแผน", "a_hr": "เสีย A", "run_time": "เวลาเดินจริง"})
    fig = px.bar(lossbars, x="month", y=["เวลาเดินจริง", "เสีย A", "หยุดตามแผน"],
                 color_discrete_map={"เวลาเดินจริง": CYAN, "เสีย A": GOLD, "หยุดตามแผน": SLATE},
                 title="ชั่วโมงทำงานรายเดือน (ทุกเครื่องที่เลือก)")
    fig.update_traces(hovertemplate="%{y:,.1f} ชม.", marker_line_width=0)
    show_chart(c2, style(fig))

# ------------------------------------------------------------------ OEE total (sheet OEE_Total)
with tab_total:
    if total_sheet is None or total_sheet.empty:
        st.info("ยังไม่พบชีต OEE_Total ในไฟล์ (ต้องตั้งชื่อชีตว่า OEE_Total)")
    else:
        tt = total_sheet[total_sheet["month"].isin(sel_months)]
        if tt.empty:
            st.info("ชีต OEE_Total ไม่มีข้อมูลในช่วงเดือนที่เลือก")
        else:
            st.caption("ตัวเลขจากชีต OEE_Total: รวมทุกเครื่องในแต่ละเดือนแล้วคำนวณจากยอดรวม "
                       "(ตัวกรองเครื่องจักรด้านซ้ายไม่มีผลกับแท็บนี้)")
            last, prev = tt.iloc[-1], (tt.iloc[-2] if len(tt) > 1 else None)
            section(f"เดือนล่าสุด: {last['month']:%b %Y}")
            cards = []
            for k in ["OEE", "A", "P", "Q"]:
                delta = ""
                if prev is not None and pd.notna(last[k]) and pd.notna(prev[k]):
                    arrow = "▲" if last[k] >= prev[k] else "▼"
                    delta = f"{arrow} {(last[k] - prev[k]) * 100:+.1f} จุด จากเดือนก่อน"
                cards.append((METRIC_NAMES[k], fmt_pct(last[k]), delta, METRIC_COLORS[k], METRIC_ICONS[k]))
            kpi_cards(cards)

            fig = go.Figure(area_trace(tt["month"], tt["OEE"], "OEE", CYAN, "%{y:.1%}"))
            for k in ["A", "P", "Q"]:
                fig.add_trace(go.Scatter(x=tt["month"], y=tt[k], name=METRIC_NAMES[k], mode="lines+markers",
                                         line=dict(color=METRIC_COLORS[k], width=2, shape="spline", smoothing=0.6),
                                         marker=dict(size=6), hovertemplate="%{y:.1%}"))
            avg_oee = tt["OEE"].mean()
            avg_line(fig, avg_oee, f"OEE เฉลี่ย {fmt_pct(avg_oee)}", GOLD)
            fig.update_layout(title=dict(text="OEE / A / P / Q รวมทุกเครื่อง รายเดือน"))
            show_chart(st, style(fig, height=400, pct_axis=True))

            c1, c2 = st.columns(2)
            fig = px.bar(tt, x="month", y="OEE", title="OEE รวมรายเดือน", text_auto=".1%")
            gradient_bars(fig, tt["OEE"])
            fig.update_traces(hovertemplate="%{y:.1%}<extra></extra>", textfont=dict(color="#fff"))
            avg_line(fig, avg_oee, "เฉลี่ย", GOLD)
            show_chart(c1, style(fig, pct_axis=True))
            hrs = tt[["month", "planned_time", "run_time", "ideal_hr"]].rename(columns={
                "planned_time": "Planned time", "run_time": "Run time", "ideal_hr": "Ideal time"})
            fig = px.bar(hrs, x="month", y=["Planned time", "Run time", "Ideal time"], barmode="group",
                         color_discrete_sequence=["#3b4f8f", BLUE, CYAN],
                         title="ชั่วโมงรวมทุกเครื่อง: Planned → Run → Ideal")
            fig.update_traces(hovertemplate="%{y:,.1f} ชม.", marker_line_width=0)
            show_chart(c2, style(fig))

            tbl = tt.sort_values("month", ascending=False).copy()
            tbl["month"] = tbl["month"].dt.strftime("%Y-%m")
            for k in ["A", "P", "Q", "OEE"]:
                tbl[k] = (tbl[k] * 100).round(1)
            tbl = tbl.rename(columns={"month": "เดือน", "machines": "จำนวนเครื่อง", "hours": "ชม.ทำงาน",
                                      "planned_time": "Planned time", "run_time": "Run time",
                                      "ideal_hr": "Ideal time", "kg_good": "ผลผลิตดี (kg)",
                                      "waste_kg": "ของเสีย (kg)"})
            cfg = {k: st.column_config.NumberColumn(format="%.1f") for k in
                   ["ชม.ทำงาน", "Planned time", "Run time", "Ideal time", "ของเสีย (kg)"]}
            cfg.update({"ผลผลิตดี (kg)": st.column_config.NumberColumn(format="%.0f"),
                        "จำนวนเครื่อง": st.column_config.NumberColumn(format="%d")})
            cfg.update({k: st.column_config.NumberColumn(f"{k} (%)", format="%.1f%%") for k in ["A", "P", "Q", "OEE"]})
            st.dataframe(tbl, hide_index=True, column_config=cfg)

# ------------------------------------------------------------------ Time loss
with tab_loss:
    loss = ev[(ev["loss_hr"] > 0) & (ev["loss_code"] != "")]
    if loss.empty:
        st.info("ไม่มีเวลาสูญเสียในช่วงที่เลือก")
    else:
        g = loss.groupby("loss_group")["loss_hr"].sum()
        kpi_cards([
            ("เวลาสูญเสียรวม", f"{loss['loss_hr'].sum():,.1f} ชม.", "", "#ffffff", "alert"),
            ("เสีย A", f"{g.get('A', 0):,.1f} ชม.", "กระทบ Availability", GROUP_COLORS["A"], "clock"),
            ("เสีย P", f"{g.get('P', 0):,.1f} ชม.", "หยุดสั้น กระทบ Performance", GROUP_COLORS["P"], "bolt"),
            ("หยุดตามแผน", f"{g.get(D.PLANNED, 0):,.1f} ชม.", "ไม่นับเป็นเวลาเสีย", "#94a3b8", "pause"),
        ])

        c1, c2 = st.columns([2, 1])
        trend = loss.groupby(["month", "loss_group"], as_index=False)["loss_hr"].sum()
        fig = px.bar(trend, x="month", y="loss_hr", color="loss_group", color_discrete_map=GROUP_COLORS,
                     category_orders={"loss_group": ["A", "P", D.PLANNED]}, title="เวลาสูญเสียรายเดือนแยกกลุ่ม")
        fig.update_traces(hovertemplate="%{y:,.1f} ชม.", marker_line_width=0)
        show_chart(c1, style(fig))
        order = [k for k in ["A", "P", D.PLANNED] if g.get(k, 0) > 0]
        fig = donut(order, [g[k] for k in order], [GROUP_COLORS[k] for k in order], "สัดส่วนเวลาสูญเสีย",
                    f"{loss['loss_hr'].sum():,.0f}<br><span style='font-size:12px;color:{MUTED}'>ชม.</span>",
                    "%{label}: %{value:,.1f} ชม. (%{percent})<extra></extra>")
        show_chart(c2, fig)

        c1, c2 = st.columns([3, 2])
        incl_planned = c1.checkbox("รวมหยุดตามแผนใน Pareto", value=False)
        par = loss if incl_planned else loss[loss["loss_group"] != D.PLANNED]
        top = (par.groupby(["loss_code", "loss_desc", "loss_group"], as_index=False)["loss_hr"].sum()
               .sort_values("loss_hr", ascending=False).head(15))
        top["label"] = top["loss_code"] + " " + top["loss_desc"]
        top["สะสม"] = top["loss_hr"].cumsum() / par["loss_hr"].sum()
        fig = px.bar(top.iloc[::-1], x="loss_hr", y="label", orientation="h", color="loss_group",
                     color_discrete_map=GROUP_COLORS, title="Pareto สาเหตุเวลาสูญเสีย (15 อันดับแรก)",
                     custom_data=["สะสม"])
        fig.update_traces(hovertemplate="%{x:,.1f} ชม. · สะสม %{customdata[0]:.0%}<extra></extra>", marker_line_width=0)
        fig.update_layout(hovermode="closest")
        show_chart(c1, style(fig, height=520).update_xaxes(showgrid=True, gridcolor=GRID).update_yaxes(showgrid=False))

        bym = loss.groupby(["machine", "loss_group"], as_index=False)["loss_hr"].sum()
        fig = px.bar(bym, x="machine", y="loss_hr", color="loss_group", color_discrete_map=GROUP_COLORS,
                     category_orders={"loss_group": ["A", "P", D.PLANNED]}, title="เวลาสูญเสียแยกเครื่อง")
        fig.update_traces(hovertemplate="%{y:,.1f} ชม.", marker_line_width=0)
        fig.update_layout(hovermode="closest")
        show_chart(c2, style(fig, height=520))

# ------------------------------------------------------------------ Waste
with tab_waste:
    w_m = ev.groupby("month", as_index=False)[["m", "kg_good", "waste_kg", "waste_m"]].sum()
    w_m["% ของเสีย (kg)"] = w_m["waste_kg"] / (w_m["kg_good"] + w_m["waste_kg"]).where(lambda x: x > 0)
    w_m["% ของเสีย (m)"] = w_m["waste_m"] / (w_m["m"] + w_m["waste_m"]).where(lambda x: x > 0)
    tw_kg, tw_m = ev["waste_kg"].sum(), ev["waste_m"].sum()
    good_kg, good_m = ev["kg_good"].sum(), ev["m"].sum()
    pct_kg = tw_kg / (good_kg + tw_kg) if good_kg + tw_kg > 0 else float("nan")
    kpi_cards([
        ("ผลผลิตรวม", f"{good_m:,.0f} m", "", CYAN, "ruler"),
        ("ของเสีย (kg)", f"{tw_kg:,.1f} kg", "", GOLD, "trash"),
        ("ของเสีย (m)", f"{tw_m:,.0f} m", "", VIOLET, "box"),
        ("% ของเสีย (kg)", fmt_pct(pct_kg), "เทียบกับ kg ดี + ของเสีย kg", RED, "alert"),
    ])

    c1, c2 = st.columns(2)
    fig = go.Figure([area_trace(w_m["month"], w_m["% ของเสีย (kg)"], "% ของเสีย (kg)", CYAN, "%{y:.2%}"),
                     go.Scatter(x=w_m["month"], y=w_m["% ของเสีย (m)"], name="% ของเสีย (m)", mode="lines+markers",
                                line=dict(color=VIOLET, width=2.2, shape="spline", smoothing=0.6),
                                marker=dict(size=6), hovertemplate="%{y:.2%}")])
    avg_line(fig, pct_kg, f"เฉลี่ย (kg) {fmt_pct(pct_kg)}", GOLD)
    fig.update_layout(title=dict(text="% ของเสียรายเดือน"))
    show_chart(c1, style(fig, pct_axis=True).update_yaxes(tickformat=".1%"))

    wm = ev.groupby(["month", "machine"], as_index=False)["waste_kg"].sum()
    fig = px.bar(wm, x="month", y="waste_kg", color="machine", color_discrete_map=cmap,
                 title="ของเสีย (kg) รายเดือนแยกเครื่อง")
    fig.update_traces(hovertemplate="%{y:,.1f} kg", marker_line_width=0)
    show_chart(c2, style(fig))

    unit = st.radio("Pareto สาเหตุของเสีย ตาม", ["kg", "m"], horizontal=True)
    val = "waste_kg" if unit == "kg" else "waste_m"
    wst = ev[(ev[val] > 0) & (ev["waste_code"] != "")]
    c1, c2 = st.columns([3, 2])
    if wst.empty:
        c1.info("ไม่มีข้อมูลของเสียที่มีรหัสสาเหตุ")
    else:
        top = (wst.groupby(["waste_code", "waste_desc"], as_index=False)[val].sum()
               .sort_values(val, ascending=False).head(15))
        top["label"] = top["waste_code"] + " " + top["waste_desc"]
        top = top.iloc[::-1]
        fig = px.bar(top, x=val, y="label", orientation="h", title=f"Pareto สาเหตุของเสีย ({unit})")
        gradient_bars(fig, top[val])
        fig.update_traces(hovertemplate="%{x:,.1f} " + unit + "<extra></extra>")
        fig.update_layout(hovermode="closest")
        show_chart(c1, style(fig, height=520).update_xaxes(showgrid=True, gridcolor=GRID).update_yaxes(showgrid=False))
    wt = ev[(ev["waste_type"] != "") & (ev[val] > 0)]
    if wt.empty:
        c2.info("ประเภทของเสีย (CU / PVC / SL / Wire) มีเฉพาะข้อมูลจากฟอร์ม")
    else:
        t = wt.groupby("waste_type", as_index=False)[val].sum().sort_values(val, ascending=False)
        palette = [CYAN, GOLD, VIOLET, TEAL, PINK, BLUE, RED]
        fig = donut(t["waste_type"].tolist(), t[val].tolist(), palette[:len(t)],
                    f"ของเสียแยกประเภท ({unit}) — ข้อมูลจากฟอร์ม",
                    f"{t[val].sum():,.0f}<br><span style='font-size:12px;color:{MUTED}'>{unit}</span>",
                    "%{label}: %{value:,.1f} " + unit + " (%{percent})<extra></extra>")
        fig.update_layout(height=520)
        show_chart(c2, fig)

# ------------------------------------------------------------------ Order tracking
DUE_BUCKETS = ["เลยกำหนดส่ง", "ส่งภายใน 7 วัน", "ส่งเกิน 7 วัน", "ไม่ระบุวันส่ง"]
DUE_COLORS = dict(zip(DUE_BUCKETS, [RED, GOLD, CYAN, SLATE]))


def _cat_sort_key(c):
    """หมวด 1, หมวด 2 … in number order, 'ไม่ระบุหมวด' last."""
    if c == D.NO_CATEGORY:
        return (2, 0, c)
    digits = "".join(ch for ch in c if ch.isdigit())
    return (0, int(digits), c) if digits else (1, 0, c)


def _search(df, text, cols):
    if not text:
        return df
    t = text.strip().lower()
    hit = pd.Series(False, index=df.index)
    for c in cols:
        hit |= df[c].astype(str).str.lower().str.contains(t, regex=False)
    return df[hit]


def _pct_done(qty, done):
    return (done / qty * 100) if qty > 0 else float("nan")


def order_tab():
    today = pd.Timestamp(datetime.now(TH_TZ).date())
    so_tab, wip_tab = st.tabs(["ใบสั่งผลิต (ส่งลูกค้า)", "ใบสั่งผลิต WIP"])

    # ---------------- sales orders
    with so_tab:
        if orders is None or orders.empty:
            st.info("ไม่พบชีต 'ใบสั่งผลิต' ในไฟล์")
        else:
            o = orders.copy()
            o["days_left"] = (o["due"] - today).dt.days
            o["due_bucket"] = np.select(
                [o["due"].isna(), o["days_left"] < 0, o["days_left"] <= 7],
                ["ไม่ระบุวันส่ง", "เลยกำหนดส่ง", "ส่งภายใน 7 วัน"], "ส่งเกิน 7 วัน")
            o["pct"] = np.where(o["qty"] > 0, o["done"] / o["qty"] * 100, np.nan)
            cats = sorted(o["category"].unique(), key=_cat_sort_key)

            f1, f2, f3, f4 = st.columns([1.2, 1.4, 1.1, 1.6])
            cat = f1.selectbox("หมวดสินค้า", ["ทุกหมวด"] + cats, key="so_cat")
            custs = sorted(c for c in o["customer"].unique() if c)
            sel_cust = f2.multiselect("ลูกค้า", custs, placeholder="ทุกลูกค้า", key="so_cust")
            status = f3.radio("สถานะ", ["ค้างส่ง", "ทั้งหมด", "เสร็จแล้ว"], horizontal=True, key="so_status")
            text = f4.text_input("ค้นหา (SO / SF / รหัส / ชื่อสินค้า)", key="so_search")

            base = o if not sel_cust else o[o["customer"].isin(sel_cust)]
            if status == "ค้างส่ง":
                base = base[base["status"] != "complete"]
            elif status == "เสร็จแล้ว":
                base = base[base["status"] == "complete"]
            base = _search(base, text, ["so", "sf", "product", "desc"])
            open_all = base[base["status"] != "complete"]

            # --- summary by category (always all categories, so they can be compared)
            section("สรุปค้างส่งแยกหมวด")
            if base.empty:
                st.info("ไม่มีรายการตามตัวกรอง")
            else:
                # (ASCII names inside agg: Python would alter Thai keyword names)
                g = base.groupby("category").agg(
                    n=("sf", "size"), qty=("qty", "sum"), done=("done", "sum"), remain=("remain", "sum"))
                late = open_all[open_all["due_bucket"] == "เลยกำหนดส่ง"].groupby("category").agg(
                    late_n=("sf", "size"), late_remain=("remain", "sum"))
                g = g.join(late).fillna(0).reset_index()
                g["pct"] = np.where(g["qty"] > 0, g["done"] / g["qty"] * 100, np.nan)
                g = g.sort_values("category", key=lambda c: c.map(_cat_sort_key))[
                    ["category", "n", "qty", "done", "remain", "pct", "late_n", "late_remain"]]
                g.columns = ["หมวด", "รายการ", "สั่งผลิต", "ผลิตแล้ว", "ค้างส่ง", "% ผลิตแล้ว",
                             "เลยกำหนด (รายการ)", "เลยกำหนด (ขด)"]

                c1, c2 = st.columns([3, 2])
                by = open_all.groupby(["category", "due_bucket"], as_index=False)["remain"].sum()
                if by.empty:
                    c1.info("ไม่มีรายการค้างส่ง")
                else:
                    fig = px.bar(by, x="remain", y="category", color="due_bucket", orientation="h",
                                 color_discrete_map=DUE_COLORS, title="จำนวนค้างส่ง (ขด) แยกหมวด",
                                 category_orders={"due_bucket": DUE_BUCKETS,
                                                  "category": sorted(by["category"].unique(), key=_cat_sort_key)})
                    fig.update_traces(hovertemplate="%{x:,.0f} ขด<extra>%{fullData.name}</extra>",
                                      marker_line_width=0)
                    fig.update_layout(hovermode="closest")
                    show_chart(c1, style(fig, height=380).update_xaxes(showgrid=True, gridcolor=GRID)
                               .update_yaxes(showgrid=False))
                cnt = open_all["due_bucket"].value_counts()
                order = [b for b in DUE_BUCKETS if cnt.get(b, 0) > 0]
                if order:
                    fig = donut(order, [int(cnt[b]) for b in order], [DUE_COLORS[b] for b in order],
                                "รายการค้างส่งตามกำหนดส่ง",
                                f"{len(open_all):,}<br><span style='font-size:12px;color:{MUTED}'>รายการ</span>",
                                "%{label}: %{value} รายการ (%{percent})<extra></extra>")
                    fig.update_layout(height=380)
                    show_chart(c2, fig)

                st.dataframe(g, hide_index=True, column_config={
                    "% ผลิตแล้ว": st.column_config.ProgressColumn(format="%.0f%%", min_value=0, max_value=100),
                    **{k: st.column_config.NumberColumn(format="%d") for k in
                       ["รายการ", "สั่งผลิต", "ผลิตแล้ว", "ค้างส่ง", "เลยกำหนด (รายการ)", "เลยกำหนด (ขด)"]}})

            # --- one category in detail
            view = base if cat == "ทุกหมวด" else base[base["category"] == cat]
            open_v = view[view["status"] != "complete"]
            section(f"รายละเอียด: {cat}")
            late_v = open_v[open_v["due_bucket"] == "เลยกำหนดส่ง"]
            soon_v = open_v[open_v["due_bucket"] == "ส่งภายใน 7 วัน"]
            kpi_cards([
                ("รายการค้างส่ง", f"{len(open_v):,}", f"จาก {len(view):,} รายการที่แสดง", CYAN, "box"),
                ("ค้างส่ง (ขด)", f"{open_v['remain'].sum():,.0f}", f"สั่งผลิตรวม {view['qty'].sum():,.0f} ขด",
                 GOLD, "ruler"),
                ("ผลิตแล้ว", fmt_pct(_pct_done(view["qty"].sum(), view["done"].sum()) / 100),
                 f"{view['done'].sum():,.0f} ขด", TEAL, "check"),
                ("เลยกำหนดส่ง", f"{len(late_v):,} รายการ", f"ค้าง {late_v['remain'].sum():,.0f} ขด", RED, "alert"),
                ("ส่งภายใน 7 วัน", f"{len(soon_v):,} รายการ", f"ค้าง {soon_v['remain'].sum():,.0f} ขด", VIOLET, "clock"),
            ])

            if not open_v.empty:
                cu = (open_v.groupby("customer", as_index=False)["remain"].sum()
                      .sort_values("remain", ascending=False).head(10).iloc[::-1])
                cu["customer"] = cu["customer"].replace("", "(ไม่ระบุ)")
                fig = px.bar(cu, x="remain", y="customer", orientation="h", title="ค้างส่งแยกลูกค้า (10 อันดับแรก, ขด)")
                gradient_bars(fig, cu["remain"])
                fig.update_traces(hovertemplate="%{x:,.0f} ขด<extra></extra>")
                fig.update_layout(hovermode="closest")
                show_chart(st, style(fig, height=max(240, 40 * len(cu) + 90))
                           .update_xaxes(showgrid=True, gridcolor=GRID).update_yaxes(showgrid=False))

            tbl = view.sort_values(["due", "so_date"], na_position="last")
            show = pd.DataFrame({
                "กำหนดส่ง": tbl["due"].dt.strftime("%d/%m/%Y").fillna("–"),
                "เหลือ (วัน)": tbl["days_left"],
                "สถานะส่ง": np.where(tbl["status"] == "complete", "ผลิตครบแล้ว", tbl["due_bucket"]),
                "หมวด": tbl["category"], "ลูกค้า": tbl["customer"], "เลขที่ SO": tbl["so"],
                "ใบสั่งผลิต (SF)": tbl["sf"], "รหัสสินค้า": tbl["product"], "รายละเอียดสินค้า": tbl["desc"],
                "สั่งผลิต": tbl["qty"], "ผลิตแล้ว": tbl["done"], "ค้างส่ง": tbl["remain"],
                "% ผลิตแล้ว": tbl["pct"], "วันที่ SO": tbl["so_date"].dt.strftime("%d/%m/%Y").fillna(""),
                "หมายเหตุ": tbl["note"]})
            st.dataframe(show, hide_index=True, column_config={
                "% ผลิตแล้ว": st.column_config.ProgressColumn(format="%.0f%%", min_value=0, max_value=100),
                "เหลือ (วัน)": st.column_config.NumberColumn(format="%d"),
                **{k: st.column_config.NumberColumn(format="%d") for k in ["สั่งผลิต", "ผลิตแล้ว", "ค้างส่ง"]}})
            st.download_button("ดาวน์โหลด CSV", show.to_csv(index=False).encode("utf-8-sig"),
                               file_name="order_tracking.csv", mime="text/csv", key="so_csv")

    # ---------------- WIP orders
    with wip_tab:
        if wip is None or wip.empty:
            st.info("ไม่พบชีต 'ใบสั่งผลิต WIP' ในไฟล์")
        else:
            w = wip.copy()
            w["pct"] = np.where(w["qty"] > 0, w["done"] / w["qty"] * 100, np.nan)
            w["days_open"] = (today - w["open_date"]).dt.days
            cats = sorted(w["category"].unique(), key=_cat_sort_key)
            types = sorted(w["wip_type"].unique())

            f1, f2, f3, f4 = st.columns([1.2, 1.4, 1.1, 1.6])
            cat = f1.selectbox("หมวดสินค้า", ["ทุกหมวด"] + cats, key="wip_cat")
            sel_type = f2.multiselect("ประเภท (ตัวอักษรหน้า SF)", types, placeholder="ทุกประเภท", key="wip_type")
            status = f3.radio("สถานะ", ["ค้างผลิต", "ทั้งหมด", "เสร็จแล้ว"], horizontal=True, key="wip_status")
            text = f4.text_input("ค้นหา (SF / รหัส / ชื่อ)", key="wip_search")

            v = w if cat == "ทุกหมวด" else w[w["category"] == cat]
            if sel_type:
                v = v[v["wip_type"].isin(sel_type)]
            if status == "ค้างผลิต":
                v = v[v["status"] != "complete"]
            elif status == "เสร็จแล้ว":
                v = v[v["status"] == "complete"]
            v = _search(v, text, ["sf", "product", "desc"])
            open_v = v[v["status"] != "complete"]

            kpi_cards([
                ("รายการค้างผลิต", f"{len(open_v):,}", f"จาก {len(v):,} รายการที่แสดง", CYAN, "box"),
                ("จำนวนค้างผลิต", f"{open_v['remain'].sum():,.0f}", f"สั่งผลิตรวม {v['qty'].sum():,.0f}",
                 GOLD, "ruler"),
                ("ผลิตแล้ว", fmt_pct(_pct_done(v["qty"].sum(), v["done"].sum()) / 100),
                 f"{v['done'].sum():,.0f}", TEAL, "check"),
            ])

            if not open_v.empty:
                c1, c2 = st.columns([3, 2])
                by = open_v.groupby(["category", "wip_type"], as_index=False)["remain"].sum()
                fig = px.bar(by, x="remain", y="category", color="wip_type", orientation="h",
                             title="จำนวนค้างผลิต WIP แยกหมวด",
                             color_discrete_sequence=[CYAN, GOLD, VIOLET, TEAL, PINK, BLUE],
                             category_orders={"category": sorted(by["category"].unique(), key=_cat_sort_key)})
                fig.update_traces(hovertemplate="%{x:,.0f}<extra>%{fullData.name}</extra>", marker_line_width=0)
                fig.update_layout(hovermode="closest")
                show_chart(c1, style(fig, height=380).update_xaxes(showgrid=True, gridcolor=GRID)
                           .update_yaxes(showgrid=False))
                t = open_v.groupby("wip_type", as_index=False)["remain"].sum().sort_values("remain", ascending=False)
                fig = donut(t["wip_type"].tolist(), t["remain"].tolist(),
                            [CYAN, GOLD, VIOLET, TEAL, PINK, BLUE][:len(t)], "ค้างผลิตแยกประเภท",
                            f"{t['remain'].sum():,.0f}", "%{label}: %{value:,.0f} (%{percent})<extra></extra>")
                fig.update_layout(height=380)
                show_chart(c2, fig)

            tbl = v.sort_values(["status", "open_date"], na_position="last")
            show = pd.DataFrame({
                "วันที่เปิด": tbl["open_date"].dt.strftime("%d/%m/%Y").fillna("–"),
                "เปิดมาแล้ว (วัน)": tbl["days_open"], "ประเภท": tbl["wip_type"], "หมวด": tbl["category"],
                "ใบสั่งผลิต (SF)": tbl["sf"], "รหัสสินค้า": tbl["product"], "รายละเอียดสินค้า": tbl["desc"],
                "สั่งผลิต": tbl["qty"], "ผลิตแล้ว": tbl["done"], "ค้างผลิต": tbl["remain"],
                "% ผลิตแล้ว": tbl["pct"],
                "สถานะ": np.where(tbl["status"] == "complete", "ผลิตครบแล้ว", "ค้างผลิต"),
                "หมายเหตุ": tbl["note"]})
            st.dataframe(show, hide_index=True, column_config={
                "% ผลิตแล้ว": st.column_config.ProgressColumn(format="%.0f%%", min_value=0, max_value=100),
                "เปิดมาแล้ว (วัน)": st.column_config.NumberColumn(format="%d"),
                **{k: st.column_config.NumberColumn(format="%d") for k in ["สั่งผลิต", "ผลิตแล้ว", "ค้างผลิต"]}})
            st.download_button("ดาวน์โหลด CSV", show.to_csv(index=False).encode("utf-8-sig"),
                               file_name="wip_tracking.csv", mime="text/csv", key="wip_csv")


with tab_order:
    order_tab()

# ------------------------------------------------------------------ table
with tab_data:
    tbl = D.oee_table(ev, ["month", "machine"]).sort_values(["month", "machine"], ascending=[False, True])
    show = tbl[["month", "machine", "hours", "planned_hr", "a_hr", "run_time", "ideal_hr",
                "m", "kg_good", "waste_kg", "A", "P", "Q", "OEE"]].rename(columns={
        "month": "เดือน", "machine": "เครื่อง", "hours": "ชม.ทำงาน", "planned_hr": "หยุดตามแผน",
        "a_hr": "เสีย A", "run_time": "Run time", "ideal_hr": "Ideal time", "m": "ผลผลิต (m)",
        "kg_good": "ผลผลิตดี (kg)", "waste_kg": "ของเสีย (kg)"})
    show["เดือน"] = pd.to_datetime(show["เดือน"]).dt.strftime("%Y-%m")
    for k in ["A", "P", "Q", "OEE"]:
        show[k] = (show[k] * 100).round(1)
    cfg = {k: st.column_config.NumberColumn(format="%.1f") for k in
           ["ชม.ทำงาน", "หยุดตามแผน", "เสีย A", "Run time", "Ideal time", "ของเสีย (kg)"]}
    cfg.update({k: st.column_config.NumberColumn(format="%.0f") for k in ["ผลผลิต (m)", "ผลผลิตดี (kg)"]})
    cfg.update({k: st.column_config.NumberColumn(f"{k} (%)", format="%.1f%%") for k in ["A", "P", "Q", "OEE"]})
    st.dataframe(show, hide_index=True, column_config=cfg)
    st.download_button("ดาวน์โหลด CSV", show.to_csv(index=False).encode("utf-8-sig"),
                       file_name="oee_monthly.csv", mime="text/csv")
