# SOURCING LADDER — how this engine gets real video

Distilled from `ytagent`, `ttagent`, `igagent`, `xthread-agent`,
`personal-social-agent`, `uaal` (full annex: `annex-R1-sourcing-and-character.md`).

## The ladder (in order, videos only — see SYSTEM_RULES R4)

1. **ytagent core** — `pip install ytagent-cli`, then:

```bash
ytagent download "<url>" --out-dir D \
  --format "bv*[ext=mp4][height<=1080]+ba[ext=m4a]/b[height<=1080]/b" \
  --timeout 180 --json
```

13-method fallback chain (android_vr + BGutil PO-token → jsless → ios →
single-file → audio → innertube → cobalt relays → piped → invidious local →
SOCKS5 farm → Actions farm), 6-layer output verification (≥1 MB, magic bytes,
ffprobe, duration, stream, moov atom), JSON verdict `{ok, final_path,
method_used, attempts[]}`. Public videos only. Datacenter IPs may degrade to
720p/360p — acceptable for face-pass analysis; prefer 1080p for hero shots.

2. **Plain yt-dlp** with tightened format selector — the bridge of last resort
   before mirrors (kept for when ytagent internals lag YouTube).
3. **Mirrors** (cobalt/piped/invidious) — already inside ytagent's chain; the
   engine only calls ytagent, never raw mirrors, for provenance clarity.

## Cross-platform agents (when the subject lives there)

- **ttagent** — TikTok via tikwm slot, prefers `hdplay`/`play` (no watermark),
  falls back `wmplay`. Stdlib-only, JSON envelope on stdout, exit 0/1/2.
- **igagent** — Instagram `/embed/captioned` scraping; login walls surface as
  `requires_auth` (never fake them away).
- **xthread-agent** — X GraphQL is dead; walks UnrollNow/ThreadReaderApp,
  decodes FixTweet/vxtwitter media.
- **uaal** — the status vocabulary to copy everywhere:
  `ok|partial|empty|failed|unsupported|requires_auth|blocked`.
- **personal-social-agent** — the discipline: deterministic validators,
  idempotent outbox, kill-switch re-read. The engine's `.done` markers and
  QC gates are this pattern applied to film.

## Engine adaptations (hardened)

- Every downloaded file passes: magic bytes → ffprobe (video+audio stream
  present) → duration > 0 → height ≥ 480 gate for analysis copies.
- Per-source `.done` markers; a failed source is logged and skipped, never
  half-usable (no partially-written mp4 ever enters the pool).
- `sources.yaml` entries carry `required: true|false`. The build fails only if
  a `required` source fails or the surviving pool cannot satisfy
  `min_clips_per_entity`.
- UMG/stream-gating ceiling (empty format lists, GVS 403 on some
  label-claimed uploads) is a known, documented limit — the manifest marks
  risky sources with `gating_risk: high` and always ships alternates.
