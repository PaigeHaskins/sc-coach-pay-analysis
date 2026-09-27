"""
01_combine.py - Merge every payslip in data/raw/ into one file.

This step only COMBINES. It keeps every original column and value exactly as
exported and adds one column, Source File, so each row can be traced back to
its payslip. Cleaning and anonymizing happen in the next step.

Outputs:
    data/interim/combined_payslips.csv
    data/interim/combined_payslips.xlsx

Usage:
    python src/01_combine.py
"""
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
RAW_DIR = ROOT / "data" / "raw"
OUT_DIR = ROOT / "data" / "interim"


def load_all(raw_dir: Path) -> pd.DataFrame:
    files = sorted(raw_dir.glob("*_PaySlips.csv"))
    if not files:
        raise FileNotFoundError(f"No payslip files found in {raw_dir}")

    frames = []
    for f in files:
        df = pd.read_csv(f, dtype=str, keep_default_na=False)  # read as-is, no type changes
        df.insert(0, "Source File", f.name)
        frames.append(df)

    # Every file must have the same columns before stacking them
    first_cols = list(frames[0].columns)
    for df in frames[1:]:
        if list(df.columns) != first_cols:
            raise ValueError(f"Column mismatch in {df['Source File'].iloc[0]}")

    return pd.concat(frames, ignore_index=True)


def inventory(df: pd.DataFrame) -> None:
    """Print a summary to check before moving on to cleaning."""
    dates = pd.to_datetime(df["Class Date"])
    print(f"\nCombined {df['Source File'].nunique()} files into {len(df)} rows")
    print(f"Classes from {dates.min():%b %d, %Y} to {dates.max():%b %d, %Y}\n")

    per_file = (df.assign(d=dates)
                  .groupby("Source File")
                  .agg(rows=("d", "size"), first=("d", "min"), last=("d", "max"),
                       payscale=("Coach Type", lambda x: ", ".join(sorted(set(x))))))
    print(per_file.to_string(), "\n")

    key = ["Studio", "Class Date", "Class Time"]
    dupes = df[df.duplicated(key, keep=False)]
    print(f"Duplicate classes (same studio, date, time): {len(dupes)}")
    if len(dupes):
        print(dupes[["Source File"] + key].to_string(index=False))


def export(df: pd.DataFrame, out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    df = df.sort_values(["Class Date", "Studio", "Class Time"]).reset_index(drop=True)
    df.to_csv(out_dir / "combined_payslips.csv", index=False)

    with pd.ExcelWriter(out_dir / "combined_payslips.xlsx", engine="openpyxl") as xw:
        df.to_excel(xw, sheet_name="Combined Payslips", index=False)
        ws = xw.sheets["Combined Payslips"]
        ws.freeze_panes = "A2"
        ws.auto_filter.ref = ws.dimensions
        for col in ws.columns:
            width = max(len(str(c.value)) for c in col if c.value is not None)
            ws.column_dimensions[col[0].column_letter].width = min(width + 2, 40)

    print(f"\nWrote {len(df)} rows to {out_dir}")


if __name__ == "__main__":
    combined = load_all(RAW_DIR)
    inventory(combined)
    export(combined, OUT_DIR)
