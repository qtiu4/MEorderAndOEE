"""OEE / Time Loss / Waste dashboard — reads the ME Order Google Sheet live."""
from datetime import datetime, timedelta, timezone

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

import data as D

st.set_page_config(page_title="OEE Dashboard", page_icon="🏭", layout="wide")

# Fixed colours: a machine keeps its colour on every chart, whatever the filter.
MACHINE_COLORS = {"IL1": "#2a78d6", "IL2": "#eb6834", "IL3": "#1baf7a", "DT": "#eda100",
                  "DT1": "#e87ba4", "DT2": "#6250d6"}
GROUP_COLORS = {"A": "#2a78d6", "P": "#eb6834", D.PLANNED: "#a3a29c"}
TH_TZ = timezone(timedelta(hours=7))
PCT = ".1%"


# ------------------------------------------------------------------ data
@st.cache_data(ttl=600, show_spinner="กำลังดึงข้อมูลจาก Google Sheets…")
def load_events() -> tuple[pd.DataFrame, pd.DataFrame | None, str]:
    try:
        secrets = dict(st.secrets)
    except Exception:  # noqa: BLE001 - no secrets configured
        secrets = {}
    sheet_id = secrets.get("sheet_id", D.DEFAULT_SHEET_ID)
    if "gcp_service_account" in secrets:
        raw = D.load_service_account(sheet_id, dict(secrets["gcp_service_account"]))
    else:
        raw = D.load_public_xlsx(sheet_id)
    return D.build_events(raw), D.build_total(raw), datetime.now(TH_TZ).strftime("%d/%m/%Y %H:%M")


def machine_color_map(machines):
    extra = ["#1baf7a", "#e34948", "#008300", "#6250d6"]
    out, i = {}, 0
    for m in sorted(machines):
        if m in MACHINE_COLORS:
            out[m] = MACHINE_COLORS[m]
        else:
            out[m] = extra[i % len(extra)]
            i += 1
    return out


def style(fig, height=360, pct_axis=False):
    fig.update_layout(height=height, margin=dict(l=10, r=10, t=40, b=10),
                      legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0, title=None),
                      hovermode="x unified")
    fig.update_xaxes(title=None, showgrid=False)
    fig.update_yaxes(title=None, gridcolor="rgba(128,128,128,0.15)", zeroline=False)
    if pct_axis:
        fig.update_yaxes(tickformat=".0%")
    return fig


def show_chart(container, fig):
    """Full-width chart on both newer (width=) and older (use_container_width=) Streamlit."""
    try:
        container.plotly_chart(fig, width="stretch")
    except TypeError:
        container.plotly_chart(fig, use_container_width=True)


def fmt_pct(v):
    return "–" if pd.isna(v) else f"{v:.1%}"


try:
    events, total_sheet, loaded_at = load_events()
except Exception as e:  # noqa: BLE001
    st.error("ดึงข้อมูลจาก Google Sheets ไม่ได้ ตรวจว่าแชร์ชีตแล้ว หรือใส่ service account ใน Secrets แล้ว")
    st.exception(e)
    st.stop()

# ------------------------------------------------------------------ sidebar filters
with st.sidebar:
    st.header("ตัวกรอง")
    months = sorted(events["month"].unique())
    month_labels = [pd.Timestamp(m).strftime("%b %Y") for m in months]
    default_start = max(0, len(months) - 12)
    m_from, m_to = st.select_slider("ช่วงเดือน", options=month_labels,
                                    value=(month_labels[default_start], month_labels[-1]))
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

st.title("OEE Dashboard")
st.caption(f"{m_from} – {m_to} · {', '.join(sel_machines)}")

tab_oee, tab_total, tab_loss, tab_waste, tab_data = st.tabs(
    ["OEE แยกเครื่อง", "OEE รวมรายเดือน", "Time Loss", "Waste", "ตารางข้อมูล"])

