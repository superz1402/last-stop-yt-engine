# SYSTEM RULES — hardened law of this engine

These rules are **load-bearing**. Engine code enforces them mechanically. A
stage that violates a rule does not warn — it **fails the build**.

---

## R1 — THE NO-IMAGE RULE (absolute)

The final video contains **zero still images**. Not one frame.

- Every visual slot in `timeline.json` MUST have `kind: "video"`.
- `render.py` raises `NoImageViolation` if `kind != video` and
  `project.rules.allow_images` is `false`.
- No Ken Burns over stills. No generated "cover art" shots. No slideshow
  montage. If there is no moving footage for a moment, the engine uses moving
  footage of a related entity — never a still.
- **Internal exception (tooling only):** face-reference photos exist inside
  `refs/` for the *detection* stack (InsightFace centroids). They are inputs
  to face recognition, never rendered content. The renderer cannot load them.

> Why: this system was built by people who hate the AI-slideshow look.
> A documentary of real people is made of real footage. Hard rule.

## R2 — CHARACTER LOCK (narration ↔ picture binding)

Every narration block carries `on_screen: [entities]`. Every visual slot
inherited from that block MUST be a clip whose tagged entity resolves into the
block's entity set (see `projects/*/entities.yaml` for the resolution graph).

- The `storyboard` stage refuses to place a clip outside the block's entity set.
- The `qc` stage recomputes the lock from the final timeline and fails the
  build on any violation. **Lock coverage must be 100%.**
- Detection basis: InsightFace 512-d embeddings, cosine match, per-character
  centroids built from verified reference frames (`engine/refs.py`).
- Multi-member entity sets (e.g. `blackpink:group`) accept any member or the
  group shot.

## R3 — RESEARCH LIVES IN THE REPO

`projects/<slug>/research/` is committed before scripting starts. Facts carry
source URLs and dates. Claims that cannot be sourced are cut, hedged, or
framed as interpretation. The script stage may only narrate facts present in
the research artifact. This makes every film auditable after the fact.

## R4 — SOURCING LADDER (videos only)

Order of preference for every visual need:

1. **Subject-official video** (official MV / performance / interview of the
   entity being discussed) — downloaded via the ytagent-derived ladder.
2. **Verified community/press footage** of the subject event.
3. **Related-entity footage** explicitly declared in `entities.yaml`
   (e.g. YG story → 2NE1/BABYMONSTER footage).
4. If nothing fits: restructure the beat. **Never fall back to images.**

Download validation (from `imgagent`/`ytagent` doctrine): magic bytes,
ffprobe stream check, duration > 0, minimum resolution gate. Failed sources
are dropped and logged — the engine never ships a broken clip.

## R5 — VOICE

- Narration: **edge-tts** (offline-grade, deterministic). Default doc voice:
  `en-US-AndrewMultilingualNeural` at documentary pace.
- Every block's VO is synthesized separately, measured with ffprobe, and the
  timeline is **gap-calibrated** so the finished film hits its target runtime
  exactly (±1 s).
- Narration and picture are cut to the same clock: slot length is derived from
  the block's measured VO duration, not from vibes.

## R6 — OUTPUT SPEC

1920×1080 · 30 fps · H.264 (yuv420p, faststart) · AAC 192 kbps 48 kHz
**stereo** · −14 LUFS integrated / −1.5 dBTP · captions burned in.
QC asserts all of it with ffprobe before a Release can be cut.

## R7 — EDITING DOCTRINE (from vfactory + opuscar + reelmimic)

- **Entity-timed cuts:** when an anchor word lands ("BLACKPINK", "Ahyeon"),
  the corresponding entity is already on screen — slots are planned per block,
  and the block's first slot leads with the block's subject entity.
- **Variety law:** never the same source video twice in a row; average shot
  length ≤ 8 s; ≥ 6 cuts/minute of narration.
- **Continuity:** within a block, alternate group↔member framing; don't
  return to a source clip within 6 slots.
- **The screen is never blank** (opuscar law): every millisecond has moving
  footage or intentional black beat — and black beats never carry narration.

## R8 — RESUMABILITY

Every stage writes `.done` markers with artifact hashes. A killed run resumes
where it stopped — on a laptop or on Actions. No stage re-does paid work.

## R9 — PROVENANCE

`sources.yaml` records URL, channel, and role for every source. The QC report
lists every source used. Takedowns are a maintenance operation, not a mystery.

## R10 — ONE COMMAND

`python -m engine.cli build <project>` is the entire system. No stage is
invoked manually in production. If it can't be run by one command, it's not
part of the engine.

---

## Enforcement map

| Rule | Enforced in |
|---|---|
| R1 | `engine/render.py` (`NoImageViolation`), `engine/rules.py` (timeline audit) |
| R2 | `engine/storyboard.py`, `engine/qc.py` (`lock audit` section of QC report) |
| R3 | `engine/script.py` (research artifact must exist & parse), project template |
| R4 | `engine/source.py` (validation ladder), `engine/storyboard.py` (fallback ladder) |
| R5 | `engine/voice.py`, `engine/storyboard.py` (gap calibration) |
| R6 | `engine/qc.py` (spec asserts) |
| R7 | `engine/storyboard.py` (variety/ASL validators) |
| R8 | `engine/cli.py` (`.done` markers) |
| R9 | `sources.yaml` schema + `engine/qc.py` provenance report |
| R10 | `engine/cli.py` |
