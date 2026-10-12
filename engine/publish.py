"""S12 PUBLISH — GitHub Release v1.0 with final.mp4 + QC + provenance."""
from __future__ import annotations
import json, subprocess

from .config import Project, human_s


def publish(project: Project) -> str:
    final = project.build / "final.mp4"
    qc = json.loads((project.build / "qc_report.json").read_text())
    timeline = json.loads((project.build / "timeline.json").read_text())
    qc_copy = project.build / "qc_report_v1.json"
    qc_copy.write_text(json.dumps(qc, indent=2))
    manifest_copy = project.build / "used_sources.json"
    manifest_copy.write_text(json.dumps(
        {"used_sources": qc["used_sources"],
         "runtime": human_s(timeline["target"])}, indent=2))

    tag = "v1.0"
    title = project.cfg.get("release", {}).get("title", f"{project.slug} — final")
    notes = project.cfg.get("release", {}).get("notes", "")
    repo_env = project.cfg.get("release", {}).get("repo")

    def gh(*args):
        cmd = ["gh", *args]
        if repo_env:
            cmd += ["-R", repo_env]
        r = subprocess.run(cmd, capture_output=True, text=True)
        return r

    # idempotent: drop old release, recreate
    gh("release", "delete", tag, "--yes", "--cleanup-tag")
    r = gh("release", "create", tag, str(final), str(qc_copy), str(manifest_copy),
           "--title", title, "--notes", notes)
    if r.returncode != 0:
        raise RuntimeError(f"gh release failed: {r.stderr[-500:]}")
    print(f"[publish] release {tag} created", flush=True)
    return r.stdout.strip()
