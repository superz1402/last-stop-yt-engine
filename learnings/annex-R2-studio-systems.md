# R2 — Studio & Editing Repos: Technical Synthesis

Task ID: 2-b · Agent: R2-studio-research · Read-only analysis
Clones: `/home/z/my-project/research/clones/` (shallow, depth 1, no pushes)

Repos analyzed (10): `superz1402/ahyeon-documentary`, `superz1402/documentary-agent-kit`,
`superz1402/opuscar-studio`, `superz1402/vfactory`, `superz1402/films`,
`superz1402/somerton-man-documentary`, `superz1402/promos`, `superz1402/imgagent`,
`edenfunf/reelmimic`, `ChatCut-Inc/agent-plugin`.

**Goal of the consumer**: `last-stop-yt-engine` — config-driven, one-command autonomous
documentary engine. 30–40 min, 1080p, **videos only (no still images in final output)**,
narration **character-locked to visuals**.

---

## 1. `superz1402/ahyeon-documentary` — THE CORE PIPELINE (deep dive)

### 1.1 Purpose & verdict

The proven end-to-end system: one GitHub Actions click turns a fact-gated script into a
29:00.0 exact, 1080p30 H.264+AAC, −14 LUFS YouTube documentary released as a GitHub
Release asset (`v1.0`, 211 MB, QC PASS). 67 narration beats / 8 acts / 4,231 narration
words. This repo **is** the reference implementation for stages S5–S7 of
last-stop-yt-engine. Its gaps vs the new engine: (a) visuals are mostly Ken-Burns-animated
*still images* (exactly what we must eliminate), (b) cut placement is gap-calibration, not
word-locked (vfactory solves this), (c) no thumbnail/publish stage.

### 1.2 Repo map (exact paths)

```
ahyeon-documentary/
├── README.md                       # system description ("this repo IS the studio")
├── docs/INTEGRATIONS.md            # MPT + ytagent integration guide + live test log
├── .github/workflows/
│   ├── render.yml                  # one-click film render → QC → Release v1.0
│   ├── remux.yml                   # post-hoc audio remux (48k stereo) + asset replace
│   ├── shorts.yml                  # MoneyPrinterTurbo 3× vertical shorts → release
│   └── yt-download-farm.yml        # remote yt-dlp worker (WARP + BGutil POT, 6-tier ladder)
├── pipeline/                       # 17 scripts, all standalone python3, no framework
│   ├── tts.py  source_media.py  mpt_bridge.py  ytagent_bridge.py
│   ├── build_cards.py  build_timeline.py
│   ├── render.py  render_final.py  audio_assemble.py  normalize_audio.py
│   ├── qc.py  qc_fast.py  qa_nim.py
│   ├── shorts.py  mpt_bridge.py  ytagent_bridge.py
│   └── expand_script.py  expand_script2.py     # manual beat-insertion (duration trims)
├── project/
│   ├── script.json                 # ← master creative config (67 beats)
│   ├── timing.json  timeline.json  captions.ass  metadata.json
│   ├── media_manifest.json         # license ledger (57 images + music + video slots)
│   ├── subject_sources.json        # curated YouTube subject-clip wishlist
│   ├── qc_report.json  nim_qa.json  render.log
│   └── cards/ facts/ media/ music/ voice/     # generated/downloaded artifacts
└── integrations/MoneyPrinterTurbo  # pinned submodule @4204d0f (shorts only)
```

### 1.3 `project/script.json` — the creative config schema (verbatim keys)

```json
{
  "title": "JUNG AHYEON — The One Who Was Worth the Wait",
  "slug": "...", "language": "en",
  "voice": "en-US-AndrewNeural",
  "target_total_s": 1740,          // duration is a promise, calibrated to the second
  "fps": 30, "width": 1920, "height": 1080,
  "brand": {...},
  "fonts": {"display": ".../NotoSerifSC-SemiBold.ttf",
            "display_black": ".../NotoSerifSC-Black.ttf",
            "body": ".../DejaVuSans.ttf"},
  "lexicon": {"Ahyeon": "AH-hyun", "Chuncheon": "CHUN-chon", "MONSTIEZ": "MON-steez",
              "Kyocera": "KEE-oh-seh-rah", "BABYMONS7ER": "BABY-MON-SEVEN-ER", ...},
  "cold_open_pause_s": ..., "beat_gap_s": 0.55,
  "intro_music_s": 8.0, "outro_music_s": 22.0,
  "segments": [                     // 9 segments = 8 acts + cold open
    {"id": "seg0", "act": "COLD OPEN", "chapter_title": "The One Who Was Missing",
     "beats": [
       {"id": "b001",
        "narration": "On November 27th, 2023, a K-pop debut broke the internet. ...",
        "pause_after": 0.6,                     // breathing gap after this beat
        "on_screen": ["22,590,104 views — first 24 hours", "NOVEMBER 27, 2023"],
        "visuals": [
          {"kind": "image", "query": "seoul night city neon skyline"},
          {"kind": "card", "card": "stat", "kicker": "THE RECORD",
           "big": "22.59M", "small": "views in 24 hours — most-viewed K-pop debut MV ever"}
        ]}
     ]}
  ]
}
```

Beat `visuals[].kind` ∈ `image | card | (video)`; card subtypes handled by
`build_cards.py`: `title | chapter | stat | quote | timeline | credits` (+ per-act
`ambient` cards). This is the schema last-stop-yt-engine should keep but with
`kind:"image"` **deleted** and `kind:"video"` mandatory.

### 1.4 `pipeline/tts.py` — narration (exact interface)

```python
# Batch TTS via edge-tts CLI; resumable (skips mp3 >1000 B); 4 attempts, 2*(n+1)s backoff.
# lexicon applied by word-boundary regex BEFORE synthesis:
def ttsify(text):
    for k, v in LEX.items():
        text = re.sub(rf"\b{re.escape(k)}\b", v, text)
    return text

# per beat:
subprocess.run(["edge-tts", "--text", ttsify(b["narration"]), "--voice", VOICE,
                f"--rate={RATE}", "--write-media", mp3, "--write-subtitles", srt])
# RATE = "-3%"; VOICE from script.json (en-US-AndrewNeural)
# duration measured via: ffprobe -show_entries format=duration -of csv=p=0
# outputs project/voice/beat_<id>.mp3 + .srt  →  project/timing.json:
# {"beats": [{"id","file","srt","duration_s","pause_after","provider":"edge-tts"}],
#  "total_s": <sum>}
```

