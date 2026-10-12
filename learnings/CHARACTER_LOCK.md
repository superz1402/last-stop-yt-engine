# CHARACTER LOCK — the narration ↔ face binding system

Origin: `ansaribilal14/character-clip-extractor` (CCE) — full annex:
`annex-R1-sourcing-and-character.md`. This engine re-implements the proven
core as `engine/extract.py` with one critical upgrade: **multi-character
detection in a single pass per video** (CCE detects per character, 4× the
CPU for a 4-member group).

## The proven algorithm (CCE, kept 1:1)

1. **Normalize** losslessly → `max_height 1080`.
2. **Shot detection** — PySceneDetect ContentDetector.
3. **Face pass @2 fps** — InsightFace `buffalo_l` on CPU, det size 640×640,
   faces ≥ 80 px, 512-d embeddings, per-frame JSONL (`analysis.jsonl`,
   frame-level resume).
4. **Match vs centroid** — cosine, threshold **0.42** (idol-tuned).
5. **RAW visibility** — bridge gaps ≤ 1 s, drop segments < 1 s.
6. **Scene grouping** — evidence-based: merge groups ≤ 3.0 s apart, hard
   blocks at gap > 12 s or > 2 shot cuts → `grouped_scenes.json`
   `{start, end, confidence, visibility_ratio}`.
7. **Export** — CRF16 / AAC-192k padded windows + duration-parity QC.

## Centroid acquisition (how the engine knows who is who)

- **Solo-MV bootstrap** (`engine/refs.py`): the member's own solo MV
  (SOLO, LALISA, FLOWER, On The Ground…) contains one dominant face. Sample
  frames evenly (skip first/last 15 s), embed, greedy-agglomerate
  (cosine 0.45), keep the dominant cluster, drop outliers > 0.35 from the
  cluster median, save 12–24 verified ref jpgs + centroid. Solo dominance is
  the identity grounding — no hand-labeled photos needed, ever.
- **Vendored refs** — BABYMONSTER's 7 members ship with CCE
  (`references/<member>/*.jpg`, copied to `engine/refs_builtin/`), used when a
  group's members must be split from group content that predates solo work.
- **Group-pure sources don't need faces**: an official BLACKPINK MV contains
  only BLACKPINK → scene mode suffices for group-entity blocks.

## Why single-pass matters

Group of 4 × 6 MVs × ~3.5 min ≈ 84 min of video. CCE-per-character =
4 detection sweeps. Single-pass = 1 sweep, classify every detected face
against all centroids simultaneously. On a 4-core runner: ~25 min vs
~100 min. This is the difference between a workflow that fits in a runner
timeout and one that doesn't.

## Failure modes & guards

| Mode | Guard |
|---|---|
| Similar-looking idols cross-match | threshold 0.42 + per-entity `min_confidence` in `sources.yaml`; optional `blocklist_refs` |
| Heavy styling (wigs/makeup) shifts embedding | centroid from solo MVs captures canonical identity; outlier rejection at bootstrap |
| < 1 s appearances missed @2fps | acceptable: sub-second slots are unusable anyway (min slot 2.5 s) |
| Detection finds zero faces (wide shots) | shot still usable as `group` clip if source is entity-pure |
