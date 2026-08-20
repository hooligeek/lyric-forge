"""Label configuration loading and path resolution.

The forge never hardcodes anything about a specific label. Everything it needs
comes from label/label.yaml, so this framework/ tree can be lifted into another
project untouched.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

import yaml

# framework/forge/config.py -> repo root is three parents up.
REPO_ROOT = Path(__file__).resolve().parents[2]
LABEL_DIR = REPO_ROOT / "label"
LABEL_FILE = LABEL_DIR / "label.yaml"
CACHE_DIR = REPO_ROOT / ".cache"


@dataclass(frozen=True)
class Band:
    slug: str
    audio_dir: str
    prefix: str

    @property
    def dir(self) -> Path:
        return LABEL_DIR / "bands" / self.slug

    @property
    def tracks_file(self) -> Path:
        return self.dir / "tracks.yaml"

    @property
    def band_file(self) -> Path:
        return self.dir / "band.yaml"


@dataclass(frozen=True)
class Config:
    raw: dict
    audio_root: Path
    bands: dict[str, Band]

    @property
    def label_name(self) -> str:
        return self.raw.get("label", {}).get("name", "Unnamed Label")

    @property
    def eras(self) -> dict:
        return self.raw.get("eras", {})

    @property
    def excluded_audio(self) -> set[str]:
        return set(self.raw.get("excluded_audio", []) or [])

    def band_audio_dir(self, slug: str) -> Path:
        return self.audio_root / self.bands[slug].audio_dir


def load() -> Config:
    if not LABEL_FILE.exists():
        raise SystemExit(f"No label config at {LABEL_FILE}")
    raw = yaml.safe_load(LABEL_FILE.read_text(encoding="utf-8"))

    audio_root = Path(raw["audio_root"]).expanduser()
    bands = {
        slug: Band(slug=slug, audio_dir=spec["audio_dir"], prefix=spec["prefix"])
        for slug, spec in raw.get("bands", {}).items()
    }
    return Config(raw=raw, audio_root=audio_root, bands=bands)


_SLUG_STRIP = re.compile(r"[^a-z0-9]+")


def slugify(title: str) -> str:
    """Title -> stable filesystem/id slug.

    Ampersands become 'and' rather than vanishing, so 'The Prompt & The Pulse'
    and 'The Prompt The Pulse' cannot collide.
    """
    s = title.lower().replace("&", " and ")
    s = _SLUG_STRIP.sub("-", s)
    return s.strip("-")
