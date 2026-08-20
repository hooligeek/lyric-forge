"""Import lyric sheets out of notebook harvest documents into the ledger.

Matching parsed songs back to ledger entries is fuzzy on purpose: the audio
filenames and the canonical titles disagree in ways that are meaningful rather
than accidental. `Systemic Obsolescence One.mp3` is
`Systemic Obsolescence (Pt. 1: The Infrastructure Grievance)`; that is a
filename convention, not a different song. But `Local Sentinel` is genuinely not
`Under My Own Metal`, and the importer must refuse to guess there.

Anything unmatched in either direction is reported rather than silently dropped.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from difflib import SequenceMatcher
from pathlib import Path

from . import config as config_mod
from . import ledger as ledger_mod
from . import lyrics as lyrics_mod
from .config import Band, Config, slugify

MATCH_THRESHOLD = 0.82

# Filename conventions vs canonical titles.
NUMERALS = {
    "one": "1", "two": "2", "three": "3", "four": "4", "five": "5",
    "pt": "part", "pt.": "part", "i": "1", "ii": "2",
}


def normalise_title(title: str) -> str:
    t = title.lower()
    t = re.sub(r"[\(\[].*?[\)\]]", " ", t)      # drop parentheticals
    t = re.sub(r"[^a-z0-9\s]", " ", t)
    words = [NUMERALS.get(w, w) for w in t.split()]
    return " ".join(words).strip()


def score(a: str, b: str) -> float:
    na, nb = normalise_title(a), normalise_title(b)
    if not na or not nb:
        return 0.0
    if na == nb:
        return 1.0
    # Containment handles "systemic obsolescence part 1" vs "systemic obsolescence 1"
    if na in nb or nb in na:
        return 0.95
    return SequenceMatcher(None, na, nb).ratio()


@dataclass
class Match:
    song: lyrics_mod.Song
    track: dict | None
    confidence: float
    reason: str


def match_songs(songs: list[lyrics_mod.Song], tracks: list[dict]) -> list[Match]:
    out: list[Match] = []
    claimed: set[str] = set()

    for song in songs:
        best: dict | None = None
        best_score = 0.0
        for t in tracks:
            if t.get("id") in claimed:
                continue
            s = score(song.title, t.get("title", ""))
            if s > best_score:
                best, best_score = t, s

        if best is not None and best_score >= MATCH_THRESHOLD:
            claimed.add(best["id"])
            reason = "exact" if best_score >= 0.99 else f"fuzzy {best_score:.2f}"
            out.append(Match(song, best, best_score, reason))
        else:
            near = f" (closest: {best.get('title')} at {best_score:.2f})" if best else ""
            out.append(Match(song, None, best_score, f"no ledger entry{near}"))
    return out


def import_file(
    cfg: Config,
    band: Band,
    source: Path,
    dry_run: bool = True,
) -> tuple[list[Match], list[dict], list[str]]:
    """Returns (matches, unmatched_ledger_tracks, written_paths)."""
    raw = source.read_text(encoding="utf-8", errors="replace")
    rel_source = _relative_source(source)
    songs = lyrics_mod.parse(raw, source=rel_source)

    tracks = ledger_mod.load_band_tracks(band)
    matches = match_songs(songs, tracks)

    matched_ids = {m.track["id"] for m in matches if m.track}
    unmatched_tracks = [t for t in tracks if t.get("id") not in matched_ids]

    written: list[str] = []
    if not dry_run:
        lyrics_dir = band.dir / "lyrics"
        lyrics_dir.mkdir(parents=True, exist_ok=True)
        for m in matches:
            if not m.track:
                continue
            slug = m.track.get("slug") or slugify(m.track["title"])
            sheet = lyrics_mod.emit_sheet(
                m.song,
                band=band.slug,
                track_id=m.track["id"],
                slug=slug,
                era=m.track.get("era") or "pre-standard",
            )
            dest = lyrics_dir / f"{slug}.md"
            dest.write_text(sheet, encoding="utf-8")
            rel = dest.relative_to(config_mod.REPO_ROOT).as_posix()
            m.track["lyric_sheet"] = rel
            # Record the canonical title from the source when it is richer than
            # the filename-derived one, but keep the slug stable so paths hold.
            if len(m.song.title) > len(m.track.get("title", "")):
                m.track.setdefault("notes_titles", None)
                m.track["canonical_title"] = m.song.title
            written.append(rel)
        ledger_mod.save_band_tracks(band, tracks)

    return matches, unmatched_tracks, written


def _relative_source(source: Path) -> str:
    try:
        return source.relative_to(Path.home()).as_posix()
    except ValueError:
        return source.name


def format_result(
    band: Band,
    source: Path,
    matches: list[Match],
    unmatched: list[dict],
    written: list[str],
    dry_run: bool,
) -> str:
    lines: list[str] = []
    mode = "DRY RUN" if dry_run else "WRITTEN"
    lines.append("=" * 78)
    lines.append(f"IMPORT [{mode}]  {band.slug}  <-  {source.name}")
    lines.append("=" * 78)
    lines.append(f"{'PARSED TITLE':<42} {'SECT':>4} {'WORDS':>6}  MATCH")
    for m in matches:
        n_sec = len(m.song.lyric_sections)
        target = m.track["id"] if m.track else "--"
        detail = f"{target} ({m.reason})"
        flag = " " if m.track else "!"
        lines.append(
            f"{flag}{m.song.title[:41]:<41} {n_sec:>4} {m.song.word_count:>6}  {detail}"
        )

    if unmatched:
        lines.append("")
        lines.append("Ledger tracks with no lyrics in this source:")
        for t in unmatched:
            lines.append(f"  - {t.get('id')} {t.get('title')}")

    if written:
        lines.append("")
        lines.append(f"{len(written)} lyric sheets written.")
    elif dry_run:
        lines.append("")
        lines.append("Nothing written. Re-run with --write to commit.")
    return "\n".join(lines)