Key design point: **edge-tts emits its own SRT per beat**, which becomes word-chunk
caption timing downstream. 0.35 s sleep between calls = rate-limit hygiene.

### 1.5 `pipeline/build_timeline.py` — the EDL/storyboard builder

Signature surface: reads `script.json` + `timing.json` + `media_manifest.json`;
writes `timeline.json`, `captions.ass`, `metadata.json`.

- **Gap calibration to hit the exact runtime** (the trick that landed 29:00.0):
  ```python
  scale = (TARGET - INTRO - OUTRO - sum(speech)) / sum(base_pauses)
  scale = max(0.4, min(2.6, scale))     # clamp; actual run: gap_scale 1.944
  ```
- **Asset assignment**: `video_for(query, used)` prefers `kind:"video"` manifest entries
  (queried first, then any video); `asset_for(query, used)` falls back to images; any
  asset reused **max 2×** (`used.get(key,0) < 2`); missing files are dropped (fresh-clone
  safety); `USE_VIDEOS=0` env disables video slots.
- **Beat duration = voice + scaled pause**, split across visuals with `min 2.4 s` each,
  renormalized to the beat; Ken Burns modes cycle `["in","out","left","right"]`.
- **timeline.json (the storyboard schema — verbatim)**:
  ```json
  {"target": 1740, "actual": 1740.0, "fps": 30, "w": 1920, "h": 1080,
   "intro_music_s": 8.0, "outro_music_s": 22.0, "gap_scale": 1.944,
   "music": "project/music/bed.mp3",
   "clips": [{
     "beat_id": "b001", "seg": "seg0",
     "start": 8.0,            // absolute film seconds (cursor-accumulated)
     "dur_s": 20.078,         // voice + pause
     "voice_s": 18.912,
     "voice": "project/voice/beat_b001.mp3",
     "visuals": [{
        "kind": "image|video|card",
        "path": "project/media/img001.jpg",
        "asset_id": "img001", "license": "CC:BY-SA 2.0",
        "artist": "mattk1979", "credit": "flickr",
        "origin_url": "https://www.flickr.com/...",
        "title": "Seoul city skyline at night from Namsan Mountain",
        "dur_s": 10.039, "kb": "in"          // kb omitted for kind:video
     }],
     "on_screen": ["22,590,104 views — first 24 hours", "NOVEMBER 27, 2023"]
   }]}
  ```
- **captions.ass**: parses each beat's edge-tts SRT (`parse_srt(path, offset)`), offsets
  by `clip.start`, clamps to voice end (`min(t1, start+voice_s)`), emits
  `{\fad(140,140)}` events in style `Cap` (DejaVu Sans 46, ivory on charcoal outline) —
  plus `Receipt` style (Noto Serif SC 44, gold) events for `on_screen` lines, distributed
  across the beat: `t0 = start + 0.45 + (dur_s-1.2) * (i/n)`.
- **metadata.json**: title, ≤4900-char description with `CHAPTERS` (mm:ss + act + title),
  `SOURCES`, `MUSIC & IMAGE ATTRIBUTIONS` (built from the manifest → auto-credits),
  tags, `category_id:"24"`, `privacy_status:"unlisted"`.

### 1.6 `pipeline/build_cards.py` — visual identity system

Pillow generator, 1920×1080, brand `(10,10,10)` bg + `(201,168,76)` gold + ivory.
Reusable primitives: `tracked()` (per-char letter-spacing), `wrap()` (measured word wrap),
`rule()` (gold rule), cached `vignette()`. Card factories with fixed composition geometry:
`card_title(kicker,title,subtitle)` / `card_chapter(act,title)` / `card_stat(kicker,big,small)`
(auto-shrinks big numeral 210→90 px to fit 1700 px) / `card_quote(quote,attr)` (gold
left-bar) / `card_timeline(date,event)` / `card_credits(lines,note)` / `card_ambient(act,
variant)` (procedural concentric gold arcs — a generative texture, not a photo).

### 1.7 `pipeline/render.py` — the renderer (Phase 1/2/3, resumable)

```python
BASE = dirname(dirname(abspath(__file__))); os.chdir(BASE)   # all paths repo-relative
tl = json.load(open("project/timeline.json")); FPS, W, H = tl["fps"], tl["w"], tl["h"]
TOTAL = tl["actual"]; SEGS = "project/segments"; PRESCALE = 2160   # zoom headroom

def run(cmd, tag=""):                    # fail-loud subprocess wrapper (stderr tail 600)

def kb_filter(mode, dur, fade_in=True, fade_out=False):
    # zoompan on a 2160-prescaled crop; d=1 per-frame zoom expressions:
    #   in:  z = 1+0.10*(on/frames-1)     out: z = 1.10-0.10*(on/frames-1)
    #   left/right: z=1.09, x pans 60% of slack, y centered
    f = f"scale={PRESCALE}:-2,crop={PRESCALE}:{int(PRESCALE*H/W)},"
        f"zoompan=z='{z}':x='{x}':y='{y}':d=1:s={W}x{H}:fps={FPS}"
    f += ",eq=contrast=1.03:saturation=1.05"
    f += ",fade=t=in:st=0:d=0.28" (+ fade out st=dur-2.6 d=2.6 when last-of-film)

def seg_out(name, dur, filt, source_args):   # RESUMABLE: skip if <name>.done exists;
    # tmp.mp4 → os.replace → .done marker; -frames:v int(dur*FPS); x264 veryfast crf20
```

- **Phase 1**: `seg_intro` (ambient card, 1.4 s black-fade-in) → per clip per visual:
  `kind=="video"` → `scale/crop 1920×1080, fps, eq`, **`-stream_loop -1 -t dur`** (loop
  footage shorter than slot), no Ken Burns; `kind=="image"` → `kb_filter(...)`;
  `kind=="card"` → Ken Burns on card PNG. `seg_outro` = lavfi black.
- **Phase 2**: concat demuxer over `segments/list.txt` → `project/master_video.mp4`
  (`-c copy`), skipped if file >10 MB.
