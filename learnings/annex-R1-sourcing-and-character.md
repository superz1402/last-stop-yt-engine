# R1 — Sourcing & Character-Lock Research Synthesis

**Task ID:** 2-a · **Agent:** R1-sourcing-research
**Purpose:** Feed the design of `last-stop-yt-engine` — an autonomous documentary production system that (1) must NEVER use still images in final videos (video-only), (2) must keep narration and visuals character-locked (if narration says "Jennie", Jennie must be on screen), (3) sources all footage from YouTube/TikTok/Instagram/X.
**Method:** `git clone --depth 1` into `/home/z/my-project/research/clones/`, then full source reads. All 7 repos cloned successfully at HEAD:
`character-clip-extractor@4712de7` · `ytagent@7290dcd` · `ttagent@01c5145` · `igagent@65faa47` · `xthread-agent@e5bbfbe` · `personal-social-agent@f59321f` · `uaal@c0d9af6`.

---

## 0. Executive map — how the repos fit together

The user's repos form a **layered acquisition + identification stack**, with shared engineering doctrine (slots, fail-closed verification, JSON envelopes, no-login, no-LLM-at-runtime):

```
                    ┌────────────────────────────────────────────┐
                    │  personal-social-agent  (orchestration OS) │   state machine, outbox,
                    │  GitHub Actions + Discord review + Buffer  │   kill switch, human approval
                    └────────────────────────────────────────────┘
                                         │ orchestrates
        ┌───────────────┬───────────────┼────────────────┬───────────────┐
        ▼               ▼               ▼                ▼               ▼
   ┌─────────┐    ┌─────────┐    ┌──────────┐     ┌───────────────┐  ┌────────┐
   │ ytagent │    │ ttagent │    │ igagent  │     │ xthread-agent │  │  uaal  │
   │ YouTube │    │ TikTok  │    │ Instagram│     │  X/Twitter    │  │ universal
   │ 13-chain│    │ 4 slots │    │ 3 slots  │     │ walker+decoder│  │ (TS, all 8)
   └────┬────┘    └────┬────┘    └────┬─────┘     └──────┬────────┘  └───┬────┘
        └──────────────┴──────────────┴──────────────────┴───────────────┘
                                       │ verified video files
                                       ▼
                    ┌────────────────────────────────────────────┐
                    │       character-clip-extractor (CCE)       │
                    │  ytagent-embedded download → normalize →   │
                    │  PySceneDetect shots → InsightFace @2fps → │
                    │  visibility → grouping → CRF16 windows →   │
                    │  ONE full per-character video + reports    │
                    └────────────────────────────────────────────┘
```

- `character-clip-extractor` (CCE) **embeds `ytagent-cli` as its download engine** and is the only repo that answers the *character-lock* requirement: it maps a face identity to time ranges in a video.
- `ytagent` is the strongest YouTube downloader of the set (datacenter-IP defeats).
- `ttagent` / `igagent` / `xthread-agent` are stdlib-only single-file harvesters for TikTok / Instagram / X, each with a machine JSON contract and MCP wrappers.
- `uaal` is the generalized TypeScript rewrite of all of the above patterns (8 platforms, one interface).
- `personal-social-agent` is not a media tool at all — it is the **orchestration discipline** (20-state machine, idempotent outbox, kill switch, human approval) worth transplanting into any engine that must run autonomously without publishing garbage.

---

## 1. character-clip-extractor — THE character-lock engine (deep dive)

Repo: https://github.com/ansaribilal14/character-clip-extractor · v0.3.0 · MIT · Python ≥ 3.10
Package: `character_clip_extractor` (installable, console script `character-clip-extractor`) + standalone `scripts/` pipeline steps (env-driven) + bundled BABYMONSTER reference photos (`references/<member>/01..08.jpg`, `refs_summary.json` with 512-d centroids).

### 1.1 What it does

One command: give it a **YouTube URL** and a **character** (name with bundled references, or your own photos). It downloads the video (embedded ytagent, 13-method chain + BGutil POT), normalizes losslessly, then runs a CPU face pipeline:

```
00 normalize → 01 shot detection (PySceneDetect) → 02 face analysis @2fps (InsightFace buffalo_l)
→ 03 RAW visibility intervals → 04 audio activity (energy VAD) → 04b captions (yt-dlp)
→ 05 scene-continuity grouping (multi-evidence) → 06 export CRF16 windows → 06b contact sheet
→ 07 QC → 08 reports → 10 concat into ONE full per-character video
```

