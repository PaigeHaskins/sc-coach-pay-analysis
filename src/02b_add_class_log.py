"""
02b_add_class_log.py - Add classes logged by hand to the cleaned payslip data.

Payslips were missing for May 1-15 and for classes after mid-August, so the
coach logged those classes from her own class history. This step cleans that
log into the same format as the payslips, estimates pay where it's missing,
and merges the two into one complete dataset.

Inputs:  data/processed/payslips_clean.csv          (from 02_clean.py)
         data/raw/class_log/*_ClassLog.xlsx          (hand-logged classes)
Output:  data/processed/classes_clean.csv / .xlsx    (payslips + class log)

Usage:
    python src/02b_add_class_log.py
"""
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
PAYSLIPS = ROOT / "data" / "processed" / "payslips_clean.csv"
LOG_DIR = ROOT / "data" / "raw" / "class_log"
OUT_DIR = ROOT / "data" / "processed"

from config import (BANNED_TERMS, CLASS_NAME, COACH, COMPANY, FLOOR_PAY, MAX_PAY,
                    REVENUE_PER_VISIT, STUDIO_REV_SHARE)


def load_log() -> pd.DataFrame:
    files = sorted(LOG_DIR.glob("*_ClassLog.xlsx"))
    if not files:
        raise FileNotFoundError(f"No class log found in {LOG_DIR}")
    frames = []
    for f in files:
        df = pd.read_excel(f)
        df["source_file"] = f.name
        frames.append(df)
    log = pd.concat(frames, ignore_index=True)
    print(f"Loaded {len(log)} logged classes from {len(files)} file(s)")
    return log


def estimate_pay(visits: pd.Series, studio_num: pd.Series) -> pd.Series:
    """Standard formula: between the $28 floor and the $83 maximum."""
    share = studio_num.map(STUDIO_REV_SHARE)
    return (visits * REVENUE_PER_VISIT * share).round(2).clip(FLOOR_PAY, MAX_PAY)


def clean_log(log: pd.DataFrame) -> pd.DataFrame:
    df = pd.DataFrame({
        "class_date": pd.to_datetime(log["Class Date"]),
        "class_time": pd.to_datetime(log["Class Time"].astype(str),
                                     format="%H:%M:%S").dt.time,
        "company": COMPANY,
        "studio": "Studio " + log["Studio"].astype(str),
        "studio_num": log["Studio"].astype(int),
        "coach": COACH,
        "class_name": CLASS_NAME,
        "class_type": "normal",
        "total_visits": log["Total Visits"].astype(int),
        "pay_type": log["Pay Type"].str.strip().str.title(),
        "starter_rate": FLOOR_PAY,
        "revenue_per_visit": REVENUE_PER_VISIT,
        "incentive_pay": 0.0,
        "total_class_pay": pd.to_numeric(log["Total Class Pay"]),
        "private_class": pd.NA,
        "data_note": "",
        "source_file": log["source_file"],
    })
    df["revenue_share_pct"] = df["studio_num"].map(STUDIO_REV_SHARE).where(
        df["pay_type"] == "Standard", 0.0)

    # Fill missing pay: Starter classes pay $28; Standard classes use the formula
    missing = df["total_class_pay"].isna()
    starter = df["pay_type"] == "Starter"
    df.loc[missing & starter, "total_class_pay"] = FLOOR_PAY
    df.loc[missing & ~starter, "total_class_pay"] = estimate_pay(
        df.loc[missing & ~starter, "total_visits"], df.loc[missing & ~starter, "studio_num"])
    df["pay_estimated"] = missing & ~starter

    capped = df["pay_estimated"] & (df["total_class_pay"] == MAX_PAY)
    df.loc[capped, "data_note"] = "Pay estimate capped at $83 maximum"
    cancelled = df["total_visits"] == 0
    df.loc[cancelled, "class_type"] = "cancelled"
    df.loc[cancelled, "data_note"] = "Cancelled, no attendees; paid $28 base"

    print(f"Estimated pay for {df['pay_estimated'].sum()} classes "
          f"({capped.sum()} capped at ${MAX_PAY:.0f}); "
          f"{cancelled.sum()} cancelled class(es) kept at $28")
    return df


