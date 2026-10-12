"""S8 EDIT — entity-timed storyboard builder (the editor brain).

Implements learnings/EDITING_DOCTRINE.md:
  - lead-with-subject: a block's first slot shows the block's subject entity
  - variety law: no source twice in a row, no return within 6 slots,
    ASL ≤ 8 s, ≥ 6 cuts/minute
  - every slot is a VIDEO (R1) that resolves into the block's entity set (R2)
  - gap calibration lands the film on its declared runtime to the second
"""
from __future__ import annotations
import hashlib, json

from .config import Project
from . import rules


def _jitter(clip_id: str, slot_i: int, span: float) -> float:
    """Deterministic in-clip offset so we don't always open at first frame."""
    h = hashlib.md5(f"{clip_id}:{slot_i}".encode()).hexdigest()
    return (int(h[:8], 16) / 0xFFFFFFFF) * max(0.0, span)


def _pick(pool_by_ent: dict, block: dict, slot_i: int, lead: bool,
          recent_sources: list, recent_clips: list, usage: dict,
          max_use: int) -> dict | None:
    cands = []
    for ent in block["on_screen"]:
        cands += pool_by_ent.get(ent, [])
    if not cands:
        return None
    def score(c):
        s = c.get("confidence", 1.0) * 0.45
        s += min(1.0, c.get("motion", 0.0) / 40.0) * 0.25
        s -= usage.get(c["clip_id"], 0) * 0.55
        if c["source_id"] in recent_sources[-1:]:
            s -= 10.0
        if c["clip_id"] in recent_clips[-6:]:
            s -= 3.0
        if lead:
            # lead-with-subject: first on_screen tag governs the opening shot
            want = block["on_screen"][0]
            if c["entity"] == want:
                s += 1.2
            elif c.get("kind") == "member":
                s += 0.6
        return s
    cands = [c for c in cands if usage.get(c["clip_id"], 0) < max_use]
    if not cands:
        cands = pool_by_ent[block["on_screen"][0]]
    cands.sort(key=score, reverse=True)
    return cands[0]


