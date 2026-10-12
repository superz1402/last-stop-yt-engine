# OPS — running the cycle for real

## Where things run

| Work | Where | Why |
|---|---|---|
| S0–S3 authoring | laptop / editor | human-quality writing |
| S4 downloads | Actions runner | ytagent farm methods expect clean IPs |
| S5–S6 face passes | Actions runner | CPU-bound 1080p decode |
| S7 voice | either | edge-tts is light |
| S10 render | Actions runner | x264 1080p ≈ 2–3× realtime on 4 cores |
| S11–S12 QC/publish | Actions runner | release surgery where the file is |

`.github/workflows/build-documentary.yml` = `workflow_dispatch` with
`project` input. 350-min timeout, `contents: write`, apt ffmpeg + fonts,
pip from `requirements.txt`, one job, resumable stages throughout.

## Cost/time budget (34-min film, 4-core runner)

| Stage | Budget |
|---|---|
| pip/apt setup | ~6 min |
| downloads (20 sources) | 25–40 min |
| face pass (≈90 min of video @2fps, single-pass) | 25–35 min |
| scene mode (remaining sources) | 8–12 min |
| voice (72 blocks) | 4–6 min |
| storyboard | < 1 min |
| render phase 1 (≈360 slots) | 45–70 min |
| render phases 2–3 | 25–40 min |
| QC + release | 4–6 min |
| **total** | **≈ 2.5–3.5 h** |

## Known ceilings (honest)

- **UMG stream-gating**: some label-claimed uploads return empty format
  lists / GVS 403 from datacenter IPs. Manifest marks `gating_risk: high`;
  alternates always declared. If a required source dies, the build fails
  loudly rather than shipping holes.
- **Runner wall-clock**: all stages resumable; a timeout re-run continues,
  it never restarts from zero.
- **edge-tts network flake**: per-block retry ×3, then hard fail (voice is
  the spine of the film — silent fallbacks would violate R5).

## Provenance & takedown protocol

`sources.yaml` is the registry. QC emits `used_sources` in the report. If a
source gets struck, remove it from the manifest, re-dispatch — the storyboard
rebuilds from the surviving pool (min-coverage gates protect the film).
