"""`forge ingest-audio` — bring a render back in and close the loop.

The counterpart to spark. A track that went out as a sheet comes back as audio,
gets filed under the naming convention, hashed, and handed to the analyser.

Two things this does that matter more than the file copy.

It enforces the convention at the door. Suno hands you "Under My Own Metal.mp3";
the repo wants label/audio/warhead/under-my-own-metal.mp3. Renaming on ingest is
why the ASSET_NAMING gate stays green instead of needing a migration every few
months.

It refuses to silently supersede evidence. Re-rendering is normal — Suno produces
variants and you pick one — but a new master invalidates every timecode measured
against the old one. Replacing audio therefore archives the existing analysis and
glitch log under the hash they describe, rather than leaving stale timecodes
presented as current. Nothing is destroyed and nothing false is shown.
"""

from __future__ import annotations

import datetime
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from . import audio as audio_mod
from . import config as config_mod
from . import fingerprint as fp_mod
from . import ledger as ledger_mod
from . import lifecycle as lc_mod
from .config import Config

AUDIO_SUFFIXES = {".mp3", ".wav", ".flac", ".m4a", ".ogg"}
IMAGE_SUFFIXES = {".jpeg", ".jpg", ".png", ".webp"}

# Ingesting audio for a track that never got as far as an approved sheet is
# allowed — a render can come from a draft, or from outside the tool entirely —
# but it is worth saying so, because it means the sheet the analyser will diff
# against may not be what was actually sung.
EXPECTED_STAGE = "sheet"


class IngestError(RuntimeError):
    pass


@dataclass
class IngestResult:
    band: str
    track_slug: str
    track_id: str
    audio_rel: str
    duration_s: int
    sha256: str
    artwork_rel: str | None = None
    replaced: bool = False
    superseded: dict | None = None
    warnings: list[str] = field(default_factory=list)
    analysed: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "band": self.band,
            "track": self.track_slug,
            "track_id": self.track_id,
            "audio": self.audio_rel,
            "artwork": self.artwork_rel,
            "duration_s": self.duration_s,
            "sha256": self.sha256[:12],
            "replaced": self.replaced,
            "superseded": self.superseded,
            "analysed": self.analysed,
            "warnings": self.warnings,
        }


def _file_track(cfg: Config, band: str, slug: str):
    rows = ledger_mod.load_band_tracks(cfg.bands[band])
    track = next((t for t in rows if t.get("slug") == slug), None)
    if track is None:
        known = ", ".join(t.get("slug") or "?" for t in rows)
        raise IngestError(f"no track '{slug}' in {band}. Known: {known}")
    return rows, track


def _archive_superseded(track: dict, old_hash: str | None) -> dict | None:
    """Move analysis and glitch log aside, keyed by the hash they describe."""
    analysis = track.get("analysis")
    log = track.get("glitch_log") or []
    if not analysis and not log:
        return None

    record = {
        "superseded_on": datetime.date.today().isoformat(),
        "audio_sha256": old_hash,
        "reason": (
            "audio replaced; every timecode below was measured against the "
            "previous master and does not apply to the new one"
        ),
        "analysis": analysis,
        "glitch_log": log,
    }
    history = track.setdefault("superseded", [])
    history.append(record)
    track["analysis"] = None
    track["glitch_log"] = []
    return {
        "audio_sha256": (old_hash or "")[:12],
        "glitch_entries": len(log),
        "had_analysis": bool(analysis),
    }


