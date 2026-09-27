"""
02_clean.py - Anonymize and clean the combined payslips.

Input:  data/interim/combined_payslips.csv   (from 01_combine.py)
Output: data/processed/payslips_clean.csv
        data/processed/payslips_clean.xlsx

What this step does:
  1. Anonymizes: coach name -> Jane Doe, company/location -> ABC Studio,
     removes all brand language and internal payroll file paths.
  2. Renames columns to snake_case and drops redundant ones.
  3. Converts dates, times, and numbers to proper data types.
  4. Fixes the inconsistent revenue share column.
  5. Scans every text cell to confirm no identifiers remain.

Usage:
    python src/02_clean.py
"""
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
IN_FILE = ROOT / "data" / "interim" / "combined_payslips.csv"
OUT_DIR = ROOT / "data" / "processed"

from config import BANNED_TERMS, CLASS_NAME, COMPANY, STUDIO_REV_SHARE
from config import COACH as COACH_NAME

# Old column -> new column. Columns not listed here are dropped.
COLUMN_MAP = {
    "Source File": "source_file",
    "Name": "coach",
    "Studio": "studio",
    "Class Date": "class_date",
    "Class Time": "class_time",
    "Total Visits": "total_visits",
    "Class Type": "class_type",
    "Coach Type": "pay_type",
    "Private Class": "private_class",
    "Starter Pay": "starter_rate",
    "Revenue Share %": "revenue_share_pct",
    "RPV": "revenue_per_visit",
    "Incentive Pay": "incentive_pay",
    "Class Name": "class_name",
    "Total Class Pay": "total_class_pay",
}
# Dropped on purpose:
#   Subsidiary      -> replaced by a single "company" column
#   Payscale        -> duplicate of Coach Type with brand name attached
#   Per Class Rate  -> identical to Total Class Pay on every row (checked below)
#   Studio & Level  -> duplicate of Studio + Coach Type
#   Output          -> internal payroll file path


def check_redundant(df: pd.DataFrame) -> None:
    """Confirm the columns we drop really are duplicates before dropping them."""
    assert (df["Per Class Rate"] == df["Total Class Pay"]).all(), \
        "Per Class Rate differs from Total Class Pay somewhere - don't drop it"
    payscale = df["Payscale"].str.split().str[-1]   # drop the company prefix
    assert (payscale == df["Coach Type"]).all(), "Payscale and Coach Type disagree"
    print("Checked: dropped columns are exact duplicates of kept ones")


