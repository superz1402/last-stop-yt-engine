# EDITING DOCTRINE — how the storyboard thinks like an editor

Distilled from `vfactory` (`s4_smart.py` + AGENT.md + DESIGN_V2 numeric
gates), `opuscar-studio` (MOTION-CRAFT), `reelmimic`, `ChatCut agent-plugin`,
`documentary-agent-kit`. Full annex: `annex-R2-studio-systems.md`.

## The vfactory insight (the seed of character-lock editing)

> Cut **0.30 s before the anchor word**. When narration says "BLACKPINK",
> BLACKPINK must already be on screen — the cut leads the word, it doesn't
> chase it.

This engine operationalizes it at the *block* level: every narration block is
tagged `on_screen: [...]`, and its first slot **leads with the subject
entity**, followed by variety within the entity set.

## Numeric gates (from vfactory DESIGN_V2, adopted as QC asserts)

| Gate | Value |
|---|---|
| Average shot length (ASL) | ≤ 8 s |
| Cuts per narration minute | ≥ 6 |
| Same source twice in a row | forbidden |
| Return to a source within | ≥ 6 slots |
| Slot length range | 2.5–8 s |
| Screen blank while narration plays | never |

## opuscar MOTION-CRAFT (applied via clip selection)

- Every cut needs a **carrier** (motion in the incoming clip — MV choreo,
  camera moves). Prefer clips whose frames move; face-pass clips with high
  `visibility_ratio` and shot-change boundaries naturally carry motion.
- Ease and rhythm: alternate wide group shots with member closeups —
  the "breathing" pattern of concert films.

## reelmimic: fresh-reviewer rule

The storyboard builder and the QC lock-audit are **separate code paths**. The
builder places; the auditor re-derives entity compatibility from the final
timeline + clips.json independently. A builder bug cannot self-certify.

## ChatCut verification law

> "A successful mutation is not visual proof until pixels are inspected."

Hence `qc.py` runs ffprobe on the **final mp4** (not intermediates) and
`freezedetect` to prove no still-image behavior crept in (R1).

## documentary-agent-kit artifact contracts

Stages emit named artifacts (`00_brief` … `12_publish`); later stages consume
artifacts, never chat history. This engine's `build/*.json` chain implements
it; `ENGINE.md` is the contract table.
