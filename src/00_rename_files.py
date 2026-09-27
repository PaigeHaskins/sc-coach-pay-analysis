"""
00_rename_files.py - File new data under a clear, consistent name.

Reads every CSV or Excel file in the input folder (default: data/inbox), works
out whether it's a payroll export or a hand-kept class log, and files it:

    payslip    -> data/raw/DD-DDMMYYYY_StudioX_PaySlips.csv
    class log  -> data/raw/class_log/DD-DDMMYYYY_ClassLog.xlsx

DD-DD is the first and last class date in the file; if those fall in different
months the name becomes DDMM-DDMMYYYY. Files already added (same contents) are
skipped; a new file covering the same dates replaces the older one. Originals
are moved to data/inbox/_added so nothing is processed twice.

Usage:
    python src/00_rename_files.py                 # uses data/inbox
    python src/00_rename_files.py <input_folder>
"""
import hashlib
import shutil
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
INBOX = ROOT / "data" / "inbox"
RAW = ROOT / "data" / "raw"
LOG_DIR = RAW / "class_log"
LEDGER = RAW / ".added_files.txt"   # fingerprints of every file already taken in
PAYSLIP_COLS = {"Studio", "Class Date", "Class Time", "Total Visits", "Total Class Pay", "Coach Type"}
LOG_COLS = {"Class Date", "Class Time", "Studio", "Total Visits"}


def read_any(path: Path) -> pd.DataFrame:
    if path.suffix.lower() == ".csv":
        return pd.read_csv(path, dtype=str, keep_default_na=False)
    return pd.read_excel(path)


def date_span(dates: pd.Series) -> str:
    start, end = dates.min(), dates.max()
    if (start.month, start.year) == (end.month, end.year):
        return f"{start:%d}-{end:%d%m%Y}"
    return f"{start:%d%m}-{end:%d%m%Y}"


def file_hash(path: Path) -> str:
    return hashlib.md5(path.read_bytes()).hexdigest()


def existing_hashes() -> set:
    known = {file_hash(f) for f in RAW.rglob("*") if f.is_file() and f != LEDGER}
    if LEDGER.exists():
        known |= set(LEDGER.read_text().split())
    return known


def file_payslip(src: Path, df: pd.DataFrame) -> Path:
    studio = df["Studio"].astype(str).str.extract(r"Studio (\d)")[0].iloc[0]
    dates = pd.to_datetime(df["Class Date"])
    target = RAW / f"{date_span(dates)}_Studio{studio}_PaySlips.csv"
    if src.suffix.lower() == ".csv":
        shutil.copy2(src, target)
    else:
        # Excel export: write it out in the same text format as the CSV exports
        out = df.copy()
        out["Class Date"] = dates.dt.strftime("%Y-%m-%d")
        out["Class Time"] = pd.to_datetime(out["Class Time"].astype(str), format="mixed").dt.strftime("%H:%M:%S")
        out.to_csv(target, index=False)
    return target


def file_class_log(src: Path, df: pd.DataFrame) -> Path:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    target = LOG_DIR / f"{date_span(pd.to_datetime(df['Class Date']))}_ClassLog.xlsx"
    if src.suffix.lower() == ".xlsx":
        shutil.copy2(src, target)
    else:
        df.to_excel(target, index=False)
    return target


def main(in_dir: Path) -> int:
    files = sorted(f for f in in_dir.glob("*") if f.suffix.lower() in (".csv", ".xlsx"))
    if not files:
        print(f"No new files in {in_dir}")
        return 0
    RAW.mkdir(parents=True, exist_ok=True)
    added_dir = in_dir / "_added"
    added_dir.mkdir(exist_ok=True)
    known = existing_hashes()
    added = 0

    for f in files:
        h = file_hash(f)
        if h in known:
            print(f"SKIPPED    {f.name}: already added")
            shutil.move(f, added_dir / f.name)
            continue
        df = read_any(f)
        cols = set(df.columns)
        if PAYSLIP_COLS <= cols:
            target = file_payslip(f, df)
        elif LOG_COLS <= cols:
            target = file_class_log(f, df)
        else:
            print(f"UNKNOWN    {f.name}: not a payslip or class log - left in the inbox")
            continue
        known.add(h)
        with LEDGER.open("a") as ledger:
            ledger.write(h + "\n")
        added += 1
        shutil.move(f, added_dir / f.name)
        dates = pd.to_datetime(df["Class Date"])
        print(f"ADDED      {f.name} -> {target.relative_to(ROOT)}  "
              f"({len(df)} classes, {dates.min():%b %d} to {dates.max():%b %d})")
    return added


if __name__ == "__main__":
    main(Path(sys.argv[1]) if len(sys.argv) > 1 else INBOX)
