"""Step 14a: paper figure for the line-launch uptake design (Kaplan-Meier share adopted, days 0-240).

Same estimator as step13h_lu_estimate.py: projects active within 365 days, event = first release declaring the new
line, censored at the project's last release in the window. Plotted to day 240, the primary horizon.
Output: outputs/step14/fig_launch_uptake.pdf / .png
"""
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
O = ROOT / "outputs/step14"
O.mkdir(parents=True, exist_ok=True)
D = pd.read_csv(ROOT / "outputs/step13/lu/cohorts.csv")


def km(x):
    x = x[x.act365 == 1]
    t = np.where(x.adopt_days.notna(), x.adopt_days, x.last_rel_days).astype(float)
    e = x.adopt_days.notna().values
    S, out = 1.0, []
    for day in range(0, 241):
        n = (t >= day).sum()
        if n:
            S *= 1 - ((t == day) & e).sum() / n
        out.append(1 - S)
    return np.array(out)


series = [
    ("Typelevel series, 2019-20", D[(D.group == "cmp") & (D.period == "early")], "#7a7a7a", "--"),
    ("Typelevel series, 2022-23", D[(D.group == "cmp") & (D.period == "late")], "#7a7a7a", "-"),
    ("Akka 2.6 (Apache), 2019", D[D.cohort == "A26"], "#2f6db3", "-"),
    ("Akka 2.7 (BSL), 2022", D[D.cohort == "A27"], "#c4512b", "-"),
]
plt.rcParams.update({"font.size": 9, "font.family": "serif"})
fig, ax = plt.subplots(figsize=(5.6, 3.4))
days = np.arange(241)
for lab, x, col, ls in series:
    y = km(x)
    ax.step(days, y, where="post", color=col, ls=ls, lw=1.6, label=f"{lab} (n = {int((x.act365 == 1).sum())})")
    ax.annotate(f"{y[-1]:.0%}", (240, y[-1]), xytext=(4, 0), textcoords="offset points", va="center", fontsize=8,
                color="#333333")
ax.set_xlim(0, 262)
ax.set_ylim(0, 1)
ax.set_xticks([0, 60, 120, 180, 240])
ax.set_xlabel("Days since the launch of the new series")
ax.set_ylabel("Share of projects that adopted the new series")
ax.yaxis.set_major_formatter(matplotlib.ticker.PercentFormatter(1.0))
ax.grid(axis="y", color="#e6e6e6", lw=0.6)
for s in ("top", "right"):
    ax.spines[s].set_visible(False)
ax.legend(frameon=False, fontsize=7.5, loc="upper left")
fig.tight_layout()
fig.savefig(O / "fig_launch_uptake.pdf")
fig.savefig(O / "fig_launch_uptake.png", dpi=200)
print("saved")
