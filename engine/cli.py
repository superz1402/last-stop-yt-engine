"""last stop yt engine — one command: build <project-dir>

Runs the full cycle (ENGINE.md): script → download → refs → extract →
voice → storyboard → music → render → qc → publish. Every stage resumable
via .done markers (R8). This CLI is the entire system (R10).
"""
from __future__ import annotations
import json, sys, time
from pathlib import Path

from .config import Project
from . import script as script_mod, source, refs, extract, voice, \
    storyboard, music, render, qc, publish

STAGES = ["research", "script", "download", "refs", "extract",
          "voice", "storyboard", "music", "render", "qc", "publish"]


def _stage(project: Project, name: str, fn):
    if project.is_done(name):
        print(f"[{name}] done — skipping", flush=True)
        return
    t0 = time.time()
    print(f"[{name}] running …", flush=True)
    fn()
    project.mark_done(name, f"{time.time() - t0:.0f}s")
    print(f"[{name}] OK ({time.time() - t0:.0f}s)", flush=True)


def build(project_dir: str, upto: str | None = None):
    project = Project(Path(project_dir))
    project.build.mkdir(parents=True, exist_ok=True)

    def s_research():
        r = sorted((project.dir / "research").glob("*.md"))
        if not r:
            raise RuntimeError("R3: research/ empty")
        print(f"[research] artifacts: {[p.name for p in r]}")

    def s_script():
        out = script_mod.parse(project)
        print(f"[script] {out['word_count']} words, "
              f"{len(out['blocks'])} blocks, ~{out['est_minutes']} min "
              f"(target {project.cfg['target_duration_s'] / 60:.0f})")

    def s_download():
        res = source.build(project)
        print(f"[download] {res['ok_sources']}/{res['total']} sources usable")

    def s_refs():
        idx = json.loads((project.build / "source_index.json").read_text())
        refs.ensure_all(project, idx)

    def s_extract():
        idx = json.loads((project.build / "source_index.json").read_text())
        extract.build(project, idx)

    def s_voice():
        out = voice.build(project)
        print(f"[voice] {out['n_blocks']} blocks, "
              f"{out['total_voice_s']:.0f}s total")

    def s_storyboard():
        storyboard.build(project)

    def s_music():
        music.build(project)

    def s_render():
        render.render(project)

    def s_qc():
        qc.run(project)

    def s_publish():
        publish.publish(project)

    table = {"research": s_research, "script": s_script, "download": s_download,
             "refs": s_refs, "extract": s_extract, "voice": s_voice,
             "storyboard": s_storyboard, "music": s_music, "render": s_render,
             "qc": s_qc, "publish": s_publish}
    for name in STAGES:
        _stage(project, name, table[name])
        if upto and name == upto:
            break
    print("[build] complete", flush=True)


def main(argv: list[str]):
    if len(argv) >= 2 and argv[0] == "build":
        upto = argv[2] if len(argv) > 2 else None
        build(argv[1], upto)
        return
    print(__doc__)
    sys.exit(2)


if __name__ == "__main__":
    main(sys.argv[1:])
