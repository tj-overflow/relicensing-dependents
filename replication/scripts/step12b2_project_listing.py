"""Step 12b2: project-level listing for coder A (the codebook's unit is the item, but the
1,096 relevant-candidate items are too many to read individually).

Selection rule: per repository, among non-bot items that mention the supplier's licence
or the fork (pattern SUPM below), rank by (title mentions the fork or a licence) desc, then the number of
coder-B motive flags desc, then creation date asc; keep the top 4.
Excerpt: title, then the body with HTML comments, code blocks and URLs removed, first 450 characters, plus up to
3 further sentences that contain a motive keyword (coder B patterns), each cut to 200 characters.
Outputs: outputs/step12/text_project_items.csv (selected items), text_for_coding_projects.txt
"""
import re
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
O = ROOT / "outputs/step12"
c = pd.read_csv(O / "text_corpus.csv", keep_default_na=False)
k = pd.read_csv(O / "text_keyword.csv")
m = c.merge(k, on="id")
SUPM = {"akka": r"pekko|lightbend|\bbsl\b|business source|akka.{0,40}licen|licen.{0,40}akka",
        "es": r"opensearch|elv2|sspl|elastic.{0,40}licen|licen.{0,40}elastic"}
TITLE = {"akka": r"pekko|licen|bsl|lightbend", "es": r"opensearch|licen|sspl|elv2"}
MOT = re.compile(r"licen|fee|commercial|legal|complian|incompatib|users|customers|trust|rug|lock-?in|vendor|"
                 r"governance|foundation|cve|security|vulnerab|end of life|eol|patch|maintain|scala ?3|jdk|java|"
                 r"wait|ported|port |ecosystem|play ?3|effort|breaking|migrat|rewrite", re.I)
FLAGS = ["LEGAL_OWN", "LEGAL_USERS", "TRUST", "AGEING", "COMPAT", "COORD", "COST"]
m = m[~m.bot.astype(bool)].copy()
m["sup"] = [bool(re.search(SUPM[e], f"{t} {x}".lower())) for e, t, x in zip(m.event, m.title, m.text)]
m = m[m.sup]
m["t_hit"] = [bool(re.search(TITLE[e], t.lower())) for e, t in zip(m.event, m.title)]
m["n_flags"] = m[FLAGS].sum(axis=1)
m = m.sort_values(["event", "repo", "t_hit", "n_flags", "created"], ascending=[True, True, False, False, True])
sel = m.groupby(["event", "repo"]).head(4)
sel.drop(columns=["text"]).to_csv(O / "text_project_items.csv", index=False)


def clean(s):
    s = re.sub(r"<!--.*?-->|```.*?```", " ", s, flags=re.S)
    s = re.sub(r"https?://\S+", "<url>", s)
    return re.sub(r"\s+", " ", s).strip()


with open(O / "text_for_coding_projects.txt", "w", encoding="utf-8") as fh:
    for (ev, repo), g in sel.groupby(["event", "repo"], sort=True):
        n_all = int(((c.event == ev) & (c.repo == repo)).sum())
        fh.write(f"=== {ev} | {repo} | items in corpus {n_all}, shown {len(g)}\n")
        for r in g.itertuples():
            b = clean(r.text)
            head = b[:450]
            extra = [s[:200] for s in re.split(r"(?<=[.!?])\s+", b[450:]) if MOT.search(s)][:3]
            fh.write(f" [{r.number}] {'PR' if r.is_pr else 'IS'} {r.created} | {r.title}\n   {head}"
                     + ("".join(f" … {x}" for x in extra)) + "\n")
print(sel.groupby("event").repo.nunique().to_dict(), len(sel), (O / "text_for_coding_projects.txt").stat().st_size)
