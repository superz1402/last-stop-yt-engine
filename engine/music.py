"""S9 MUSIC — CC0 bed via Openverse (verified license) with a deterministic
numpy fallback so the build never depends on a third-party API being up."""
from __future__ import annotations
import json, urllib.parse, urllib.request

import numpy as np

from .config import Project, media_duration


def _openverse(query: str, min_dur: int = 90) -> dict | None:
    try:
        url = ("https://api.openverse.org/v1/audio/?q=" +
               urllib.parse.quote(query) +
               "&license=cc0&length=long&filter_dead=false&page_size=20")
        req = urllib.request.Request(url, headers={"User-Agent": "last-stop-yt-engine/1.0"})
        with urllib.request.urlopen(req, timeout=30) as r:
            data = json.loads(r.read().decode())
        for item in data.get("results", []):
            dur = item.get("duration") or 0
            if dur and (dur / 1000.0) >= min_dur and item.get("url"):
                return {"url": item["url"],
                        "title": item.get("title", "openverse bed"),
                        "creator": item.get("creator", "unknown"),
                        "license": item.get("license", "cc0")}
    except Exception as exc:  # noqa: BLE001
        print(f"[music] openverse unavailable: {exc}", flush=True)
    return None


def _numpy_bed(project: Project, seconds: int) -> dict:
    """Dark ambient pad: stacked sines + slow LFO + filtered noise.
    Deterministic (seeded) — the somerton-man lesson: never block the film
    on an external service."""
    sr = 44100
    rng = np.random.default_rng(2040 + int(seconds))
    n = sr * seconds
    t = np.arange(n) / sr
    root = 55.0  # A1
    bed = np.zeros(n, dtype=np.float64)
    for mult, amp in [(1.0, 0.42), (1.5, 0.22), (2.0, 0.18), (3.0, 0.09), (4.0, 0.05)]:
        f = root * mult
        lfo = 0.5 + 0.5 * np.sin(2 * np.pi * (0.02 + 0.011 * mult) * t + mult)
        bed += amp * lfo * np.sin(2 * np.pi * f * t + mult * 0.7)
    noise = rng.normal(0, 1, n)
    # FFT lowpass (fast, deterministic): keep < 220 Hz for sub-pad rumble
    spec = np.fft.rfft(noise)
    freqs = np.fft.rfftfreq(n, 1 / sr)
    spec *= np.exp(-np.clip(freqs - 120, 0, None) / 90.0)
    lp = np.fft.irfft(spec, n)
    bed += 0.10 * lp
    bed /= (np.max(np.abs(bed)) + 1e-9)
    # gentle fades
    fade = sr * 4
    bed[:fade] *= np.linspace(0, 1, fade)
    bed[-fade:] *= np.linspace(1, 0, fade)
    pcm = (bed * 32767 * 0.9).astype(np.int16)
    out = project.build / "bed.wav"
    import wave
    with wave.open(str(out), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(pcm.tobytes())
    return {"source": "numpy_fallback", "title": "engine dark pad",
            "creator": "last-stop-yt-engine", "license": "internal"}


def build(project: Project) -> dict:
    cfg = project.cfg.get("music", {})
    query = cfg.get("query", "dark ambient documentary")
    meta = _openverse(query)
    if meta:
        out = project.build / "bed_dl.mp3"
        try:
            urllib.request.urlretrieve(meta["url"], out)
            if out.exists() and out.stat().st_size > 500_000 and \
                    media_duration(out) > 60:
                import subprocess
                wav = project.build / "bed.wav"
                subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", str(out),
                                "-ar", "44100", "-ac", "1", str(wav)],
                               check=True, capture_output=True)
                meta["file"] = str(wav)
                (project.build / "bed_meta.json").write_text(json.dumps(meta, indent=2))
                print(f"[music] openverse bed: {meta['title']} by {meta['creator']}", flush=True)
                return meta
        except Exception as exc:  # noqa: BLE001
            print(f"[music] bed download failed: {exc}", flush=True)
    meta = _numpy_bed(project, int(project.cfg["target_duration_s"] / 2))
    meta["file"] = str(project.build / "bed.wav")
    (project.build / "bed_meta.json").write_text(json.dumps(meta, indent=2))
    print(f"[music] numpy fallback bed ({meta['title']})", flush=True)
    return meta