KEY = ["studio_num", "class_date", "class_time"]


def resolve_overlaps(log: pd.DataFrame, payslips: pd.DataFrame) -> pd.DataFrame:
    """
    A class can appear more than once when:
      - it's in two class log files (the later file wins), or
      - a payslip arrives for a class that was logged by hand (the payslip wins,
        replacing the estimated pay with the actual amount).
    """
    log = log.sort_values("source_file")
    dup = log.duplicated(KEY, keep="last")
    if dup.any():
        print(f"Class log: {dup.sum()} class(es) appear in more than one log; kept the latest")
    log = log[~dup]

    on_payslip = log.set_index(KEY).index.isin(payslips.set_index(KEY).index)
    if on_payslip.any():
        print(f"Class log: {on_payslip.sum()} class(es) now have a payslip; "
              f"using the payslip's actual pay instead")
    return log[~on_payslip]


def validate(log: pd.DataFrame, payslips: pd.DataFrame) -> None:
    if not log["studio_num"].isin([1, 2]).all():
        raise ValueError("Studio must be 1 or 2")
    if not log["pay_type"].isin(["Starter", "Standard"]).all():
        raise ValueError(f"Unexpected pay types: {log['pay_type'].unique()}")

    # Compare estimates with real payslip classes of the same studio and size
    real = payslips[payslips["pay_type"] == "Standard"]
    ref = real.groupby(["studio_num", "total_visits"])["total_class_pay"].mean()
    est = log[log["pay_estimated"]]
    matched = est.join(ref.rename("payslip_avg"), on=["studio_num", "total_visits"])
    matched = matched.dropna(subset=["payslip_avg"])
    diff = (matched["total_class_pay"] - matched["payslip_avg"]).abs()
    print(f"Estimate check: {len(matched)} of {len(est)} estimated classes have a "
          f"payslip class with the same studio and attendance; "
          f"{(diff <= 0.01).sum()} match to the cent")
    over = diff[diff > 0.01]
    for i in over.index:
        r = matched.loc[i]
        print(f"   {r['class_date']:%b %d} {r['studio']}, {r['total_visits']} visits: "
              f"estimate ${r['total_class_pay']:.2f} vs payslip ${r['payslip_avg']:.2f}")


def verify_anonymized(df: pd.DataFrame) -> None:
    if not BANNED_TERMS:
        print("WARNING: private_terms.txt not found, so the anonymization check was skipped")
        return
    text = df.astype(str).apply(lambda c: c.str.lower())
    hits = [(c, t) for c in text.columns for t in BANNED_TERMS if text[c].str.contains(t).any()]
    if hits:
        raise ValueError(f"Identifiers still present: {hits}")
    print("Verified: no names, brand terms, locations, or file paths remain")


def export(df: pd.DataFrame) -> None:
    out = df.sort_values(["class_date", "studio_num", "class_time"]).reset_index(drop=True)
    out["class_date"] = out["class_date"].dt.date
    out.to_csv(OUT_DIR / "classes_clean.csv", index=False)
    with pd.ExcelWriter(OUT_DIR / "classes_clean.xlsx", engine="openpyxl") as xw:
        out.to_excel(xw, sheet_name="Classes", index=False)
        ws = xw.sheets["Classes"]
        ws.freeze_panes = "A2"
        ws.auto_filter.ref = ws.dimensions
    print(f"Wrote {len(out)} classes "
          f"({(out['data_source'] == 'Payslip').sum()} payslip, "
          f"{(out['data_source'] == 'Class log').sum()} class log) to {OUT_DIR}")


def main():
    payslips = pd.read_csv(PAYSLIPS, parse_dates=["class_date"])
    payslips["class_time"] = pd.to_datetime(payslips["class_time"],
                                            format="%H:%M:%S").dt.time
    payslips["data_note"] = payslips["data_note"].fillna("")
    payslips["pay_estimated"] = False
    payslips["data_source"] = "Payslip"

    log = clean_log(load_log())
    log["data_source"] = "Class log"
    log = resolve_overlaps(log, payslips)
    validate(log, payslips)

    combined = pd.concat([payslips, log[payslips.columns]], ignore_index=True)
    verify_anonymized(combined)
    export(combined)


if __name__ == "__main__":
    main()
