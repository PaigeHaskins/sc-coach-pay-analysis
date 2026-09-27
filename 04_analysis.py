"""
04_analysis.py - Answer the three questions and build the charts.

  1. Which days of the week pay the most?
  2. How do regular shifts compare with picked-up shifts?
  3. Which classes are consistently full, and which should I pick up next?

Input:  data/processed/classes_features.csv   (from 03_features.py)
Output: outputs/tables/*.csv, outputs/charts/*.png, outputs/summary.md

Pay measures used:
  total_class_pay  what was actually paid (used for "how much did I earn")
  pay_if_standard_rate     the same class on the Standard formula (used for fair
                   comparisons and future decisions, since June's Starter
                   classes paid a flat $28 regardless of attendance)

Usage:
    python src/04_analysis.py
"""
from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd
import seaborn as sns

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data" / "processed" / "classes_features.csv"
OUT = ROOT / "outputs"
TABLES, CHARTS = OUT / "tables", OUT / "charts"

DAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
from config import current_regular_slots  # noqa: E402

REGULAR_NOW = current_regular_slots()  # excluded from pickup recommendations
COLORS = {"Regular": "#3D5A80", "Picked up": "#EE6C4D",
          "Pick up": "#2A9D8F", "Worth it if convenient": "#E9C46A",
          "Skip": "#C8553D"}

sns.set_theme(style="whitegrid", font="DejaVu Sans")
plt.rcParams.update({"axes.titleweight": "bold", "axes.titlesize": 12})


# ---------------------------------------------------------------- tables
def by_day(df):
    t = (df.groupby("day_of_week")
           .agg(classes=("total_class_pay", "size"),
                total_earned=("total_class_pay", "sum"),
                avg_pay=("pay_if_standard_rate", "mean"),
                avg_fill_rate=("fill_rate", "mean"),
                pct_full=("is_full", "mean"),
                pickups=("shift_type", lambda s: (s == "Picked up").sum()))
           .reindex([d for d in DAYS if d in df["day_of_week"].unique()]))
    return t.round(2)


def by_shift(df):
    t = (df.groupby("shift_type")
           .agg(classes=("total_class_pay", "size"),
                total_earned=("total_class_pay", "sum"),
                avg_pay=("pay_if_standard_rate", "mean"),
                avg_visits=("total_visits", "mean"),
                avg_fill_rate=("fill_rate", "mean"),
                pct_full=("is_full", "mean"),
                pct_paid_floor=("hit_floor", "mean"))
           .reindex(["Regular", "Picked up"]))
    return t.round(2)


def by_slot(df):
    t = (df.groupby(["slot", "studio", "day_of_week", "day_num", "class_hour",
                     "time_label"])
           .agg(classes=("pay_if_standard_rate", "size"),
                avg_pay=("pay_if_standard_rate", "mean"),
                min_pay=("pay_if_standard_rate", "min"),
                max_pay=("pay_if_standard_rate", "max"),
                avg_visits=("total_visits", "mean"),
                avg_fill_rate=("fill_rate", "mean"),
                pct_full=("is_full", "mean"),
                total_waitlist=("waitlist", "sum"),
                pct_paid_floor=("hit_floor", "mean"),
                last_taught=("class_date", "max"))
           .reset_index())
    t["currently_regular"] = t["slot"].isin(REGULAR_NOW)
    num = t.select_dtypes("number").columns
    t[num] = t[num].round(2)
    return t.sort_values("avg_pay", ascending=False)


def recommend(slots):
    """Rate every slot that isn't on the current regular schedule."""
    cand = slots[~slots["currently_regular"]].copy()

    def tier(r):
        if r["classes"] < 2:
            return "Not enough data"
        if r["avg_pay"] >= 70 and r["pct_paid_floor"] == 0:
            return "Pick up"
        if r["avg_pay"] < 50 or r["pct_paid_floor"] >= 0.25:
            return "Skip"
        return "Worth it if convenient"

    cand["recommendation"] = cand.apply(tier, axis=1)
    order = {"Pick up": 0, "Worth it if convenient": 1, "Skip": 2, "Not enough data": 3}
    cand["_o"] = cand["recommendation"].map(order)
    return cand.sort_values(["_o", "avg_pay"], ascending=[True, False]).drop(columns="_o")