def anonymize(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["studio_num"] = df["studio"].str.extract(r"Studio (\d)")[0].astype(int)
    df["studio"] = "Studio " + df["studio_num"].astype(str)
    df["coach"] = COACH_NAME
    df["class_name"] = CLASS_NAME
    df.insert(1, "company", COMPANY)
    return df


def fix_types(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["class_date"] = pd.to_datetime(df["class_date"])
    df["class_time"] = pd.to_datetime(df["class_time"], format="%H:%M:%S").dt.time
    for col in ["total_visits", "private_class", "starter_rate", "revenue_per_visit",
                "incentive_pay", "total_class_pay"]:
        df[col] = pd.to_numeric(df[col])
    df["total_visits"] = df["total_visits"].astype(int)
    return df


def fix_revenue_share(df: pd.DataFrame) -> pd.DataFrame:
    """
    The raw column is inconsistent: blank in May, 0.24/0.16 in later Standard
    payslips, and 28 (the flat Starter rate, not a percentage) on Starter rows.
    Standard rows get their studio's rate; Starter rows get 0 (no revenue share).
    """
    df = df.copy()
    raw = pd.to_numeric(df["revenue_share_pct"], errors="coerce")
    studio_rate = df["studio_num"].map(STUDIO_REV_SHARE)

    filled = raw.isna() & (df["pay_type"] == "Standard")
    conflict = raw.notna() & (df["pay_type"] == "Standard") & (raw != studio_rate)
    if conflict.any():
        raise ValueError(f"{conflict.sum()} Standard rows have an unexpected rate")

    df["revenue_share_pct"] = studio_rate.where(df["pay_type"] == "Standard", 0.0)
    print(f"Revenue share: filled {filled.sum()} blank rows, "
          f"set {(df['pay_type'] == 'Starter').sum()} Starter rows to 0")
    return df


def flag_oddities(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    typical = df["private_class"].mode()[0]
    odd = df["private_class"] != typical
    df["data_note"] = ""
    df.loc[odd, "data_note"] = f"private_class differs from typical value ({typical})"
    if odd.any():
        print(f"Flagged {odd.sum()} row(s) with an unusual private_class value")
    return df


def verify_anonymized(df: pd.DataFrame) -> None:
    if not BANNED_TERMS:
        print("WARNING: private_terms.txt not found, so the anonymization check was skipped")
        return
    text = df.astype(str)  # check every column, not just text ones
    hits = [(col, term) for col in text.columns for term in BANNED_TERMS
            if text[col].str.lower().str.contains(term).any()]
    headers = [c for c in df.columns if any(t in c.lower() for t in BANNED_TERMS)]
    if hits or headers:
        raise ValueError(f"Identifiers still present: {hits or headers}")
    print("Verified: no names, brand terms, locations, or file paths remain")


def export(df: pd.DataFrame) -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    order = ["class_date", "class_time", "company", "studio", "studio_num", "coach",
             "class_name", "class_type", "total_visits", "pay_type", "starter_rate",
             "revenue_share_pct", "revenue_per_visit", "incentive_pay",
             "total_class_pay", "private_class", "data_note", "source_file"]
    df = df[order].sort_values(["class_date", "studio_num", "class_time"])
    df = df.reset_index(drop=True)

    out = df.copy()
    out["class_date"] = out["class_date"].dt.date
    out.to_csv(OUT_DIR / "payslips_clean.csv", index=False)

    with pd.ExcelWriter(OUT_DIR / "payslips_clean.xlsx", engine="openpyxl") as xw:
        out.to_excel(xw, sheet_name="Payslips Clean", index=False)
        ws = xw.sheets["Payslips Clean"]
        ws.freeze_panes = "A2"
        ws.auto_filter.ref = ws.dimensions
        fmt = {"A": "yyyy-mm-dd", "B": "h:mm AM/PM", "L": "0%", "M": "$#,##0.00",
               "K": "$#,##0.00", "N": "$#,##0.00", "O": "$#,##0.00"}
        for letter, number_format in fmt.items():
            for cell in ws[letter][1:]:
                cell.number_format = number_format
        for col in ws.columns:
            width = max(len(str(c.value)) for c in col if c.value is not None)
            ws.column_dimensions[col[0].column_letter].width = min(width + 2, 45)
    print(f"Wrote {len(df)} rows, {len(order)} columns to {OUT_DIR}")


def remove_duplicate_classes(df: pd.DataFrame) -> pd.DataFrame:
    """If two payslips list the same class (a re-export), keep the most recent file."""
    key = ["Studio", "Class Date", "Class Time"]
    df = df.sort_values("Source File")
    dupes = df.duplicated(key, keep="last")
    if dupes.any():
        print(f"Removed {dupes.sum()} duplicate class(es) listed on more than one payslip")
    return df[~dupes]


def main():
    raw = pd.read_csv(IN_FILE, dtype=str, keep_default_na=False)
    raw = remove_duplicate_classes(raw)
    check_redundant(raw)
    df = raw.rename(columns=COLUMN_MAP)[list(COLUMN_MAP.values())]
    df = anonymize(df)
    df = fix_types(df)
    df = fix_revenue_share(df)
    df = flag_oddities(df)
    verify_anonymized(df)
    export(df)


if __name__ == "__main__":
    main()