- **Phase 3** (single big ffmpeg): inputs = master + looped `bed.mp3` + 67 voice mp3s;
  filtergraph:
  ```text
  [N:a]aresample=48000,adelay={ms}|{ms}[vN]                       # per voice
  [v0..v66]amix=inputs=67:normalize=0,volume=1.0,aresample=48000,apad=whole_dur=TOTAL[voice]
  [1:a]aloop=loop=-1:size=2e9,atrim=0:TOTAL,aresample=48000,volume=0.32,
       afade=t=in:st=0:d=2.5,afade=t=out:st=TOTAL-4:d=4[bed]
  [voice]asplit=2[sc][vmix]                                        # ASPLIT LAW!
  [bed][sc]sidechaincompress=threshold=0.015:ratio=7:attack=120:release=700[bedd]
  [vmix][bedd]amix=inputs=2:normalize=0,loudnorm=I=-14:TP=-1.5:LRA=11[aout]
  ```
  video: `-vf ass=project/captions.ass,tpad=stop_mode=clone:stop_duration=45`,
  `-c:v libx264 -preset veryfast -crf 21 -c:a aac -b:a 192k -ar 48000 -ac 2
  -movflags +faststart -t TOTAL` (the `-ar/-ac` were the v1.0 post-fix — mono 96 kHz
  leak otherwise).

`pipeline/render_final.py` is the 2-core-friendly alternative: three resumable steps
`audio|beats|mux` with a **470 s per-call budget**; `beat_ass(clip)` rewrites per-beat
shifted ASS files (re-bases Dialogue timestamps to beat-local); per-beat caption burn
re-encodes only that beat (`crf 21`), then mux `-c copy` — the pattern to copy for CI
where a single 29-min encode risks job limits.

### 1.8 Music approach

Not composed — **sourced + mixed programmatically**:
1. `source_media.py` searches Openverse **audio** (`license=cc0`) with
   `["ambient cinematic drone", "cinematic ambient pad", "ambient atmosphere dark"]`
   → downloads first hit to `project/music/bed.mp3`, ledger entry `music01`.
2. Mixed at **0.32 gain, sidechain-ducked** under the voice bus
   (`threshold=0.015 ratio=7 attack=120 release=700`), 2.5 s fade-in / 4 s fade-out.
3. Loudness: two paths — ffmpeg `loudnorm=I=-14:TP=-1.5:LRA=11` in render.py, or the
   numpy twin `normalize_audio.py` (chunked 2-pass, flat-RMS LUFS proxy `20log10(rms)−0.691`,
   tanh soft-knee at −1.5 dBTP ceiling).
4. `audio_assemble.py` = pure-numpy alternative mixer: decodes each voice via
   `ffmpeg -f s16le -ac 1 -ar 48000`, places at clip starts, 250 ms box-filter voice
   envelope, bed gain `0.32*(1-0.78*env)` → duck to ~22 % under speech.

### 1.9 Sourcing layer

- `source_media.py`: `commons_search(q, n=6)` (MediaWiki `generator=search`,
  `gsrnamespace=6`, `iiurlwidth=1920`, `extmetadata` → LicenseShortName, rejects
  fair-use + SVG + <900×600) + `openverse_search(q, n=6)`
  (`license_type=commercial&mature=false`, ≥1000×650); cap 3 per query; descriptive
  User-Agent; manifest schema:
  `{"asset_id","kind","query","source","title","origin_url","local_path","license","artist","credit","w","h"}`.
- `mpt_bridge.py` (video upgrade): env-gated `ENABLE_MPT_STOCK=1` + `PEXELS_API_KEY` /
  `PIXABAY_API_KEY`; `pexels_videos(q,key,n=6)` picks HD mp4 nearest 1920 wide,
  `pixabay_videos(q,key,n=6)` large→medium→small; `MAX_PER_QUERY=2`, `MAX_CLIP_S=12`;
  `normalize(src,dest,dur_s)` = scale/crop 1080p30 + eq + `-an` (audio stripped!);
  **checkpoint per query** (manifest rewritten after each query — crash-safe).
- `ytagent_bridge.py` (subject footage): reads `subject_sources.json`
  (`{video_id,label,credit,segments:[{start_s,dur_s≤10,query}]}`); download ladder =
  ytagent *library mode* (`Orchestrator(TruthAgent, Verifier).download(video_id, out,
  opts)` with `github_workflow="yt-download-farm.yml"` farm opts) → `ytagent` CLI →
  local cache; `normalize_cut()` cuts silent 1080p segments; manifest license string
  literally encodes the policy: `"Subject clip — rights of owner; fair-use documentary
  commentary — REVIEW BEFORE MONETIZED PUBLISH"`.

### 1.10 QC & fact gates

- `qc.py`/`qc_fast.py` checks: duration ±45 s, 1920×1080, fps 30, h264, aac, size
  100 MB–3 GB, loudness (full loudnorm JSON or 4×60 s sampled windows, −18..−10 band),
  plus **subject_clip_policy** (auto-publish block if any `source=="youtube_subject"`).
- `qa_nim.py`: NVIDIA NIM chat (`nvidia/nemotron-3-super-120b-a12b`, temp 0.2) with
  dossier + all narration → JSON `{unsupported:[{beat_id,claim,problem}],
  slop:[{beat_id,phrase}], tone_score, notes}` — the fact/slop audit to keep.
- `qc_report.json` (verified in repo): all PASS, `sampled avg −14.7 LUFS-ish`.

### 1.11 GitHub Actions structure

- **render.yml** — `workflow_dispatch` only (push-trigger full rebuilds were disabled
  after a costly accident); `ubuntu-latest`, `timeout-minutes: 350`, `permissions:
  contents: write`; steps: apt ffmpeg + `fonts-noto-core fonts-dejavu-core` →
  setup-python 3.11 → `pip install pillow` (deps deliberately minimal) → **bridges
  (secrets-gated, clean-skip)** → `build_timeline.py` (deterministic rebuild) →
  `render.py` → `qc.py` → upload-artifact (retention 7) → `softprops/action-gh-release@v2`
  attaching `project/final.mp4` to tag `v1.0` with description body. **No caching of
  ffmpeg/pip** (job is one-shot; cache would be the easy win).
- **remux.yml** — release-asset surgery pattern: `gh release download v1.0` →
  `-c:v copy` + `aresample=48000,aformat=channel_layouts=stereo` → python QC asserts
  (duration drift <1 s, h264/1080p, aac 48 k stereo) → `gh release delete-asset` +
  `upload --clobber` + PATCH asset name back to `final.mp4`.
- **shorts.yml** — `push` paths (`pipeline/shorts.py`, `integrations/**`) + dispatch;
  `submodules: recursive`; stages CC0 bed into `integrations/MoneyPrinterTurbo/storage/bgm/`
  (MPT only reads BGM from its own dir); `shorts.py plan` (deterministic material
  selection printout) then `render` → per-short QC assert (1080×1920 h264+aac, 25–90 s)
  → release `shorts-v1`.