def saturday_switch(df):
    """Compare the old regular Saturday block (to May 31) with the new one (from June 1)."""
    sat = df[(df["shift_type"] == "Regular") & (df["day_of_week"] == "Saturday")
             & (df["studio"] == "Studio 2")].copy()
    sat["block"] = sat["class_date"].lt("2026-06-01").map(
        {True: "Before: 11:30 AM-1:30 PM", False: "After: 6:30/7:30 AM"})
    t = (sat.groupby("block")
            .agg(classes=("pay_if_standard_rate", "size"), avg_pay=("pay_if_standard_rate", "mean"),
                 avg_visits=("total_visits", "mean"), pct_paid_floor=("hit_floor", "mean"))
            .round(2))
    return t


# ---------------------------------------------------------------- charts
def chart_days(day_tbl):
    fig, axes = plt.subplots(1, 2, figsize=(12, 4.8))
    labels = [d[:3] for d in day_tbl.index]

    ax = axes[0]
    bars = ax.bar(labels, day_tbl["total_earned"], color="#3D5A80")
    for b, n in zip(bars, day_tbl["classes"]):
        ax.text(b.get_x() + b.get_width() / 2, b.get_height() + 20,
                f"{n} classes", ha="center", fontsize=9)
    ax.set_title("Total earned by day")
    ax.set_ylabel("Total pay ($)")

    ax = axes[1]
    best = day_tbl["avg_pay"].idxmax()
    colors = ["#2A9D8F" if d == best else "#98C1D9" for d in day_tbl.index]
    bars = ax.bar(labels, day_tbl["avg_pay"], color=colors)
    for b, v in zip(bars, day_tbl["avg_pay"]):
        ax.text(b.get_x() + b.get_width() / 2, v + 1, f"${v:.0f}",
                ha="center", fontsize=9)
    ax.axhline(28, ls="--", color="gray", lw=1)
    ax.text(6.4, 29.5, "$28 floor", color="gray", fontsize=8, ha="right")
    ax.set_title("Average pay per class by day")
    ax.set_ylabel("Avg pay per class ($, Standard rate)")
    ax.set_ylim(0, 90)

    most = day_tbl["total_earned"].idxmax()
    top2 = day_tbl["avg_pay"].nlargest(2).index
    fig.suptitle(f"{most} earns the most in total ({day_tbl.loc[most, 'classes']:.0f} classes); "
                 f"{top2[0]} and {top2[1]} pay the most per class", fontsize=11)
    fig.tight_layout()
    fig.savefig(CHARTS / "1_days_of_week.png", dpi=150)
    plt.close(fig)


def chart_shift(shift_tbl, df):
    fig, axes = plt.subplots(1, 4, figsize=(13, 4))
    metrics = [("avg_pay", "Avg pay per class", "${:.0f}"),
               ("avg_fill_rate", "Avg fill rate", "{:.0%}"),
               ("pct_full", "% of classes full", "{:.0%}"),
               ("pct_paid_floor", "% paid only $28", "{:.0%}")]
    for ax, (col, title, fmt) in zip(axes, metrics):
        vals = shift_tbl[col]
        bars = ax.bar(vals.index, vals, color=[COLORS[i] for i in vals.index])
        for b, v in zip(bars, vals):
            ax.text(b.get_x() + b.get_width() / 2, v * 1.02, fmt.format(v),
                    ha="center", fontsize=10, fontweight="bold")
        ax.set_title(title)
        ax.grid(False)
        ax.set_ylim(0, vals.max() * 1.25 if vals.max() > 0 else 1)
        ax.set_yticks([])
    n = shift_tbl["classes"]
    fig.suptitle(f"Regular ({n['Regular']} classes) vs picked up "
                 f"({n['Picked up']} classes)", fontsize=12)
    fig.tight_layout()
    fig.savefig(CHARTS / "2_regular_vs_pickup.png", dpi=150)
    plt.close(fig)

    # Monthly earnings split by shift type
    m = (df.pivot_table(index="month", columns="shift_type",
                        values="total_class_pay", aggfunc="sum")
           .fillna(0)[["Regular", "Picked up"]])
    fig, ax = plt.subplots(figsize=(8, 4.5))
    m.plot(kind="bar", stacked=True, ax=ax,
           color=[COLORS["Regular"], COLORS["Picked up"]], rot=0)
    for i, total in enumerate(m.sum(axis=1)):
        ax.text(i, total + 25, f"${total:,.0f}", ha="center", fontsize=9)
    last = df["class_date"].max()
    ax.set_title("Monthly earnings: regular vs picked-up classes\n"
                 f"(Starter weeks paid $28 flat; pay estimated where there's no payslip yet; "
                 f"data through {last:%b %d})")
    ax.set_xlabel("")
    ax.set_ylabel("Total pay ($)")
    ax.legend(title="")
    fig.tight_layout()
    fig.savefig(CHARTS / "3_monthly_by_shift.png", dpi=150)
    plt.close(fig)


