"""S5 REFS — face centroids via solo-MV dominant-cluster bootstrap
(identity grounding needs zero hand-labeled photos) or vendored refs
(BABYMONSTER, from character-clip-extractor's references/).

Output per entity: build/refs/<entity>/{centroid.npy, refs.json, ref_XX.jpg}
"""
from __future__ import annotations
import json, math

import numpy as np

from .config import Project

FPS_AN = 2.0          # analysis frames per second
MIN_FACE_PX = 80      # CCE proven value
SKIP_EDGE_S = 15      # skip intro/outro of solo MVs (title cards, extras)

_faceapp = None


def faceapp():
    global _faceapp
    if _faceapp is None:
        from insightface.app import FaceAnalysis
        _faceapp = FaceAnalysis(name="buffalo_l",
                                providers=["CPUExecutionProvider"])
        _faceapp.prepare(ctx_id=-1, det_size=(640, 640))
    return _faceapp


def _embed(img) -> np.ndarray | None:
    """Largest face in frame → 512-d normalized embedding, or None."""
    try:
        faces = faceapp().get(img)
    except Exception:  # noqa: BLE001
        return None
    if not faces:
        return None
    f = max(faces, key=lambda x: (x.bbox[3] - x.bbox[1]))
    if (f.bbox[3] - f.bbox[1]) < MIN_FACE_PX:
        return None
    e = f.normed_embedding
    return e / (np.linalg.norm(e) + 1e-9)


def _iter_frames(path: str, fps_an: float = FPS_AN, skip_edge_s: float = 0.0):
    """Yield (t, bgr) at fps_an, streaming (no memory blowup)."""
    import cv2
    cap = cv2.VideoCapture(path)
    fps_src = cap.get(cv2.CAP_PROP_FPS) or 30.0
    total = cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0
    dur = (total / fps_src) if fps_src else 0.0
    step = max(1, int(round(fps_src / fps_an)))
    idx = 0
    while True:
        ok = cap.grab()
        if not ok:
            break
        t = idx / fps_src
        if idx % step == 0 and skip_edge_s <= t <= (dur - skip_edge_s if dur else 1e9):
            ok2, frame = cap.retrieve()
            if ok2:
                yield t, frame
        idx += 1
    cap.release()


def _dominant_cluster(embs: np.ndarray, merge_cos: float = 0.45,
                      outlier_cos: float = 0.35):
    """Greedy agglomerative on cosine similarity; return dominant cluster."""
    if len(embs) == 0:
        return None
    clusters: list[list[int]] = [[0]]
    cents = [embs[0].copy()]
    for i in range(1, len(embs)):
        sims = [float(np.dot(embs[i], c) /
                      ((np.linalg.norm(c) or 1e-9))) for c in cents]
        j = int(np.argmax(sims))
        if sims[j] >= merge_cos:
            clusters[j].append(i)
            ids = clusters[j]
            m = embs[ids].mean(axis=0)
            cents[j] = m / (np.linalg.norm(m) + 1e-9)
        else:
            clusters.append([i])
            cents.append(embs[i].copy())
    dom = max(range(len(clusters)), key=lambda j: len(clusters[j]))
    ids = np.array(clusters[dom])
    med = np.median(embs[ids], axis=0)
    med /= (np.linalg.norm(med) + 1e-9)
    keep = ids[[float(np.dot(embs[i], med)) >= 1 - outlier_cos for i in ids]]
    if len(keep) == 0:
        keep = ids
    return keep


