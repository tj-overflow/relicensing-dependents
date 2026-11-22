"""Step 14c: blinded human coding packet for the text-code validation.

Builds a self-contained local HTML page (validation/human_coding.html) that shows,
for each of the 59 repositories in the Step 12 validation sample, the same items
coder A read (title plus first 4,000 characters of the body), the codebook, and a
repository-level coding form. Coder A's codes are NOT included (blinding).

Codes are saved in the browser (localStorage) and exported as CSV
(validation/human_codes_<initials>.csv), which step14d_validation_score.py reads.

The page embeds third-party issue text, so it stays local: it is not in the
release package and must not be published.

Inputs:  outputs/step12/text_validation_sample.csv, outputs/step12/text_corpus.csv
Output:  validation/human_coding.html
"""
from pathlib import Path
import json
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "validation"
OUT.mkdir(exist_ok=True)
SEED = 20261112

v = pd.read_csv(ROOT / "outputs/step12/text_validation_sample.csv")
c = pd.read_csv(ROOT / "outputs/step12/text_corpus.csv")
items = v[["event", "repo", "id"]].merge(
    c[["id", "number", "is_pr", "created", "bot", "title", "text"]], on="id", how="left"
)
items["text"] = items["text"].fillna("").str.slice(0, 4000)

units = items[["event", "repo"]].drop_duplicates().reset_index(drop=True)
order = np.random.default_rng(SEED).permutation(len(units))
units = units.iloc[order].reset_index(drop=True)

data = []
for _, u in units.iterrows():
    it = items[(items.event == u.event) & (items.repo == u.repo)].sort_values("created")
    data.append({
        "event": u.event,
        "repo": u.repo,
        "items": [
            {
                "number": int(r.number),
                "kind": "Pull request" if bool(r.is_pr) else "Issue",
                "created": str(r.created)[:10],
                "bot": bool(r.bot),
                "title": str(r.title),
                "text": r.text,
            }
            for r in it.itertuples()
        ],
    })

payload = json.dumps(data, ensure_ascii=False).replace("</", "<\\/")
html = (ROOT / "scripts/step14c_validation_template.html").read_text(encoding="utf-8")
html = html.replace("/*__DATA__*/[]", payload)
(OUT / "human_coding.html").write_text(html, encoding="utf-8")
print(f"{len(data)} repositories, {len(items)} items -> {OUT / 'human_coding.html'}")
