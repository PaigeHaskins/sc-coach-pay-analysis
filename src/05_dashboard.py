"""
05_dashboard.py - Build the interactive dashboard.

Computes every number the dashboard shows from the complete dataset, then
injects them into src/dashboard_template.html as JSON. The output is one
self-contained HTML file (no server needed) that can be opened in a browser
or hosted on GitHub Pages.

Input:  data/processed/classes_features.csv   (from 03_features.py)
Output: outputs/dashboard.html
        docs/index.html   (the same page, served by GitHub Pages)

Usage:
    python src/05_dashboard.py
"""
import importlib.util
import json
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data" / "processed" / "classes_features.csv"
TEMPLATE = ROOT / "src" / "dashboard_template.html"
OUT = ROOT / "outputs" / "dashboard.html"
PAGES = ROOT / "docs" / "index.html"

from config import FORECAST_WEEKS, RECENT_OCCURRENCES, RECENT_WEEKS  # noqa: E402
DAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
BUCKETS = [("Early", 6, 9), ("Morning", 9, 12), ("Midday", 12, 15),
           ("Afternoon", 15, 18), ("Evening", 18, 22)]

# Reuse the slot table and recommendation rules from the analysis step
_spec = importlib.util.spec_from_file_location("analysis", ROOT / "src" / "04_analysis.py")
analysis = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(analysis)


def r2(x):
    return None if pd.isna(x) else round(float(x), 2)


def kpis(df):
    active_weeks = df["class_date"].dt.to_period("W").nunique()
    revenue = (df["total_visits"] * df["revenue_per_visit"]).sum()
    return {
        "classes": int(len(df)),
        "earned": r2(df["total_class_pay"].sum()),
        "earned_estimated": r2(df.loc[df["pay_estimated"], "total_class_pay"].sum()),
        "estimated_classes": int(df["pay_estimated"].sum()),
        "avg_pay_actual": r2(df["total_class_pay"].mean()),
        "avg_pay_standard": r2(df["pay_if_standard_rate"].mean()),
        "utilization": r2(df["fill_rate"].mean()),
        "utilization_capped": r2((df["booked"] / df["capacity"]).mean()),
        "avg_clients": r2(df["total_visits"].mean()),
        "clients": int(df["total_visits"].sum()),
        "waitlist": int(df["waitlist"].sum()),
        "pct_full": r2(df["is_full"].mean()),
        "per_week": r2(len(df) / active_weeks),
        "studio_revenue": r2(revenue),
        "pay_share": r2(df["total_class_pay"].sum() / revenue),
    }


def weekly(df):
    w = (df.set_index("class_date")
           .resample("W-MON", label="left", closed="left")
           .agg(earned=("total_class_pay", "sum"), classes=("total_class_pay", "size"),
                avg_clients=("total_visits", "mean"), fill=("fill_rate", "mean"),
                estimated=("pay_estimated", "sum")))
    return [{"week": d.strftime("%Y-%m-%d"), "label": d.strftime("%b %-d"),
             "earned": r2(r["earned"]), "classes": int(r["classes"]),
             "avg_clients": r2(r["avg_clients"]), "fill": r2(r["fill"]),
             "estimated": int(r["estimated"])} for d, r in w.iterrows()]


def monthly(df):
    m = (df.groupby(df["class_date"].dt.to_period("M"))
           .agg(classes=("total_class_pay", "size"), earned=("total_class_pay", "sum"),
                avg_std=("pay_if_standard_rate", "mean"), fill=("fill_rate", "mean"),
                avg_clients=("total_visits", "mean")))
    last = df["class_date"].max()
    def label(p):
        partial = p == last.to_period("M") and last < p.end_time.normalize()
        return p.strftime("%b") + (f" (to {last:%-d})" if partial else "")
    return [{"month": label(p), "classes": int(r["classes"]),
             "earned": r2(r["earned"]), "avg_std": r2(r["avg_std"]),
             "fill": r2(r["fill"]), "avg_clients": r2(r["avg_clients"])}
            for p, r in m.iterrows()]


def shift_summary(df):
    out = {}
    for k, g in df.groupby("shift_type"):
        out[k] = {"classes": int(len(g)), "earned": r2(g["total_class_pay"].sum()),
                  "avg_pay": r2(g["pay_if_standard_rate"].mean()),
                  "fill": r2(g["fill_rate"].mean()), "pct_full": r2(g["is_full"].mean()),
                  "pct_floor": r2(g["hit_floor"].mean()),
                  "avg_clients": r2(g["total_visits"].mean())}
    return out


def regular_slots(df):
    """Every recurring regular slot, past and current, with its average pay."""
    reg = df[(df["shift_type"] == "Regular") & df["schedule_note"].isna()]
    rows = []
    for slot, g in reg.groupby("slot"):
        g = g.sort_values("class_date")
        rows.append({"slot": slot, "n": int(len(g)),
                     "avg": r2(g["pay_if_standard_rate"].mean()),
                     "current": slot in analysis.REGULAR_NOW,
                     "last": g["class_date"].max().strftime("%b %-d")})
    return sorted(rows, key=lambda r: -r["avg"])