def bootstrap_from_video(project: Project, entity: str, video_path: str) -> dict:
    import cv2
    out_dir = project.build / "refs" / entity
    out_dir.mkdir(parents=True, exist_ok=True)
    cj = out_dir / "refs.json"
    if cj.exists():
        return json.loads(cj.read_text())

    embs, frames = [], []
    for t, img in _iter_frames(video_path, skip_edge_s=SKIP_EDGE_S):
        e = _embed(img)
        if e is not None:
            embs.append(e)
            # store downscaled copy (memory cap); refs are detection tooling
            h, w = img.shape[:2]
            frames.append((t, cv2.resize(img, (640, max(1, int(640 * h / w))))))
            if len(frames) > 200:
                break
    if len(embs) < 12:
        raise RuntimeError(f"refs bootstrap {entity}: only {len(embs)} faces "
                           f"found in {video_path} — not enough")
    embs = np.array(embs)
    keep = _dominant_cluster(embs)
    if keep is None or len(keep) < 12:
        raise RuntimeError(f"refs bootstrap {entity}: dominant cluster too small")
    cen = embs[keep].mean(axis=0)
    cen = cen / (np.linalg.norm(cen) + 1e-9)
    # save up to 16 ref jpgs (internal detection tooling — never rendered, R1)
    np.save(out_dir / "centroid.npy", cen)
    sel = list(keep)[:16]
    import cv2
    for n, i in enumerate(sel):
        cv2.imwrite(str(out_dir / f"ref_{n:02d}.jpg"), frames[i][1])
    sims = [float(np.dot(embs[i], cen)) for i in keep]
    info = {"entity": entity, "source": "solo_bootstrap", "n_raw": len(embs),
            "n_refs": int(len(keep)),
            "mean_sim": round(float(sum(sims) / len(sims)), 4)}
    cj.write_text(json.dumps(info, indent=2))
    return info


def bootstrap_from_builtin(project: Project, entity: str, ref_dir) -> dict:
    out_dir = project.build / "refs" / entity
    out_dir.mkdir(parents=True, exist_ok=True)
    cj = out_dir / "refs.json"
    if cj.exists():
        return json.loads(cj.read_text())
    import cv2
    embs = []
    for jpg in sorted(ref_dir.glob("*.jpg")) + sorted(ref_dir.glob("*.png")):
        img = cv2.imread(str(jpg))
        if img is None:
            continue
        e = _embed(img)
        if e is not None:
            embs.append(e)
    if len(embs) < 4:
        raise RuntimeError(f"builtin refs for {entity}: too few usable images")
    embs = np.array(embs)
    keep = _dominant_cluster(embs, merge_cos=0.40)
    cen = embs[keep].mean(axis=0)
    cen = cen / (np.linalg.norm(cen) + 1e-9)
    np.save(out_dir / "centroid.npy", cen)
    for n, i in enumerate(list(keep)[:16]):
        pass  # builtin jpgs already exist upstream; not copied per-project
    info = {"entity": entity, "source": "builtin_refs", "n_raw": len(embs),
            "n_refs": int(len(keep)),
            "mean_sim": round(float(np.mean([embs[i].dot(cen) for i in keep])), 4)}
    cj.write_text(json.dumps(info, indent=2))
    return info


def ensure_all(project: Project, source_index: dict) -> dict:
    """Build every centroid demanded by sources with mode=character."""
    refs_cfg = project.cfg.get("refs", {})
    manifest = {e["id"]: e for e in project.sources_manifest["sources"]}
    report = {}
    needed = set()
    for e in project.sources_manifest["sources"]:
        if e.get("mode") == "character":
            needed.update(e.get("chars", []))
    for entity in sorted(needed):
        spec = refs_cfg.get(entity, {})
        try:
            if spec.get("builtin"):
                info = bootstrap_from_builtin(
                    project, entity,
                    project.dir.parent.parent / "engine" / "refs_builtin" / spec["builtin"])
            elif spec.get("solo_source"):
                src = source_index.get(spec["solo_source"], {})
                if not src.get("ok"):
                    raise RuntimeError(f"ref source {spec['solo_source']} unavailable")
                info = bootstrap_from_video(project, entity, src["path"])
            else:
                raise RuntimeError(f"no ref spec for {entity}")
            report[entity] = {"ok": True, **info}
            print(f"[refs] {entity}: {info['n_refs']} refs, sim {info['mean_sim']}", flush=True)
        except Exception as exc:  # noqa: BLE001
            report[entity] = {"ok": False, "error": str(exc)}
            print(f"[refs] {entity} FAILED: {exc}", flush=True)
            raise
    (project.build / "refs_report.json").write_text(json.dumps(report, indent=2))
    return report


def load_centroid(project: Project, entity: str) -> np.ndarray | None:
    p = project.build / "refs" / entity / "centroid.npy"
    if not p.exists():
        return None
    return np.load(p)
