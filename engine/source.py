"""S4 DOWNLOAD — sourcing ladder (R4): ytagent → yt-dlp android_vr → yt-dlp.

Every artifact is validated (magic bytes, ffprobe streams, duration window,
min height) before it may enter the pool. Failed sources are dropped and
logged; `required` sources and per-entity minimums gate the build.
"""
from __future__ import annotations
import json, shutil, subprocess, sys

from .config import Project, probe_media

MAGIC = {b"\x00\x00\x00\x18ftypmp42", b"\x00\x00\x00\x20ftypisom",
         b"\x00\x00\x00\x18ftypisom", b"\x00\x00\x00\x1cftypisom",
         b"\x1a\x45\xdf\xa3"}


def _shutil_which(binary: str) -> bool:
    return shutil.which(binary) is not None


def resolve_url(entry: dict) -> str:
    """sources.yaml entries carry either url: or search: (yt-dlp resolves)."""
    if entry.get("url"):
        return entry["url"]
    q = entry["search"]
    return f"ytsearch1:{q}"


def download(entry: dict, dest_dir, max_h: int = 1080) -> dict:
    """Ladder per learnings/SOURCING_LADDER.md. Tries url: then search:.
    Returns {ok, path, method}."""
    dest_dir.mkdir(parents=True, exist_ok=True)
    out_tpl = str(dest_dir / f"{entry['id']}.%(ext)s")
    fmt = (f"bv*[height<={max_h}][ext=mp4]+ba[ext=m4a]/"
           f"b[height<={max_h}]/bv*+ba/b")
    attempts = []
    urls = []
    if entry.get("url"):
        urls.append(entry["url"])
    if entry.get("search"):
        urls.append(f"ytsearch1:{entry['search']}")

    for url in urls:
        if _shutil_which("ytagent"):
            r = subprocess.run(
                ["ytagent", "download", url, "--out-dir", str(dest_dir),
                 "--format", fmt, "--timeout", "240", "--json"],
                capture_output=True, text=True, timeout=600)
            attempts.append({"method": "ytagent", "rc": r.returncode})
            try:
                verdict = json.loads(r.stdout.strip().splitlines()[-1])
                if verdict.get("ok"):
                    return {"ok": True, "path": verdict["final_path"],
                            "method": "ytagent"}
            except Exception:  # noqa: BLE001
                pass

        for client in (["-N", "4"],
                       ["--extractor-args", "youtube:player_client=android_vr",
                        "-N", "4"]):
            r = subprocess.run(
                ["yt-dlp", *client, "-f", fmt, "--merge-output-format", "mp4",
                 "--no-playlist", "-o", out_tpl, "--restrict-filenames", url],
                capture_output=True, text=True, timeout=900)
            attempts.append({"method": "yt-dlp", "rc": r.returncode})
            if r.returncode == 0:
                break
        for p in sorted(dest_dir.glob(f"{entry['id']}.*")):
            if p.suffix.lower() in {".mp4", ".mkv", ".webm"}:
                return {"ok": True, "path": str(p),
                        "method": attempts[-1]["method"] if attempts else "yt-dlp"}
    return {"ok": False, "error": "no artifact", "attempts": attempts}


def validate(path: str, entry: dict) -> tuple[bool, str]:
    p = path if isinstance(path, str) else str(path)
    from pathlib import Path
    f = Path(p)
    if not f.exists() or f.stat().st_size < 1_000_000:
        return False, "too small/missing"
    head = f.read_bytes()[:12]
    if not any(head.startswith(m) for m in MAGIC):
        return False, "bad magic"
    info = probe_media(f)
    streams = info.get("streams", [])
    has_v = any(s.get("codec_type") == "video" for s in streams)
    has_a = any(s.get("codec_type") == "audio" for s in streams)
    if not (has_v and has_a):
        return False, "missing video/audio stream"
    dur = 0.0
    try:
        dur = float(info["format"]["duration"])
    except Exception:  # noqa: BLE001
        pass
    lo, hi = entry.get("expect_duration_s", [30, 1200])
    if not (lo <= dur <= hi):
        return False, f"duration {dur:.0f}s outside [{lo},{hi}]"
    hmax = 0
    for s in streams:
        if s.get("codec_type") == "video":
            hmax = max(hmax, s.get("height") or 0)
    min_h = entry.get("min_height", 480)
    if hmax < min_h:
        return False, f"height {hmax} < {min_h}"
    return True, f"{dur:.0f}s {hmax}p"


def build(project: Project) -> dict:
    manifest = project.sources_manifest["sources"]
    sdir = project.build / "sources"
    sdir.mkdir(parents=True, exist_ok=True)
    index_path = project.build / "source_index.json"
    index = json.loads(index_path.read_text()) if index_path.exists() else {}

    for entry in manifest:
        sid = entry["id"]
        done = sdir / f".{sid}.done"
        if done.exists() and sid in index and index[sid].get("ok"):
            continue
        print(f"[source] downloading {sid} …", flush=True)
        res = download(entry, sdir)
        if res["ok"]:
            ok, note = validate(res["path"], entry)
            if ok:
                index[sid] = {"ok": True, "path": res["path"],
                              "method": res["method"], "note": note,
                              "entity": entry.get("entity"),
                              "mode": entry.get("mode", "scene"),
                              "title": entry.get("title", sid)}
                done.write_text("ok\n")
                print(f"[source] {sid} OK ({note})", flush=True)
            else:
                index[sid] = {"ok": False, "error": note}
                print(f"[source] {sid} REJECTED: {note}", flush=True)
        else:
            index[sid] = {"ok": False, "error": res.get("error", "download failed")}
            print(f"[source] {sid} FAILED: {index[sid]['error']}", flush=True)
        index_path.write_text(json.dumps(index, indent=2))

    # gates: required sources + per-entity clip-capable pool sizing happens
    # after extraction; here we fail only if a required source is dead.
    dead_required = [e["id"] for e in manifest
                     if e.get("required") and not index.get(e["id"], {}).get("ok")]
    if dead_required:
        raise RuntimeError(f"required sources failed: {dead_required}")

    ok_n = sum(1 for v in index.values() if v.get("ok"))
    (project.build / "sources_report.json").write_text(json.dumps(index, indent=2))
    return {"ok_sources": ok_n, "total": len(manifest), "index": index}
