"""R1/R2 rule enforcement — the no-image gate and the lock auditor."""
from __future__ import annotations
import json
from pathlib import Path

from .config import Project


class NoImageViolation(RuntimeError):
    pass


class LockViolation(RuntimeError):
    pass


def audit_no_images(timeline: dict) -> int:
    """SYSTEM_RULES R1: every visual slot must be kind == video."""
    bad = []
    for i, slot in enumerate(timeline.get("clips", [])):
        for v in slot.get("visuals", []):
            if v.get("kind") != "video":
                bad.append((i, v.get("kind"), v.get("asset_id", "?")))
    if bad:
        raise NoImageViolation(
            f"{len(bad)} non-video slots found (R1 violation): {bad[:5]}")
    return len(bad)


def audit_lock(project: Project, timeline: dict) -> dict:
    """SYSTEM_RULES R2: every slot's clip entity must resolve into the
    narration block's on_screen set. Recomputed independently of the
    storyboard builder (reelmimic fresh-reviewer rule)."""
    pool = {}
    clips_path = project.build / "clips.json"
    if clips_path.exists():
        for c in json.loads(clips_path.read_text()).get("clips", []):
            pool[c["clip_id"]] = c
    bad, checked = [], 0
    for slot in timeline.get("clips", []):
        want = slot.get("on_screen", [])
        for v in slot.get("visuals", []):
            checked += 1
            ent = v.get("entity")
            if ent is None:
                cid = v.get("clip_id")
                ent = pool.get(cid, {}).get("entity")
            if not project.resolve_compatible(ent, want):
                bad.append({"t": round(slot.get("t", -1), 1),
                            "block": slot.get("beat_id"),
                            "on_screen": want, "clip_entity": ent})
    if bad:
        raise LockViolation(
            f"{len(bad)}/{checked} slots break the character lock (R2): "
            f"{json.dumps(bad[:5])}")
    return {"checked": checked, "violations": 0}
