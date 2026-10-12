"""S10 RENDER — 3-phase resumable render (ahyeon-documentary lineage).

Phase 1: per-slot segment extractions (video only, -an, crf16, .done markers)
Phase 2: concat -c copy → master_video.mp4
Phase 3: voices amix + ducked bed + loudnorm + captions + final x264

R1 hard gate: any visual slot with kind != "video" raises NoImageViolation.
Audio law: final encode carries explicit -ar 48000 -ac 2 (the 96 kHz lesson).
"""
from __future__ import annotations
import json, subprocess

from .config import Project, W, H, LOUDNORM, media_duration
from . import rules

SEG_DIR = "segs"


def _seg_path(project: Project, i: int):
    return project.build / SEG_DIR / f"seg_{i:05d}.mp4"


def phase1(project: Project, timeline: dict) -> int:
    sdir = project.build / SEG_DIR
    sdir.mkdir(parents=True, exist_ok=True)
    n = len(timeline["clips"])
    for i, slot in enumerate(timeline["clips"]):
        seg = _seg_path(project, i)
        done = sdir / f".{i:05d}.done"
        if done.exists() and seg.exists():
            continue
        v = slot["visuals"][0]
        if v.get("kind") != "video":
            raise rules.NoImageViolation(
                f"slot {i}: kind={v.get('kind')} — R1 hard gate")
        r = subprocess.run(
            ["ffmpeg", "-y", "-v", "error",
             "-ss", str(v["start"]), "-t", str(v["dur"]), "-i", v["path"],
             "-filter:v",
             f"scale={W}:{H}:force_original_aspect_ratio=increase,"
             f"crop={W}:{H},fps=30,setsar=1",
             "-an", "-c:v", "libx264", "-preset", "veryfast", "-crf", "16",
             "-pix_fmt", "yuv420p", str(seg)],
            capture_output=True, text=True)
        if r.returncode != 0 or not seg.exists() or seg.stat().st_size < 1024:
            raise RuntimeError(f"seg {i} failed: {r.stderr[-400:]}")
        done.write_text("ok\n")
        if i % 25 == 0:
            print(f"[render:p1] {i+1}/{n} segments", flush=True)
    return n


def phase2(project: Project, timeline: dict) -> str:
    lst = project.build / "concat.txt"
    with open(lst, "w") as f:
        for i in range(len(timeline["clips"])):
            f.write(f"file '{_seg_path(project, i).resolve()}'\n")
    master = project.build / "master_video.mp4"
    r = subprocess.run(
        ["ffmpeg", "-y", "-v", "error", "-f", "concat", "-safe", "0",
         "-i", str(lst), "-c", "copy", str(master)],
        capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"concat failed: {r.stderr[-400:]}")
    return str(master)


def write_ass(project: Project, timeline: dict) -> str:
    ass = project.build / "captions.ass"
    hdr = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {W}
PlayResY: {H}
WrapStyle: 2

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Doc,Montserrat,54,&H00FFFFFF,&H000000FF,&H00101010,&H80000000,-1,0,0,0,100,100,0.5,0,1,3.2,1.2,2,110,110,64,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    def ts(t: float) -> str:
        h = int(t // 3600)
        m = int((t % 3600) // 60)
        s = t % 60
        return f"{h}:{m:02d}:{s:05.2f}"

    lines = [hdr]
    for c in timeline.get("captions", []):
        txt = c["text"].replace("{", "<").replace("}", ">").replace("\n", " ")
        lines.append(f"Dialogue: 0,{ts(c['t'])},{ts(c['t'] + c['dur_s'])},"
                     f"Doc,,0,0,0,,{txt}")
    ass.write_text("\n".join(lines))
    return str(ass)


def phase3(project: Project, timeline: dict, master: str) -> str:
    import shlex
    bed_meta = json.loads((project.build / "bed_meta.json").read_text())
    bed = bed_meta["file"]
    ass = write_ass(project, timeline)

    cmd = ["ffmpeg", "-y", "-v", "error", "-i", master]
    cmd += ["-stream_loop", "-1", "-i", bed]
    fparts = []
    voices = timeline["voices"]
    for j, v in enumerate(voices):
        cmd += ["-i", v["wav"]]
        ms = int(round(v["t"] * 1000))
        fparts.append(f"[{j + 2}:a]aformat=sample_rates=48000:channel_layouts=stereo,"
                      f"adelay={ms}|{ms}[vj{j}]")
    fparts.append("[1:a]aformat=sample_rates=48000:channel_layouts=stereo,"
                  "volume=0.32,asplit=2[bedm][bedk]")
    if voices:
        mix_ins = "".join(f"[vj{j}]" for j in range(len(voices)))
        fparts.append(f"{mix_ins}amix=inputs={len(voices)}:normalize=0,"
                      "dropout_transition=0,asplit=2[vm1][vmk]")
        fparts.append("[bedk][vmk]sidechaincompress=threshold=0.015:ratio=7:"
                      "attack=120:release=700[duck]")
        fparts.append("[vm1][duck]amix=inputs=2:normalize=0,"
                      f"loudnorm={LOUDNORM}[aout]")
    else:
        fparts.append("[bedm]loudnorm=" + LOUDNORM + "[aout]")

    deficit = timeline["target"] - timeline["actual"]
    pad = max(0.0, deficit) + 2.0
    vf = f"ass={shlex.quote(ass)},tpad=stop_mode=clone:stop_duration={pad:.2f}"
    final = project.build / "final.mp4"
    cmd += ["-filter_complex", ";".join(fparts),
            "-map", "0:v", "-vf", vf,
            "-map", "[aout]",
            "-t", str(timeline["target"]),
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "21",
            "-pix_fmt", "yuv420p", "-movflags", "+faststart",
            "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-ac", "2",
            str(final)]
    print("[render:p3] final encode …", flush=True)
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"phase3 failed: {r.stderr[-600:]}")
    return str(final)


def render(project: Project) -> str:
    timeline = json.loads((project.build / "timeline.json").read_text())
    rules.audit_no_images(timeline)  # R1 gate at render entry, again
    phase1(project, timeline)
    master = phase2(project, timeline)
    final = phase3(project, timeline, master)
    print(f"[render] final: {final} "
          f"({media_duration(final):.1f}s, target {timeline['target']}s)",
          flush=True)
    return final
