"""Load the ME Order Google Sheet and turn it into tidy tables for the dashboard.

Column positions are set in COLS below (Excel-style letters). If a column moves in
the sheet, change the letter here; nothing else needs editing.
"""
from __future__ import annotations

import io
import re

import numpy as np
import pandas as pd

DEFAULT_SHEET_ID = "1LKTmEWT3AqRqeecplgLJlmDelN_z-tk9A1JKWEz-XwI"

SHEETS = ["OEE_DATA", "OEE_FORM", "TimeLoss", "Waste"]
ORDER_SHEET, WIP_SHEET, MASTER_SHEET = "ใบสั่งผลิต", "ใบสั่งผลิต WIP", "Master"
OPTIONAL_SHEETS = ["OEE_Total", ORDER_SHEET, WIP_SHEET, MASTER_SHEET]  # used if present; the app still works without them

# Column letters per sheet --------------------------------------------------
COLS = {
    "OEE_DATA": {
        "date": "A", "machine": "B", "sf": "C", "product": "D",
        "hours": "I", "kg_good": "J", "m": "K",
        "loss_code": "O", "loss_desc": "P", "loss_hr": "Q",
        "waste_code": "R", "waste_desc": "S", "waste_m": "U", "waste_kg": "V",
        "loss_group": "AP", "planned_hr": "AQ", "a_hr": "AR", "p_hr": "AS",
        "ideal_hr": "AU",
    },
    "OEE_FORM": {
        "date": "A", "start": "B", "end": "C", "hours": "D", "machine": "E", "sf": "F", "product": "G",
        "type": "K", "waste_type": "P", "waste_code": "Q",
        "loss_code": "S", "loss_hr": "U", "waste_kg": "V", "waste_m": "W",
        "ideal_hr": "AB", "loss_group": "AC", "planned_hr": "AD", "a_hr": "AE",
        "p_hr": "AF", "m": "AH", "kg_good": "AI",
    },
    "TimeLoss": {"code": "A", "desc": "B", "group": "C"},
    "OEE_Total": {
        "month": "A", "machines": "B", "hours": "C", "planned_time": "D", "run_time": "E",
        "ideal_hr": "F", "kg_good": "G", "waste_kg": "H", "A": "I", "P": "J", "Q": "K", "OEE": "L",
    },
    "Waste": {"code": "A", "desc": "B"},
    "ใบสั่งผลิต": {
        "so": "A", "so_date": "B", "due": "C", "customer": "D", "sf": "E", "product": "F",
        "desc": "G", "qty": "H", "done": "I", "remain": "J", "status": "K", "note": "L",
    },
    "ใบสั่งผลิต WIP": {
        "open_date": "A", "sf": "B", "product": "C", "desc": "D", "qty": "E", "done": "F",
        "remain": "G", "status": "H", "note": "I",
    },
    "Master": {"product": "A", "name": "B", "category": "O"},
}

PLANNED = "หยุดตามแผน"


def col_idx(letter: str) -> int:
    n = 0
    for ch in letter.upper():
        n = n * 26 + (ord(ch) - 64)
    return n - 1


# ---------------------------------------------------------------- loading
def load_public_xlsx(sheet_id: str) -> dict[str, pd.DataFrame]:
    """Read the sheet through its public export link (sheet shared as 'Anyone with the link')."""
    import urllib.request

    url = f"https://docs.google.com/spreadsheets/d/{sheet_id}/export?format=xlsx"
    with urllib.request.urlopen(url, timeout=120) as r:
        raw = r.read()
    xls = pd.ExcelFile(io.BytesIO(raw))
    wanted = SHEETS + [n for n in OPTIONAL_SHEETS if n in xls.sheet_names]
    return {n: pd.read_excel(xls, sheet_name=n, header=None, dtype=object) for n in wanted}


def load_service_account(sheet_id: str, creds: dict) -> dict[str, pd.DataFrame]:
    """Read the sheet with a Google service account (sheet kept private, shared to the account email)."""
    import gspread

    gc = gspread.service_account_from_dict(creds)
    sh = gc.open_by_key(sheet_id)
    out = {}
    existing = {ws.title for ws in sh.worksheets()}
    for name in SHEETS + [n for n in OPTIONAL_SHEETS if n in existing]:
        values = sh.worksheet(name).get_all_values(
            value_render_option="UNFORMATTED_VALUE",
            date_time_render_option="SERIAL_NUMBER",
        )
        width = max((len(r) for r in values), default=0)
        out[name] = pd.DataFrame([r + [None] * (width - len(r)) for r in values], dtype=object)
    return out