# ------------------------------------------------------------------ OEE
with tab_oee:
    tot = D.oee_total(ev)
    last_m = max(sel_months)
    prev_m = (pd.Timestamp(last_m) - pd.offsets.MonthBegin(1))
    cur = D.oee_total(ev[ev["month"] == last_m]) if (ev["month"] == last_m).any() else None
    prv_ev = pool[(pool["month"] == prev_m) & pool["machine"].isin(sel_machines)]
    prv = D.oee_total(prv_ev) if not prv_ev.empty else None

    st.subheader("ภาพรวมช่วงที่เลือก")
    c = st.columns(4)
    for col, key, label in zip(c, ["OEE", "A", "P", "Q"], ["OEE", "Availability", "Performance", "Quality"]):
        col.metric(label, fmt_pct(tot[key]))
    if cur is not None:
        st.caption(f"เดือนล่าสุด {pd.Timestamp(last_m):%b %Y}: OEE {fmt_pct(cur['OEE'])}"
                   + (f" (เดือนก่อน {fmt_pct(prv['OEE'])})" if prv is not None else ""))

    by_mm = D.oee_table(ev, ["month", "machine"])
    by_m = D.oee_table(ev, ["month"]).assign(machine="รวม")

    metric = st.radio("ตัวชี้วัด", ["OEE", "A", "P", "Q"], horizontal=True,
                      format_func={"OEE": "OEE", "A": "Availability", "P": "Performance", "Q": "Quality"}.get)
    fig = px.line(by_mm, x="month", y=metric, color="machine", markers=True,
                  color_discrete_map=cmap, title=f"{metric} รายเดือนแยกเครื่อง")
    fig.add_trace(go.Scatter(x=by_m["month"], y=by_m[metric], name="รวม", mode="lines",
                             line=dict(color="#7f7f7f", width=2, dash="dot")))
    fig.update_traces(hovertemplate="%{y:.1%}")
    show_chart(st, style(fig, pct_axis=True))

    c1, c2 = st.columns(2)
    by_mach = D.oee_table(ev, ["machine"])
    melt = by_mach.melt(id_vars="machine", value_vars=["A", "P", "Q", "OEE"], var_name="ตัวชี้วัด", value_name="ค่า")
    fig = px.bar(melt, x="ตัวชี้วัด", y="ค่า", color="machine", barmode="group",
                 color_discrete_map=cmap, title="A / P / Q / OEE แยกเครื่อง (ทั้งช่วง)", text_auto=".0%")
    fig.update_traces(hovertemplate="%{y:.1%}", marker_line_width=0)
    show_chart(c1, style(fig, pct_axis=True))

    lossbars = by_m[["month", "planned_hr", "a_hr", "run_time"]].rename(
        columns={"planned_hr": "หยุดตามแผน", "a_hr": "เสีย A", "run_time": "เวลาเดินจริง"})
    fig = px.bar(lossbars, x="month", y=["เวลาเดินจริง", "เสีย A", "หยุดตามแผน"],
                 color_discrete_map={"เวลาเดินจริง": "#1baf7a", "เสีย A": "#2a78d6", "หยุดตามแผน": "#a3a29c"},
                 title="ชั่วโมงทำงานรายเดือน (ทุกเครื่องที่เลือก)")
    fig.update_traces(hovertemplate="%{y:,.1f} ชม.", marker_line_width=0)
    show_chart(c2, style(fig))