def ingest(
    cfg: Config,
    band: str,
    slug: str,
    source: Path,
    artwork: Path | None = None,
    replace: bool = False,
    move: bool = False,
) -> IngestResult:
    if band not in cfg.bands:
        raise IngestError(f"unknown band: {band}")
    if not source.exists():
        raise IngestError(f"no such file: {source}")
    if source.suffix.lower() not in AUDIO_SUFFIXES:
        raise IngestError(
            f"{source.suffix} is not audio. Expected one of "
            f"{', '.join(sorted(AUDIO_SUFFIXES))}"
        )

    rows, track = _file_track(cfg, band, slug)
    warnings: list[str] = []

    stage = ledger_mod.get_nested(track, "lifecycle.stage") or "imported"
    if stage in ("spark", "brief", "draft", "review"):
        warnings.append(
            f"track is at stage '{stage}', before an approved sheet. The analyser "
            f"will diff the render against whatever sheet exists, which may not be "
            f"what was actually sung."
        )

    # Convention enforced here, not later.
    dest = cfg.audio_root / band / f"{slug}{source.suffix.lower()}"
    dest.parent.mkdir(parents=True, exist_ok=True)

    old_hash = track.get("audio_sha256")
    new_hash = fp_mod.sha256_file(source)
    superseded = None
    replaced = False

    if dest.exists():
        if fp_mod.sha256_file(dest) == new_hash:
            warnings.append("identical file already ingested; nothing changed on disk")
        elif not replace:
            raise IngestError(
                f"{dest.relative_to(config_mod.REPO_ROOT)} already exists with "
                f"different content.\n"
                f"Re-rendering is normal, but the recorded analysis and "
                f"{len(track.get('glitch_log') or [])} glitch log entries were "
                f"measured against the current file and will not apply to the new "
                f"one. Pass --replace to proceed; they will be archived under the "
                f"old hash rather than deleted."
            )
        else:
            superseded = _archive_superseded(track, old_hash)
            replaced = True

    if not (dest.exists() and fp_mod.sha256_file(dest) == new_hash):
        if move:
            shutil.move(str(source), str(dest))
        else:
            shutil.copy2(source, dest)

    probe = audio_mod.probe(dest)
    audio_rel = f"{band}/{dest.name}"

    track["audio"] = audio_rel
    track["audio_sha256"] = new_hash
    track["duration_s"] = round(probe.duration_s)

    artwork_rel = None
    if artwork is not None:
        if not artwork.exists():
            raise IngestError(f"no such artwork: {artwork}")
        if artwork.suffix.lower() not in IMAGE_SUFFIXES:
            raise IngestError(f"{artwork.suffix} is not an image")
        art_dest = cfg.artwork_root / "songs" / f"{slug}{artwork.suffix.lower()}"
        art_dest.parent.mkdir(parents=True, exist_ok=True)
        if move:
            shutil.move(str(artwork), str(art_dest))
        else:
            shutil.copy2(artwork, art_dest)
        artwork_rel = f"songs/{art_dest.name}"
        track["artwork"] = artwork_rel
        track["artwork_sha256"] = fp_mod.sha256_file(art_dest)

    if track.get("status") in (None, "needs-backfill"):
        track["status"] = "wip"

    note = f"{probe.duration_s:.0f}s, {new_hash[:12]}"
    if replaced:
        note += "; replaced previous master, prior analysis archived"
    lc_mod.stamp(track, "rendered", by="forge ingest-audio", note=note)
    ledger_mod.save_band_tracks(cfg.bands[band], rows)

    return IngestResult(
        band=band,
        track_slug=slug,
        track_id=track.get("id") or "?",
        audio_rel=audio_rel,
        duration_s=round(probe.duration_s),
        sha256=new_hash,
        artwork_rel=artwork_rel,
        replaced=replaced,
        superseded=superseded,
        warnings=warnings,
    )


def format_result(r: IngestResult) -> str:
    lines = ["=" * 78, f"INGESTED  {r.track_id} {r.track_slug}", "=" * 78]
    lines.append(f"audio   : {r.audio_rel}  ({r.duration_s}s, {r.sha256[:12]})")
    if r.artwork_rel:
        lines.append(f"artwork : {r.artwork_rel}")
    lines.append("stage   : rendered")
    if r.replaced and r.superseded:
        lines.append("")
        lines.append("-- SUPERSEDED")
        lines.append(
            f"   Previous master {r.superseded['audio_sha256']} archived with "
            f"{r.superseded['glitch_entries']} glitch entries"
            + (" and its analysis." if r.superseded["had_analysis"] else ".")
        )
        lines.append(
            "   Those timecodes were measured against the old file and do not "
            "apply here. Nothing was deleted."
        )
    for w in r.warnings:
        lines.append("")
        lines.append(f"!! {w}")
    lines.append("")
    lines.append("-- NEXT")
    if r.analysed:
        lines.append("   Analysis complete. Adjudicate the candidates:")
    else:
        lines.append("   Measure it:")
        lines.append(
            f"     forge analyze --band {r.band} --track {r.track_slug} --write"
        )
        lines.append("   Then adjudicate:")
    lines.append(f"     forge adjudicate --band {r.band} --write")
    return "\n".join(lines)
