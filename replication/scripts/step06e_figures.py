"""Step 6e: diagnostic figures (static PNG for the research note).

Fig 1: M1 (upgrade hazard) quarterly mean, Akka dependents vs comparison dependents, 2020Q4-2025Q3.
Fig 2: cumulative share of active non-vendor Akka dependents with a first Pekko release, by Scala 3
       status before the event.
Palette: reference categorical slots 1-2 (blue #2a78d6, orange #eb6834), validated pair.
Outputs: outputs/step06/fig1_upgrade_hazard.png, fig2_switch_timeline.png
"""
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
O = ROOT / "outputs/step06"
BLUE, ORANGE, INK, MUTED, GRID = "#2a78d6", "#eb6834", "#0b0b0b", "#52514e", "#e4e3df"
plt.rcParams.update({"font.size": 10, "axes.edgecolor": GRID, "axes.labelcolor": MUTED, "xtick.color": MUTED,
                     "ytick.color": MUTED, "axes.spines.top": False, "axes.spines.right": False})

# Fig 1
pq = pd.read_csv(O / "panel_quarters.csv")
pq = pq[pq.M1.notna()]
m = pq.groupby(["quarter", "group"]).M1.mean().unstack()
qs = list(m.index)
x = range(len(qs))
fig, ax = plt.subplots(figsize=(8, 4.2), dpi=150)
ax.grid(axis="y", color=GRID, linewidth=0.8)
ax.plot(x, m["cmp"], color=ORANGE, lw=2, marker="o", ms=4, label="Comparison libraries (cats-effect, ZIO, fs2, http4s)")
ax.plot(x, m["akka"], color=BLUE, lw=2, marker="o", ms=4, label="Akka (non-vendor dependents)")
ev = qs.index("2022Q3")
ax.axvline(ev, color=MUTED, lw=1, ls="--")
ax.text(ev + 0.15, 0.95, "Relicensing\nannounced (2022Q3)", color=MUTED, fontsize=8, va="top")
ax.text(len(qs) - 1 + 0.2, m["cmp"].iloc[-1], "Comparison", color=INK, fontsize=9, va="center")
ax.text(len(qs) - 1 + 0.2, m["akka"].iloc[-1], "Akka", color=INK, fontsize=9, va="center")
ax.set_xticks(list(x)[::2], qs[::2], rotation=0, fontsize=8)
ax.set_ylim(0, 1)
ax.set_ylabel("Share of active project-quarters\nthat raise the supplier version")
ax.set_title("Upgrade hazard (M1) of the supplier dependency", loc="left", color=INK, fontsize=11)
ax.legend(frameon=False, loc="lower left", fontsize=8)
fig.tight_layout()
fig.savefig(O / "fig1_upgrade_hazard.png")

# Fig 2
t = pd.read_csv(O / "timeline_monthly.csv")
fig, ax = plt.subplots(figsize=(8, 4.2), dpi=150)
ax.grid(axis="y", color=GRID, linewidth=0.8)
xi = range(len(t))
ax.plot(xi, t["scala3_pre_1"], color=ORANGE, lw=2, label="Published Scala 3 artifacts before the event (n=30)")
ax.plot(xi, t["scala3_pre_0"], color=BLUE, lw=2, label="No Scala 3 artifacts before the event (n=176)")
p1 = list(t.month).index("2023-07")
ax.axvline(p1, color=MUTED, lw=1, ls="--")
ax.text(p1 + 0.4, 0.55, "Pekko 1.0\n(July 2023)", color=MUTED, fontsize=8, va="top")
ax.text(len(t) - 1 + 0.4, t["scala3_pre_1"].iloc[-1], "Scala 3 before", color=INK, fontsize=9, va="center")
ax.text(len(t) - 1 + 0.4, t["scala3_pre_0"].iloc[-1], "No Scala 3 before", color=INK, fontsize=9, va="center")
ax.set_xticks(list(xi)[::6], list(t.month)[::6], fontsize=8)
ax.set_ylim(0, 0.6)
ax.set_ylabel("Cumulative share with a\nfirst Pekko release")
ax.set_title("Switching to Pekko among active Akka dependents, by Scala 3 status", loc="left", color=INK, fontsize=11)
ax.legend(frameon=False, loc="lower right", fontsize=8)
fig.tight_layout()
fig.savefig(O / "fig2_switch_timeline.png")
print("ok")
