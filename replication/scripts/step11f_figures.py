"""Step 11f: figures for Step 11 (style as step06e: reference categorical slots in fixed order, thin marks,
recessive grid, direct labels plus legend; marker shape as secondary encoding because the palette validator
could not be run here).
Fig 3: event-study coefficients (M1), Akka and Elasticsearch, 95% CIs, shared y-axis.
Fig 4: treated raises split into the open series and restricted versions, by quarter, with comparison-group M1.
Fig 5: E1 cumulative switch-or-dual share by months since complete port availability, by cohort.
Outputs: outputs/step11/fig3_event_study.png, fig4_decomposition.png, fig5_e1_curves.png
"""
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import pandas as pd  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
O = ROOT / "outputs/step11"
BLUE, ORANGE, AQUA, INK, MUTED, GRID = "#2a78d6", "#eb6834", "#1baf7a", "#0b0b0b", "#52514e", "#e4e3df"
plt.rcParams.update({"font.size": 9, "axes.edgecolor": GRID, "axes.labelcolor": MUTED, "xtick.color": MUTED,
                     "ytick.color": MUTED, "axes.spines.top": False, "axes.spines.right": False})
EVQ = {"akka": "2022Q3", "es": "2021Q1"}
TITLE = {"akka": "Akka (BSL, user restriction)", "es": "Elasticsearch (ELv2, competitor-only restriction)"}

# Fig 3
es = pd.read_csv(O / "event_study.csv")
es = es[es["sample"] == "all"]
fig, axes = plt.subplots(1, 2, figsize=(10, 3.6), sharey=True)
for ax, ev in zip(axes, ("akka", "es")):
    d = es[es.event == ev].sort_values("quarter").reset_index(drop=True)
    x = range(len(d))
    ax.grid(axis="y", color=GRID, lw=0.8)
    ax.axhline(0, color=MUTED, lw=0.8)
    ax.errorbar(x, d.coef, yerr=1.96 * d.se, fmt="o", ms=4, color=BLUE, ecolor=BLUE, elinewidth=1, capsize=0)
    i = list(d.quarter).index(EVQ[ev])
    ax.axvline(i, color=MUTED, lw=1, ls="--")
    ax.text(i + 0.3, 0.55, "Relicensing", color=MUTED, fontsize=8, va="top")
    ax.set_xticks(list(x)[::2])
    ax.set_xticklabels(d.quarter[::2], rotation=60, fontsize=7)
    ax.set_title(TITLE[ev], loc="left", color=INK, fontsize=10)
axes[0].set_ylabel("Treated × quarter coefficient on M1\n(reference: last pre-event quarter)")
fig.suptitle("Event study of the upgrade rate, project and quarter FE, ATT weights, 95% CI (owner clusters)",
             x=0.01, ha="left", color=INK, fontsize=10)
fig.tight_layout()
fig.savefig(O / "fig3_event_study.png", dpi=200)

# Fig 4
dq = json.loads((O / "descriptives.json").read_text())["decomposition_by_quarter"]
pq = pd.read_csv(O / "panel.csv")
fig, axes = plt.subplots(1, 2, figsize=(10, 3.6), sharey=True)
for ax, ev in zip(axes, ("akka", "es")):
    t = pd.DataFrame(dq[ev]).T.sort_index()
    c = pq[(pq.event == ev) & (pq.treated == 0) & pq.M1.notna()].groupby("quarter").M1.mean()
    qs = [q for q in t.index if q in c.index]
    t, c = t.loc[qs], c.loc[qs]
    x = range(len(qs))
    ax.grid(axis="y", color=GRID, lw=0.8)
    ax.plot(x, c.values, color=MUTED, lw=1.5, ls="--", label="Comparison group, any raise (M1)")
    ax.plot(x, t.M1_open.values, color=ORANGE, lw=2, marker="s", ms=3, label="Treated, raise within the open series")
    ax.plot(x, t.M1_restr.values, color=BLUE, lw=2, marker="o", ms=3, label="Treated, raise into restricted versions")
    i = qs.index(EVQ[ev])
    ax.axvline(i, color=MUTED, lw=1, ls=":")
    ax.set_xticks(list(x)[::2])
    ax.set_xticklabels(qs[::2], rotation=60, fontsize=7)
    ax.set_ylim(0, 1)
    ax.set_title(TITLE[ev], loc="left", color=INK, fontsize=10)
axes[0].set_ylabel("Share of project-quarters")
axes[1].legend(frameon=False, fontsize=7, loc="upper right")
fig.tight_layout()
fig.savefig(O / "fig4_decomposition.png", dpi=200)
fig.savefig(O / "fig4_decomposition.pdf")

# Fig 5
e1 = pd.read_csv(O / "e1_curves.csv")
fig, ax = plt.subplots(figsize=(6.5, 3.6))
ax.grid(axis="y", color=GRID, lw=0.8)
for co, col, mk in (("2023Q3", BLUE, "o"), ("2023Q4", ORANGE, "s")):  # 2024Q1+ (n=7) has too little follow-up to plot
    d = e1[e1.cohort == co].sort_values("months_since_availability")
    n = int(d.n.iloc[0]) if len(d) else 0
    ax.plot(d.months_since_availability, d.share_switch_or_dual, color=col, lw=2, marker=mk, ms=3,
            label=f"Ports complete in {co} (n={n})")
    if len(d):
        ax.text(d.months_since_availability.iloc[-1] + 0.4, d.share_switch_or_dual.iloc[-1], co, color=INK, fontsize=8, va="center")
ax.set_xlabel("Months since every Akka-family dependency had a Pekko port")
ax.set_ylabel("Cumulative share switched or dual")
ax.set_ylim(0, 1)
ax.legend(frameon=False, fontsize=7, loc="upper left")
ax.set_title("E1 (descriptive): switching after complete port availability",
             loc="left", color=INK, fontsize=10)
fig.tight_layout()
fig.savefig(O / "fig5_e1_curves.png", dpi=200)
print("ok")