- **yt-download-farm.yml** — `workflow_dispatch` inputs `video_url`/`video_id`; installs
  Cloudflare **WARP** (`mode proxy`, 127.0.0.1:40000) on Azure egress, `yt-dlp` +
  **BGutil POT provider** (PO tokens), 6-tier client ladder (embedded → tv → mweb/web →
  web_safari → default), uploads artifact + release `vid-<id>`. This is the reusable
  bypass farm for any subject-footage need.

### 1.12 Reusable-for-engine checklist (ahyeon)

Keep as-is: script.json schema (drop `image` kind), tts.py lexicon+resumable batch,
gap-calibration math, timeline.json schema, ASS caption+receipt generator, zoompan
video-slot renderer (`-stream_loop`), the whole Phase-3 audio graph, card factory,
QC battery, render.yml skeleton, farm workflow. Change: replace image slots with the
vfactory smart director (§4); source video-first (mpt_bridge + farm + Mixkit); add
thumbnail + publish stages.

---

## 2. `superz1402/documentary-agent-kit` — the stage/skill contract (14 files)

### 2.1 What it is

The *codified operating system* of the pipeline: `AGENTS.md` orchestrator + 9 SKILL.md
stages (S0-intent, S1-research-facts, S2-write-script, S3-source-media, S4-gen-voiceover,
S5-assemble-timeline, S6-captions-meta, S7-render-qc, S8-publish-youtube) + 2 Claude
subagents (`.claude/agents/fact-researcher.md`, `media-scout.md`) + `scripts/run_stage.py`
+ `scripts/validate_artifacts.py` + 3 workflows + example `production/ahyeon/` artifacts.

### 2.2 Hard rules from AGENTS.md (all belong in last-stop-yt-engine)

1. **Fact gate** — narration may only reference `02_facts.md` VERIFIED/PUBLISHED facts;
   `[UNVERIFIED]` forbidden in narration.
2. **License gate** — only assets with a recorded license field may enter the timeline;
   strip embedded audio from all downloaded video.
3. **Approval gates** — pause after S2 (script) and S7 (QC) unless "fully automatic".
4. **Artifacts are contracts** — each stage validates input existence, writes valid JSON
   before exit, never deletes prior artifacts; resumable (skip stage whose artifact
   exists & validates).
5. **Render resumability** — per-beat segments; re-render only changed beats; concat
   `-c copy`.

### 2.3 Artifact chain (the numbering is already canonical)

```
00_brief.json (S0) → 02_facts.md (S1) → 03_script.json (S2) → 04_media_manifest.json (S3)
→ 05_voice/timing.json (S4) → 06_timeline.json (S5) → captions.ass + thumbnail.png +
07_metadata.json (S6) → final.mp4 + 08_qc_report.json (S7) → 09_publish.json (S8)
```

`scripts/run_stage.py` dispatch table (`ORDER = [(stage, module, artifact), ...]`) with
resumable skip logic; `validate_artifacts.py` enforces required keys per artifact
(`03_script.json→blocks`, `06_timeline.json→scenes`, `08_qc_report.json→checks`,
`09_publish.json→targets`) and fails CI on invalid JSON.

### 2.4 Highest-value skill content

- **S0 brief**: duration_target_s is "a promise: every later stage enforces it (±3%)";
  throughline required ("no throughline, no episode"); style tokens (palette hex, fonts,
  motif) fixed once; `gates: {facts_gate, license_gate, human_approval}`.
- **S2 write-script**: word budget 150 wpm + 8–12 % breathers; one narration paragraph +
  one visual direction per block; **numbers on screen must match the dossier
  digit-for-digit**; cold open must "earn the first 30 seconds: stakes + contradiction,
  no greetings"; explicit ban list ("little did she know", "in a world where", "but
  here's the thing", rhetorical-question stacking); duration enforcement ±3 % — extend
  "with substance, never filler".
- **S4 voiceover**: edge-tts `WordBoundary` events → word-level offsets in timing.json
  (`{"blocks":[{"id","file","duration_s","words":[{"w","t0","t1"}]}]}`); failed block
  fails loudly; drift >5 % returns to S2; fallback ladder piper (offline) → ElevenLabs
  multilingual v2 (hero); one voice per episode.
- **S5 timeline**: scenes with exact `start_s/dur_s` + `visual:{type,ref,kb:{zoom,pan}}`;
  **`breather` scenes (music-only, no narration) absorb duration drift**; license gate
  enforced here.
