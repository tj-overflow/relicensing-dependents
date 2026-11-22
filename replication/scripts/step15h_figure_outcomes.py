"""Step 15h (R6): Figure 1 of the paper. Where projects went within 240 days of each launch.

Full risk set (inactive projects included), four exclusive outcomes as in step15b_launch_estimates.py:
adopted the new series / still on the previous series (freeze) / fork or no supplier (leave) / no release.
Akka launches 2.4 (2015), 2.5 (2017), 2.6 (2019), 2.7 (2022, BSL); pooled non-competing benchmark (cats-core,
jackson-module-scala; step15f) for 2019-20 and 2022-23.
Inputs: outputs/step13/lu/cohorts.csv, cohorts_a24.csv, outputs/step15/bench_cohorts.csv
Output: outputs/step15/fig_outcomes.pdf, .png
"""
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
O = ROOT / "outputs/step15"
A = pd.concat([pd.read_csv(ROOT / "outputs/step13/lu/cohorts.csv"), pd.read_csv(ROOT / "outputs/step13/lu/cohorts_a24.csv")])
B = pd.read_csv(O / "bench_cohorts.csv")
B = B[B.pooled == 1].copy()
B["cohort"] = "B_" + B.period


def four(d):
    adopt = d.adopt_days.notna() & (d.adopt_days <= 240)
    act = d.act240 == 1
    old = d.old240.fillna(0).astype(float) == 1
    return pd.Series({"Adopted the new series": (adopt).mean(),
                      "Kept the previous series": (~adopt & act & old).mean(),
                      "Moved to the fork or dropped Akka": (~adopt & act & ~old).mean(),
                      "No release": (~act).mean(), "n": len(d)})


rows = [("Akka 2.4\n2015", A[A.cohort == "A24"]), ("Akka 2.5\n2017", A[A.cohort == "A25"]),
        ("Akka 2.6\n2019", A[A.cohort == "A26"]), ("Akka 2.7\n2022, BSL", A[A.cohort == "A27"]),
        ("Benchmark\n2019-20", B[B.cohort == "B_early"]), ("Benchmark\n2022-23", B[B.cohort == "B_late"])]
T = pd.DataFrame({k: four(d) for k, d in rows}).T
T.to_csv(O / "fig_outcomes_data.csv")
cats = ["Adopted the new series", "Kept the previous series", "Moved to the fork or dropped Akka", "No release"]
cols = ["#2f6db3", "#c4512b", "#8c8c8c", "#dcdcdc"]
ink = ["white", "white", "white", "#333333"]

plt.rcParams.update({"font.size": 9, "font.family": "DejaVu Sans"})
fig, ax = plt.subplots(figsize=(7.2, 3.9))
x = [0, 1, 2, 3, 4.6, 5.6]
for xi, (lab, r) in zip(x, T.iterrows()):
    bottom = 0.0
    for c, col, tc in zip(cats, cols, ink):
        h = r[c]
        ax.bar(xi, h, bottom=bottom, width=0.72, color=col, edgecolor="white", linewidth=1.2)
        if h >= 0.07:
            ax.text(xi, bottom + h / 2, f"{h:.0%}", ha="center", va="center", color=tc, fontsize=8.5)
        elif c == cats[0] and h > 0:
            ax.text(xi + 0.40, bottom + h / 2, f"{h:.0%}", ha="left", va="center", color=col, fontsize=8.5,
                    fontweight="bold")
        bottom += h
    ax.text(xi, -0.04, f"n = {int(r['n'])}", ha="center", va="top", fontsize=7.5, color="#555555")
ax.set_xticks(x)
ax.set_xticklabels(T.index, fontsize=8.5)
ax.tick_params(axis="x", length=0, pad=16)
ax.set_ylim(0, 1)
ax.set_yticks([0, 0.25, 0.5, 0.75, 1.0])
ax.set_yticklabels(["0%", "25%", "50%", "75%", "100%"])
ax.set_ylabel("Share of projects on the previous series at launch")
for s in ("top", "right"):
    ax.spines[s].set_visible(False)
ax.spines["left"].set_color("#999999")
ax.spines["bottom"].set_visible(False)
ax.axvline(3.8, color="#999999", lw=0.8, ls=":")
handles = [plt.Rectangle((0, 0), 1, 1, color=c) for c in cols]
ax.legend(handles, cats, ncol=4, loc="lower center", bbox_to_anchor=(0.5, 1.0), frameon=False, fontsize=8,
          handlelength=1.2, columnspacing=1.2)
fig.tight_layout()
fig.savefig(O / "fig_outcomes.pdf")
fig.savefig(O / "fig_outcomes.png", dpi=200)
print(T.round(3))
