"""
run_pipeline.py - Add new data and rebuild everything with one command.

    python run_pipeline.py

1. Files anything new in data/inbox/ (payslips or class logs, CSV or Excel)
2. Combines, cleans, and anonymizes all payslips
3. Adds hand-logged classes (payslips replace estimates once they arrive)
4. Adds features, runs the analysis, and rebuilds the charts and dashboard

Stops at the first step that fails, so a bad file can't slip through.
"""
import subprocess
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent
STEPS = [
    ("File new data", "00_rename_files.py"),
    ("Combine payslips", "01_combine.py"),
    ("Clean and anonymize", "02_clean.py"),
    ("Add class log", "02b_add_class_log.py"),
    ("Add features", "03_features.py"),
    ("Analysis and charts", "04_analysis.py"),
    ("Dashboard", "05_dashboard.py"),
]


def run(label: str, script: str) -> None:
    print(f"\n=== {label} ({script}) ===")
    result = subprocess.run([sys.executable, str(ROOT / "src" / script)], cwd=ROOT)
    if result.returncode != 0:
        sys.exit(f"\nStopped: '{label}' failed. Fix the issue above and run again.")


def summary() -> None:
    df = pd.read_csv(ROOT / "data" / "processed" / "classes_features.csv",
                     parse_dates=["class_date"])
    est = df["pay_estimated"].sum()
    print("\n=== Done ===")
    print(f"Classes:      {len(df)}  ({df['class_date'].min():%b %d, %Y} to "
          f"{df['class_date'].max():%b %d, %Y})")
    print(f"Earned:       ${df['total_class_pay'].sum():,.2f}"
          + (f"  (includes ${df.loc[df['pay_estimated'], 'total_class_pay'].sum():,.2f} "
             f"estimated for {est} classes)" if est else ""))
    print(f"Utilization:  {df['fill_rate'].mean():.0%}")
    print("Dashboard:    outputs/dashboard.html and docs/index.html")


if __name__ == "__main__":
    for label, script in STEPS:
        run(label, script)
    summary()
