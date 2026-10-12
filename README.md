# last stop yt engine

**One command. One repo. One finished documentary.**

`last stop yt engine` is a config-driven, fully autonomous documentary production
system. You give it a topic — *"build a documentary on Jennie Kim"* — and it runs
the entire cycle inside this repo, on GitHub Actions, with zero external AI calls
during production:

```
research → script → source videos → character-lock extraction →
smart editing → edge-tts narration → music → render → QC → YouTube-ready MP4
```

The first production run is **`projects/blackpink-no-next/`** — *"Why There Will
Be No Next BLACKPINK"* — a 34-minute ultra documentary.

---

## The hard rules (never negotiable)

1. **NO IMAGES. EVER.** Every frame of the final cut is moving footage. The
   renderer hard-fails if any visual slot is not a video clip. No stills, no
   Ken Burns, no slideshow. (Reference face photos exist *only* as internal
   detection tooling — they are never rendered.)
2. **CHARACTER LOCK.** If the narration says *Jennie*, Jennie is on screen.
   If it says *BLACKPINK*, BLACKPINK is on screen. Every visual slot is bound
   to a face-verified clip of the entity being talked about, and the QC gate
   rejects the render if any slot breaks the lock.
3. **REAL FOOTAGE ONLY.** All visuals come from real, sourced video
   (official MVs, performances, interviews) pulled by the sourcing ladder.
4. **RESEARCH LIVES IN THE REPO.** Every project's research, script, storyboard
   and provenance manifest are committed artifacts — not chat history.
5. **SPEC: 1920×1080 · 30 fps · H.264 · AAC 192k 48 kHz stereo · −14 LUFS ·
   faststart.** QC asserts every number before release.

The full doctrine: [`SYSTEM_RULES.md`](SYSTEM_RULES.md) ·
architecture: [`ENGINE.md`](ENGINE.md) ·
absorbed knowledge: [`learnings/`](learnings/).

---

## How to use it

```bash
# The only command there is:
python -m engine.cli build projects/blackpink-no-next
```

Runs every stage in order, resumable (`.done` markers per stage), safe to
re-run after interruption. On GitHub Actions the same command is the whole
pipeline — dispatch `build-documentary.yml`, get a Release with `final.mp4`.

### Adding a new documentary

```bash
cp -r projects/_template projects/jennie-kim
# 1. projects/jennie-kim/project.yaml   — topic, target runtime, entities
# 2. projects/jennie-kim/research/      — hardened research notes + citations
# 3. projects/jennie-kim/script/script.md — narration blocks + on_screen tags
# 4. projects/jennie-kim/sources.yaml   — source video manifest
# 5. git push, dispatch the workflow. Walk away.
```

## System lineage (absorbed, hardened, credited)

| Capability | Learned from |
|---|---|
| Character-locked clip extraction | [`ansaribilal14/character-clip-extractor`](https://github.com/ansaribilal14/character-clip-extractor) |
| Video sourcing ladder | [`Bilal140202/ytagent`](https://github.com/Bilal140202/ytagent), `ttagent`, `igagent`, `xthread-agent` |
| Orchestration discipline | [`ansaribilal14/personal-social-agent`](https://github.com/ansaribilal14/personal-social-agent), [`ansaribilal14/uaal`](https://github.com/ansaribilal14/uaal) |
| Render core (resumable 3-phase, loudnorm, captions) | [`superz1402/ahyeon-documentary`](https://github.com/superz1402/ahyeon-documentary) |
| Entity-timed editing intelligence | [`superz1402/vfactory`](https://github.com/superz1402/vfactory) (`s4_smart.py`) |
| Stage artifact contracts S0–S9 | [`superz1402/documentary-agent-kit`](https://github.com/superz1402/documentary-agent-kit) |
| Motion & pacing doctrine | [`superz1402/opuscar-studio`](https://github.com/superz1402/opuscar-studio) |
| Verification law ("pixels are proof") | [`ChatCut-Inc/agent-plugin`](https://github.com/ChatCut-Inc/agent-plugin) |
| State-machine + fresh-reviewer patterns | [`edenfunf/reelmimic`](https://github.com/edenfunf/reelmimic) |
| Fallback documentary mode | [`superz1402/somerton-man-documentary`](https://github.com/superz1402/somerton-man-documentary) |
| Promo/shorts factory | [`superz1402/promos`](https://github.com/superz1402/promos) |
| Acquisition validation contract | [`superz1402/imgagent`](https://github.com/superz1402/imgagent) |
