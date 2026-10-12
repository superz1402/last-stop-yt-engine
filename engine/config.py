"""last stop yt engine — core config & paths."""
from __future__ import annotations
import json, os, subprocess
from pathlib import Path

ENGINE_ROOT = Path(__file__).resolve().parent.parent
BUILD = "build"

VOICE_DEFAULT = "en-US-AndrewMultilingualNeural"
TARGET_FPS = 30
W, H = 1920, 1080
LOUDNORM = "I=-14:TP=-1.5:LRA=11"


class Project:
    def __init__(self, project_dir: Path):
        self.dir = Path(project_dir).resolve()
        if not self.dir.exists():
            raise FileNotFoundError(f"project dir not found: {self.dir}")
        import yaml
        self.cfg = yaml.safe_load((self.dir / "project.yaml").read_text())
        self.slug = self.cfg.get("slug") or self.dir.name
        self.build = self.dir / BUILD
        self.done_dir = self.build / ".done"
        self.sources_manifest = yaml.safe_load((self.dir / "sources.yaml").read_text())
        self.entities_cfg = yaml.safe_load((self.dir / "entities.yaml").read_text())

    # ---- paths -------------------------------------------------
    def path(self, *parts) -> Path:
        p = self.dir.joinpath(*parts)
        p.parent.mkdir(parents=True, exist_ok=True)
        return p

    def done_path(self, stage: str) -> Path:
        self.done_dir.mkdir(parents=True, exist_ok=True)
        return self.done_dir / f"{stage}.done"

    def is_done(self, stage: str) -> bool:
        return self.done_path(stage).exists()

    def mark_done(self, stage: str, note: str = "") -> None:
        self.done_path(stage).write_text(f"{note}\n")

    # ---- entity graph ------------------------------------------
    def entity_label(self, key: str) -> str:
        e = self.entities_cfg.get("entities", {}).get(key, {})
        return e.get("label", key)

    def resolve_compatible(self, clip_entity: str, block_entities: list[str]) -> bool:
        """R2 lock: is a clip tagged clip_entity allowed on a block tagged block_entities?"""
        ents = self.entities_cfg.get("entities", {})
        for want in block_entities:
            if clip_entity == want:
                return True
            we = ents.get(want, {})
            ce = ents.get(clip_entity, {})
            # clip is a member of a wanted group  (block=blackpink:group, clip=jennie)
            if clip_entity in we.get("members", []):
                return True
            # clip is the group, block names a member of it (block=jennie, clip=blackpink:group)
            if want in ce.get("members", []):
                return True
            # umbrella: block names umbrella org, clip is one of its subjects
            if clip_entity in we.get("umbrella_for", []):
                return True
            # block names a subject, clip is its declared umbrella
            for u in ce.get("umbrellas", []):
                if u in block_entities:
                    return True
        return False


def probe_media(path: Path) -> dict:
    """ffprobe a media file, return parsed json (streams+format)."""
    cmd = ["ffprobe", "-v", "quiet", "-print_format", "json",
           "-show_format", "-show_streams", str(path)]
    out = subprocess.run(cmd, capture_output=True, text=True)
    if out.returncode != 0:
        return {}
    return json.loads(out.stdout or "{}")


def media_duration(path: Path) -> float:
    info = probe_media(path)
    try:
        return float(info["format"]["duration"])
    except (KeyError, ValueError, TypeError):
        for s in info.get("streams", []):
            if "duration" in s:
                try:
                    return float(s["duration"])
                except ValueError:
                    pass
    return 0.0


def run(cmd: list[str], **kw) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True, **kw)


def human_s(sec: float) -> str:
    m, s = divmod(int(round(sec)), 60)
    h, m = divmod(m, 60)
    return f"{h:d}:{m:02d}:{s:02d}" if h else f"{m:d}:{s:02d}"
