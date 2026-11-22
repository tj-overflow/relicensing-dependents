"""Step 7-pooled scoping, part 1: are relicensed artifacts visible as LIBRARY dependencies in registries?

For each candidate event and system, list licences of selected versions around the relicensing date
from the documented deps.dev API (GetPackage + GetVersion). Output: outputs/step07_pooled/event_screen.csv
"""
import csv
import json
import time
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
O = ROOT / "outputs/step07_pooled"
O.mkdir(parents=True, exist_ok=True)
CACHE = ROOT / "data/raw/step07_pooled/api"
CACHE.mkdir(parents=True, exist_ok=True)
UA = {"User-Agent": "research-script/1.0"}
EVENT = {"elastic": "2021-01-14", "hashicorp": "2023-08-10", "redis": "2024-03-20", "cockroach": "2019-06-04",
         "grafana": "2021-04-20", "minio": "2021-04-22"}
PKGS = [  # (event, system, name)
    ("elastic", "maven", "org.elasticsearch:elasticsearch"),
    ("elastic", "maven", "org.elasticsearch.client:elasticsearch-rest-high-level-client"),
    ("elastic", "maven", "org.elasticsearch.client:transport"),
    ("elastic", "maven", "org.elasticsearch.client:elasticsearch-rest-client"),
    ("elastic", "maven", "co.elastic.clients:elasticsearch-java"),
    ("elastic", "maven", "org.opensearch:opensearch"),
    ("elastic", "maven", "org.opensearch.client:opensearch-rest-high-level-client"),
    ("elastic", "maven", "org.opensearch.client:opensearch-java"),
    ("elastic", "pypi", "elasticsearch"),
    ("elastic", "pypi", "opensearch-py"),
    ("elastic", "npm", "@elastic/elasticsearch"),
    ("hashicorp", "go", "github.com/hashicorp/terraform"),
    ("hashicorp", "go", "github.com/hashicorp/vault"),
    ("hashicorp", "go", "github.com/hashicorp/vault/api"),
    ("hashicorp", "go", "github.com/hashicorp/vault/sdk"),
    ("hashicorp", "go", "github.com/hashicorp/consul"),
    ("hashicorp", "go", "github.com/hashicorp/consul/api"),
    ("hashicorp", "go", "github.com/hashicorp/nomad"),
    ("hashicorp", "go", "github.com/hashicorp/nomad/api"),
    ("hashicorp", "go", "github.com/opentofu/opentofu"),
    ("hashicorp", "go", "github.com/openbao/openbao/api/v2"),
    ("redis", "pypi", "redis"),
    ("redis", "npm", "redis"),
    ("redis", "maven", "redis.clients:jedis"),
    ("redis", "go", "github.com/redis/go-redis/v9"),
    ("redis", "pypi", "valkey"),
    ("cockroach", "go", "github.com/cockroachdb/cockroach"),
    ("grafana", "go", "github.com/grafana/grafana"),
    ("minio", "go", "github.com/minio/minio"),
    ("minio", "go", "github.com/minio/minio-go/v7"),
]


def get(url, key):
    f = CACHE / (key.replace("/", "_").replace(":", "_").replace("@", "") + ".json")
    if f.exists():
        return json.loads(f.read_text())
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=60) as r:
            d = json.load(r)
    except urllib.error.HTTPError as e:
        d = {"error": e.code}
    f.write_text(json.dumps(d))
    time.sleep(0.1)
    return d


rows = []
for ev, sysname, name in PKGS:
    base = f"https://api.deps.dev/v3/systems/{sysname}/packages/{urllib.parse.quote(name, safe='')}"
    d = get(base, f"{sysname}__{name}")
    vs = sorted([(v.get("publishedAt", "")[:10], v["versionKey"]["version"]) for v in d.get("versions", [])
                 if v.get("publishedAt")])
    if not vs:
        rows.append(dict(event=ev, system=sysname, package=name, note="not found / no dates"))
        continue
    e = EVENT[ev]
    pre = [x for x in vs if x[0] < e]
    post = [x for x in vs if x[0] >= e]
    pick = {"first": vs[0], "last_pre": pre[-1] if pre else None, "first_post": post[0] if post else None,
            "post_+1y": next((x for x in post if x[0] >= str(int(e[:4]) + 1) + e[4:]), None), "latest": vs[-1]}
    for lab, x in pick.items():
        if not x:
            continue
        vd = get(base + "/versions/" + urllib.parse.quote(x[1], safe=""), f"{sysname}__{name}__{x[1]}")
        rows.append(dict(event=ev, system=sysname, package=name, which=lab, version=x[1], published=x[0],
                         licences=";".join(vd.get("licenses", [])), n_versions=len(vs)))
with open(O / "event_screen.csv", "w", newline="", encoding="utf-8") as f:
    w = csv.DictWriter(f, fieldnames=["event", "system", "package", "which", "version", "published", "licences",
                                      "n_versions", "note"])
    w.writeheader()
    w.writerows(rows)
for r in rows:
    print(r.get("event"), r.get("package"), r.get("which", ""), r.get("version", ""), r.get("published", ""),
          r.get("licences", r.get("note")))