def chart_regular_slots(df, slots):
    """Break the regular schedule into its individual slots vs the pickup average."""
    # One-off holiday/swapped shifts are left out so each bar is a recurring slot
    reg = (df[(df["shift_type"] == "Regular") & df["schedule_note"].isna()]
             .groupby("slot")
             .agg(avg_pay=("pay_if_standard_rate", "mean"), classes=("pay_if_standard_rate", "size"),
                  hour=("class_hour", "first"), day=("day_num", "first"))
             .sort_values("avg_pay"))
    pickup_avg = df.loc[df["shift_type"] == "Picked up", "pay_if_standard_rate"].mean()
    fig, ax = plt.subplots(figsize=(9, 5))
    colors = [COLORS["Regular"] if v >= pickup_avg else "#C8553D" for v in reg["avg_pay"]]
    bars = ax.barh(reg.index, reg["avg_pay"], color=colors)
    for b, (_, r) in zip(bars, reg.iterrows()):
        ax.text(r["avg_pay"] + 1, b.get_y() + b.get_height() / 2,
                f"${r['avg_pay']:.0f}  (n={r['classes']:.0f})", va="center", fontsize=9)
    ax.axvline(pickup_avg, ls="--", color=COLORS["Picked up"], lw=1.5)
    ax.text(pickup_avg + 1, -0.9, f"pickup avg ${pickup_avg:.0f}",
            color=COLORS["Picked up"], fontsize=9)
    ax.set_xlim(0, 95)
    ax.set_xlabel("Avg pay per class ($, Standard rate)")
    ax.set_title("My regular slots, one by one\n(red = pays less than the average pickup)")
    fig.tight_layout()
    fig.savefig(CHARTS / "2b_regular_slots.png", dpi=150)
    plt.close(fig)


def chart_fill_heatmap(df):
    fig, axes = plt.subplots(1, 2, figsize=(13, 6))
    for ax, studio in zip(axes, ["Studio 1", "Studio 2"]):
        d = df[df["studio"] == studio]
        days = [x[:3] for x in DAYS if x in d["day_of_week"].unique()]
        d = d.assign(day=d["day_of_week"].str[:3])
        piv = d.pivot_table(index="time_label", columns="day", values="fill_rate",
                            aggfunc="mean").reindex(columns=days)
        piv = piv.reindex(d.drop_duplicates("time_label")
                           .sort_values("class_hour")["time_label"])
        sns.heatmap(piv, annot=True, fmt=".0%", cmap="RdYlGn", vmin=0.3, vmax=1.1,
                    cbar=False, linewidths=0.5, ax=ax, annot_kws={"fontsize": 9})
        ax.grid(False)
        cap = 10 if studio == "Studio 1" else 16
        ax.set_title(f"{studio} (capacity {cap})")
        ax.set_xlabel("")
        ax.set_ylabel("")
    fig.suptitle("Average fill rate by day and time (over 100% = waitlist)",
                 fontsize=12)
    fig.tight_layout()
    fig.savefig(CHARTS / "4_fill_rate_heatmap.png", dpi=150)
    plt.close(fig)


def chart_consistency(slots):
    s = slots[slots["classes"] >= 3].sort_values(["pct_full", "avg_fill_rate"])
    fig, ax = plt.subplots(figsize=(9, 0.42 * len(s) + 1.5))
    colors = [COLORS["Regular"] if r else "#98C1D9" for r in s["currently_regular"]]
    bars = ax.barh(s["slot"], s["pct_full"], color=colors)
    for b, (_, r) in zip(bars, s.iterrows()):
        ax.text(b.get_width() + 0.01, b.get_y() + b.get_height() / 2,
                f"{r['pct_full']:.0%} full  ({r['classes']} classes)",
                va="center", fontsize=9)
    ax.set_xlim(0, 1.35)
    ax.set_xticks([])
    ax.set_title("Which classes are consistently full? (slots taught 3+ times)\n"
                 "dark = current regular slot")
    fig.tight_layout()
    fig.savefig(CHARTS / "5_consistently_full.png", dpi=150)
    plt.close(fig)


