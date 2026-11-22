"""Step 12b: flatten the Step 12z search results into a coding corpus and apply coder B (keyword rule).

Codebook: outputs/step12/text_codebook.md.
Outputs:
  outputs/step12/text_corpus.csv     one row per item: id, event, repo, number, is_pr, created, user, title, text
  outputs/step12/text_keyword.csv    coder B: R_kw and the seven motive flags
  outputs/step12/text_for_coding.txt compact listing for coder A (title + first 700 characters of the body)
  outputs/step12/search_summary.json repositories searched, errors, truncated queries
"""
import json
import re
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
I = ROOT / "data/raw/step12/issues"
O = ROOT / "outputs/step12"
BOTS = re.compile(r"(scala-steward|dependabot|renovate|github-actions|mergify|snyk)", re.I)
rows, summ = [], dict(repos=0, errors=0, with_hits=0, truncated=[])
for f in sorted(I.glob("*.json")):
    j = json.loads(f.read_text(encoding="utf-8"))
    summ["repos"] += 1
    if j.get("error"):
        summ["errors"] += 1
        continue
    if j["items"]:
        summ["with_hits"] += 1
    if (j.get("total_count") or 0) > len(j["items"]):
        summ["truncated"].append([j["repo"], j["total_count"]])
    for it in j["items"]:
        rows.append(dict(id=f'{j["event"]}:{j["repo"]}#{it["number"]}', event=j["event"], repo=j["repo"],
                         number=it["number"], is_pr=it["is_pr"], created=it["created_at"][:10], user=it["user"] or "",
                         bot=bool(BOTS.search(it["user"] or "")), title=it["title"] or "", text=it["body"] or ""))
c = pd.DataFrame(rows)
c.to_csv(O / "text_corpus.csv", index=False)

SUP = {"akka": r"pekko|akka|lightbend|bsl|business source", "es": r"opensearch|elastic|elv2|sspl"}
KW = {
    "LEGAL_OWN": r"licen[cs]e fee|commercial licen|\bbsl\b|business source|\belv2\b|\bsspl\b|category x|legal|complian|incompatib",
    "TRUST": r"trust|\brug\b|lock-?in|lock in|vendor|governance|foundation|future (licen|change)|community-driven",
    "AGEING": r"\bcve\b|security|vulnerab|end of life|\beol\b|\bpatch|no longer maintained|unmaintained",
    "COMPAT": r"scala ?3|\bjdk\b|java 2[1-5]|java 17|compatib",
    "COORD": r"\bwait|depends? on|dependenc(y|ies) on|\bported\b|port of|ecosystem|play ?3",
    "COST": r"effort|breaking|migration (cost|effort|path)|rewrite|too much work",
}
USERS = re.compile(r"(users|customers|downstream|companies).{0,80}(licen[cs]e|can'?t use|cannot use)|"
                   r"(licen[cs]e|can'?t use|cannot use).{0,80}(users|customers|downstream|companies)", re.I | re.S)
kw = []
for r in c.itertuples():
    t = f"{r.title}\n{r.text}".lower()
    rel = bool(re.search(SUP[r.event], t)) and bool(re.search(r"licen[cs]|pekko|opensearch|\bfork", t)) and not r.bot
    d = dict(id=r.id, R_kw=int(rel))
    for k, p in KW.items():
        d[k] = int(rel and bool(re.search(p, t)))
    d["LEGAL_USERS"] = int(rel and bool(USERS.search(t)))
    kw.append(d)
pd.DataFrame(kw).to_csv(O / "text_keyword.csv", index=False)
with open(O / "text_for_coding.txt", "w", encoding="utf-8") as fh:
    for r in c.itertuples():
        body = re.sub(r"<!--.*?-->", " ", r.text, flags=re.S)
        body = re.sub(r"\s+", " ", body)[:700]
        fh.write(f"[{r.id}] {'PR' if r.is_pr else 'IS'} {r.created} {r.user}{' (bot)' if r.bot else ''}\n"
                 f"T: {r.title}\nB: {body}\n\n")
summ["items"] = len(c)
summ["items_by_event"] = c.groupby("event").size().to_dict() if len(c) else {}
summ["bot_items"] = int(c.bot.sum()) if len(c) else 0
(O / "search_summary.json").write_text(json.dumps(summ, indent=1))
print(json.dumps({k: v for k, v in summ.items() if k != "truncated"}, indent=1), "truncated", len(summ["truncated"]))