def forecast_inputs(df, rec):
    """Expected pay for each current regular slot, plus the recent pickup habit."""
    slots = []
    for slot in sorted(analysis.REGULAR_NOW):
        g = df[df["slot"] == slot].sort_values("class_date").tail(RECENT_OCCURRENCES)
        p = g["pay_if_standard_rate"]
        slots.append({"slot": slot, "n": int(len(g)), "expected": r2(p.mean()),
                      "low": r2(p.quantile(0.25)), "high": r2(p.quantile(0.75))})

    # Pickup habit over the last few weeks, counting only weeks with classes
    # (so travel weeks don't drag the rate down)
    since = df["class_date"].max() - pd.Timedelta(weeks=RECENT_WEEKS)
    recent = df[df["class_date"] > since]
    weeks = recent["class_date"].dt.to_period("W").nunique() or 1
    pk = recent[recent["shift_type"] == "Picked up"]["pay_if_standard_rate"]
    best = rec[rec["recommendation"] == "Pick up"]
    return {
        "start": (df["class_date"].max() + pd.Timedelta(days=1)).strftime("%Y-%m-%d"),
        "weeks": FORECAST_WEEKS,
        "regular": slots,
        "pickups_per_week": r2(len(pk) / weeks),
        "pickup_pay_typical": r2(pk.mean()),
        "pickup_pay_typical_low": r2(pk.quantile(0.25)),
        "pickup_pay_typical_high": r2(pk.quantile(0.75)),
        "pickup_pay_best": r2(best["avg_pay"].mean()),
        "pickup_pay_best_low": r2(best["min_pay"].mean()),
        "pickup_pay_best_high": r2(best["max_pay"].mean()),
        "recent_from": recent["class_date"].min().strftime("%b %-d"),
    }


def slot_table(df, slots, rec):
    tiers = rec.set_index("slot")["recommendation"].to_dict()
    reg_now = df[df["slot"].isin(analysis.REGULAR_NOW)][["day_of_week", "class_hour"]]
    reg_now = reg_now.drop_duplicates()
    rows = []
    for _, s in slots[slots["classes"] >= 2].iterrows():
        same_day = reg_now[reg_now["day_of_week"] == s["day_of_week"]]
        stacks = bool(((same_day["class_hour"] - s["class_hour"]).abs() <= 1.5).any())
        rows.append({
            "slot": s["slot"], "studio": s["studio"], "day": s["day_of_week"][:3],
            "time": s["time_label"], "n": int(s["classes"]), "avg": r2(s["avg_pay"]),
            "min": r2(s["min_pay"]), "max": r2(s["max_pay"]),
            "pct_floor": r2(s["pct_paid_floor"]), "fill": r2(s["avg_fill_rate"]),
            "regular": bool(s["currently_regular"]),
            "tier": "Regular now" if s["currently_regular"] else tiers.get(s["slot"], ""),
            "stacks": stacks and not bool(s["currently_regular"]),
        })
    return rows


def heatmap(df):
    def bucket(h):
        for name, lo, hi in BUCKETS:
            if lo <= h < hi:
                return name
        return "Evening"
    d = df.assign(bucket=df["class_hour"].apply(bucket))
    g = d.groupby(["day_of_week", "bucket"])["pay_if_standard_rate"].agg(["mean", "size"])
    values = {day: {b: ({"avg": r2(g.loc[(day, b), "mean"]), "n": int(g.loc[(day, b), "size"])}
                        if (day, b) in g.index else None) for b, _, _ in BUCKETS}
              for day in DAYS}
    return {"days": DAYS, "buckets": [b for b, _, _ in BUCKETS], "values": values}


def saturday(df):
    t = analysis.saturday_switch(df)
    out = {}
    for block, r in t.iterrows():
        key = "before" if block.startswith("Before") else "after"
        out[key] = {"label": block.split(": ")[1], "n": int(r["classes"]),
                    "avg": r2(r["avg_pay"]), "clients": r2(r["avg_visits"]),
                    "floor": r2(r["pct_paid_floor"])}
    return out


def main():
    df = pd.read_csv(DATA, parse_dates=["class_date"])
    slots = analysis.by_slot(df)
    rec = analysis.recommend(slots)

    data = {
        "meta": {"start": df["class_date"].min().strftime("%b %-d"),
                 "end": df["class_date"].max().strftime("%b %-d, %Y")},
        "kpis": kpis(df),
        "weekly": weekly(df),
        "monthly": monthly(df),
        "shift": shift_summary(df),
        "regular_slots": regular_slots(df),
        "forecast": forecast_inputs(df, rec),
        "slots": slot_table(df, slots, rec),
        "heat": heatmap(df),
        "saturday": saturday(df),
    }
    html = TEMPLATE.read_text().replace("__DASHBOARD_DATA__", json.dumps(data))
    for path in (OUT, PAGES):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(html)
    print(f"Wrote dashboard to {OUT.relative_to(ROOT)} and {PAGES.relative_to(ROOT)} "
          f"({len(html) / 1024:.0f} KB)")


if __name__ == "__main__":
    main()