# ---------------------------------------------------------------- cleaning
def to_num(s: pd.Series) -> pd.Series:
    if s.dtype.kind in "if":
        return s.astype(float).fillna(0.0)
    txt = s.astype("string").str.strip()
    pct = txt.str.endswith("%", na=False)
    val = pd.to_numeric(txt.str.replace(",", "", regex=False).str.rstrip("%"), errors="coerce")
    val = val.where(~pct, val / 100)
    return val.astype(float).fillna(0.0)


def to_date(s: pd.Series, future_days: int | None = 62) -> pd.Series:
    out = pd.Series(pd.NaT, index=s.index, dtype="datetime64[ns]")
    is_dt = s.map(lambda v: isinstance(v, (pd.Timestamp, np.datetime64)) or hasattr(v, "year"))
    if is_dt.any():
        out[is_dt] = pd.to_datetime(s[is_dt], errors="coerce")
    is_num = s.map(lambda v: isinstance(v, (int, float, np.number)) and not isinstance(v, bool) and not pd.isna(v)) & ~is_dt
    if is_num.any():
        out[is_num] = pd.to_datetime(s[is_num].astype(float), unit="D", origin="1899-12-30", errors="coerce")
    rest = ~is_dt & ~is_num & s.notna()
    if rest.any():
        txt = s[rest].astype(str).str.strip()
        # Fix Buddhist-era years in the text before parsing (pandas cannot hold year 2569):
        # 24/10/68 -> 24/10/2025, 12/10/2569 -> 12/10/2026
        dmy = txt.str.extract(r"^(\d{1,2})[/.-](\d{1,2})[/.-](\d{2}|\d{4})(?!\d)")
        ok = dmy[2].notna()
        if ok.any():
            y = dmy.loc[ok, 2].astype(int)
            y = y.where(y >= 100, (2500 + y - 543).where(y >= 40, 2000 + y))
            y = y.where(y < 2400, y - 543)
            txt.loc[ok] = dmy.loc[ok, 0] + "/" + dmy.loc[ok, 1] + "/" + y.astype(str)
        out[rest] = pd.to_datetime(txt, dayfirst=True, errors="coerce", format="mixed")
    # Google Sheets turns a typed "24/10/68" into a real date 24/10/1968 (2-digit Buddhist year
    # read as 19xx). 19xx + 600 - 543 = +57 years -> 24/10/2025.
    bad19 = out.dt.year.between(1940, 1999)
    if bad19.any():
        out[bad19] = out[bad19] + pd.DateOffset(years=57)
    out[out < pd.Timestamp("2000-01-01")] = pd.NaT
    if future_days is not None:
        out[out > pd.Timestamp.today() + pd.Timedelta(days=future_days)] = pd.NaT
    return out.dt.normalize()


def to_day_fraction(s: pd.Series) -> pd.Series:
    """Clock time -> fraction of a day. Accepts 0.54, '13:00:00', time objects or datetimes."""
    def conv(v):
        if v is None or (isinstance(v, float) and np.isnan(v)) or v == "":
            return np.nan
        if isinstance(v, (int, float, np.number)):
            return float(v) % 1
        if hasattr(v, "hour"):
            return (v.hour * 3600 + v.minute * 60 + getattr(v, "second", 0)) / 86400
        m = re.match(r"^\s*(\d{1,2}):(\d{2})(?::(\d{2}))?", str(v))
        if m:
            h, mi, se = int(m.group(1)), int(m.group(2)), int(m.group(3) or 0)
            return (h * 3600 + mi * 60 + se) / 86400
        return np.nan
    return s.map(conv).astype(float)


def to_text(s: pd.Series) -> pd.Series:
    t = s.map(lambda v: "" if v is None or (isinstance(v, float) and np.isnan(v)) else
              (str(int(v)) if isinstance(v, float) and v.is_integer() else str(v)))
    return t.str.strip()


def pick(df: pd.DataFrame, sheet: str) -> pd.DataFrame:
    """Take the configured columns from a raw sheet (row 0 = header)."""
    body = df.iloc[1:].reset_index(drop=True)
    cols = {}
    for name, letter in COLS[sheet].items():
        i = col_idx(letter)
        cols[name] = body.iloc[:, i] if i < body.shape[1] else pd.Series([None] * len(body), dtype=object)
    return pd.DataFrame(cols)


