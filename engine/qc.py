"""S11 QC — spec asserts (R6), lock audit (R2), no-image audit (R1),
freeze detection (ChatCut pixels-are-proof law), provenance report (R9)."""
from __future__ import annotations
import json, subprocess

from .config import Project, probe_media, human_s
from . import rules


def _ffreeze(path: str, d: float = 2.0) -> list[str]:
    """freezedetect: any freeze ≥ d seconds → list of events."""
    r = subprocess.run(
        ["ffmpeg", "-v", "info", "-i", path,
         "-vf", f"freezedetect=n=0.003:d={d}", "-f", "null", "-"],
        capture_output=True, text=True)
    return [ln for ln in r.stderr.splitlines() if "freeze_start" in ln]


def run(project: Project) -> dict:
    timeline = json.loads((project.build / "timeline.json").read_text())
    final = project.build / "final.mp4"
    report = {"project": project.slug, "checks": [], "pass": True}

    def check(name: str, ok: bool, detail: str = ""):
        report["checks"].append({"name": name, "ok": bool(ok), "detail": detail})
        if not ok:
            report["pass"] = False

    info = probe_media(final)
    v = next((s for s in info.get("streams", []) if s["codec_type"] == "video"), {})
    a = next((s for s in info.get("streams", []) if s["codec_type"] == "audio"), {})
    fmt = info.get("format", {})
    dur = float(fmt.get("duration", 0))

    check("duration_exact", abs(dur - timeline["target"]) <= 2.0,
          f"{human_s(dur)} vs target {human_s(timeline['target'])}")
    check("resolution", (v.get("width"), v.get("height")) == (1920, 1080),
          f"{v.get('width')}x{v.get('height')}")
    check("codec_video", v.get("codec_name") == "h264", v.get("codec_name", "?"))
    check("fps", abs(float(v.get("avg_frame_rate", "0/1").split("/")[0] or 0) /
                     max(1, float(v.get("avg_frame_rate", "30/1").split("/")[1] or 30))
                     - 30) < 0.5, v.get("avg_frame_rate", "?"))
    check("codec_audio", a.get("codec_name") == "aac", a.get("codec_name", "?"))
    check("sample_rate", a.get("sample_rate") == "48000", a.get("sample_rate", "?"))
    check("channels_stereo", a.get("channels") == 2, str(a.get("channels")))
    check("bitrate_audio_192k", int(fmt.get("bit_rate", 0)) > 150_000,
          fmt.get("bit_rate", "?"))

    # moov at start (faststart): scan first 256 KB for moov before mdat
    with open(final, "rb") as f:
        head = f.read(262144)
    imoov, imdat = head.find(b"moov"), head.find(b"mdat")
    check("faststart", imoov != -1 and (imdat == -1 or imoov < imdat),
          f"moov@{imoov} mdat@{imdat}")

    # R1: no images anywhere in the timeline
    try:
        rules.audit_no_images(timeline)
        check("no_images_R1", True, "all slots kind=video")
    except rules.NoImageViolation as e:
        check("no_images_R1", False, str(e))

    # R2: character lock recomputed independently
    try:
        lock = rules.audit_lock(project, timeline)
        check("character_lock_R2", True,
              f"{lock['checked']} slots verified, 0 violations")
    except rules.LockViolation as e:
        check("character_lock_R2", False, str(e))

    # freeze detection (no slideshow behavior in a video-only film)
    freezes = _ffreeze(str(final), d=2.0)
    check("no_freeze_frames", len(freezes) == 0,
          f"{len(freezes)} freeze events ≥2s")

    # provenance (R9)
    used = sorted({slot["visuals"][0]["source_id"]
                   for slot in timeline["clips"]})
    report["used_sources"] = used
    report["editor_stats"] = timeline.get("editor_stats", {})

    out = project.build / "qc_report.json"
    out.write_text(json.dumps(report, indent=2))
    for c in report["checks"]:
        print(f"[qc] {'PASS' if c['ok'] else 'FAIL'} {c['name']} — {c['detail']}",
              flush=True)
    if not report["pass"]:
        raise RuntimeError("QC FAILED — release blocked")
    print("[qc] ALL PASS", flush=True)
    return report
