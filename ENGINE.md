# ENGINE — the cycle

```
┌────────────────────────────────────────────────────────────────────┐
│  S0 BRIEF      project.yaml          topic · runtime · entities    │
│  S1 RESEARCH   research/*.md         hardened facts + citations    │
│  S2 SCRIPT     script/script.md      narration blocks + on_screen  │
│  S3 SOURCES    sources.yaml          video manifest (URLs+roles)   │
│  S4 DOWNLOAD   build/sources/        ytagent ladder + validation   │
│  S5 REFS       build/refs/           face centroids (InsightFace)  │
│  S6 EXTRACT    build/clips.json      character-locked clip pool    │
│  S7 VOICE      build/voices/         edge-tts per block, measured  │
│  S8 EDIT       build/timeline.json   entity-timed storyboard       │
│  S9 MUSIC      build/bed.wav         CC0 bed / numpy fallback      │
│  S10 RENDER    build/final.mp4       3-phase resumable render      │
│  S11 QC        build/qc_report.json  spec + lock + freeze asserts  │
│  S12 PUBLISH   Release v1.0          final.mp4 + provenance        │
└────────────────────────────────────────────────────────────────────┘
        one command:  python -m engine.cli build projects/<slug>
```

## Stage contracts

Every stage consumes and produces **committed or build-dir artifacts** with a
stable name. Any engineer (or agent) can pick the project up mid-cycle.

| Stage | Reads | Writes | Resumable via |
|---|---|---|---|
| S0 brief | `project.yaml` | in-memory | — |
| S1 research | `research/*.md` | validated | `.done/research` |
| S2 script | `script/script.md` | `build/blocks.json` | `.done/script` |
| S3 sources | `sources.yaml` | validated | `.done/sources` |
| S4 download | `build/blocks.json` + manifest | `build/sources/*.mp4` | per-source `.done` |
| S5 refs | source videos + `refs/` seeds | `build/refs/*.json` | per-entity `.done` |
| S6 extract | videos + centroids | `build/clips.json` | per-source `.done` |
| S7 voice | `build/blocks.json` | `build/voices/*.wav` + `voices.json` | per-block `.done` |
| S8 edit | blocks + voices + clips | `build/timeline.json` | `.done/storyboard` |
| S9 music | `project.yaml` | `build/bed.wav` | `.done/music` |
| S10 render | timeline + sources + voices + bed | `build/master.mp4`, `build/final.mp4` | 3 internal phases |
| S11 qc | final.mp4 + timeline | `build/qc_report.json` | — (gate) |
| S12 publish | final.mp4 + qc PASS | GitHub Release v1.0 | idempotent replace |

## The narration ↔ picture clock

1. `script.md` blocks are split into narration sentences with `on_screen` tags.
2. `voice.py` renders each block to WAV and measures it (ffprobe).
3. `storyboard.py` lays slots: a block of measured length L gets
   `ceil(L / slot_s)` slots, each slot a character-locked clip of length
   2.5–8 s cut from the clip pool.
4. Pauses between blocks are scaled by `gap_scale` so the film lands on the
   target runtime exactly:

```
gap_scale = clamp((target − intro − outro − Σvoice) / Σpause_slots, 0.4, 2.6)
```

5. `render.py` phase 3 runs one ffmpeg graph: per-block VO `adelay` → `amix`
   → sidechain-ducked music bed → `loudnorm=I=-14:TP=-1.5:LRA=11` → caption
   burn → exact-length pad → x264 crf21 / AAC 192k 48k stereo / faststart.

## Character-lock pipeline (the core innovation)

```
official MV/performances ──download──▶ build/sources/
        │
        ├─ scene mode ──▶ PySceneDetect shots ──▶ entity-level clips
        │                (group MVs are entity-pure: a BLACKPINK MV
        │                 is a pool of BLACKPINK shots)
        │
        └─ character mode ▶ face pass @2fps (InsightFace 512-d, one pass
                             per video) → per-member visibility track →
                             scene grouping → per-member clip windows
                             (design credit: character-clip-extractor)

solo MVs (SOLO/LALISA/FLOWER/On The Ground) ──▶ dominant-cluster bootstrap
                                                  → member centroids
BABYMONSTER members ──▶ vendored refs (from character-clip-extractor)
```

## Where heavy work runs

Local laptop: fine for S0–S3, S7–S9. Production truth is the
`.github/workflows/build-documentary.yml` runner job: downloads, face passes
and rendering all execute on GitHub Actions (x264 at 1080p is not laptop
work). The workflow is the "one command" for the whole cycle.

## Failure policy

- A source that fails validation is dropped; the pool must still satisfy
  per-entity minimums (`project.yaml: min_clips_per_entity`) or QC fails.
- A lock violation at storyboard time tries, in order: another clip of the
  same entity → clip of a co-mentioned entity in the same block → group clip
  of the block's umbrella entity. Nothing else. No images. No silent breaks.
- Any QC assert failure aborts the Release.