def build_events(raw: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """One tidy row per sheet row from OEE_DATA (history) and OEE_FORM (form)."""
    tl = pick(raw["TimeLoss"], "TimeLoss")
    loss_desc = dict(zip(to_text(tl["code"]).str.upper(), to_text(tl["desc"])))
    loss_grp = dict(zip(to_text(tl["code"]).str.upper(), to_text(tl["group"])))
    ws = pick(raw["Waste"], "Waste")
    waste_desc = dict(zip(to_text(ws["code"]).str.upper(), to_text(ws["desc"])))

    frames = []
    for sheet in ("OEE_DATA", "OEE_FORM"):
        d = pick(raw[sheet], sheet)
        ev = pd.DataFrame({
            "source": "ข้อมูลเก่า" if sheet == "OEE_DATA" else "ฟอร์ม",
            "date": to_date(d["date"]),
            "machine": to_text(d["machine"]).str.upper(),
            "sf": to_text(d["sf"]).str.upper(),
            "product": to_text(d["product"]),
        })
        for c in ("hours", "m", "kg_good", "loss_hr", "planned_hr", "a_hr", "p_hr", "ideal_hr", "waste_kg", "waste_m"):
            ev[c] = to_num(d[c])
        if sheet == "OEE_FORM":
            # production hours, metres and good kg only count on Production rows
            is_prod = to_text(d["type"]).str.lower().eq("production")
            # hours from End - Start (handles shifts past midnight); fall back to the sheet's column
            st_, en_ = to_day_fraction(d["start"]), to_day_fraction(d["end"])
            span = ((en_ - st_) % 1) * 24
            ev["hours"] = span.where(span.notna() & (span > 0), ev["hours"])
            ev.loc[~is_prod, "hours"] = 0.0
            ev["waste_type"] = to_text(d["waste_type"])
        else:
            ev["waste_type"] = ""
        code = to_text(d["loss_code"]).str.upper().str.extract(r"^([A-Z][0-9]+)", expand=False).fillna("")
        ev["loss_code"] = code
        grp = to_text(d["loss_group"])
        ev["loss_group"] = grp.where(grp != "", code.map(loss_grp).fillna("A").where(code != "", ""))
        desc = code.map(loss_desc)
        if "loss_desc" in d:
            desc = desc.fillna(to_text(d["loss_desc"]))
        ev["loss_desc"] = desc.fillna("")
        wcode = to_text(d["waste_code"]).str.upper().str.extract(r"^(S[0-9]+)", expand=False).fillna("")
        ev["waste_code"] = wcode
        wdesc = wcode.map(waste_desc)
        if "waste_desc" in d:
            wdesc = wdesc.fillna(to_text(d["waste_desc"]))
        ev["waste_desc"] = wdesc.fillna("")
        frames.append(ev)

    ev = pd.concat(frames, ignore_index=True)
    ev = ev[ev["date"].notna() & (ev["machine"] != "")].copy()
    ev["month"] = ev["date"].dt.to_period("M").dt.to_timestamp()
    ev["excluded"] = ev["sf"].str.startswith("IS")
    return ev


# ---------------------------------------------------------------- metrics
def oee_table(ev: pd.DataFrame, by: list[str]) -> pd.DataFrame:
    """Sum the OEE components over `by` and compute A, P, Q, OEE from the sums."""
    g = ev.groupby(by, dropna=False)[["hours", "planned_hr", "a_hr", "p_hr", "ideal_hr", "m", "kg_good", "waste_kg"]].sum()
    g = g.reset_index() if by else g.to_frame().T
    g["planned_time"] = g["hours"] - g["planned_hr"]
    g["run_time"] = g["planned_time"] - g["a_hr"]
    g["A"] = np.where(g["planned_time"] > 0, g["run_time"] / g["planned_time"].where(g["planned_time"] > 0), np.nan)
    g["P"] = np.where(g["run_time"] > 0, g["ideal_hr"] / g["run_time"].where(g["run_time"] > 0), np.nan)
    g["Q"] = np.where(g["kg_good"] > 0, g["kg_good"] / (g["kg_good"] + g["waste_kg"]).where(g["kg_good"] > 0), 1.0)
    g["OEE"] = g["A"] * g["P"] * g["Q"]
    return g


def oee_total(ev: pd.DataFrame) -> pd.Series:
    t = ev[["hours", "planned_hr", "a_hr", "p_hr", "ideal_hr", "m", "kg_good", "waste_kg"]].sum()
    return oee_table(pd.DataFrame([t]).assign(_k=1), ["_k"]).iloc[0]


def build_total(raw: dict[str, pd.DataFrame]) -> pd.DataFrame | None:
    """Monthly all-machine OEE exactly as calculated in the OEE_Total sheet (None if the sheet is missing)."""
    if "OEE_Total" not in raw:
        return None
    d = pick(raw["OEE_Total"], "OEE_Total")
    out = pd.DataFrame({"month": to_date(d["month"])})
    for c in ["machines", "hours", "planned_time", "run_time", "ideal_hr", "kg_good", "waste_kg"]:
        out[c] = to_num(d[c])
    for c in ["A", "P", "Q", "OEE"]:
        v = to_num(d[c]).where(to_text(d[c]) != "")
        # a percent cell exported as 85.8 (not 0.858) -> scale down
        out[c] = v.where(v.abs() <= 5, v / 100)
    out = out[out["month"].notna()].copy()
    out["month"] = out["month"].dt.to_period("M").dt.to_timestamp()
    return out.sort_values("month").reset_index(drop=True)


# ---------------------------------------------------------------- order tracking
NO_CATEGORY = "ไม่ระบุหมวด"


def _category_map(raw: dict[str, pd.DataFrame]) -> dict[str, str]:
    """Product code -> category from the Master sheet (column O, header 'หมวด')."""
    if MASTER_SHEET not in raw:
        return {}
    m = raw[MASTER_SHEET]
    # find the 'หมวด' column by header; fall back to column O
    header = [to_text(pd.Series([v])).iloc[0] for v in m.iloc[0].tolist()]
    i = next((k for k, h in enumerate(header) if h.startswith("หมวด")), col_idx(COLS[MASTER_SHEET]["category"]))
    if i >= m.shape[1]:
        return {}
    body = m.iloc[1:]
    code = to_text(body.iloc[:, 0]).str.upper()
    cat = to_text(body.iloc[:, i])
    cat = cat.where(cat == "", cat.map(lambda c: f"หมวด {c}" if c.isdigit() else c))
    return {k: v for k, v in zip(code, cat) if k and v}


def _status(d: pd.DataFrame) -> pd.Series:
    st = to_text(d["status"]).str.lower()
    return np.where(st.str.startswith("complete") | (d["remain"] <= 0), "complete", "in progress")


def build_orders(raw: dict[str, pd.DataFrame]) -> pd.DataFrame | None:
    """Sales-order lines from 'ใบสั่งผลิต' with category from Master (None if the sheet is missing)."""
    if ORDER_SHEET not in raw:
        return None
    d = pick(raw[ORDER_SHEET], ORDER_SHEET)
    out = pd.DataFrame({
        "so": to_text(d["so"]), "so_date": to_date(d["so_date"], None), "due": to_date(d["due"], None),
        "customer": to_text(d["customer"]), "sf": to_text(d["sf"]), "product": to_text(d["product"]),
        "desc": to_text(d["desc"]), "qty": to_num(d["qty"]), "done": to_num(d["done"]),
        "note": to_text(d["note"]),
    })
    rem = to_num(d["remain"])
    out["remain"] = rem.where(to_text(d["remain"]) != "", (out["qty"] - out["done"]).clip(lower=0))
    out["status"] = _status(out.assign(status=d["status"].values))
    out = out[(out["sf"] != "") | (out["product"] != "")].copy()
    cats = _category_map(raw)
    out["category"] = out["product"].str.upper().map(cats).fillna(NO_CATEGORY)
    return out.reset_index(drop=True)


def build_wip(raw: dict[str, pd.DataFrame]) -> pd.DataFrame | None:
    """Work-in-process orders from 'ใบสั่งผลิต WIP' (semi-finished: DT / IS / DTIS ...)."""
    if WIP_SHEET not in raw:
        return None
    d = pick(raw[WIP_SHEET], WIP_SHEET)
    out = pd.DataFrame({
        "open_date": to_date(d["open_date"], None), "sf": to_text(d["sf"]), "product": to_text(d["product"]),
        "desc": to_text(d["desc"]), "qty": to_num(d["qty"]), "done": to_num(d["done"]), "note": to_text(d["note"]),
    })
    rem = to_num(d["remain"])
    out["remain"] = rem.where(to_text(d["remain"]) != "", (out["qty"] - out["done"]).clip(lower=0))
    out["status"] = _status(out.assign(status=d["status"].values))
    out = out[(out["sf"] != "") | (out["product"] != "")].copy()
    # WIP type = letters at the start of the SF number (DT, IS, DTIS ...)
    out["wip_type"] = out["sf"].str.upper().str.extract(r"^([A-Z]+)", expand=False).fillna("อื่นๆ")
    cats = _category_map(raw)
    out["category"] = out["product"].str.upper().map(cats).fillna(NO_CATEGORY)
    return out.reset_index(drop=True)
