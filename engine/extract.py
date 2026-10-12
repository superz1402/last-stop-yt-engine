"""S6 EXTRACT — the character-lock clip pool.

One decode pass per source video at 2 fps produces:
  - shot list (frame-diff scene cuts, ±0.5 s — fine for padded windows)
  - per-character visibility tracks (InsightFace 512-d, cosine vs centroid,
    threshold 0.42 — the proven character-clip-extractor values)
Then clip windows are built:
  character mode → member clips (visibility-merged, bridged, snapped) +
                   group shots (every shot of an entity-pure source)
  scene mode     → entity-level clips (merged/split to 2.5–9 s)
Every clip carries motion score (frame-diff mean) for the editor's
"every cut needs a carrier" rule.
"""
from __future__ import annotations
import json

import numpy as np

from .config import Project, media_duration
from .refs import faceapp, load_centroid, FPS_AN, MIN_FACE_PX

MATCH_THRESHOLD = 0.42   # CCE proven cosine threshold
BRIDGE_S = 1.0           # bridge gaps ≤ 1 s (CCE proven)
MIN_SEG_S = 1.0          # drop segments < 1 s (CCE proven)
CLIP_MIN_S, CLIP_MAX_S = 2.5, 9.0
SHOT_CUT_THRESHOLD = 30.0  # mean abs diff on 160x90 grayscale


def _decode_pass(path: str, mode: str, centroids: dict) -> dict:
    """Stream frames at 2 fps. Returns shots[], diffs[], matches{char:[]}."""
    import cv2
    cap = cv2.VideoCapture(path)
    fps_src = cap.get(cv2.CAP_PROP_FPS) or 30.0
    step = max(1, int(round(fps_src / FPS_AN)))
    idx, prev_small = 0, None
    ts, diffs = [], []
    matches = {c: [] for c in centroids}
    app = faceapp() if mode == "character" else None
    cent_keys = list(centroids)
    cent_mat = (np.array([centroids[c] for c in cent_keys])
                if centroids else None)

    while True:
        ok = cap.grab()
        if not ok:
            break
        if idx % step == 0:
            ok2, frame = cap.retrieve()
            if not ok2:
                idx += 1
                continue
            t = idx / fps_src
            small = cv2.resize(cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY), (160, 90))
            if prev_small is None:
                diffs.append(99.0)  # first frame = a "cut" (start of shot 0)
            else:
                diffs.append(float(np.abs(small.astype(np.int16) -
                                          prev_small.astype(np.int16)).mean()))
            ts.append(t)
            prev_small = small

            if app is not None and cent_mat is not None and len(cent_keys):
                hit = set()
                try:
                    faces = app.get(frame)
                except Exception:  # noqa: BLE001
                    faces = []
                for f in faces:
                    if (f.bbox[3] - f.bbox[1]) < MIN_FACE_PX:
                        continue
                    e = f.normed_embedding
                    e = e / (np.linalg.norm(e) + 1e-9)
                    sims = cent_mat @ e
                    j = int(np.argmax(sims))
                    if float(sims[j]) >= MATCH_THRESHOLD:
                        hit.add(cent_keys[j])
                for c in cent_keys:
                    matches[c].append(1 if c in hit else 0)
        idx += 1
    cap.release()
    return {"ts": ts, "diffs": diffs, "matches": matches,
            "dur": ts[-1] if ts else 0.0}


def _shots_from_diffs(ts: list[float], diffs: list[float]) -> list[list[float]]:
    cuts = [ts[i] for i, d in enumerate(diffs) if d >= SHOT_CUT_THRESHOLD]
    if not cuts:
        cuts = [ts[0]] if ts else []
    bounds = cuts + [ts[-1] + 0.5 if ts else 0.0]
    shots = []
    for a, b in zip(bounds, bounds[1:]):
        if b - a >= 0.5:
            shots.append([a, b])
    return shots


def _merge_visibility(ts: list[float], flags: list[int]) -> list[list[float]]:
    """CCE raw visibility: bridge ≤ BRIDGE_S gaps, drop < MIN_SEG_S segs."""
    if not flags:
        return []
    segs, start, last = [], None, None
    for t, f in zip(ts, flags):
        if f:
            if start is None:
                start = t
            elif t - last > BRIDGE_S:
                segs.append([start, last])
                start = t
            last = t
    if start is not None:
        segs.append([start, last])
    return [[a, b] for a, b in segs if b - a >= MIN_SEG_S]


def _window_clips(segs: list[list[float]], shots: list[list[float]],
                  fps_t: list[float], flags: list[int]) -> list[dict]:
    """Snap visibility segs to shot bounds; split into ≤CLIP_MAX_S windows."""
    out = []
    for a, b in segs:
        # pad ±0.6 s and snap to nearest shot boundaries
        a2 = min(s[0] for s in shots if s[0] <= a + 0.5) if shots else max(0.0, a - 0.6)
        b2 = max(s[1] for s in shots if s[1] >= b - 0.5) if shots else b + 0.6
        dur = b2 - a2
        if dur > CLIP_MAX_S:
            n = int(np.ceil(dur / CLIP_MAX_S))
            w = dur / n
            out += [[a2 + i * w, a2 + (i + 1) * w] for i in range(n)]
        else:
            out.append([a2, b2])
    # confidence from frame flags inside each window
    clips = []
    for a, b in out:
        ins = [f for t, f in zip(fps_t, flags) if a - 0.05 <= t <= b + 0.05]
        conf = (sum(ins) / len(ins)) if ins else 0.0
        if conf >= 0.55 and (b - a) >= CLIP_MIN_S:
            clips.append([a, b, round(conf, 3)])
    return clips


