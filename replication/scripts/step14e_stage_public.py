"""Step 14e: stage the public GitHub repository and the Zenodo archives from release/ (built by step14b).

Nothing is uploaded. Outputs (local, for the author to review):
  release/github/   repository layout: top-level README, LICENSE, CITATION.cff, .gitignore, dataset/, and
                    replication/ without data/raw (about 60 MB); replication/data/README.md says where the raw
                    extracts are (Zenodo)
  release/zenodo/   replication_package.zip  the full replication package, including data/raw
                    dataset.zip              the documented dataset
Run after step14b_build_release.py.
"""
import shutil
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REL = ROOT / "release"
DS, RP = REL / "dataset", REL / "replication"
GH, ZN = REL / "github", REL / "zenodo"
for d in (GH, ZN):
    if d.exists():
        shutil.rmtree(d)
    d.mkdir(parents=True)

TITLE = "Frozen on the Last Open Version: How Dependent Libraries Respond When an Open-Source Supplier Relicenses"

# ---------- GitHub layout ----------
shutil.copytree(DS, GH / "dataset")
shutil.copytree(RP, GH / "replication", ignore=shutil.ignore_patterns("raw"))
(GH / "replication/data").mkdir(exist_ok=True)
(GH / "replication/data/README.md").write_text(
    "# Raw extracts\n\n"
    "The raw extracts (`data/raw/`, about 560 MB) are too large for this repository. They are archived on Zenodo "
    "with the full replication package: [doi:10.5281/zenodo.24440614](https://doi.org/10.5281/zenodo.24440614).\n\n"
    "Download `replication_package.zip` from the Zenodo record and copy its `data/raw/` folder here, so that this "
    "folder contains `raw/`. Then run `python run_all.py` from `replication/` as described in "
    "`replication/README.md`.\n", encoding="utf-8")
shutil.copy2(RP / "LICENSE", GH / "LICENSE")
(GH / ".gitignore").write_text("replication/data/raw/\n__pycache__/\n*.pyc\n", encoding="utf-8")
(GH / "CITATION.cff").write_text(
    'cff-version: 1.2.0\n'
    'message: "If you use this code or data, please cite the paper below."\n'
    f'title: "{TITLE}: replication package"\n'
    'version: "1.0"\n'
    'date-released: "2026-11-22"\n'
    'doi: "10.5281/zenodo.24440614"\n'
    'license: MIT\n'
    'authors:\n'
    '  - family-names: Oh\n'
    '    given-names: Taejun\n'
    '    affiliation: "Independent researcher"\n'
    '    email: "taejun.oh5@gmail.com"\n'
    'preferred-citation:\n'
    '  type: article\n'
    f'  title: "{TITLE}"\n'
    '  authors:\n'
    '    - family-names: Oh\n'
    '      given-names: Taejun\n'
    '  year: 2026\n'
    '  notes: "Working paper"\n', encoding="utf-8")
(GH / "README.md").write_text(f"""# {TITLE}

Taejun Oh (independent researcher, taejun.oh5@gmail.com). Working paper, November 2026.

When Lightbend moved new versions of Akka to the Business Source License in 2022, few of the open-source projects
built on Akka followed. This repository contains the paper, the dataset of dependents' choices, and the code that
reproduces every result in the paper.

| Folder | Content |
|---|---|
| `replication/paper/` | The paper (PDF and LaTeX source) |
| `dataset/` | The documented dataset: dependents of Akka and Elasticsearch, their release-level status, launch cohorts and motive codes (CC BY 4.0). See `dataset/README.md`. |
| `replication/` | Scripts, outputs and instructions to reproduce the results (code under MIT). See `replication/README.md`. |

The raw extracts used by the scripts (about 560 MB) are archived on Zenodo with the full replication package:
[doi:10.5281/zenodo.24440614](https://doi.org/10.5281/zenodo.24440614). See `replication/data/README.md`.

## License

Code: MIT. Dataset, derived tables and outputs: CC BY 4.0. The underlying package metadata comes from deps.dev
(Google Open Source Insights) and the package registries, chiefly Maven Central; see `LICENSE`.
""", encoding="utf-8")

# ---------- Zenodo archives ----------
def zipdir(src, dst, arcroot):
    with zipfile.ZipFile(dst, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as z:
        for p in sorted(src.rglob("*")):
            if p.is_file():
                z.write(p, Path(arcroot) / p.relative_to(src))


zipdir(RP, ZN / "replication_package.zip", "replication_package")
zipdir(DS, ZN / "dataset.zip", "dataset")


def size(d):
    return sum(p.stat().st_size for p in d.rglob("*") if p.is_file()) / 1e6


print("github MB", round(size(GH), 1), "| largest file MB",
      round(max(p.stat().st_size for p in GH.rglob("*") if p.is_file()) / 1e6, 1))
for z in sorted(ZN.iterdir()):
    print(z.name, "MB", round(z.stat().st_size / 1e6, 1))
