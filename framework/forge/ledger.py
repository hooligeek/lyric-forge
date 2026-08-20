"""The ledger: track state as real data, one tracks.yaml per band.

This replaces the prose "Metadata Ledger" that lived inside notebook documents.
The point of moving it here is that prose ledgers cannot be checked — a model
reading one will happily report PASS for a track that does not exist. A file on
disk either has a field or it does not.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import yaml

from . import config
from .config import Band, Config, slugify

# Fields every track carries. Anything not yet known is explicitly None rather
# than absent, so a gap is visible instead of merely undefined.
TRACK_FIELDS = [
    "id",
    "title",
    "slug",
    "band",
    "era",           # pre-standard | acap
    "status",        # needs-backfill | wip | mastered | archived
    "lifecycle",     # {stage, history[]} — see lifecycle.py
    "provenance",    # how this song came to exist; spark referenced by id only
    "audio",         # path relative to audio_root
    "audio_sha256",  # pins the file the analysis block describes
    "artwork",       # path relative to artwork_root
    "artwork_sha256",
    "duration_s",
    "suno",          # {style_prompt, declared_bpm, declared_key}
    "matrix",        # {suite, stance}
    "lyric_sheet",   # path relative to repo root, or None
    "glitch_log",    # list of entries (see framework/schema/track.schema.json)
    "analysis",      # filled by `forge analyze`, never hand-edited
    "sheet_mismatch_acknowledged",  # {reason} — a known, recorded discrepancy
    "created",
    "release_quarter",
    "compilation",
    "notes",
]


def blank_track(track_id: str, title: str, band: str, audio: str | None = None) -> dict:
    return {
        "id": track_id,
        "title": title,
        "slug": slugify(title),
        "band": band,
        "era": "pre-standard",
        "status": "needs-backfill",
        "lifecycle": {"stage": "imported", "history": []},
        # The spark itself is never stored here — label/sparks/ is gitignored,
        # since it is the rawest personal input in the system and git is forever.
        # Only the id travels, so provenance survives without the text.
        "provenance": {
            "spark": None,
            "brief": None,
            "brief_confirmed": False,
            "draft": None,
            "prompt_template": None,
            "prompt_version": None,
            "model": None,
            "review": None,
        },
        "audio": audio,
        "artwork": None,
        "duration_s": None,
        "suno": {"style_prompt": None, "declared_bpm": None, "declared_key": None},
        "matrix": {"suite": None, "stance": None},
        "lyric_sheet": None,
        "glitch_log": [],
        "analysis": None,
        "created": None,
        "release_quarter": None,
        "compilation": None,
        "notes": None,
    }


class LedgerError(RuntimeError):
    """A ledger file cannot be trusted. Raised rather than returning something
    plausible, because every caller derives paths and measurements from this."""


# A slug addresses every asset a track owns, and is joined onto asset roots to
# build write destinations. It is therefore a path component and must be
# validated as one.
SLUG_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


def _validate(band: Band, tracks: list[dict]) -> list[dict]:
    """Validate on READ, so a crafted ledger cannot reach a write.

    `slugify()` is a correct sanitiser but it only ever ran on values the tool
    derived itself. A `slug:` typed straight into tracks.yaml — by a collaborator
    in a pull request, or by anything that edits the file — was passed unchecked
    into `cfg.audio_root / band / f"{slug}{suffix}"`, so `../../..` escaped the
    repository. The sanitiser was in the wrong place: on the values that did not
    need it.
    """
    for t in tracks:
        slug = t.get("slug")
        if slug is None:
            continue
        if not isinstance(slug, str) or not SLUG_RE.match(slug):
            raise LedgerError(
                f"{band.tracks_file.name}: track {t.get('id') or '?'} has an "
                f"invalid slug {slug!r}. A slug is a path component and must be "
                f"lowercase alphanumerics separated by single hyphens."
            )
    return tracks


def load_band_tracks(band: Band) -> list[dict]:
    if not band.tracks_file.exists():
        return []
    try:
        data = yaml.safe_load(band.tracks_file.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as exc:
        # Typed, so reconcile can report it instead of dying. Previously this
        # raised raw YAMLError from inside the reporting loop, which killed the
        # process *after* the malformed-YAML finding had been computed and
        # before anything was printed — the diagnostic could never be seen.
        raise LedgerError(f"{band.tracks_file.name} is not valid YAML: {exc}") from exc
    if not isinstance(data, dict):
        raise LedgerError(f"{band.tracks_file.name}: expected a mapping at the top level")
    return _validate(band, data.get("tracks", []) or [])


def save_band_tracks(band: Band, tracks: list[dict]) -> None:
    band.dir.mkdir(parents=True, exist_ok=True)
    ordered = [_order_fields(t) for t in tracks]
    header = (
        "---\n"
        f"# {band.slug} — track ledger. Generated by `forge bootstrap`, then hand-enriched.\n"
        "# `analysis` is written by `forge analyze`; do not hand-edit that block.\n"
    )
    body = yaml.safe_dump(
        {"band": band.slug, "tracks": ordered},
        sort_keys=False,
        allow_unicode=True,
        width=100,
    )
    band.tracks_file.write_text(header + body, encoding="utf-8")


def _order_fields(track: dict) -> dict:
    out = {k: track.get(k) for k in TRACK_FIELDS if k in track or k in TRACK_FIELDS}
    # Preserve any extra keys someone added by hand rather than silently dropping them.
    for k, v in track.items():
        if k not in out:
            out[k] = v
    return out


def load_all(cfg: Config) -> dict[str, list[dict]]:
    return {slug: load_band_tracks(band) for slug, band in cfg.bands.items()}


def next_id(cfg: Config, band: Band, existing: list[dict]) -> str:
    used = set()
    for t in existing:
        tid = t.get("id") or ""
        if tid.startswith(band.prefix + "-"):
            tail = tid.split("-", 1)[1]
            if tail.isdigit():
                used.add(int(tail))
    n = 1
    while n in used:
        n += 1
    return f"{band.prefix}-{n:03d}"


def find_lyric_sheet(track: dict) -> Path | None:
    """Locate a lyric sheet for a track by convention, if one exists."""
    band = track.get("band")
    slug = track.get("slug")
    if not band or not slug:
        return None
    candidate = config.LABEL_DIR / "bands" / band / "lyrics" / f"{slug}.md"
    return candidate if candidate.exists() else None


def as_dict(tracks: list[dict]) -> dict[str, dict]:
    return {t["slug"]: t for t in tracks if t.get("slug")}


def get_nested(track: dict, path: str) -> Any:
    cur: Any = track
    for part in path.split("."):
        if not isinstance(cur, dict):
            return None
        cur = cur.get(part)
    return cur
