"""Step 3c: retrieve archived 2022-2023 versions of Lightbend's Akka licence FAQ and announcement blog.

Uses the Internet Archive Wayback Machine's original-content endpoint (timestamp + "id_").
Saves raw HTML (with SHA-256) and extracted text to data/raw/wayback/.
Usage: python -I scripts/step03c_wayback_snapshots.py
"""
import gzip
import hashlib
import html
import json
import re
import time
import urllib.request
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "raw" / "wayback"
OUT.mkdir(parents=True, exist_ok=True)

SNAPSHOTS = [
    ("faq", "20220907063228", "https://www.lightbend.com/akka/license-faq"),
    ("faq", "20220909085557", "https://www.lightbend.com/akka/license-faq"),
    ("faq", "20220922095902", "https://www.lightbend.com/akka/license-faq"),
    ("faq", "20221031061944", "https://www.lightbend.com/akka/license-faq"),
    ("faq", "20230516163726", "https://www.lightbend.com/akka/license-faq"),
    ("blog", "20220907063009", "https://www.lightbend.com/blog/why-we-are-changing-the-license-for-akka"),
    ("blog", "20220909135225", "https://www.lightbend.com/blog/why-we-are-changing-the-license-for-akka"),
    ("blog", "20220926000408", "https://www.lightbend.com/blog/why-we-are-changing-the-license-for-akka"),
]


class Text(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts, self.skip = [], 0

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style", "noscript"):
            self.skip += 1
        if tag in ("p", "br", "li", "h1", "h2", "h3", "h4", "div", "tr"):
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in ("script", "style", "noscript") and self.skip:
            self.skip -= 1

    def handle_data(self, data):
        if not self.skip:
            self.parts.append(data)


meta = []
for kind, ts, url in SNAPSHOTS:
    wb = f"https://web.archive.org/web/{ts}id_/{url}"
    req = urllib.request.Request(wb, headers={"User-Agent": "research-archive-check/1.0"})
    raw = None
    for attempt in range(6):
        try:
            with urllib.request.urlopen(req, timeout=90) as r:
                raw = r.read()
            break
        except Exception as e:  # 503/429 from the archive: back off and retry
            print("retry", kind, ts, e)
            time.sleep(10 * (attempt + 1))
    if raw is None:
        meta.append(dict(kind=kind, timestamp=ts, original_url=url, error="failed after retries"))
        continue
    if raw[:2] == b"\x1f\x8b":  # archived body stored gzip-compressed
        raw = gzip.decompress(raw)
    sha = hashlib.sha256(raw).hexdigest()
    (OUT / f"{kind}_{ts}.html").write_bytes(raw)
    p = Text()
    p.feed(raw.decode("utf-8", errors="replace"))
    txt = html.unescape("".join(p.parts))
    txt = re.sub(r"[ \t]+", " ", txt)
    txt = re.sub(r"\n\s*\n+", "\n", txt).strip()
    (OUT / f"{kind}_{ts}.txt").write_text(txt, encoding="utf-8")
    meta.append(dict(kind=kind, timestamp=ts, original_url=url, wayback_url=f"https://web.archive.org/web/{ts}/{url}",
                     sha256=sha, bytes=len(raw), text_chars=len(txt)))
    print(kind, ts, len(raw), len(txt))
    time.sleep(2)

(OUT / "manifest.json").write_text(json.dumps({"retrieved": time.strftime("%Y-%m-%d"), "snapshots": meta}, indent=1))
