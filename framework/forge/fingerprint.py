"""Content hashes for the binary assets the ledger describes.

The ledger stores measurements — detected tempo, word accuracy, glitch timecodes
— derived from audio and art that live outside the repo. Without a hash, none of
that is verifiable after the fact, and worse, it degrades silently: re-export a
different Suno generation of the same title and the numbers stay put while the
thing they describe changes underneath them.

That is not hypothetical here. Five tracks already have lyric sheets that do not
match their masters, so "which master?" is a live question in this catalogue
rather than a precaution.

Hashing is cheap (117 MB of mp3 in about a second) and makes the ledger
self-verifying: reconcile can state that a file has changed since it was
analysed, rather than everyone assuming it has not.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

from . import ledger as ledger_mod
from .config import Config

CHUNK = 1 << 20


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        while chunk := fh.read(CHUNK):
            h.update(chunk)
    return h.hexdigest()


def short(digest: str | None) -> str:
    return digest[:12] if digest else "-"


def run(cfg: Config, write: bool = False) -> str:
    lines: list[str] = []
    lines.append("=" * 78)
    lines.append("ASSET FINGERPRINTS" + ("" if write else "  (dry run)"))
    lines.append("=" * 78)

    stamped = 0
    drifted = 0
    missing = 0

    for slug, band in cfg.bands.items():
        tracks = ledger_mod.load_band_tracks(band)
        changed = False
        for t in tracks:
            for field, root, rel in (
                ("audio", cfg.audio_root, t.get("audio")),
                ("artwork", cfg.artwork_root, t.get("artwork")),
            ):
                key = f"{field}_sha256"
                if not rel:
                    continue
                path = root / rel
                if not path.exists():
                    lines.append(f"   MISSING  {t.get('id')} {field}: {rel}")
                    missing += 1
                    continue
                digest = sha256_file(path)
                previous = t.get(key)
                if previous and previous != digest:
                    lines.append(
                        f"   DRIFT    {t.get('id')} {t.get('title')} {field}: "
                        f"{short(previous)} -> {short(digest)}"
                    )
                    lines.append(
                        f"            any analysis recorded for this track predates "
                        f"the current file and should be re-run"
                    )
                    drifted += 1
                if previous != digest:
                    t[key] = digest
                    changed = True
                    stamped += 1
        if changed and write:
            ledger_mod.save_band_tracks(band, tracks)

    lines.append("")
    lines.append(
        f"{stamped} hashes recorded, {drifted} drifted, {missing} missing files"
    )
    if not write:
        lines.append("Nothing written. Re-run with --write.")
    return "\n".join(lines)


def check_drift(cfg: Config) -> list[tuple[str, str, str]]:
    """(track id, field, detail) for assets whose hash no longer matches."""
    out: list[tuple[str, str, str]] = []
    for slug, band in cfg.bands.items():
        for t in ledger_mod.load_band_tracks(band):
            for field, root, rel in (
                ("audio", cfg.audio_root, t.get("audio")),
                ("artwork", cfg.artwork_root, t.get("artwork")),
            ):
                recorded = t.get(f"{field}_sha256")
                if not (rel and recorded):
                    continue
                path = root / rel
                if not path.exists():
                    continue
                if sha256_file(path) != recorded:
                    out.append(
                        (
                            t.get("id") or "?",
                            field,
                            f"{rel} changed since it was fingerprinted; "
                            f"recorded analysis is stale",
                        )
                    )
    return out