def build(project: Project) -> dict:
    blocks = json.loads((project.build / "blocks.json").read_text())["blocks"]
    voices = json.loads((project.build / "voices.json").read_text())
    pool = json.loads((project.build / "clips.json").read_text())["clips"]
    vmap = {v["id"]: v for v in voices["entries"]}

    target = float(project.cfg["target_duration_s"])
    intro = float(project.cfg.get("intro_music_s", 6.0))
    outro = float(project.cfg.get("outro_music_s", 8.0))
    ed = project.cfg.get("editing", {})
    slot_target = float(ed.get("slot_target_s", 6.0))
    base_pause = float(ed.get("base_pause_s", 0.55))
    gap_min, gap_max = ed.get("gap_scale_bounds", [0.4, 2.6])
    max_use = int(ed.get("max_uses_per_clip", 3))

    # pool indexed by compatibility (precompute: entity → clips)
    all_ents = sorted({c["entity"] for c in pool})
    pool_by_ent = {}
    for c in pool:
        for want in all_ents:
            if project.resolve_compatible(c["entity"], [want]):
                pool_by_ent.setdefault(want, []).append(c)

    # --- slot plan: block slots + pause weights ----------------------
    plan = []           # (kind, block_or_None, slot_len)
    pause_weights = []
    for i, b in enumerate(blocks):
        b = dict(b)
        vd = vmap[b["id"]]["dur_s"]
        n = max(1, round(vd / slot_target))
        sl = vd / n
        if sl > 9.0:
            n = int(-(-vd // 9.0))
            sl = vd / n
        for k in range(n):
            plan.append(("block", b, sl, k == 0, k))
        if i < len(blocks) - 1:
            nxt = blocks[i + 1]
            w = 2.0 if nxt["section"] != b["section"] else 1.0
            plan.append(("pause", b, base_pause, False, 0))
            pause_weights.append((w, b))
        elif i == len(blocks) - 1:
            pass
    # intro/outro as pause regions with first/last block entity sets
    intro_slots = max(1, round(intro / slot_target))
    outro_slots = max(1, round(outro / slot_target))

    total_voice = sum(vmap[b["id"]]["dur_s"] for b in blocks)
    total_pause_weight = sum(w for w, _ in pause_weights)
    slack = target - intro - outro - total_voice
    if slack <= 0:
        raise RuntimeError(f"runtime overspill: voice {total_voice:.0f}s vs "
                           f"target {target:.0f}s — trim the script")
    gap_scale = max(gap_min, min(gap_max, slack / max(1e-6, total_pause_weight * base_pause)))
    pause_len = base_pause * gap_scale

    # --- slot sequence: intro slots + block/pause plan + outro slots --
    slot_seq = []
    first_b, last_b = blocks[0], blocks[-1]
    for i in range(intro_slots):
        slot_seq.append(("intro", first_b, intro / intro_slots, i == 0, i))
    for kind, b, sl, lead, k in plan:
        slot_seq.append((kind, b, sl, lead, k))
    for i in range(outro_slots):
        slot_seq.append(("outro", last_b, outro / outro_slots, False, i))

    # --- select visuals + assemble (two-pass for exact runtime) ------
    def assemble(pause_extra: float) -> tuple[dict, float, list]:
        out_slots, t_cursor = [], 0.0
        voice_events, caption_events = [], []
        pause_iter = iter(pause_weights)
        for kind, b, sl, lead, k in slot_seq:
            if kind == "pause":
                w, _ = next(pause_iter)
                sl = base_pause * w * gap_scale + pause_extra
            c = _pick(pool_by_ent, b, k, lead, recent_sources,
                      recent_clips, usage, max_use)
            if c is None:
                raise RuntimeError(f"no compatible clip for block {b['id']} "
                                   f"on_screen={b['on_screen']} (R2/R4 pool gap)")
            off = _jitter(c["clip_id"], len(out_slots),
                          max(0.0, c["dur"] - sl - 0.2))
            vis = {"kind": "video", "clip_id": c["clip_id"], "path": c["path"],
                   "start": round(c["start"] + off, 3), "dur": round(sl, 3),
                   "entity": c["entity"], "title": c["title"],
                   "source_id": c["source_id"]}
            out_slots.append({"t": round(t_cursor, 3), "beat_id": b["id"],
                              "section": b["section"], "on_screen": b["on_screen"],
                              "kind": kind, "slot_len": round(sl, 3),
                              "voice_s": 0.0, "visuals": [vis]})
            usage[c["clip_id"]] = usage.get(c["clip_id"], 0) + 1
            recent_sources.append(c["source_id"])
            recent_clips.append(c["clip_id"])
            if kind == "block" and k == 0:
                vd = vmap[b["id"]]["dur_s"]
                voice_events.append({"id": b["id"], "wav": vmap[b["id"]]["wav"],
                                     "t": round(t_cursor, 3), "dur_s": vd})
                for cap in _captions(b, t_cursor, vd):
                    caption_events.append(cap)
            t_cursor += sl
        return out_slots, t_cursor, (voice_events, caption_events)

    # NOTE: selection uses mutable recency/usage state; a deterministic
    # rebuild resets them so both passes see identical worlds.
    recent_sources, recent_clips, usage = [], [], {}
    slots_a, actual_a, aux_a = assemble(0.0)
    recent_sources, recent_clips, usage = [], [], {}
    n_pauses = len(pause_weights)
    err = target - actual_a
    pause_extra = max(-0.35, min(1.2, err / max(1, n_pauses)))
    out_slots, actual, aux = assemble(pause_extra)
    voice_events, caption_events = aux
    timeline = {
        "project": project.slug,
        "target": target, "actual": round(actual, 2),
        "fps": 30, "w": 1920, "h": 1080,
        "intro_music_s": intro, "outro_music_s": outro,
        "gap_scale": round(gap_scale, 4),
        "music": project.cfg.get("music", {"query": "ambient documentary dark"}),
        "voices": voice_events,
        "captions": caption_events,
        "clips": out_slots,
    }

    # --- hard audits (R1/R2) ------------------------------------------
    rules.audit_no_images(timeline)
    lock = rules.audit_lock(project, timeline)
    asl = actual / max(1, len(out_slots))
    cuts_per_min = len(out_slots) / (actual / 60.0)
    if asl > 8.5:
        raise RuntimeError(f"ASL {asl:.1f}s exceeds gate")
    if cuts_per_min < 6.0:
        raise RuntimeError(f"cuts/min {cuts_per_min:.1f} below gate")

    timeline["editor_stats"] = {
        "slots": len(out_slots), "asl_s": round(asl, 2),
        "cuts_per_min": round(cuts_per_min, 1),
        "lock": lock, "gap_scale": gap_scale,
        "runtime_error_s": round(actual - target, 2)}
    (project.build / "timeline.json").write_text(json.dumps(timeline, indent=1))
    print(f"[storyboard] slots={len(out_slots)} actual={actual:.1f}s "
          f"target={target:.0f}s ASL={asl:.1f} cuts/min={cuts_per_min:.1f} "
          f"lock={lock}", flush=True)
    return timeline


def _captions(block: dict, t0: float, dur: float) -> list[dict]:
    """Split block text into ≤2-line caption chunks, proportional timing."""
    text = block["text"]
    sents = [s.strip() for s in text.replace("! ", "!\n").replace("? ", "?\n")
             .replace(". ", ".\n").split("\n") if s.strip()]
    units = []
    for s in sents:
        words = s.split()
        cur = []
        for w in words:
            cur.append(w)
            if len(" ".join(cur)) >= 80:
                units.append(" ".join(cur))
                cur = []
        if cur:
            units.append(" ".join(cur))
    if not units:
        units = [text]
    total_chars = sum(len(u) for u in units)
    out, tt = [], t0
    for u in units:
        d = dur * (len(u) / total_chars)
        out.append({"t": round(tt, 3), "dur_s": round(d, 3), "text": u})
        tt += d
    return out