def chart_recommendations(rec):
    r = rec[rec["recommendation"] != "Not enough data"].iloc[::-1]
    fig, ax = plt.subplots(figsize=(9, 0.42 * len(r) + 1.8))
    for i, (_, row) in enumerate(r.iterrows()):
        ax.barh(i, row["avg_pay"], color=COLORS[row["recommendation"]])
        ax.plot([row["min_pay"], row["max_pay"]], [i, i], color="black", lw=1)
        ax.text(max(row["max_pay"], row["avg_pay"]) + 1.5, i,
                f"${row['avg_pay']:.0f} avg  (n={row['classes']})",
                va="center", fontsize=9)
    ax.set_yticks(range(len(r)))
    ax.set_yticklabels(r["slot"])
    ax.axvline(28, ls="--", color="gray", lw=1)
    ax.set_xlim(0, 118)
    ax.set_xlabel("Pay per class ($, Standard rate)   line = worst to best week")
    ax.set_title("Pickup guide: slots outside the current regular schedule\n"
                 "(slots taught at least twice)")
    from matplotlib.patches import Patch
    ax.legend(handles=[Patch(color=COLORS[k], label=k)
                       for k in ["Pick up", "Worth it if convenient", "Skip"]],
              loc="lower right", fontsize=9)
    fig.tight_layout()
    fig.savefig(CHARTS / "6_pickup_recommendations.png", dpi=150)
    plt.close(fig)


# ---------------------------------------------------------------- summary
def write_summary(df, day_tbl, shift_tbl, rec):
    s = shift_tbl
    lines = [
        "# Summary", "",
        f"{len(df)} classes, {df['class_date'].min():%b %d} to "
        f"{df['class_date'].max():%b %d, %Y}. Total paid: "
        f"${df['total_class_pay'].sum():,.2f} "
        f"(${df.loc[df['pay_estimated'], 'total_class_pay'].sum():,.2f} of it estimated "
        f"for {df['pay_estimated'].sum()} classes without payslips).", "",
        f"Utilization (average fill rate): {df['fill_rate'].mean():.0%} counting waitlist, "
        f"{(df['booked'] / df['capacity']).mean():.0%} capped at capacity.", "",
        "## Days of the week", "",
        "| Day | Classes | Total earned | Avg pay per class | Avg fill |",
        "|---|---|---|---|---|"]
    for d, r in day_tbl.iterrows():
        lines.append(f"| {d} | {r['classes']:.0f} | ${r['total_earned']:,.2f} | "
                     f"${r['avg_pay']:.2f} | {r['avg_fill_rate']:.0%} |")
    lines += ["", "## Regular vs picked up", "",
              "| | Classes | Total earned | Avg pay | Avg fill | % full | % at $28 floor |",
              "|---|---|---|---|---|---|---|"]
    for k, r in s.iterrows():
        lines.append(f"| {k} | {r['classes']:.0f} | ${r['total_earned']:,.2f} | "
                     f"${r['avg_pay']:.2f} | {r['avg_fill_rate']:.0%} | "
                     f"{r['pct_full']:.0%} | {r['pct_paid_floor']:.0%} |")
    lines += ["", "## Pickup guide", "",
              "| Slot | Recommendation | Classes | Avg pay | Worst week |",
              "|---|---|---|---|---|"]
    for _, r in rec[rec["recommendation"] != "Not enough data"].iterrows():
        lines.append(f"| {r['slot']} | {r['recommendation']} | {r['classes']} | "
                     f"${r['avg_pay']:.2f} | ${r['min_pay']:.2f} |")
    (OUT / "summary.md").write_text("\n".join(lines) + "\n")


def main():
    TABLES.mkdir(parents=True, exist_ok=True)
    CHARTS.mkdir(parents=True, exist_ok=True)
    df = pd.read_csv(DATA, parse_dates=["class_date"])

    day_tbl, shift_tbl, slots = by_day(df), by_shift(df), by_slot(df)
    rec = recommend(slots)

    day_tbl.to_csv(TABLES / "by_day_of_week.csv")
    shift_tbl.to_csv(TABLES / "regular_vs_pickup.csv")
    slots.to_csv(TABLES / "by_slot.csv", index=False)
    rec.to_csv(TABLES / "pickup_recommendations.csv", index=False)
    sat = saturday_switch(df)
    sat.to_csv(TABLES / "saturday_switch.csv")
    print(sat.to_string())

    chart_days(day_tbl)
    chart_shift(shift_tbl, df)
    chart_regular_slots(df, slots)
    chart_fill_heatmap(df)
    chart_consistency(slots)
    chart_recommendations(rec)
    write_summary(df, day_tbl, shift_tbl, rec)
    print(f"Wrote tables, charts, and summary to {OUT}")


if __name__ == "__main__":
    main()