def _scene_clips(shots: list[list[float]]) -> list[list[float]]:
    """Merge tiny shots, split long ones → entity-level 2.5–9 s clips."""
    merged = []
    for a, b in shots:
        if merged and (b - merged[-1][0]) < CLIP_MIN_S:
            merged[-1][1] = b
        else:
            merged.append([a, b])
    clips = []
    for a, b in merged:
        dur = b - a
        if dur > CLIP_MAX_S:
            n = int(np.ceil(dur / CLIP_MAX_S))
            w = dur / n
            clips += [[a + i * w, a + (i + 1) * w] for i in range(n)]
        elif dur >= CLIP_MIN_S:
            clips.append([a, b])
    return clips


def extract_source(project: Project, entry: dict, path: str) -> list[dict]:
    mode = entry.get("mode", "scene")
    ents = entry.get("entity", "unknown")
    cent = {}
    if mode == "character":
        for c in entry.get("chars", []):
            e = load_centroid(project, c)
            if e is not None:
                cent[c] = e
        if not cent:
            raise RuntimeError(f"{entry['id']}: character mode but no centroids")
    pass_ = _decode_pass(path, mode, cent)
    shots = _shots_from_diffs(pass_["ts"], pass_["diffs"])
    clips = []

    def motion(a, b):
        ins = [d for t, d in zip(pass_["ts"], pass_["diffs"]) if a <= t <= b]
        return round(float(np.mean(ins)) if ins else 0.0, 1)

    if mode == "character":
        for c, flags in pass_["matches"].items():
            segs = _merge_visibility(pass_["ts"], flags)
            for a, b, conf in _window_clips(segs, shots, pass_["ts"], flags):
                clips.append({"entity": c, "start": round(a, 2),
                              "end": round(b, 2), "confidence": conf,
                              "kind": "member"})
        for a, b in shots:
            if (b - a) >= CLIP_MIN_S:
                clips.append({"entity": ents, "start": round(a, 2),
                              "end": round(b, 2), "confidence": 1.0,
                              "kind": "group"})
    else:
        for a, b in _scene_clips(shots):
            clips.append({"entity": ents, "start": round(a, 2),
                          "end": round(b, 2), "confidence": 1.0,
                          "kind": "scene"})

    for i, c in enumerate(clips):
        c["clip_id"] = f"{entry['id']}:{i:04d}"
        c["source_id"] = entry["id"]
        c["path"] = path
        c["title"] = entry.get("title", entry["id"])
        c["motion"] = motion(c["start"], c["end"])
        c["dur"] = round(c["end"] - c["start"], 2)
    return [c for c in clips if 1.8 <= c["dur"] <= 12.0]


def build(project: Project, source_index: dict) -> dict:
    manifest = project.sources_manifest["sources"]
    all_clips = []
    for entry in manifest:
        idx = source_index.get(entry["id"], {})
        if not idx.get("ok"):
            continue
        done = project.build / "sources" / f".extract_{entry['id']}.done"
        if done.exists():
            cached = json.loads((project.build / "clips.json").read_text()) \
                if (project.build / "clips.json").exists() else {"clips": []}
            all_clips += [c for c in cached["clips"]
                          if c.get("source_id") == entry["id"]]
            continue
        print(f"[extract] {entry['id']} ({entry.get('mode','scene')}) …", flush=True)
        try:
            got = extract_source(project, entry, idx["path"])
        except Exception as exc:  # noqa: BLE001
            print(f"[extract] {entry['id']} FAILED: {exc}", flush=True)
            if entry.get("required"):
                raise
            continue
        all_clips += got
        done.write_text(f"{len(got)} clips\n")
        print(f"[extract] {entry['id']}: {len(got)} clips", flush=True)

    # pool balance: cap per (source, entity) so one MV cannot flood the pool
    from collections import Counter
    cap = int(project.cfg.get("editing", {}).get("max_clips_per_source_entity", 60))
    seen = Counter()
    balanced = []
    for c in all_clips:
        k = (c["source_id"], c["entity"])
        if seen[k] < cap:
            seen[k] += 1
            balanced.append(c)
    all_clips = balanced

    pool = {"clips": all_clips, "total": len(all_clips)}
    (project.build / "clips.json").write_text(json.dumps(pool, indent=1))

    # per-entity usable coverage gate
    blocks = json.loads((project.build / "blocks.json").read_text())["blocks"]
    need = sorted({t for b in blocks for t in b["on_screen"]})
    min_n = int(project.cfg.get("min_clips_per_entity", 12))
    coverage = {}
    for ent in need:
        n = sum(1 for c in all_clips
                if project.resolve_compatible(c["entity"], [ent]))
        coverage[ent] = n
    poor = {e: n for e, n in coverage.items() if n < min_n}
    if poor:
        raise RuntimeError(f"clip pool too small for entities (min {min_n}): {poor}")
    report = {"total_clips": len(all_clips), "coverage": coverage,
              "entities_needed": need}
    (project.build / "extract_report.json").write_text(json.dumps(report, indent=2))
    print(f"[extract] pool={len(all_clips)} coverage={coverage}", flush=True)
    return report
