# RENDER CORE — the proven 3-phase render (from ahyeon-documentary)

Origin: `superz1402/ahyeon-documentary` `pipeline/render.py` — shipped one
29:00 film at exact runtime with QC PASS. Adapted here with all image paths
removed (R1) and the `NoImageViolation` gate added.

## Phase 1 — per-slot segments (resumable)

For every visual slot in `timeline.json`:

```
ffmpeg -ss <start> -t <dur> -i sources/<clip>.mp4
  -filter:v "scale=1920:1080:force_original_aspect_ratio=increase,
             crop=1920:1080,fps=30,setsar=1"
  -an -c:v libx264 -preset veryfast -crf 16 seg_XXXX.mp4
```

- `-an`: slots are silent; all audio is built in phase 3.
- CRF16 intermediates: phase 3's final CRF21 encode is the only generation
  that matters for delivery quality.
- `.done` markers per segment — a killed runner resumes mid-render.

## Phase 2 — concat

`concat -c copy` → `master_video.mp4` (all segments share codec params —
copy is safe and instant).

## Phase 3 — one ffmpeg graph (audio truth + captions + final encode)

```
voices: per-block adelay(positions from timeline) → amix normalize=0
music:  bed.wav looped, gain 0.32 → asplit 2
duck:   sidechaincompress(threshold=0.015:ratio=7:attack=120:release=700)
master: amix voices+ducked bed → loudnorm=I=-14:TP=-1.5:LRA=11
video:  ass captions burn (from narration text, timed to blocks)
length: tpad to exact target runtime (covers sub-second rounding)
encode: libx264 crf21 veryfast, yuv420p, faststart
        aac 192k -ar 48000 -ac 2   ← NEVER omit (96kHz-mono lesson)
```

## The audio lesson (paid for in v1.0 of ahyeon-documentary)

`loudnorm` internally upsamples to 192 kHz; omitting `-ar 48000 -ac 2`
leaks a 96 kHz mono track into delivery. The final encode MUST carry explicit
`-ar 48000 -ac 2`. QC asserts `channels=2, sample_rate=48000`.

## Music bed

Primary: CC0 ambient bed via Openverse API (query from `project.yaml`,
duration ≥ 60 s, license CC0 verified). Fallback: deterministic numpy dark
ambient pad (sine stack + slow LFO + lowpass noise, 44.1k mono → stretched)
so the build never depends on a third-party API being up.

## Exact runtime

`gap_scale` calibration lands within ±1.5 s; `tpad` + `-t target` makes the
deliverable hit the declared runtime to the second.
