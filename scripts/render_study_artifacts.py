"""Render the ReproLab study artifact and replication-log pages.

These static pages are the live evidence sources that studionet validators
fetch with `gl.nondet.web.render(...)`, so they are generated from one table
and stay byte-identical across rebuilds. Output: frontend/public/artifacts/.
"""

from __future__ import annotations

import hashlib
import pathlib

OUT = pathlib.Path("frontend/public/artifacts")

STYLE = """
    body { background:#0B132B; color:#D7E1F0; font-family:'IBM Plex Serif',Georgia,serif;
           margin:0 auto; max-width:46rem; padding:3rem 1.25rem 4rem; line-height:1.65 }
    h1 { color:#06B6D4; font-size:1.5rem }
    h2 { color:#10B981; font-size:1.05rem; margin-top:2rem }
    .meta { font-family:'IBM Plex Mono',ui-monospace,monospace; font-size:.78rem; color:#8AA0BF }
    .headline { border-left:3px solid #10B981; background:#1C2541; padding:.9rem 1.1rem;
                margin:1.6rem 0; font-family:'IBM Plex Mono',ui-monospace,monospace }
    table { border-collapse:collapse; width:100%;
            font-family:'IBM Plex Mono',ui-monospace,monospace; font-size:.85rem }
    td, th { border-bottom:1px solid #263252; padding:.4rem .5rem; text-align:left }
    ul { padding-left:1.2rem }
"""

# key, title, target token, reference line, headline percent, extra metric rows
STUDIES = [
    {
        "key": "drift",
        "title": "LLM Quantization Perplexity Drift Study",
        "target": "quantization-perplexity-drift",
        "ref": "arXiv 2311.05915 (GPTQ and AWQ family), Zenodo record 10419084, protocol r3",
        "pct": "52.50",
        "rows": [
            ("secondary inference latency overhead", "8.40", "percent"),
            ("secondary memory reduction", "71.00", "percent"),
        ],
    },
    {
        "key": "crispr",
        "title": "CRISPR Off-Target Cleavage Dataset Benchmark",
        "target": "crispr-offtarget-cleavage-rate",
        "ref": "doi 10.5281/zenodo.10419085, Guide-seq dataset v2, GEO GSE241190",
        "pct": "67.50",
        "rows": [
            ("secondary on-target efficiency", "91.20", "percent"),
            ("secondary indel fraction", "12.75", "percent"),
        ],
    },
    {
        "key": "meissner",
        "title": "Superconductor Meissner Curve Reproduction",
        "target": "meissner-flux-expulsion-fraction",
        "ref": "arXiv 2403.11871 supplementary, Zenodo record 10834221, run 4",
        "pct": "40.00",
        "rows": [
            ("secondary transition width", "2.30", "percent"),
            ("secondary hysteresis loss", "5.75", "percent"),
        ],
    },
    {
        "key": "sequencing",
        "title": "Sanger Sequencing Read Accuracy Benchmark",
        "target": "sanger-basecall-accuracy",
        "ref": "doi 10.1093/nar/gkae1102, ENA study PRJNA987654",
        "pct": "82.50",
        "rows": [
            ("secondary read depth coverage", "96.40", "percent"),
            ("secondary chimera rate", "1.60", "percent"),
        ],
    },
]

# lab, study key, replicated percent, integrity percent, checksum, note
LOGS = [
    {
        "lab": "Northgate Independent Replication Lab",
        "study": "drift",
        "rep": "52.50",
        "integrity": "92.50",
        "checksum": "7d21c4b9f0a53e18c6d7a0b215e94c3d8a6f1b0c2d3e4f50617283a4b5c6d7e8",
        "hardware": "2x A100 80GB, CUDA 12.4, transformer-engine 1.5",
        "seeds": "seeds 17, 23, 41 (three independent runs, median reported)",
    },
    {
        "lab": "Kantaro Cell Systems Group",
        "study": "crispr",
        "rep": "75.00",
        "integrity": "90.00",
        "checksum": "1f3d9c2a7b5e4018d6c3a9b0e5f2741c8a3d6b9e0f51c72a4b8d3e69f0c15a72",
        "hardware": "Illumina NovaSeq 6000, paired-end 150bp, n=4 replicates",
        "seeds": "biological replicates R1..R4, technical triplicate each",
    },
    {
        "lab": "Cryogenic Metrology Collective",
        "study": "meissner",
        "rep": "40.00",
        "integrity": "92.50",
        "checksum": "a4b7c9d0e1f23586a7b1c4d9e0f3a25c6b7d8e9f0a1b2c3d4e5f60718293a4b5",
        "hardware": "PPMS 14T, SQUID magnetometer, 2K to 300K sweep",
        "seeds": "sweeps 1..5 at 5 mK/min, field-cooled and zero-field-cooled",
    },
]


