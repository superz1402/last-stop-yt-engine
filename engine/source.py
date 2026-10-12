"""S4 DOWNLOAD — sourcing ladder (R4).

On Actions runners, plain yt-dlp hits YouTube's datacenter bot-check. The
proven bypass (from the ahyeon-documentary download farm, battle-tested
2026): Cloudflare WARP proxy + BGutil PO-token provider, mweb/web/web_safari
clients. The workflow exports WARP_PROXY and BGUTIL_URL; the ladder reads
them and prefers farm attempts. Falls back gracefully when unset.
"""
from __future__ import annotations
import json, os, shutil, subprocess, sys, time

from .config import Project, probe_media

MAGIC = {b"\x00\x00\x00\x18ftypmp42", b"\x00\x00\x00\x20ftypisom",
         b"\x00\x00\x00\x18ftypisom", b"\x00\x00\x00\x1cftypisom",
         b"\x1a\x45\xdf\xa3"}

FMT_1080 = ("bv*[height<=1080][ext=mp4]+ba[ext=m4a]/"
            "b[height<=1080]/bv*+ba/b")
FMT_720 = "bv*[height<=720]+ba/b/bv*+ba"


def _shutil_which(binary: str) -> bool:
    return shutil.which(binary) is not None


def _yt_dlp(url: str, out_tpl: str, fmt: str, proxy: str | None,
            clients: str, pot: bool, timeout: int = 300) -> bool:
    cmd = ["yt-dlp", "--no-cache-dir", "-N", "3"]
    if proxy:
        cmd += ["--proxy", proxy]
    ea = f"youtube:player_client={clients}"
    if pot:
        ea += ";fetch_pot=always"
    cmd += ["--extractor-args", ea]
    if pot and os.environ.get("BGUTIL_URL"):
        cmd += ["--extractor-args",
                f"youtubepot-bgutilhttp:base_url={os.environ['BGUTIL_URL']}"]
    cmd += ["-f", fmt, "--merge-output-format", "mp4", "--no-playlist",
            "--restrict-filenames", "-o", out_tpl, url]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True,
                           timeout=timeout)
        return r.returncode == 0
    except subprocess.TimeoutExpired:
        return False


def download(entry: dict, dest_dir, max_h: int = 1080) -> dict:
    """Farm-first ladder per learnings/SOURCING_LADDER.md."""
    dest_dir.mkdir(parents=True, exist_ok=True)
    out_tpl = str(dest_dir / f"{entry['id']}.%(ext)s")
    urls = []
    if entry.get("url"):
        urls.append(entry["url"])
    if entry.get("search"):
        urls.append(f"ytsearch1:{entry['search']}")

    warp = os.environ.get("WARP_PROXY")
    bgutil = os.environ.get("BGUTIL_URL")
    attempts = []

    # ladder profiles: (label, proxy, clients, pot, fmt)
    profiles = []
    if warp:
        profiles += [
            ("warp+mweb+pot", warp, "mweb", True, FMT_1080),
            ("warp+web+pot", warp, "web", True, FMT_1080),
            ("warp+web_safari+pot", warp, "web_safari", True, FMT_1080),
            ("warp+mweb+pot720", warp, "mweb", True, FMT_720),
        ]
    profiles += [
        ("tv_embedded+pot", None, "tv,web_embedded", True, FMT_720),
        ("android_vr", None, "android_vr", False, FMT_720),
    ]

    for url in urls:
        for label, proxy, clients, pot, fmt in profiles:
            ok = _yt_dlp(url, out_tpl, fmt, proxy, clients, pot)
            attempts.append({"method": label, "ok": ok})
            for p in sorted(dest_dir.glob(f"{entry['id']}.*")):
                if p.suffix.lower() in {".mp4", ".mkv", ".webm"} and \
                        p.stat().st_size > 500_000:
                    return {"ok": True, "path": str(p), "method": label}
            # small leftover files (fragments) — clean before next attempt
            for p in dest_dir.glob(f"{entry['id']}.*"):
                if p.stat().st_size <= 500_000:
                    p.unlink()
        if _shutil_which("ytagent"):
            try:
                r = subprocess.run(
                    ["ytagent", "download", url, "--out-dir", str(dest_dir),
                     "--format", FMT_1080, "--timeout", "240", "--json"],
                    capture_output=True, text=True, timeout=600)
                attempts.append({"method": "ytagent", "rc": r.returncode})
                try:
                    verdict = json.loads(
                        r.stdout.strip().splitlines()[-1])
                    if verdict.get("ok"):
                        return {"ok": True, "path": verdict["final_path"],
                                "method": "ytagent"}
                except Exception:  # noqa: BLE001
                    pass
            except Exception:  # noqa: BLE001
                pass
    return {"ok": False, "error": "all ladder attempts failed",
            "attempts": attempts}


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

    dead_required = [e["id"] for e in manifest
                     if e.get("required") and not index.get(e["id"], {}).get("ok")]
    if dead_required:
        raise RuntimeError(f"required sources failed: {dead_required}")

    ok_n = sum(1 for v in index.values() if v.get("ok"))
    (project.build / "sources_report.json").write_text(json.dumps(index, indent=2))
    return {"ok_sources": ok_n, "total": len(manifest), "index": index}