Output: `<target>_FULL_<video_id>.mp4` (the whole episode's character content as one video, non-character stretches removed, 5 s safety padding, zero scene splitting), plus `timeline.json`, `matches.json`, `report.csv`, `report.html`, `WORKLOG.md`, contact sheet, ZIP.

### 1.2 Exact invocation

**CLI** (from `character_clip_extractor/cli.py` + README):

```bash
python -m character_clip_extractor --url URL [--character NAME]
    [--ref-images FILE [FILE...]] [--auto-refs] [--out DIR] [--pad SEC]
    [--max-height N] [--skip-analysis] [--force-download] [--no-zip]
    [--no-deliver] [--keep-files] [--tg-send]
# console-script alias: character-clip-extractor --url ... --character ...
```

| flag | default | meaning (verbatim from argparse) |
|---|---|---|
| `--url` | required | "YouTube video link (youtu.be / watch / shorts)" |
| `--character` | `target` | "character name (slug); must have references available unless --ref-images is given" |
| `--ref-images` | None | "reference photo(s) or directory of the character" — `.jpg/.jpeg/.png/.webp/.bmp`, files or dir |
| `--auto-refs` | off | "best-effort fancam search for references (needs reachable YouTube)" |
| `--out` | `<repo>/workspaces/default` | workspace directory |
| `--pad` | `5.0` | "padding seconds around scenes" |
| `--max-height` | `1080` | "max download height (falls back to best available)" |
| `--skip-analysis` | off | reuse existing analysis outputs (resume) |
| `--force-download` | off | re-download even if source exists |
| `--no-zip` / `--no-deliver` / `--keep-files` | off | delivery controls |

Real quickstart from README:

```bash
python3 -m character_clip_extractor \
    --url https://youtu.be/SDxj3hDFOVI \
    --character ahyeon \
    --out workspaces/syt_01_seoul
```

Bundled characters (references shipped in-repo): `ahyeon, asa, chiquita, pharita, rami, rora, ruka`.

**Python API** (the four public modules; signatures copied from source):

```python
from character_clip_extractor import downloader, refs, runner, packager, delivery

# 1) references — build verified face centroid for any character
ok, msg = refs.ensure_references(workspace, target, ref_images=None, auto_search=None)
#    order: (1) existing refs_summary.json entry → keep; (2) user images;
#           (3) bundled repo references; (4) --auto-refs fancam search (get_refs.py)

# 2) download — inbuilt ytagent engine
path = downloader.download(url, out_dir, max_height=720, attempts=4,
                           spacing_s=15, timeout=60)   # returns local path or None

# 3) pipeline — sentinel-based, auto-resuming
runner.run_pipeline(base, target, video_id, video_url, pad=5.0,
                    skip_analysis=False, step_timeout=3600, maxh=1080, resume=True)
# env contract injected for scripts: CCE_BASE, CCE_TARGET, CCE_VIDEO_ID,
# CCE_VIDEO_URL, CCE_PAD, CCE_MAXH  (scripts dir override: CCE_SCRIPTS)

# 4) packaging + delivery
zip_path = packager.make_zip(base, target, video_url, out_path=None)
res = delivery.deliver_auto(path, caption='', keep=False, chat=None)  # dict(kind, ok, ...)
res = delivery.upload_storage_to(path)   # dict(url, filename, human_size, expires_at)
ok  = delivery.send_document(path, caption='')   # Telegram sendDocument, ≤49MB only
```

**Standalone single-script usage** (each script is env-driven, so you can run any step in isolation — this is the cleanest integration seam):

```bash
export CCE_BASE=/path/to/workspace CCE_TARGET=jennie CCE_VIDEO_ID=abc123 \
       CCE_VIDEO_URL=https://youtu.be/abc123 CCE_PAD=5 CCE_MAXH=1080
python3 scripts/02_analyze_faces.py     # reads <base>/output/analysis/normalized.mp4
                                        # + <base>/references/refs_summary.json
                                        # writes <base>/output/analysis/analysis.jsonl
```

**Downloader module standalone:**

```bash
python downloader.py <url> --out-dir DIR --max-height 720 --attempts 4
```

### 1.3 Face/embedding technology (exact)

- **InsightFace `buffalo_l`** pack (SCRFD-10GF-BNKPS detector + ArcFace R100 512-d embedding), executed via **onnxruntime** on **CPU only**: `FaceAnalysis(name='buffalo_l', providers=['CPUExecutionProvider']); app.prepare(ctx_id=-1, det_size=(640, 640))` (`refs.py::_load_app`, `02_analyze_faces.py`).
- **Reference building** (`refs.py`): constants `MIN_FACE_PX = 80`, `OUTLIER_COS = 0.35`. Per image: detect → keep largest face → require bbox height ≥ 80 px → 512-d `normed_embedding` → mean centroid (L2-normalized) → drop faces with cosine < 0.35 from centroid → recompute centroid → save padded face crops (25% pad, JPEG q92) as `NN.jpg` + `refs_summary.json` entry `{centroid: [...512 floats...], n_refs, refs, source}`. `verify_refs.py` adds cross-member separation matrix (warn if any pair distance < 0.45) and iterative 2-pass outlier removal.
- **Frame matching** (`02_analyze_faces.py`): sample at `FPS_SAMPLE = 2.0` (every 0.5 s), downscale frame to `PROC_W = 1280` (env `CCE_PROC_W`) before detection, then per detected face compute cosine similarity of `normed_embedding` against every member centroid; `MATCH_THRESHOLD = 0.42` — below that the face is labeled `unknown`. Emits one JSONL record per sample:

```python
rec = {'t': round(t, 3), 'n_faces': len(rec_faces), 'faces': rec_faces,
       TKEY: best_target_cos}    # TKEY = f'{TARGET}_best_cos', None if absent
# each face: {'member', 'cos': 4dp, 'bbox': [x1,y1,x2,y2] source-scale,
#             'det_score': 3dp, 'size': px height}
```

- The docstring claims **member centroids are separated by ≥ 0.72 cosine** in the bundled set — i.e., 0.42 threshold has large margin for multi-character disambiguation.

### 1.4 Extraction & output format

- **Shots** (`01_detect_shots.py`): `scenedetect.detect(VIDEO, ContentDetector(threshold=27.0))` → `shots.json` `[{shot_id, start, end, duration}]`, coverage extended to EOF.
- **RAW visibility** (`03_raw_visibility.py`): group 0.5 s samples where target visible; bridge ≤ 1 consecutive miss (`MAX_MISS = 1` → max 1.0 s gap); **drop intervals < 1.0 s** as likely false positives; output per interval `{start, end, duration, n_samples, mean_cos, max_cos, shots[]}`.
- **Grouping** (`05_group_scenes.py`) — the intelligence layer. Sequential merge of raw intervals using an evidence score; merge if `score >= MERGE_THRESHOLD (3.0)`; **hard blocks: `gap > MAX_GAP_S (12.0)` or `intervening shot boundaries > MAX_SHOTS (2)`**:

```python
if   gap <= 1.5: score += 2.0   # E1 temporal proximity
elif gap <= 3.0: score += 1.5
elif gap <= 6.0: score += 1.0
else:            score += 0.5
if   nshots == 0: score += 1.0  # E2 shot adjacency
elif nshots == 1: score += 0.5
if speech_spans_gap: score += 1.0     # E3 audio energy bridges the gap (VAD only)
if caption_spans_gap: score += 1.0    # E4 a caption segment covers the gap
if same_other_members_both_sides: score += 1.0   # E5
# E6 position/size stability: mean bbox center delta < 15% of width/height
#    AND size ratio in (0.6, 1.6)  → +1.0
# E7 embedding-across-gap: recorded as null (not implemented in MVP)
```

Scene records include `visibility_ratio`, `members_present`, `speech_seconds`, and a `confidence` = `0.7·mean(max_cos) + 0.3·visibility_ratio`.
- **Export** (`06_export_clips.py`): each grouped scene padded by `CCE_PAD` (clamped to video duration); overlapping padded windows merged (0.5 s tolerance); min scene span `MIN_CLIP_S = 1.0`; encode:

```python
['ffmpeg', '-y', '-ss', f'{a:.3f}', '-i', VIDEO, '-t', f'{b-a:.3f}',
 '-c:v', 'libx264', '-preset', 'medium', '-crf', '16', '-pix_fmt', 'yuv420p',
 '-c:a', 'aac', '-b:a', '192k', '-movflags', '+faststart', out]
```

Plus a peak-visibility thumbnail (frame at max cos inside the window).
- **Full video** (`10_concat_full.py`): union-merges ALL windows (`merge_windows(..., gap=0.25)`), honors a human-review file `output/analysis/review_verified.json` (`[{start, end, accept}]` for micro-detections), stream-copy concat via the ffmpeg concat demuxer with duration-parity check (tolerance `max(3.0 s, 2.5%)`), fallback to one `filter_complex` concat re-encode (`libx264 veryfast crf16`) if copy-concat drifts. Output `<target>_FULL_<video_id>.mp4` + `full_video.json`.
- **QC** (`07_qc.py`): ffprobe every clip, duration delta vs plan window (pass ≤ 1.5 s), audio presence, contact sheet build.
- **Normalize** (`00_normalize.py`): h264+aac mp4 ≤ `CCE_MAXH` → lossless remux (`-c copy`); otherwise one CRF18 re-encode `scale=-2:min(MAXH\,ih)`. Atomic `.part` → `os.replace`.

### 1.5 Download engine details (downloader.py — embedded ytagent)

```python
FMT = ("bv*[ext=mp4][height<={h}]+ba[ext=m4a]/bv*[height<={h}]+ba/"
       "b[height<={h}]/b")          # h = --max-height

cmd = ['ytagent', 'download', url, '--out-dir', out_dir,
       '--format', FMT.format(h=max_height), '--json', '--timeout', str(timeout)]
```

Order of operations in `downloader.download()`:
1. `ensure_ytagent_cli()` — auto `pip install ytagent-cli` if `ytagent` binary missing.
2. `ensure_pot()` — probe `http://127.0.0.1:4416/` (ANY HTTP answer incl. 400 = alive); if dead, spawn `ytagent setup` (starts the BGutil POT provider), poll up to 30 s.
3. `_farm_pickup()` — if `CCE_GH_TOKEN` set, look for an existing GitHub-Artifact/Release from a previous farm run (release mirror preferred: "Release asset downloads bypass the artifact-zip rate limit").
4. Up to `attempts=4` rounds: `ytagent download` → on failure direct yt-dlp fallback:

```python
cmd = [sys.executable, '-m', 'yt_dlp', '--no-warnings', '-f', FMT,
       '--merge-output-format', 'mp4', '-o', '%(id)s.%(ext)s',
       '--socket-timeout', str(timeout),
       '--extractor-args',
       'youtube:player_skip=webpage,configs;player_client=android_vr,android,web;'
       'youtubepot-bgutilhttp:base_url=http://127.0.0.1:4416', url]
```

5. Bot-check regex `r"confirm you.?re not a bot|Sign in to confirm"` — when hit, skip remaining direct attempts and go straight to the **GitHub Actions farm** (`CCE_FARM_OWNER` default `ansaribilal14`, `CCE_FARM_REPO` default `yt-farm`, workflow `yt-download-farm.yml`; dispatch → poll every 20 s, budget 540 s → download artifact zip or release asset, resumable with HTTP Range).
6. Verification of every candidate file (`verify_file`): size ≥ 1 MB, video+audio stream present via ffprobe, **A/V per-stream duration parity ≤ 2.0 s** (catches truncated relay downloads), container/video duration parity ≤ 2.0 s. Failed/truncated files deleted and retried.

### 1.6 Delivery (delivery.py)

Single path for every artifact: `deliver_auto(path, caption, keep)`:
- ≤ 49 MB (`SAFE_TG_BYTES`) → Telegram `sendDocument` (env `CCE_TG_TOKEN`, `CCE_TG_CHAT`; skipped with warning if unset).
- \> 49 MB → **storage.to** anonymous upload: `POST /api/upload/init` → single `PUT` or multipart part `PUT`s (per-part 3 retries, ETag collection, `POST /upload/parts` for fresh presigned URLs) → `POST /upload/complete-multipart` → `POST /upload/confirm`; persistent `X-Visitor-Token` at `~/.cache/character_clip_extractor_visitor_token` (env `CCE_VISITOR_TOKEN_FILE`); link messaged to Telegram; local file deleted after confirm unless `keep=True`.

### 1.7 Auto-resume machinery (runner.py)

- Every step has an on-disk sentinel (`output/analysis/normalized.mp4`, `shots.json`, `analysis.jsonl`, `raw_visibility.json`, `audio_activity.json`, `captions.json`, `grouped_scenes.json`, `export_plan.json`, `qc.json`, `output/reports/report.html`, `full_video.json`).
- Step 02 completeness is verified by **counting JSONL records ≥ expected `int(dur/0.5)+1`** (a non-empty partial file proves nothing); step 06 completeness requires every planned clip `export_ok=true`.
- Step 02 itself resumes at frame level: torn JSONL lines from a killed run are truncated to the last valid record, then processing continues from `t_last * fps`.
- Scripts also use atomic `.part` writes + `os.replace` (normalize) and `_clip_ok/_seg_ok` ffprobe re-checks for leftovers of killed runs.

### 1.8 Dependencies + install

```bash
git clone https://github.com/ansaribilal14/character-clip-extractor.git
cd character-clip-extractor
python3 -m pip install -r requirements.txt   # ffmpeg/ffprobe must be on PATH
```

requirements.txt: `numpy, opencv-python, insightface, onnxruntime, scenedetect>=0.7, yt-dlp, ytagent-cli, requests`. System: **ffmpeg + ffprobe on PATH**; model `buffalo_l` (~280 MB) auto-downloads to `~/.insightface` on first run. ytagent side needs **Node.js + npm + git** for the BGutil POT provider auto-bootstrap. GPU: **none required** (CPUExecutionProvider hardcoded; `ctx_id=-1`). Observed cost in docstrings/logs: 2 fps sampling, ~x s/frame on CPU (printed as `elapsed/frames`), step timeout default 3600 s.

### 1.9 Weaknesses / limits (as admitted + as observed)

Admitted (README "Honest limitations"):
- Voice activity ≠ speaker identity — step 04 cannot tell who talks (irrelevant for our use; we lock on faces).
- Detection recall: heavy blur, extreme angles, sub-80 px faces, bad lighting drop detections; padding + grouping mitigate but don't eliminate.
- Grouping is conservative — hard blocks can split one long continuous scene into two adjacent grouped scenes (seamless if padded windows overlap).
- Source resolution bounded by download IP (720p common on datacenter IPs; reported honestly).
- Datacenter-IP throttling — retries spaced; "throttles often lift with spacing (observed ~35 min)".

Observed from source (extra things to know before integrating):
- Thresholds are **hard-coded constants** in scripts (`MATCH_THRESHOLD=0.42`, `OUTLIER_COS=0.35`, `MIN_FACE_PX=80`, `MERGE_THRESHOLD=3.0`, `MAX_GAP_S=12.0`, `MAX_SHOTS=2`, `FPS_SAMPLE=2.0`, `PROC_W=1280`, `NOISE_DB=-30`, `MIN_SILENCE=0.6`) — to tune for a new documentary you edit the script or fork the constants; there is no config file.
- Scripts default `BASE` to `/home/z/my-project/clipextractor` if `CCE_BASE` is unset — harmless with the env set, but a footgun.
- One target character per run (`CCE_TARGET`), though multi-member centroids are supported in the data model (`members` dict) — matching is against ALL known members and per-face `member` labels are recorded, so a multi-character pass is nearly free (just aggregate by `member` instead of `TKEY`).
- 2 fps sampling means appearances shorter than ~0.5–1.0 s can be missed (mitigated by padding, but relevant for cutaway flashes).
- `MATCH_THRESHOLD=0.42` was tuned for a K-pop idol face set; for arbitrary documentary subjects the threshold may need per-subject calibration (the refs pipeline gives you the centroid; validate with the contact sheet + QC reports).
- Captions step may legitimately fail on bot-checked IPs (writes `CAPTIONS_UNAVAILABLE`, pipeline continues).
- E7 (embedding continuity across gap) is stubbed `None`; no VLM.
- The 06 export uses `-ss` before `-i` (input seek) — keyframe-rounded starts; acceptable (QC tolerance 1.5 s) but not frame-exact.
- Delivery deletes local files after storage.to confirm by default — set `--keep-files` in an engine context.

### 1.10 Integration recipe for last-stop-yt-engine (pseudocode)

CCE is the **character-lock oracle**: it converts "narration mentions X" into "X is visibly on screen between t1..t2".

```python
# Phase A — per sourced video, before it is eligible for the cut
def character_lock_video(youtube_url, character, ref_images, workspace):
    ok, msg = refs.ensure_references(workspace, character, ref_images=ref_images)
    assert ok, msg                              # build/verify centroid once per subject
    src = downloader.download(youtube_url, f"{workspace}/output/source", max_height=1080)
    run_normalize(src, workspace)               # scripts/00_normalize.py via CCE_* env
    runner.run_pipeline(workspace, character, vid, url, pad=5.0, maxh=1080)
    grouped = json.load(open(f"{workspace}/output/analysis/grouped_scenes.json"))
    return [Scene(s['start'], s['end'], s['confidence'], s['visibility_ratio'])
            for s in grouped['scenes']]         # the ONLY spans where character may appear

# Phase B — narration→visual binding (the engine's core rule)
def bind_narration_to_visuals(script_lines, locked_scenes_per_video):
    for line in script_lines:                   # line mentions entity E with t_narr
        candidates = [s for s in locked_scenes_per_video[E] if s.confidence >= 0.6]
        assert candidates, f"NO CHARACTER FOOTAGE for {E} — reject script line"
        pick = rank(candidates, by="visibility_ratio, then scene length")
        emit(shot=clip_at(pick.video, pick.start, pick.end), narration=line)
    # HARD INVARIANT: every emitted shot's time range ⊆ a locked scene of the
    # narrated entity. No scene → no shot → rewrite narration (never a still image).

# Phase C — post-render character-lock QC (defense in depth)
def qc_character_lock(final_mp4, character, refs_summary):
    for probe_t in sample_timestamps(final_mp4, every=1.0):
        frame = grab(final_mp4, probe_t)
        cos = face_similarity(frame, refs_summary.centroid)
        record(probe_t, cos)
    # fail the build if any narration-spanning probe frame has cos < 0.42
```

Also steal: sentinel-based auto-resume (`runner.PIPELINE`/`SENTINELS`), the `review_verified.json` human-override file, JSONL frame-resume pattern, and the honest RAW-vs-GROUPED dual reporting for auditability.

---

## 2. ytagent — the YouTube download recipe

Repo: https://github.com/Bilal140202/ytagent · v0.3.0 · MIT · Python ≥ 3.11 · PyPI **`ytagent-cli`** (CLI command `ytagent`).

### 2.1 What it is

"An agentic YouTube downloader for cloud-based AI agents." Wraps yt-dlp in a **13-method fallback chain** + a **Truth Agent** (learns which methods work in this environment) + a **6-layer Verifier** (never trusts a method's self-report). No cookies, no OAuth, no browser, no LLM at runtime. Public videos only.

### 2.2 Invocation

```bash
pip install ytagent-cli            # system deps: apt install ffmpeg nodejs npm git

ytagent download "<url-or-id>" [--out-dir DIR] [--format FMT] [--proxy URL] \
                   [--timeout N] [--state-dir DIR] [--json]
ytagent setup [--status | --stop]  # BGutil POT provider lifecycle
ytagent truth show | truth reset [--method NAME]
ytagent list-methods
ytagent self-test --mode quick|full
ytagent agent-instructions [--format text|json|markdown]
```

Machine JSON on stdout (`--json`), logs on stderr:

```json
{
  "ok": true, "video_id": "YOUR_VIDEO_ID",
  "final_path": "downloads/YOUR_VIDEO_ID.mp4",
  "method_used": "ytdlp_default", "total_duration_ms": 5432,
  "attempts": [{"method": "transcript_probe", "ok": true, "reason": "reachable"}],
  "trace_id": "a750a4d4b477"
}
```

Programmatic (README-verbatim):

```python
import subprocess, json
result = subprocess.run(["ytagent", "download", url, "--json"], capture_output=True, text=True)
data = json.loads(result.stdout)
if data["ok"]:
    print(data["final_path"], data["method_used"])
```

Python-internal (orchestrator): `Orchestrator(truth, verifier, methods).download(target: str, out_dir: Path, opts: dict) -> DownloadResult` — never raises; per-method temp dir under `<out>/.tmp/<video_id>/<method>/`; verified file atomically moved to `<out>/<video_id>.<ext>`.

### 2.3 The 13-method chain (truth.py `DEFAULT_METHODS`, in order)

| # | method | gist |
|---|---|---|
| 0 | `transcript_probe` | preflight reachability (fast-fail when IP blocked) |
| 1 | `ytdlp_default` | yt-dlp + `player_client=["android_vr"]` + BGutil POT |
| 2 | `ytdlp_jsless` | `visionos, android_vr` clients + BGutil |
| 3 | `ytdlp_ios` | IOS client (HLS) |
| 4 | `ytdlp_single_file` | pre-muxed MP4 (no ffmpeg merge) |
| 5 | `ytdlp_audio_only` | audio salvage |
| 6 | `innertube_direct` | hand-rolled POST `/youtubei/v1/player` |
| 7 | `cobalt` | self-hosted Cobalt sidecar |
| 8 | `cobalt_community` | public Cobalt relays (bypasses datacenter block; ~2 calls/IP before rate limit) |
| 9 | `piped` | Piped API, 4-instance rotation |
| 10 | `invidious` | `local=true` proxy → `{base}/latest_version?id={vid}&itag=18&local=true` (360p muxed mp4; proven bypass) |
| 11 | `socks5_farm` | free SOCKS5 discovery, 50 parallel, two-phase test (watch page `playabilityStatus=OK` + innertube `streamingData` present), then yt-dlp through the working proxy |
| 12 | `github_actions_farm` | dispatch workflow on GH runners (Azure IPs) + WARP; artifact upload; resumable artifact fetch |

Truth Agent: `truth.json` holds `rank/consecutive_failures/success_ratio/attempts` per method; **demote after 3 consecutive failures, promote on success**; every attempt appended to `observations.jsonl` (append-only audit).

### 2.4 yt-dlp option block (from `_ytdlp_base.py` — copy these verbatim)

```python
BASE_OPTS = {
    "quiet": True, "no_warnings": True, "noprogress": True, "ignoreerrors": True,
    "nocheckcertificate": True, "nocache_dir": True, "no_cookies": True,
    "socket_timeout": 30, "retries": 10, "fragment_retries": 10,
    "extractor_retries": 3, "file_access_retries": 10,
    "retry_sleep_functions": {"extractor": "linear=5::30",
                              "fragment": "linear=5::30", "http": "linear=5::30"},
    "merge_output_format": "mp4",
    "postprocessor_args": {"ffmpeg": ["-movflags", "+faststart"]},
    "writethumbnail": False, "writeinfojson": False, "writedescription": False,
    "writesubtitles": False, "writeautomaticsub": False,
}
# extractor_args (build_opts):
#   youtube.player_client = ['android_vr']
#   youtubepot-bgutilhttp.base_url = 'http://127.0.0.1:4416'   (server alive)
#   youtubepot-bgutilscript-node.server_home = '/home/z/bgutil-ytdlp-pot-provider'
#                                              (script fallback: node generate_once.js)
```

BGutil bootstrap (`bootstrap.py`): clones `Brainicism/bgutil-ytdlp-pot-provider` (depth 1) to `YTAGENT_BGUTIL_HOME` (default `/home/z/bgutil-ytdlp-pot-provider`), `npm install --production` + `npm install typescript`, `tsc`, then `node build/main.js --port 4416` detached, PID at `/tmp/ytagent-bgutil.pid`, health `GET /ping`. Plugin dirs injected via `YTDLP_PLUGIN_DIRS` **before** `import yt_dlp`.

Verifier (6 layers, fail-fast): (1) exists & ≥ 1 MB; (2) magic bytes (ftyp/matroska/mp3/mpeg/OggS/FLV/RIFF) with HTML-error-page detection; (3) ffprobe parses; (4) duration > 0; (5) ≥ 1 video or audio stream; (6) MP4 top-level box walk → `moov` present & sane.

### 2.5 Dependencies + versions

`yt-dlp>=2026.07.04, requests>=2.32, python-magic>=0.4.27, click>=8.1, rich>=13.7, bgutil-ytdlp-pot-provider>=1.3.0, pysocks>=1.7.1`. System: ffmpeg/ffprobe, Node+npm+git (BGutil), Python 3.11+. Optional sidecars (`docker-compose.sidecars.yml`, `scripts/install_sidecars.sh`): WARP proxy + Cobalt.

### 2.6 Integration recipe

```python
def fetch_youtube(url, out_dir) -> Asset:
    ensure_pot()                                   # or ytagent setup once at boot
    r = run(["ytagent", "download", url, "--out-dir", out_dir,
             "--format", "bv*[ext=mp4][height<=1080]+ba[ext=m4a]/b[height<=1080]/b",
             "--timeout", "180", "--json"])
    d = json.loads(r.stdout)
    assert d["ok"], d["attempts"]                  # provenance = d["method_used"]
    verify_streams(d["final_path"])                # ffprobe parity check (defense in depth)
    return Asset(path=d["final_path"], method=d["method_used"], video_id=d["video_id"])
```

For `last-stop-yt-engine`: reuse CCE's `downloader.py` wholesale (it already wraps all of this, adds spaced retries + bot-check short-circuit + farm pickup) **or** call `ytagent` CLI directly with the CCE format string. Set `CCE_GH_TOKEN` only if you control a farm repo; otherwise rely on POT + the relay methods.

### 2.7 Risks/limits

- Datacenter IPs: 1080p metadata is often bot-gated; honest fallback to 720p/360p (invidious tier is 360p-only). No cookies/OAuth = no age-restricted/members-only/private content, ever.
- BGutil POT provider is a moving target tied to YouTube's BotGuard; needs Node and periodic yt-dlp upgrades (`yt-dlp>=2026.07.04` pinned for a reason).
- Free proxy/relay tiers (socks5 farm, community cobalt, public invidious) are unreliable and rate-limited; the farm tier needs a GitHub token and a repo.
- Orchestrator timeout uses a daemon thread — a hung yt-dlp may keep writing after timeout (output ignored, but disk can grow).
- Default `--state-dir`/`--out-dir` hardcode `/home/z/my-project/ytdl-agent/...` — always pass explicit dirs.

---

## 3. ttagent — TikTok sourcing

Repo: https://github.com/Bilal140202/ttagent · v1.0.0 · MIT · **Python 3.9+, stdlib-only, single file `ttagent.py`** (1141 lines) + `mcp_server.py` + PyPI package `ttagent` (`python -m ttagent`).

### 3.1 What it does / invocation

```bash
python ttagent.py "<input>" [--out DIR] [--no-download] [--no-music] [--json] [--quiet]
# <input>: tiktok.com/@user/video/<id> · /photo/<id> · vm./vt. short links (1 hop)
#          · tiktok.com/t/<code> · bare 15–20 digit id
# exit: 0 ok/partial · 1 empty · 2 invalid
python ttagent.py "<input>" --json --quiet     # THE machine contract: one JSON on stdout
```

Output: verified video (`<id>_video.mp4`), soundtrack (`<id>_music.mp3`), covers, and `video_manifest.json` (draft-07 schema bundled at `schema/video-result.schema.json`). Summary JSON example (README-verbatim): `{ok, status, video_id, canonical_url, extraction_source, author, video_file, music_file, images, downloaded, failed_downloads, out_dir, manifest_path, errors[], duration_sec}`. MCP tools: `extract_video`, `lookup_video`, `read_manifest`, `get_schema` (newline-delimited JSON-RPC 2.0 on stdio, stdlib only).

### 3.2 Decode slots (the API approach)

```python
# Slot 1 — tikwm mirror worker API (richest):
api = "https://www.tikwm.com/api/?url=" + urllib.parse.quote(url, safe="") + "&hd=1"
# code 0 + data = success; "parsing/deleted/private" msg = honest "unavailable"
# data gives: hdplay / play / wmplay (watermarked), music(+music_info), cover,
# origin_cover, author{unique_id,nickname,avatar}, stats{plays,likes,comments,
# shares,collects,downloads}, images[] for slideshow posts, region, create_time

# Slot 2 — TikTok's own embed hydration blob:  https://www.tiktok.com/embed/v2/<vid>
# Slot 3 — tiklydown second mirror (documented slot)
# Slot 4 — oembed (official, metadata-only last resort)
```

**Watermark handling:** `video_url = hd or play or wm` — prefers `hdplay`, then clean `play`, and only falls back to `watermarked_url` (`wmplay`) if nothing else exists; all three variants are recorded in the manifest so the engine can prefer/penalize.

**Delivery:** hard CDN allowlist — `.tikwm.com, .tiktokcdn.com, .tiktokcdn-us.com, .tiktokcdn-eu.com, .tiktok.com, .tiktokv.com, .tiktokv.us, .byteoversea.com, .ibyteimg.com, .akamaized.net, .muscdn.com, .musical.ly, .ttwstatic.com`; stream to `.part` → `Content-Length` check → magic bytes (`ftyp` mp4, `ID3`/frame-sync mp3, JPEG, PNG) → `os.replace` atomic. Politeness constants: `DECODE_SLEEP=0.6`, `DECODE_TIMEOUT=30`, `DOWNLOAD_TIMEOUT=180`, `DOWNLOAD_TRIES=3`, `DECODE_MAX_BYTES=10 MB`. Chrome UA spoof. Structured error codes: `E_INVALID_INPUT, E_SHORTLINK_DEAD, E_VIDEO_UNAVAILABLE, E_DECODE_FAILED, E_DOWNLOAD_FAILED, E_MANIFEST_WRITE_FAILED`.

### 3.3 Integration recipe

```python
def fetch_tiktok(url_or_id, out_dir) -> Asset:
    r = run([PY, TTAGENT, url_or_id, "--out", out_dir, "--json", "--quiet"])
    d = json.loads(r.stdout)                     # exit 1 = honest empty (skip, log)
    if d["status"] != "ok": return None
    assert d["video_file"], "photo/slideshow post — engine is video-only, skip"
    return Asset(path=f"{out_dir}/{d['video_file']}", platform="tiktok",
                 meta=json.load(open(d["manifest_path"])))   # title/stats/author/music
```

### 3.4 Risks/limits

- Mirrors are "borrowed ground": tikwm rate-limits and rotates; region walls are real; embed hydration often an empty shell from datacenter IPs. Envelope reports which slot produced what (`metadata.decode_slots_tried`).
- Photo/slideshow posts yield images — the engine must filter to `video_file != None` (its "no still images" rule).
- Livestreams/private accounts out of scope (no auth by design). Music download is a bonus but also a rights trap — don't ship TikTok music into final films.
- No resolution choice (what the mirror serves is what you get).

---

## 4. igagent — Instagram sourcing

Repo: https://github.com/Bilal140202/igagent · v1.0.0 · MIT · Python 3.9+, stdlib-only single file `igagent.py` (1175 lines) + `mcp_server.py` + PyPI `igagent`.

### 4.1 Invocation

```bash
python igagent.py "<input>" [--out DIR] [--no-download] [--json] [--quiet]
# inputs: instagram.com /p|reel|reels|tv/<code>/ · m./l./ddinstagram/instagr.am mirrors
#         · share links (instagram.com/share/<token>/, 1 hop) · bare shortcodes
#         (5–32 chars A-Za-z0-9_- that decode to a positive media id)
# exit: 0 ok/partial · 1 empty · 2 invalid
```

Output `post_manifest.json` + files; summary JSON has `post_type` (`image`/`video`/`carousel`), `media.images[] / media.videos[]` with `url / file / downloaded / downloadable / reason`, `carousel{known, child_count}`, author with explicit nulls, `errors[]`, `metadata.decode_slots_tried`. Shortcode ↔ media-id conversion is pure base64 math, cross-checked against Instagram's `ig_cache_key`.

### 4.2 Decode slots (embed-based, no login)

```python
# Slot 1 embed_json: https://www.instagram.com/{p|reel|tv}/<code>/embed/captioned/
#   mines window.__additionalDataLoaded('extra', {...}) / "contextJSON":"..."
#   / "items":[{ — deepest source: caption, metrics, sidecar children, author
# Slot 2 embed_html: unfurler SSR page — regexes for class="EmbeddedMediaImage",
#   EmbeddedMediaVideo (src|data-video-src), ViewProfileButton (author),
#   FollowerCountText, ig_cache_key
# Slot 3 og_meta: OpenGraph og:image, og:video:secure_url (floor)
DECODE_SLOT_FNS = [_fetch_embed_json, _fetch_embed_html, _fetch_og_meta]
```

Delivery: CDN allowlist **only** `.cdninstagram.com` / `.fbcdn.net`; same `.part` → Content-Length → magic-bytes → `os.replace` chain. Carousel membership only from `edge_sidecar_to_children` (never inferred). MCP tools: `extract_post`, `lookup_post`, `read_manifest`, `get_schema`.

### 4.3 Integration recipe

```python
def fetch_instagram(url, out_dir) -> Asset | None:
    d = json.loads(run([PY, IGAGENT, url, "--out", out_dir, "--json", "--quiet"]).stdout)
    if d["status"] != "ok": return None
    videos = [m for m in manifest_media(d) if m["type"] == "video" and m.get("downloaded")]
    return Asset(video_files=videos) if videos else None   # engine is video-only
```

### 4.4 Risks/limits

- The embed surface is the **only honest no-auth door**; login walls surface as `requires_auth` (never bypassed); stories rejected at identity level. Deep payload increasingly rare (client-side moves) → often you get just the SSR video URL.
- **No reels pagination/search** — it's a per-URL harvester; the engine must supply URLs (from its own discovery/search step).
- Carousel/image posts must be filtered out for video-only builds.

---

## 5. xthread-agent — X/Twitter sourcing

Repo: https://github.com/Bilal140202/xthread-agent · v3.2.0 · MIT · Python 3.9+, stdlib-only single file `xthread-agent.py` (982 lines) + PyPI `xthread-agent` + MCP + docs site.

### 5.1 What it does / invocation

```bash
python3 xthread-agent.py "https://x.com/<user>/status/<id>" --out media/ [--json] [--quiet]
```

Reconstructs a full public thread (posts, authors, timestamps, quoted posts, self-reply chain), downloads every photo AND video from `pbs.twimg.com`/`video.twimg.com` (allowlist `MEDIA_HOST_SUFFIX = ".twimg.com"`), writes `thread_manifest.json` (schema 3.0, draft-07 validated). 24 URL forms accepted; `t.co` expanded one hop (`expand_tco` follows the interstitial). Largest live-verified transfer: 167 MB 4K MP4 (atomic, Content-Length verified).

### 5.2 API approach (2026 autopsy, from README + source)

X's GraphQL is walled: gallery-dl guest tokens dead, yt-dlp on status URLs dead, Nitter dead, direct scrape = empty shell on datacenter IPs. What still works:

```python
WALKER_SLOTS = (("unrollnow", "https://unrollnow.com/status/{root}"),
                ("threadreaderapp", "https://threadreaderapp.com/thread/{root}"))
# decoder slots:
def _fetch_fxtweet(tid, tries):
    url = f"https://api.fxtwitter.com/status/{tid}"
    # code 200 + tweet dict = ok; 404 (body or HTTP) = 'unavailable' — FILTER signal
    # (recommendation candidates die silently here), never retried
def _fetch_vxtweet(tid, ...):   # fallback: https://api.vxtwitter.com/... normalized
    ...                          # into the FixTweet shape with explicit nulls
# chain membership from data relations: post["replying_to_status"] links, not page order
```

Bounds: `MAX_CANDIDATES=50`, `MAX_ANCESTORS=25`, `WALK_MAX_BYTES=20 MB`, `DECODE_MAX_BYTES=5 MB`, `DOWNLOAD_TIMEOUT=180`, decode sleep 0.6 s. Videos mapped via `_best_mp4_variant` (picks highest-bitrate mp4 variant). Statuses: `ok | partial | empty` with stable error codes (`E_ROOT_UNAVAILABLE`, `E_WALKER_UNAVAILABLE`, `E_WALKER_EMPTY`, `E_DECODE_FAILED`, ...).

### 5.3 Integration recipe

```python
def fetch_x(url, out_dir) -> Asset | None:
    d = json.loads(run([PY, "xthread-agent.py", url, "--out", out_dir, "--json"]).stdout)
    vids = [v for p in d["posts"] for v in p["media"]["videos"] if v.get("downloaded")]
    return Asset(video_files=vids, thread_text=[p["text"] for p in d["posts"]]) if vids else None
```

### 5.4 Risks/limits

- Depends on third-party mirrors (UnrollNow embeds *recommendations* — filtered by 404-as-filter logic but the walker is the fragile part; ThreadReaderApp fallback exists).
- **No search** — per-status-URL harvesting only; engine needs its own tweet discovery (e.g., via its research layer).
- Photo-only threads → `videos: []` → engine skips (video-only rule).
- Note: despite the name, this repo covers **X/Twitter threads**; Meta-Threads support lives in `uaal` (official `/embed` surface), not here.

---

## 6. personal-social-agent — orchestration architecture to steal

Repo: https://github.com/ansaribilal14/personal-social-agent · MIT · Python 3.10+ · 246 tests. (README + docs/ARCHITECTURE.md + scripts/run_pipeline.py only, per scope.)

### 6.1 What it is

An editorial pipeline OS for X + Threads: NVIDIA NIM (generation) → Buffer (publishing) → GitHub Actions (12 cron/issue_comment workflows) → Discord (human review cards) → Postgres/Supabase (state; SQLite default). **"AI does the work. The system enforces the rules. You own the publish button."**

### 6.2 Orchestration mechanics worth transplanting

- **Stage runner** — one CLI drives every stage:

```bash
python scripts/run_pipeline.py --stage research|ideas|generate|quality|review|iterate \
    |approval|schedule|publish|analytics|weekly-report|maintenance
# each stage = an idempotent pipeline class in src/pipeline/production.py, returns JSON
# AI stages BLOCK cleanly when NVIDIA_API_KEY is absent (no fake outputs)
```

- **Explicit 20-state content machine** (`src/state/machine.py`): `DISCOVERED → CANDIDATE → RESEARCHED → STRATEGIZED → DRAFTED → QUALITY_REVIEW → QUALITY_PASSED → EDITORIALLY_RANKED → WAITING_APPROVAL → APPROVED → SCHEDULED → PUBLISHING → PUBLISHED` + side states (`QUALITY_FAILED/REVISING`, `ITERATING`, `REJECTED/CANCELLED/BLOCKED/PUBLISH_FAILED`). Invariants enforced in code and proven by tests: APPROVED reachable only from WAITING_APPROVAL; PUBLISHED only from PUBLISHING; every invalid transition raises; "approving v1 never authorizes v2".
- **Idempotent outbox**: `publication_outbox.idempotency_key UNIQUE = post_uid:platform:version`; atomic claim via conditional `UPDATE ... WHERE status IN (...)` — exactly one runner wins; bounded exponential backoff; failure alerts to Discord.
- **Kill switch**: `SOCIAL_AUTOMATION_ENABLED` in DB, **re-read immediately before scheduling and before publishing** (never cached); DB unreadable ⇒ publishing blocked (fail-safe).
- **Deterministic quality gates** — the LLM never counts characters; 7 critic classes/10 roles return `{passed, score, issues, evidence, recommended_changes}`; hard gates (platform_fit, antislop, fact) fail regardless of score; bounded revision loop (default 2 cycles) then BLOCKED; anti-slop regex gates (press-release cadence, abstract-noun soup, meta-labels).
- **Config-as-YAML** (`config/*.yml` for platforms/strategy/voice/quality/schedule/security), versioned prompt library (`prompts/library.yml` snapshotted onto every generated version), prompt-injection defense for external content (UNTRUSTED_DATA delimiters, contamination flagging, comment bodies reach Python via env vars only).

### 6.3 Integration recipe (for last-stop-yt-engine)

```python
# Adopt, in order of value:
# 1. state machine: SCRIPTED → SOURCED → CHARACTER_LOCKED → NARRATED → RENDERED
#    → QC_PASS → WAITING_HUMAN_APPROVAL → PUBLISHED (invalid transitions raise)
# 2. idempotent render/publish outbox keyed (episode, cut_version) — a cut ships once
# 3. kill switch re-read immediately before any upload/publish call
# 4. deterministic validators for the engine's own hard rules:
#      - video_only: every shot asset kind == 'video' (checked in code, not by LLM)
#      - character_lock: shot.time_range ⊆ locked_scene[entity] (join in SQL/code)
# 5. Discord (or Telegram) review card with approve/reject/iterate for each cut
# 6. budget-limited resumable rounds (also see CCE scripts/driver.py: BUDGET_S=210,
#    STEP_CAP=170, re-invoke to continue — survives sandbox tool-call timeouts)
```

### 6.4 Risks/limits

Heavy infra coupling (NIM/Buffer/Discord/Supabase) — adopt patterns, not the stack; the media pipeline here is zero (text-only domain); 12 GitHub workflows are opinionated.

---

## 7. uaal — the generalized universal layer

Repo: https://github.com/ansaribilal14/uaal · v2.0.0 · MIT · **Node ≥ 20.10, TypeScript** (`npm install -g uaal`; bins `uaal`, `uaal-worker`).

### 7.1 What it is

"Universal Agent Access Layer" — the design patterns of ytagent/xthread-agent/ttagent/igagent generalized into one platform-independent core: discovery → route selection → multi-route execution → evidence → reconstruction → normalization → **method-blind verification** → artifact. 8 built-in adapters (YouTube, TikTok, Douyin, X, Instagram, Threads, Reddit, Generic-Web), 40+ independent routes; YouTube adapter family is explicitly the ytagent method chain (InnerTube ANDROID_VR→IOS, yt-dlp profiles, Piped, Invidious `local=true`, Cobalt sidecar, optional yt-dlp quality upgrade). Interfaces: CLI (`uaal resolve|inspect|acquire|health|platforms|routes|capabilities`), HTTP API (`uaal serve --port 7800`), MCP (`uaal mcp` — 8 tools), in-process TS lib (`UAAL.create()`). Src layout: `src/core/{engine,router,verify/{file,media},learning,policy,security,jobs,sessions,cache,contracts,schemas...}`, `src/adapters/{youtube,tiktok,douyin,x,instagram,threads,reddit,generic-web}`.

### 7.2 What's worth stealing (even if you never run Node)

1. **The status vocabulary — every operation returns exactly one of:** `ok | partial | empty | failed | unsupported | requires_auth | blocked`. This is the cleanest failure contract for a sourcing layer; adopt it verbatim in the engine's asset manifest.
2. **The 10 design rules** (README): one platform ≠ one method; one failed method ≠ failed resource; HTTP success ≠ resource success; downloaded file ≠ verified artifact; chain membership from data relations; no LLM in the core; learning reorders routes, never removes; `partial` is first-class; unknown ≠ success (fail closed); fail honestly.
3. **Route-level provenance** in every result (`attempts: [{route, failureCode}]`) and a per-platform endpoint matrix doc kept as a living maintenance protocol.
4. **`docs/PLATFORMS.md` knowledge**: e.g., Instagram = only honest no-auth surface is `/embed/captioned`; Douyin `iesdouyin` play endpoint with mobile profile; TikTok `tikwm.acquire` gives no-watermark mp4 + slideshow photos.

### 7.3 Integration option

```ts
const uaal = await UAAL.create({ config: { logLevel: "info" } });
const res = await uaal.acquire({ resource: url, capability: "acquire" });
// res.status ∈ ok|partial|empty|failed|unsupported|requires_auth|blocked
// res.artifacts[] verified files; res.attempts[] route provenance
```

If the engine is Python-first (it is, given CCE), prefer the four Python agents and only borrow uaal's contracts/statuses; if a polyglot deploy is acceptable, uaal can replace all four single-platform agents behind one HTTP/MCP boundary.

### 7.4 Risks/limits

Node ≥ 20.10 runtime (separate from the Python stack); same mirror volatility as its parents; adapters declare per-platform capability limits (`uaal capabilities` prints the live matrix).

---

## 8. Cross-cutting synthesis for last-stop-yt-engine

### 8.1 The sourcing backbone (video-only, 4 platforms)

| platform | tool | quality ceiling | key risk | filter for video-only |
|---|---|---|---|---|
| YouTube | `ytagent` (via CCE `downloader.py`) | up to 1080p (POT), 720p/360p bypass tiers | bot-check on datacenter IP | always video |
| TikTok | `ttagent` | mirror-served (HD via tikwm) | mirror rotation/regions | require `video_file`; skip `images>0` |
| Instagram | `igagent` | embed-served mp4 | login walls (`requires_auth`) | require `media.videos[]` non-empty |
| X | `xthread-agent` | up to 4K mp4 via FixTweet | walker/decoder mirrors | require `media.videos[]` non-empty |

Common contract to enforce engine-side (borrowed from all four): **JSON envelope on stdout, logs on stderr; stable error codes; status ∈ {ok, partial, empty, failed, unsupported, requires_auth, blocked}; per-attempt provenance; files verified (magic bytes + ffprobe + A/V parity) before promotion.**

### 8.2 The character-lock subsystem (the differentiator)

Only CCE solves it. Concretely:
1. **Reference build once per subject**: `refs.ensure_references(ws, "jennie", ref_images=[...])` → centroid + verified crops + contact sheet; audit with cross-member separation.
2. **Per source video**: normalize → shots → 2 fps InsightFace → `analysis.jsonl` → `raw_visibility.json` → `grouped_scenes.json`. The grouped scenes ARE the character-lock map.
3. **Bind narration→scenes**: a shot may back a narration line about entity E only if the shot's window ⊆ a grouped scene of E (confidence ≥ threshold). No scene ⇒ rewrite narration or drop the line — **never a still image, never a wrong face**.
4. **Post-render QC**: re-run face match on sampled frames of the final cut within narration spans; fail the build under threshold.
5. Multi-character episodes: matching already scores every known member per face — aggregate per member to build all subjects' maps in one pass.

### 8.3 Engineering discipline to adopt

- CCE: sentinel auto-resume everywhere; frame-level JSONL resume with torn-line truncation; atomic `.part`+`os.replace` writes; ffprobe re-verification of leftovers; spaced retries ("throttles often lift with spacing"); budget-limited resumable driver rounds; honest RAW vs GROUPED reporting; human-override file (`review_verified.json`).
- ytagent: never trust a method's self-report (6-layer verifier); Truth-Agent rank learning (demote after 3 consecutive failures); per-method temp isolation + atomic final move; BGutil POT auto-bootstrap.
- personal-social-agent: state machine + idempotent outbox + kill switch re-read + deterministic validators for the engine's hard rules + human approval gate.
- uaal: unified status vocabulary + route provenance as the manifest schema.

### 8.4 Consolidated dependency/install sheet

```bash
# System
apt install ffmpeg nodejs npm git            # ffmpeg for CCE/ytagent; node for BGutil POT
# Python (3.10+ for CCE; 3.11+ for ytagent)
pip install numpy opencv-python insightface onnxruntime "scenedetect>=0.7" \
            yt-dlp ytagent-cli requests       # CCE requirements.txt
# The four platform harvesters are stdlib-only: no pip (run the single files or
# pip install ttagent / igagent / xthread-agent / ytagent-cli from PyPI)
# Node (optional, for uaal): npm install -g uaal   (Node >= 20.10)
# Env secrets (never commit): CCE_TG_TOKEN, CCE_TG_CHAT, CCE_GH_TOKEN (farm),
# CCE_FARM_OWNER/CCE_FARM_REPO, YTAGENT_BGUTIL_HOME, CCE_VISITOR_TOKEN_FILE
```

### 8.5 Top risks for the engine (aggregated)

1. **Datacenter-IP YouTube throttling** is the #1 operational risk; mitigations proven in-repo: BGutil POT + android_vr, spaced retries, relay tiers, GH farm. Resolution may honestly degrade to 720p.
2. **Mirror volatility on TikTok/X** — slots rotate; keep the endpoint-matrix maintenance protocol and slot replacement pattern.
3. **Face-match threshold transfer** — 0.42 was tuned on idol faces; calibrate per documentary subject using CCE's own contact-sheet/QC artifacts.
4. **Short appearances** (< ~1 s) can be missed at 2 fps; mitigate with padding, grouping, and the human-review override file.
5. **Hard-coded constants & default paths** in CCE scripts (`/home/z/my-project/clipextractor`, ytagent's `/home/z/my-project/ytdl-agent`) — always set the env vars.
6. **No search/discovery in ttagent/igagent/xthread-agent** — they are per-URL harvesters; the engine needs its own discovery layer feeding them URLs.
7. None of the repos push still images anywhere — but igagent/ttagent/xthread-agent happily download images; the engine's video-only gate must be a deterministic validator (personal-social-agent pattern), not a prompt.

### 8.6 Open follow-ups (next actions)

1. Vendor CCE's `scripts/` + `character_clip_extractor/` into the engine (or pin as submodule) and expose `run_pipeline()` as the character-lock service; add a config layer for its hard-coded thresholds.
2. Stand up the BGutil POT provider as a long-lived sidecar at boot (CCE `ensure_pot()` / ytagent `ytagent setup`) and health-check it in CI.
3. Prototype `bind_narration_to_visuals()` against `grouped_scenes.json` + an SRT to prove the character-lock invariant end-to-end on one episode.
4. Decide Python-direct (4 agents) vs uaal-as-a-service for sourcing; either way, adopt the unified status envelope.
5. Wire delivery: engine-internal artifacts (skip CCE's Telegram/storage.to unless used as the human-review transport).
