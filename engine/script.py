"""S2 SCRIPT — parse script.md into blocks.json.

script.md format (strict):

    ## b01 :: Cold Open :: on_screen=blackpink:group
    Narration paragraph. One block = one paragraph.

Rules enforced here:
  - research artifact must exist (R3)
  - every block has non-empty on_screen tags
  - every on_screen tag exists in entities.yaml
  - word counts are computed by code, never by an LLM
"""
from __future__ import annotations
import json, re

from .config import Project

BLOCK_RE = re.compile(r"^##\s+(\w+)\s*::\s*(.+?)\s*::\s*on_screen=(.+?)\s*$")


def parse(project: Project) -> dict:
    research = sorted((project.dir / "research").glob("*.md"))
    if not research:
        raise RuntimeError("R3 violation: no research artifact in research/")
    script_path = project.dir / "script" / "script.md"
    if not script_path.exists():
        raise RuntimeError(f"missing script: {script_path}")

    known = set(project.entities_cfg.get("entities", {}).keys())
    blocks, cur = [], None
    for raw in script_path.read_text().splitlines():
        m = BLOCK_RE.match(raw.strip())
        if m:
            if cur:
                blocks.append(cur)
            bid, section, tags = m.group(1), m.group(2), m.group(3)
            on = [t.strip() for t in tags.split(",") if t.strip()]
            cur = {"id": bid, "section": section, "on_screen": on, "text": ""}
        elif cur is not None and raw.strip():
            cur["text"] = (cur["text"] + " " + raw.strip()).strip()
    if cur:
        blocks.append(cur)

    if not blocks:
        raise RuntimeError("script.md has no parseable blocks")

    words = 0
    for b in blocks:
        if not b["text"]:
            raise RuntimeError(f"block {b['id']} has no narration text")
        if not b["on_screen"]:
            raise RuntimeError(f"block {b['id']} has no on_screen tags (R2)")
        for t in b["on_screen"]:
            if t not in known:
                raise RuntimeError(f"block {b['id']}: unknown entity '{t}'")
        b["words"] = len(b["text"].split())
        words += b["words"]

    out = {"project": project.slug, "blocks": blocks,
           "word_count": words,
           "est_minutes": round(words / 150.0, 1)}
    project.build.mkdir(parents=True, exist_ok=True)
    (project.build / "blocks.json").write_text(json.dumps(out, indent=2))
    return out
