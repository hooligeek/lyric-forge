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
    prefix: str
    # Defaults to the slug. Only set this if a band's audio directory genuinely
    # cannot be renamed — it existed here solely to accommodate directories that
    # disagreed with their slugs (`screenlit_panic`, and a misspelled
    # `the_skalgoritms`), and both have since been normalised.
    audio_dir: str = ""

    def __post_init__(self) -> None:
        if not self.audio_dir:
            object.__setattr__(self, "audio_dir", self.slug)

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
    artwork_root: Path
    bands: dict[str, Band]

    @property
    def label_name(self) -> str:
        return self.raw.get("label", {}).get("name", "Unnamed Label")

    @property
    def eras(self) -> dict:
        return self.raw.get("eras", {})

    @property
    def current_era(self) -> str:
        """The era new work belongs to. Label-defined: `framework/` hardcoded
        "acap", which is one label's private name for its own standards epoch."""
        declared = self.raw.get("current_era")
        if declared:
            return str(declared)
        # Fall back to the last non-legacy era declared, then to a generic name.
        for name, spec in reversed(list(self.eras.items())):
            if not (spec or {}).get("exempt_gates"):
                return name
        return "current"

    @property
    def excluded_audio(self) -> set[str]:
        return set(self.raw.get("excluded_audio", []) or [])

    @property
    def catalog_hero(self) -> Path | None:
        """Optional banner image for the generated catalogue index.

        Returns None when unset *or* when the declared file is not on disk. A
        fork without one gets no banner, which is the right outcome: emitting an
        `<img>` for a file that is not there would put a broken image at the top
        of the catalogue and nothing would report it. Abstain rather than claim.
        """
        rel = str(self.raw.get("catalog_hero") or "").strip()
        if not rel:
            return None
        p = Path(rel).expanduser()
        p = p if p.is_absolute() else (REPO_ROOT / p)
        return p if p.is_file() else None

    def band_audio_dir(self, slug: str) -> Path:
        return self.audio_root / self.bands[slug].audio_dir


def load() -> Config:
    if not LABEL_FILE.exists():
        raise SystemExit(f"No label config at {LABEL_FILE}")
    raw = yaml.safe_load(LABEL_FILE.read_text(encoding="utf-8"))

    # Roots may be absolute, ~-relative, or repo-relative. Repo-relative is the
    # normal case now that the binaries live in-tree; resolving those against the
    # CWD instead of the repo would silently break every path the moment forge is
    # run from anywhere but the repo root.
    def _root(value: str, default: Path) -> Path:
        if not value:
            return default
        p = Path(value).expanduser()
        return p if p.is_absolute() else (REPO_ROOT / p)

    audio_root = _root(raw.get("audio_root", ""), REPO_ROOT / "label" / "audio")
    artwork_root = _root(raw.get("artwork_root", ""), audio_root / "artwork")
    # Label-declared harvest banners, so the parser does not carry them.
    from . import lyrics as _lyrics
    _lyrics.set_label_furniture((raw.get("import") or {}).get("furniture_markers") or [])

    bands = {
        slug: Band(
            slug=slug,
            prefix=spec["prefix"],
            audio_dir=spec.get("audio_dir", ""),
        )
        for slug, spec in raw.get("bands", {}).items()
    }
    return Config(
        raw=raw, audio_root=audio_root, artwork_root=artwork_root, bands=bands
    )


_SLUG_STRIP = re.compile(r"[^a-z0-9]+")


def slugify(title: str) -> str:
    """Title -> stable filesystem/id slug.

    Ampersands become 'and' rather than vanishing, so 'The Prompt & The Pulse'
    and 'The Prompt The Pulse' cannot collide.
    """
    s = title.lower().replace("&", " and ")
    s = _SLUG_STRIP.sub("-", s)
    return s.strip("-")