- **S7 QC gate** (fail the run on): duration ±3 %, loudness −14 ±1 LUFS (ebur128),
  blackdetect (intro/outro only), freezedetect ("no frozen frames > 4 s except
  intentional holds" — the anti-stills check!), caption sync spot-check at 3 beats,
  fact-vs-dossier diff clean, license ledger complete.
- **S8 publish**: GitHub Release default; YouTube resumable `videos.insert` unlisted
  (quota 1600 units ⇒ ≤6/day); storage.to 3-step mirror; `09_publish.json` records
  targets + sha256 provenance; never publish with failing QC or missing credits.
- **Subagents** (frontmatter format worth copying verbatim):
  `fact-researcher` (tools WebFetch/WebSearch/Bash; ≥2 independent sources; living-persons
  rule — no rumors/dating/medical; "minimum 25 VERIFIED facts for a 10-minute script;
  report gaps, never pad with UNVERIFIED") and `media-scout` (rate-limit table: Pexels
  200/hr · Pixabay 100/60 s · Openverse 200/day · Freesound 2000/day; sha256 download
  cache; "A missing license field = asset is invalid"; subject clips ≤6 s/beat,
  `-an`, tagged `FAIR-USE-CLIP (short, narrated, transformed)`; 2+ options per subject
  beat).

**Harden into the engine**: the artifact numbering + validator as CI; the QC gate list
(esp. freezedetect as a no-stills tripwire); the two subagent specs; S0 brief as the
top-level `engine config` format.

---

## 3. `superz1402/vfactory` — topic→video factory + THE CHARACTER-LOCK DIRECTOR

### 3.1 What it does

`python3 vfactory.py "<topic>" --style documentary --minutes 29` → research → script →
TTS → smart scene direction → score → render → deliver (Telegram ≤48 MB / storage.to).
Stage table s1–s8, each checkpointed (`.done_*`), resumable via `--run-dir`.
`telegram_listener.py` = phone front-end (long-poll, prefixes `9:16`, `#hype`, scene
count). Plus `tools/doc_builder/` (the Ahyeon v3 29-min variant) and the v2/v3 long-form
chapter engine: ~2.6-min chapters, word-level timestamps, **entity-aligned hard cuts**
("the screen shows the subject at the moment it is spoken"), per-chapter checkpoints.

### 3.2 `AGENT.md` — 220 lines of earned law (quote-level importance)

> "**Real footage only.** Never compile slideshows of still images." · "Entity-accurate
> footage. The screen shows WHAT the narrator says WHEN they say it." · "Subject-pure
> capture… Other entities appear only when NAMED." · "Never rip the source audio as the
> soundtrack… music bed must be SYNTHESIZED… loudness-normalized." · "No cheap overlays…
> No drawtext captions floating on screen." · "**Do not self-certify quality**… extract
> frames at known narration timestamps and LOOK at them."

**Scene Doctrine span schema** (this is the character-lock contract):
```json
"visual": [
  {"entity": "blackpink_group", "anchor": "BLACKPINK", "clip": "blackpink_group",
   "in_point": 27.8, "note": "screen must show BLACKPINK the moment the word is spoken"}
]
```
- `anchor` = narration word that TRIGGERS the cut; cut placed `LEAD=0.30 s` **before**
  the word is spoken, from **real whisper timestamps, never estimates**.
- `entity` from a fixed vocabulary; every library clip carries entity tags derived from
  its **authoritative source title** (official MV title beats vision guessing).
- `clip` = hard lock (intent-explicit beats); `in_point` = pinned source second.
- Matcher: pinned hints → entity-covering clips → variety (no repeats within last 3);
  same clip back-to-back must **continue** (in_point advances), never replay.
- Pronunciation variants allowed (`["Ahyeon","ahyahn"]`) because TTS pronounces names
  phonetically.

**Render doctrine traps (each cost a build — carry into engine docs)**:
`zoompan` MUST use `d=1` with incremental zoom (`zoom+0.0006`) — `d=frames` expands every
input frame N× (freeze-frames, huge files); shots must be EXACT duration (`-frames:v`) —
any 0.4 s pad × 15 shots = 6 s desync; content-aware caches validate a sidecar
`shot_i.json` (clip+in_point+dur), never duration-only mtime; **ASPLIT LAW**: a bus feeding
BOTH `sidechaincompress` (key) AND final `amix` MUST be `asplit=2` first — label reuse is
accepted by the graph parser but routes all narration into the sidechain only → **silent
voiceover that volume probes miss; only ASR catches it**; **ASR voiceover gate**: extract
1–2 mono 16 k windows post-mux and transcribe — non-empty = pass (code 1214 = >30 s or
not mono); whisper words cached to `words.json` (re-transcribe on resume = drift vs
cached renders); Popen + `start_new_session` + killpg for CLI grandchildren; Telegram 504
= transient, retry ×3; concat demuxer needs absolute paths.

### 3.3 `stages/s4_smart.py` — the smart director (full interface)

```python
GAP = 0.35   # inter-scene silence in narration_full.wav
LEAD = 0.30  # cut this many seconds BEFORE the anchor word

def concat_narration(run_dir):        # scene WAVs + GAP → narration_full.wav + bounds{}
def word_timestamps(wav, cache=None): # faster-whisper "small.en", int8, cpu_threads=4,
                                      # beam_size=3, word_timestamps=True; audio decoded
                                      # via ffmpeg→f32le numpy (PyAV bypass); cached.
def norm(w):                          # alnum-collapse: 'black pink's'→'blackpink'
def find_anchor(words, lo, hi, anchor):
    # join the normalized token window, exact substring first, then fuzzy
    # difflib ratio ≥0.78 (whisper splits 'baby'+'monster' and misspells 'ahyahn');
    # returns the token whose span contains the match start.
def pick_in_point(clip, shot_dur, shot_idx, span_entity):
    # deterministic variety: middle 60% of source (intros/outros are static logos);
    # md5(clip_id:shot_idx:entity) → offset. Never past end.
def match_span(span, scene_id, shot_idx, library, used_recent, hints):
    # 1) span-level clip lock  2) pinned entity hints  3) any entity-covering clip
    # (recency respected)  4) last-resort ignores recency
def build_timeline(run_dir, plan, words, bounds, library):
    # per scene: cut_times=[scene_start] + anchor cuts (skipped if <0.8s from prev,
    # shots <0.6s dropped); spans carry into shots; shots[] = {start,end,dur,narr_start,
    # narr_end,scene,span_index,entity,clip,file,in_point,punch: in|out alternating};
    # last shot +1.2s hold for fade-out. Output: <run>/04_smart/timeline.json.
```

### 3.4 Footage library (`footage/`)

- `sources.json` = curated official uploads (video_id, title, channel, kind, workspace).
- `build_library.py` wraps **character-clip-extractor** (sibling repo): normalize → shot
  detect → InsightFace @2 fps → raw visibility → audio activity → scene grouping, per
  workspace, resumable via sentinels → emits `library.json`:
  ```json
  {"character": "...", "built": "...", "sources": [...],
   "clips": [{"clip_id": "dangerously_eval",
              "file": "/.../xw7Y2gviWbA.mp4", "video_id": "xw7Y2gviWbA",
              "source_title": "AHYEON Dangerously (Last Evaluation solo)",
              "entities": ["ahyeon_solo", "stage_performance"],
              "duration": 146.118, "verified": "title+vision",
              "segment_hints": {"whole": "ahyeon solo studio performance"}}]}
  ```
  "s4 consumes ONLY windows from this library. No image-search, no stock photos, no
  unverified footage can enter the pipeline."

### 3.5 `research/DESIGN_V2.md` — measured documentary benchmarks (hard gates)

Measured from real K-pop documentaries (BPM Stories, KOOKIELIT): **13.1–13.5 cuts/min**,
ASL 4.4–4.6 s, median 2.5–4.0 s, p90 8.0–8.5 s, ≤1 s shots 12–24 %; audio **−10.6 LUFS,
true peak +0.4 dB, ZERO silences >1 s** (wall-to-wall sound); chapters 45–90 s; pacing
arc intro 20.8 cpm → mid 11.8 → tail 6.5 (fast hook, cinematic tail); letterbox 2.35:1
inside 16:9 = instant documentary feel; text rare + serif ("November 15, 2023") + small
source attribution. v1 post-mortem (why it failed): one still per 7.6 s with zoompan =
slideshow; sine-drone music = "weird noises"; giant drawtext captions; no grade; "reported
done without watching the output". **v2 hard gates**: cuts/min ≥ 8 (target 10–16), ASL
≤6 s, **video-source shots ≥60 %** (stills ≤40 % — our engine: 0 %), LUFS [−13.5,−11.5],
TP ≤ −1.0 dB, zero silence >1.2 s, ≤1 text overlay per beat, letterbox+grain+grade.

### 3.6 `stages/s8_qc.py` — QC gate worth porting wholesale

8 checks: resolution/aspect, duration drift ≤1.5 s, dark-frame via sampled mean luma
(PNG frames + PIL — "signalstats YAVG proved unreliable, returned near-black for frames
measuring 150+"), no digital silence >6 s (`silencedetect=noise=-45dB:d=6`), integrated
loudness −16±2.5 LUFS, **narration audibility via ASR on two sampled chunks** (429
retry 60 s/120 s), **footage provenance: every shot `ahyeon_verified` with credit**,
**music provenance: real licensed track, never "synthesized"**. Fails → SystemExit, run
never delivered.

### 3.7 For last-stop-yt-engine

This repo is **the** answer to "narration character-locked to visuals": adopt
`s4_smart.py` (anchor→LEAD cut), `library.json` entity tagging, the ASR+frame-vision
closure protocol, the DESIGN_V2 metric gates, and AGENT.md as the engine's `AGENT.md`
base (it is literally a quality doctrine written from user rejections).

---

## 4. `superz1402/somerton-man-documentary` — the zero-footage, code-drawn doc

15½-min documentary where **every frame is drawn in code** (deterministic SVG/halftone
page rendered headless frame-by-frame via lemo-opuscar), score+foley **synthesized in
numpy**, narration **Kokoro `bm_george` @0.92 verified by faster-whisper (0 mismatches)**.
No video gen, no stock, no photos — "every photograph is a labelled in-frame
reconstruction." Editorial rule: evidence vs speculation enforced **visually** (red
SPECULATION stamps, evidence ledger, "NOT VERIFIED" caveats).

Key schemas/quirks:

- `film/lines.json`: `{"id":"L01","sec":"S1","text":...,"display":"...«1 December 1948»..."
  (guillemet-highlight markup),"vis":"dark dawn, waves, figure at seawall","voice":
  "bm_george","speed":0.92,"asr":"..."}` — the `asr` field is the **expected transcript**
  the verifier checks.
- `film/lock_timeline.py`: hardcoded `SCENES = [(id, sec, [line ids], lead, tail,
  min_dur, cut∈{wipe|hard|fade}), ...]` → computes `timeline.json` (`t0 = cursor`,
  speech placed at lead offsets, `t1 = max(last speech end + tail, t0+min)`) + `cues.json`
  (caption events) + chips/wipes/hits. Per-scene **min_dur** + deliberate silences
  ("silence before TAMÁM SHUD snap") = pacing authored, not derived.
- `film/mix.py`: numpy synth kit — `kick(f0→f1 sweep)`, `pluck`, `bell` (inharmonic
  partials 2.76×/5.4×), `drone(freqs, detune)`, `waves_bed/rain_bed/room_bed` (filtered
  noise), FFT lowpass/bandpass; foley from `events.json` (whoosh/stamp/tick/drawer at
  absolute times, exported by the render page); two-pass loudnorm −14 LUFS.
- `film/build.sh`: `node core/render/events.mjs` → `node core/render/video.mjs --fps 24
  --workers 2` → `mix.py` → `mux.sh` → `srt.py` (cues.json → .srt).

vs ahyeon-documentary: different philosophy — ahyeon = sourced-media assembly; somerton =
**fully generative frame drawing** (license-pure by construction, the ultimate no-stills
fallback); improvements over ahyeon: ASR-verified narration, scene-level min-dur + authored
silences, deterministic single-source-of-truth timeline, evidence/speculation visual
rhetoric. Reusable: numpy music/foley kit, ASR verification step, the display-markup
`«highlight»` convention, evidence-stamp card language.

## 5. `superz1402/opuscar-studio` — motion craft + release convention

Public studio page for lemo-opuscar films (video-002-zodiac 17:23). Two reusable assets:

- **`MOTION-CRAFT.md`** — distilled motion rules: nothing linear except mechanical;
  ease-out entrances (`cubic-bezier(.16,1,.3,1)`), ease-in exits; stagger related
  elements 2–4 frames; **overlap actions** (next element starts before last settles);
  **read time = words/3 + 1 s after animation-in**; let key ideas hold still; 5 %/3.5 %
  title/action safe areas; **every cut needs a carrier** (an on-screen element that leads
  into the next scene; no bare dip-to-black); **the screen never goes blank**; vocabulary
  of 2–3 transition families per film, same cut = same meaning; crossfades only as last
  resort. Directly adoptable as the engine's motion-style prompt/validator rules.
- **Release convention**: per-film tag `video-NNN-<slug>-vMAJOR.MINOR` attaching
  film.mp4 + .srt + poster + thumbnail_1280×720 + chapters.txt + youtube.md + SOURCES.md
  + CREDITS + TREATMENT.md; `render_range.mjs` = resumable range renderer for
  constrained hosts; `films/<slug>/` layout (index.html + timeline.js + lines.json +
  mix.py + build.sh) is a clean per-episode source bundle.

## 6. `superz1402/films` — the output catalog page

Tiny repo = landing page for **vfactory** output ("topic in, documentary out"): film
cards with self-hosted `trailer.mp4` + first-frame posters, and a QC table row per film
(`PASS (5.8 cpm, -13.9 LUFS, voiceover verified)` — cuts/min, loudness, ASR-verified
voice as the *public* quality signal). Reusable: the delivery page pattern + the idea
that **cpm/LUFS/ASR are the canonical QC triple** shown to the world. Trailers are cut
from the film itself (0:41 / 0:17 promo cuts of a 33:11 film).

## 7. `superz1402/promos` — promo/trailer generation approach

Launch videos for every shipped project, built with **brag (latent-spaces/brag) +
Hyperframes**, rendered locally, delivered as GitHub Release assets. Pattern per product
(×7–8 cuts): `main/longer/cinematic/chaotic/detailed/reels(9:16)/producthunt/twitter`.

- **`<product>/brag-plan.md`** — the creative contract: *source grounding* (every claim
  is verbatim copy from the live site bundle — "no invented claims"), *visual identity
  extracted from the site's CSS custom properties* (exact hexes + fonts + "never weight
  700/900 on Archivo Black (ships 400 only)"), *audio system* (3 music tracks with cue
  presets + beat grids, 1–3 locks per video; SFX inventory; audio-reactive RMS "no
  equalizer bars, no waveforms").
- **`<cut>/composition-brief.md`** — scene table (`hook 4.5s / stats 4.0s / d1 5.0s /
  quote 4.5s / outro 4.0s`), poster pick timestamp (baked as frame 0), determinism rules
  ("ambient tweens only, finite yoyo cycles; no tl.call (v0.8.141 TDZ bug workaround)").
- **`<cut>/share-copy.txt`** — platform caption per cut.
- Gates: `hyperframes check` clean before render.

For last-stop-yt-engine's trailer/shorts stage: adopt the multi-variant brief system
(one plan → N platform cuts), source-grounding rule, poster-frame baking, and
determinism notes.

## 8. `superz1402/imgagent` — image acquisition agent (plumbing patterns only)

Production-grade CLI: `imgagent run "<query>" --limit 20 --top 5 --out ./assets --json`
→ search (wikimedia · openverse · duckduckgo · `custom:*` config-driven official APIs) →
normalize (single versioned `ImageCandidate`) → **deterministic rank (text+entity+
technical+rights, no LLM)** → dedupe (URL + SHA-256 + perceptual near-dup) → download
(streaming, bounded concurrency, atomic `.part`) → **validate (magic bytes + full
Pillow decode)** → manifest (`/manifests/<job>.json` + metadata.jsonl) → verified paths.
Structured `errors[]` per source ("a broken provider never breaks the others"); SSRF
hardening (private ranges + cloud-metadata blocked, redirect-by-redirect validation,
size caps, TLS never disabled). **No video sourcing** — for our engine, steal the
contract patterns (one command → manifest → verified bytes → honest negatives) for the
*video* acquisition agent, and the `custom:*` provider-config format for Pexels/Pixabay.

## 9. `edenfunf/reelmimic` — style cloning + multi-agent review production line

"Show it a video you love. Get a new video in the same style." Local web app (Node
server + React + agent workspace) that drives Claude Code/Codex to clone a reference
video's **editing rhythm, shot lengths, BPM, transitions, colors, framing, camera moves**
into a new animation (7 2-D engines; HyperFrames-based motion graphics among them).

Architecture worth stealing:

- **File-based contract between server and agents**: "the server decides whether a step
  is done by checking whether the files it must produce were updated" (mtime check) —
  the same trick as ahyeon's `.done` markers, generalized to a state machine
  (`analyzing → styling → planning → plan_review ⇄ replanning → producing → critiquing
  ⇄ revising → done`); interrupted jobs flagged `recoverOrphans` on restart.
- **Production line with fresh reviewers**: cast gate per character (reviewer ⇄ fixer,
  ≤3 rounds) → parallel builders (1–4 shots each) → **every finished shot immediately
  reviewed by a fresh conversation** ("nobody grades their own work"); two severities
  (`blocker` vs `polish`); **fixes need before/after crop evidence**; global `MAX_AGENTS`
  budget with reviews jumping the queue.
- `scripts/analyze.py` → `analysis/report.json` + contact sheets (`sheet_1fps.jpg`,
  `sheet_scenes.jpg`) — the reference-breakdown step (shot count, lengths, BPM).
- **Style DNA as JSON**: `.claude/skills/embedded-captions/dna/*.json` — e.g.
  `documentary.json` = "Errol Morris dignity": `register: formal`, light-on-dark
  `#F5EFE6` on charcoal, `reveal: "burn"` (no animation), modest hero, no accent/glow,
  motion budgets (`impact: y 6, scale 1.03, dur 0.2, power2.out`), read-time defaults.
  A whole caption/graphic identity system as declarative JSON — drop-in for our
  caption/card styling config.
- **`.claude/skills/cut-the-curve/`** — a formal technique catalog: 5 seam techniques
  (zoom-through, inverse zoom-through, cut-the-curve, waterfall cut, rack-focus
  blur-cut) + 2 in-scene techniques (waterfall entry, nudge curve); the **seam law**:
  "cut at peak velocity, match direction and speed on both sides of the cut"; Z-axis
  sign rule (banned mirrors: receding exit answered by grow-from-small entry); blur
  peaks 10 px text / 18–20 px full-frame; word-by-word staggered cuts; 10/65/25 slide
  ratio. Pure editing intelligence, engine-agnostic.

## 10. `ChatCut-Inc/agent-plugin` — LLM-driven editing patterns

Official plugins (Codex/Claude/Grok/Kimi) that drive **ChatCut**, a cloud multi-track
NLE, over hosted MCP (`https://api.chatcut.io/api/external-mcp/mcp`; tools
`read_project`, `edit_item`, `preview_timeline views:["viewer"]`, `inspect_item`,
`track_export`). We won't depend on their cloud, but three skill patterns are gold:

- **`verification/SKILL.md`** — "A successful mutation is not visual proof… Successful
  rendering or mutation metadata is not visual proof until the returned pixels are
  inspected." Structural check + composed-frame check, both mandatory before reporting
  success. Same doctrine as vfactory's closure protocol — make it an engine law.
- **`multicam-sync/SKILL.md`** — "AI locates; arithmetic decides frames." Transcript
  overlap matrix decides which assets are simultaneous angles vs sequential spans of one
  camera; speaker-follow draft cut by default. Pattern reusable for aligning multiple
  subject-footage captures to narration.
- **`known-errors/SKILL.md`** — maintain a living known-errors skill; on validation
  errors change only the rejected field; "do not retry with remembered legacy payloads
  when the current manifest differs"; never silently delete conflicting items.

---

## 11. Synthesis for `last-stop-yt-engine`

### 11.1 Pipeline mapping (source → engine stage)

| Engine stage | Primary donor | Notes |
|---|---|---|
| Config | documentary-agent-kit S0 `00_brief.json` | + style DNA json (reelmimic) + fonts/palette/lexicon from ahyeon script.json |
| Research/facts | kit S1 + fact-researcher subagent | ≥25 VERIFIED facts/10 min; UNVERIFIED banned in narration |
| Script | kit S2 + ahyeon beats | word budgets, ban list, duration ±3 % |
| Voice | ahyeon tts.py | lexicon, edge-tts SRT, resumable; word timestamps from SRT/WordBoundary |
| **Footage acquisition** | ahyeon mpt_bridge + ytagent farm + vfactory library.json | **video-only ladder** (below) |
| **Smart director** | vfactory s4_smart.py | anchor-word LEAD cuts; entity tags; variety; continuation |
| Timeline/EDL | ahyeon build_timeline.py | gap calibration; timeline.json schema (videos + cards only) |
| Music | ahyeon CC0 bed + duck | upgrade path: somerton numpy kit / incompetech CC-BY |
| Render | ahyeon render.py Phase1/2/3 | `d=1` zoompan; `-frames:v` exact; ASPLIT LAW |
| Captions | ahyeon ASS + reelmimic documentary DNA | styles as declarative JSON |
| QC | ahyeon qc + vfactory s8_qc | + freezedetect, ASR voiceover gate, frame-entity vision check, cpm/ASL gates |
| Publish | kit S8 + ahyeon remux.yml | GitHub Release canonical; unlisted-first; 09_publish.json sha256 |

### 11.2 The no-stills media ladder (engine rule: zero photographic stills in output)

Ranked fallback chain, each step **moving** pixels:
1. **Verified subject footage** — vfactory `library.json` entity-tagged clips (farm
   download via yt-download-farm.yml), audio stripped, ≤10 s segments.
2. **Licensed stock video** — mpt_bridge (Pexels/Pixabay video APIs), Mixkit/Coverr
   direct mp4s (validated live in DESIGN_V2).
3. **Code-drawn segments** — somerton/opuscar engine (deterministic HTML/SVG render) or
   procedural generative cards (ahyeon `card_ambient`-style Pillow art + zoompan/loop,
   i.e. *animated* graphics, never a static photo).
4. **AI-generated b-roll** (optional, off by default; vfactory `--ai-broll`, 429-prone).
`freezedetect` (>4 s) + shot-source mix gate (video ≥60 % per DESIGN_V2; stills = 0 %)
enforce the rule mechanically in QC.

### 11.3 Character-lock integration pseudocode

```python
# after TTS:  project/voice/beat_*.mp3 + timing.json (voice_s per beat)
narr = concat_narration(timing, gap=0.35)                  # vfactory s4_smart
words = word_timestamps(narr, cache="04_smart/words.json") # faster-whisper small.en
plan = llm_write_visual_plan(script, entity_vocab, library_index)
#   plan.scenes[i].visual = [{entity, anchor|None, clip|None, in_point|None}]
tl = build_timeline(plan, words, bounds, library)          # LEAD=0.30 anchor cuts
for shot in tl.shots: assert library[shot.clip].entities covers shot.entity  # gate
# render shots (exact -frames:v, d=1 zoompan), concat -c copy, ASPLIT-LAW audio graph,
# loudnorm I=-14 TP=-1.5 LRA=11
qc_battery(final)          # ffprobe + LUFS + silence + freezedetect + cpm/ASL vs DESIGN_V2
asr_voiceover_gate(final)  # 2× mono 16k windows → non-empty transcript
vision_entity_audit(final) # extract frames at anchor timestamps → VLM: entity on screen?
# any FAIL → SystemExit, no publish (kit S7/S8 + vfactory s8 law)
```

### 11.4 CI skeleton (from ahyeon render.yml, with fixes)

`workflow_dispatch` only; 350 min timeout; `contents: write`; apt ffmpeg+fonts; minimal
pip; **add**: actions/cache for pip + whisper model + farm downloads; per-beat resumable
renders with `.done` markers (render_final.py pattern) so re-runs are minutes, not hours;
QC gate job; release via softprops; optional shorts/trailer job (shorts.yml pattern);
remux.yml as the surgical asset-repair pattern.

### 11.5 Top risks (ranked)

1. **Subject-footage availability**: UMG stream-gating (empty format lists / GVS 403)
   even via farm; mitigation = license-pure ladder (stock/code-drawn), honest QC flag.
2. **Silent-voiceover class of bugs**: ASPLIT LAW violations survive level probes — keep
   the ASR gate as a hard post-mux check.
3. **Whisper anchor misspells names** ('ahyahn') → fuzzy 0.78 + variant lists; cache
   `words.json` to avoid resume drift.
4. **Drift accumulation**: any per-shot pad multiplies; `-frames:v` exact + sidecar
   caches mandatory.
5. **CI limits**: 29–40 min render ≈ runner ceiling; use beat-chunked steps + caching;
   350 min timeout already proven sufficient.
6. **YouTube policy**: inauthentic-content policy for mass AI narration + fair-use
   subject clips → unlisted-first, attribution appendix, `subject_clip_policy` gate.
7. **MusicGen-type license traps**: keep music CC0 (Openverse) or CC-BY (incompetech,
   credited) — never NC weights.
8. **zoompan cost**: 2160-prescale is CPU-heavy on GitHub runners; veryfast + resumable
   segments is the proven compromise.

---

## Appendix A — Exact interfaces worth keeping verbatim

- `render.py`: `kb_filter(mode, dur, fade_in, fade_out) -> str` (modes in/out/left/right;
  PRESCALE 2160; eq contrast 1.03 saturation 1.05; fades 0.28 s in / 2.6 s out),
  `seg_out(name, dur, filt, source_args)` (.done resumable).
- `build_timeline.py`: gap scale `max(0.4, min(2.6, (TARGET-INTRO-OUTRO-sum_dur)/sum_pause)))`;
  `video_for(query, used)`, `asset_for(query, used)` (reuse cap 2; min visual 2.4 s).
- `tts.py`: `ttsify(text)` lexicon regex; edge-tts flags `--rate=-3% --write-media
  --write-subtitles`.
- `mpt_bridge.py`: `pexels_videos(q,key,n=6)`, `pixabay_videos(q,key,n=6)`,
  `normalize(src,dest,dur_s)` (crop-fit, `-an`), manifest checkpoint per query.
- `ytagent_bridge.py`: `ytagent_download(video_id, out_dir)` library→CLI→cache;
  `normalize_cut(src,dest,start,dur)`.
- `s4_smart.py`: `find_anchor(words, lo, hi, anchor)`, `match_span(...)`,
  `pick_in_point(...)`, `build_timeline(...)`; constants GAP=0.35 LEAD=0.30.
- `s8_qc.py`: `_luma_samples` (PNG+PIL, not signalstats), `_silence_max`
  (`silencedetect=noise=-45dB:d=6`), `_asr_words` (mono 16 k, ≤30 s, 429 backoff).

## Appendix B — File inventory of clones

`research/clones/{ahyeon-documentary, documentary-agent-kit, opuscar-studio, vfactory,
films, somerton-man-documentary, promos, imgagent, reelmimic, agent-plugin}` — all
shallow-cloned, read-only, nothing pushed. (Other agents' clones also present in the
same directory: character-clip-extractor, igagent, ttagent, ytagent, xthread-agent,
personal-social-agent, uaal — outside this task's scope.)