def _bps(pct: str) -> str:
    return str(int(round(float(pct) * 100)))


def _page(title: str, meta: str, body: str) -> str:
    return (
        "<!doctype html>\n<html lang=\"en\">\n<head>\n"
        "<meta charset=\"utf-8\" />\n"
        "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\" />\n"
        "<title>" + title + "</title>\n<style>" + STYLE + "</style>\n</head>\n<body>\n"
        + meta + body + "</body>\n</html>\n"
    )


def artifact_page(study: dict) -> str:
    bps = _bps(study["pct"])
    rows = "".join(
        "<tr><td>" + n + "</td><td>" + v + "</td><td>" + u + "</td></tr>\n"
        for n, v, u in study["rows"]
    )
    meta = "<p class=\"meta\">ReproLab registered study artifact and source of record</p>"
    body = (
        "<h1>" + study["title"] + "</h1>\n"
        "<p>Reference: " + study["ref"] + ".</p>\n"
        "<div class=\"headline\">Headline quantitative result for the study "
        + study["title"] + " measured under the target " + study["target"]
        + ": " + study["pct"] + " percent, which is " + bps
        + " basis points. This single number is the reported effect size.</div>\n"
        "<p>Only the headline value above is the reported effect size for "
        + study["target"] + ". Basis points are percent times 100.</p>\n"
        "<table>\n<tr><th>Metric</th><th>Value</th><th>Units</th></tr>\n"
        "<tr><td>" + study["target"] + " headline</td><td>" + study["pct"]
        + "</td><td>percent</td></tr>\n"
        "<tr><td>" + study["target"] + " in basis points</td><td>" + bps
        + "</td><td>bps</td></tr>\n" + rows + "</table>\n"
    )
    return _page("ReproLab artifact: " + study["title"], meta, body)


def log_page(study: dict, log: dict) -> str:
    rep_bps = _bps(log["rep"])
    int_bps = _bps(log["integrity"])
    meta = "<p class=\"meta\">ReproLab independent replication log, peer-reviewable</p>"
    body = (
        "<h1>Replication log: " + study["title"] + "</h1>\n"
        "<p>Replicating group: " + log["lab"] + ". This group has no author "
        "overlap with the original study and re-ran the frozen protocol from the "
        "public dataset.</p>\n"
        "<h2>Independent replication protocol</h2>\n<ul>"
        "<li>Instrument: " + log["hardware"] + "</li>"
        "<li>Sampling: " + log["seeds"] + "</li>"
        "<li>Dataset obtained from the public record, checksum verified before "
        "analysis, no manual edits.</li>"
        "<li>Analysis script pinned to the commit hash recorded below, all "
        "random seeds fixed, raw outputs published.</li></ul>\n"
        "<div class=\"headline\">Measured " + study["target"] + " after "
        "replication: " + log["rep"] + " percent, which is " + rep_bps
        + " basis points. Dataset integrity score: " + log["integrity"]
        + " percent, which is " + int_bps + " basis points.</div>\n"
        "<table>\n<tr><th>Field</th><th>Value</th></tr>\n"
        "<tr><td>replicated score bps</td><td>" + rep_bps + "</td></tr>\n"
        "<tr><td>dataset integrity bps</td><td>" + int_bps + "</td></tr>\n"
        "<tr><td>sha256 dataset checksum</td><td>" + log["checksum"]
        + "</td></tr>\n<tr><td>original reported percent</td><td>"
        + study["pct"] + "</td></tr>\n</table>\n"
        "<p class=\"meta\">Deviations between the original and this replication "
        "are reported in full. No sample was excluded and no threshold was "
        "tuned after the runs.</p>\n"
    )
    return _page("ReproLab replication log: " + study["title"], meta, body)


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    by_key = {s["key"]: s for s in STUDIES}
    written = []
    for study in STUDIES:
        path = OUT / (study["key"] + "-artifact.html")
        path.write_text(artifact_page(study), encoding="utf-8", newline="\n")
        written.append(path)
    for log in LOGS:
        path = OUT / (log["study"] + "-log.html")
        path.write_text(log_page(by_key[log["study"]], log), encoding="utf-8", newline="\n")
        written.append(path)
    for path in sorted(written):
        raw = path.read_bytes()
        print(path.as_posix(), len(raw), hashlib.sha256(raw).hexdigest()[:16])


if __name__ == "__main__":
    main()