# ------------------------------------------------------------------ OEE total (sheet OEE_Total)
METRIC_COLORS = {"OEE": "#2a78d6", "A": "#eb6834", "P": "#1baf7a", "Q": "#eda100"}
METRIC_NAMES = {"OEE": "OEE", "A": "Availability", "P": "Performance", "Q": "Quality"}
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
            st.subheader(f"เดือนล่าสุด: {last['month']:%b %Y}")
            c = st.columns(4)
            for col, k in zip(c, ["OEE", "A", "P", "Q"]):
                delta = None
                if prev is not None and pd.notna(last[k]) and pd.notna(prev[k]):
                    delta = f"{(last[k] - prev[k]) * 100:+.1f} จุด จากเดือนก่อน"
                col.metric(METRIC_NAMES[k], fmt_pct(last[k]), delta)

            long = tt.melt(id_vars="month", value_vars=["OEE", "A", "P", "Q"], var_name="k", value_name="v")
            long["ตัวชี้วัด"] = long["k"].map(METRIC_NAMES)
            fig = px.line(long, x="month", y="v", color="ตัวชี้วัด", markers=True,
                          color_discrete_map={METRIC_NAMES[k]: v for k, v in METRIC_COLORS.items()},
                          category_orders={"ตัวชี้วัด": list(METRIC_NAMES.values())},
                          title="OEE / A / P / Q รวมทุกเครื่อง รายเดือน")
            fig.update_traces(hovertemplate="%{y:.1%}")
            show_chart(st, style(fig, height=400, pct_axis=True))

            c1, c2 = st.columns(2)
            fig = px.bar(tt, x="month", y="OEE", title="OEE รวมรายเดือน", text_auto=".1%",
                         color_discrete_sequence=[METRIC_COLORS["OEE"]])
            fig.update_traces(hovertemplate="%{y:.1%}<extra></extra>", marker_line_width=0)
            show_chart(c1, style(fig, pct_axis=True))
            hrs = tt[["month", "planned_time", "run_time", "ideal_hr"]].rename(columns={
                "planned_time": "Planned time", "run_time": "Run time", "ideal_hr": "Ideal time"})
            fig = px.bar(hrs, x="month", y=["Planned time", "Run time", "Ideal time"], barmode="group",
                         color_discrete_sequence=["#a3a29c", "#eb6834", "#1baf7a"],
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
        c = st.columns(4)
        c[0].metric("เวลาสูญเสียรวม", f"{loss['loss_hr'].sum():,.1f} ชม.")
        c[1].metric("เสีย A (กระทบ Availability)", f"{g.get('A', 0):,.1f} ชม.")
        c[2].metric("เสีย P (หยุดสั้น)", f"{g.get('P', 0):,.1f} ชม.")
        c[3].metric("หยุดตามแผน", f"{g.get(D.PLANNED, 0):,.1f} ชม.")

        trend = loss.groupby(["month", "loss_group"], as_index=False)["loss_hr"].sum()
        fig = px.bar(trend, x="month", y="loss_hr", color="loss_group", color_discrete_map=GROUP_COLORS,
                     category_orders={"loss_group": ["A", "P", D.PLANNED]}, title="เวลาสูญเสียรายเดือนแยกกลุ่ม")
        fig.update_traces(hovertemplate="%{y:,.1f} ชม.", marker_line_width=0)
        show_chart(st, style(fig))

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
        show_chart(c1, style(fig, height=520))

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
    c = st.columns(4)
    c[0].metric("ผลผลิตรวม", f"{good_m:,.0f} m")
    c[1].metric("ของเสีย (kg)", f"{tw_kg:,.1f} kg",
                help="% เทียบกับผลผลิตดี (kg) + ของเสีย (kg)")
    c[2].metric("ของเสีย (m)", f"{tw_m:,.0f} m")
    c[3].metric("% ของเสีย (kg)", fmt_pct(tw_kg / (good_kg + tw_kg)) if good_kg + tw_kg > 0 else "–")

    c1, c2 = st.columns(2)
    fig = px.line(w_m, x="month", y=["% ของเสีย (kg)", "% ของเสีย (m)"], markers=True,
                  color_discrete_sequence=["#2a78d6", "#eb6834"], title="% ของเสียรายเดือน")
    fig.update_traces(hovertemplate="%{y:.2%}")
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
        fig = px.bar(top.iloc[::-1], x=val, y="label", orientation="h",
                     color_discrete_sequence=["#2a78d6"], title=f"Pareto สาเหตุของเสีย ({unit})")
        fig.update_traces(hovertemplate="%{x:,.1f} " + unit + "<extra></extra>", marker_line_width=0)
        fig.update_layout(hovermode="closest")
        show_chart(c1, style(fig, height=520))
    wt = ev[(ev["waste_type"] != "") & (ev[val] > 0)]
    if wt.empty:
        c2.info("ประเภทของเสีย (CU / PVC / SL / Wire) มีเฉพาะข้อมูลจากฟอร์ม")
    else:
        t = wt.groupby("waste_type", as_index=False)[val].sum().sort_values(val, ascending=False)
        fig = px.bar(t, x="waste_type", y=val, color_discrete_sequence=["#eb6834"],
                     title=f"ของเสียแยกประเภท ({unit}) — ข้อมูลจากฟอร์ม")
        fig.update_traces(hovertemplate="%{y:,.1f} " + unit + "<extra></extra>", marker_line_width=0)
        fig.update_layout(hovermode="closest")
        show_chart(c2, style(fig, height=520))

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
