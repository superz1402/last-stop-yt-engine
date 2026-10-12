"""S7 VOICE — edge-tts narration per block, measured to the millisecond."""
from __future__ import annotations
import asyncio, json, subprocess, sys, time

from .config import Project, VOICE_DEFAULT, media_duration


async def _synth(text: str, out_mp3: str, voice: str, rate: str = "+0%"):
    import edge_tts
    tts = edge_tts.Communicate(text, voice, rate=rate)
    await tts.save(out_mp3)


def synth_block(project: Project, block: dict, voice: str, rate: str,
                retries: int = 3) -> dict:
    """Synthesize one block, convert to 48k stereo wav, measure duration."""
    bdir = project.build / "voices"
    bdir.mkdir(parents=True, exist_ok=True)
    mp3 = bdir / f"{block['id']}.mp3"
    wav = bdir / f"{block['id']}.wav"
    done = bdir / f".{block['id']}.done"

    if not done.exists():
        last = None
        for attempt in range(1, retries + 1):
            try:
                asyncio.run(_synth(block["text"], str(mp3), voice, rate))
                if mp3.exists() and mp3.stat().st_size > 1024:
                    break
                raise RuntimeError("edge-tts produced empty/missing file")
            except Exception as e:  # noqa: BLE001
                last = e
                sys.stderr.write(f"[voice] {block['id']} attempt {attempt} failed: {e}\n")
                time.sleep(3 * attempt)
        else:
            raise RuntimeError(f"edge-tts failed for {block['id']}: {last}")
        # 48k stereo conversion (delivery graph requires it)
        r = subprocess.run(
            ["ffmpeg", "-y", "-v", "error", "-i", str(mp3),
             "-ar", "48000", "-ac", "2", "-c:a", "pcm_s16le", str(wav)],
            capture_output=True, text=True)
        if r.returncode != 0:
            raise RuntimeError(f"wav convert failed for {block['id']}: {r.stderr[-300:]}")
        done.write_text("ok\n")

    dur = media_duration(mp3)
    if dur <= 0:
        dur = media_duration(wav)
    if dur <= 0:
        raise RuntimeError(f"could not measure voice for {block['id']}")
    return {"id": block["id"], "text": block["text"],
            "voice": voice, "rate": rate,
            "mp3": str(mp3), "wav": str(wav), "dur_s": round(dur, 3)}


def build(project: Project) -> dict:
    blocks = json.loads((project.build / "blocks.json").read_text())["blocks"]
    voice = project.cfg.get("voice", {}).get("model", VOICE_DEFAULT)
    rate = project.cfg.get("voice", {}).get("rate", "+0%")
    entries = [synth_block(project, b, voice, rate) for b in blocks]
    total = sum(e["dur_s"] for e in entries)
    out = {"voice": voice, "rate": rate, "entries": entries,
           "total_voice_s": round(total, 2), "n_blocks": len(entries)}
    (project.build / "voices.json").write_text(json.dumps(out, indent=2))
    return out
