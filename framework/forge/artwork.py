"""Cover art indexing, duplicate detection, and palette extraction.

Art is the third asset class per track, alongside audio and lyrics, and it had
no representation in the ledger at all — the same gap the lyric sheets were in
before they were imported.

It also needs the same variance check as everything else. Two Warhead covers are
separate renders of one composition, differing only in the title plate baked into
the image, so they are *not* byte-identical and exact hashing misses them
entirely. A perceptual hash catches them. That matters because a label whose
declared enemy is homogenisation should not discover visual repetition by eye.

Decoding goes through ffmpeg rather than Pillow: ffmpeg is already a hard
requirement for the audio pipeline, and a 9x8 greyscale or 32x32 RGB reduction is
a one-line filter graph. No new dependency for either check.
"""

from __future__ import annotations

import hashlib
import subprocess
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

from .config import Config, slugify

# dHash geometry: 9x8 greyscale gives 8x8 = 64 horizontal-gradient comparisons.
DHASH_W, DHASH_H = 9, 8

# Two hashes per image, because a whole-frame hash answers the wrong question.
#
# These covers are template-built: an identical band-name plate across the top, a
# shared torn-collage background, a shared border treatment, and a title stamp in
# the same corner. A full-frame perceptual hash is dominated by that furniture,
# so it reported Screen-Lit Panic's "MINE!" and "Take the L" as the same picture
# at distance 8 when one is a pair of hands clutching pearls and the other is a
# reel-to-reel deck. That is a false positive for duplication and a true positive
# for a shared template — which is a feature of the label's art direction, not a
# defect.
#
# So: hash the full frame to measure template consistency, and hash only the
# central subject region to measure whether the actual art repeats.
# Validated against the catalogue: with this crop, Screen-Lit Panic's MINE! and
# Take the L (same template, different subject) separate correctly, while Roots
# Futuria's War on the Wire / Un-Wind / The Prompt & The Pulse (genuinely one
# beach photograph re-titled three times) land at distances 1-3.
CROP_CENTER = "crop=iw*0.70:ih*0.45:iw*0.15:ih*0.30"

# Full-frame distances: below this the covers share a template.
TEMPLATE_DISTANCE = 12
# Centre-crop distances: below this the subject art itself is duplicated.
NEAR_DUPE_DISTANCE = 8
# Palette reduction: 32x32 is plenty for dominant-colour shares.
PALETTE_SIZE = 32
PALETTE_BUCKET = 6  # bits dropped per channel -> 4 levels per channel


@dataclass
class Art:
    path: Path
    slug: str
    title: str
    sha256: str
    dhash: int          # full frame — template similarity
    dhash_center: int   # subject region — actual art similarity
    width: int | None = None
    height: int | None = None
    palette: list[tuple[str, float]] = field(default_factory=list)

    @property
    def size_label(self) -> str:
        if self.width and self.height:
            return f"{self.width}x{self.height}"
        return "?"


def _ffmpeg_raw(path: Path, vf: str, pix_fmt: str) -> bytes:
    res = subprocess.run(
        [
            "ffmpeg", "-nostdin", "-v", "error", "-i", str(path),
            "-vf", vf, "-pix_fmt", pix_fmt, "-f", "rawvideo", "-",
        ],
        capture_output=True,
        check=False,
    )
    if res.returncode != 0:
        raise RuntimeError(f"ffmpeg failed on {path.name}: {res.stderr.decode()[:200]}")
    return res.stdout


def dhash(path: Path, crop: str | None = None) -> int:
    """64-bit difference hash: 1 bit per horizontal neighbour comparison.

    Pass crop=CROP_CENTER to hash only the subject area, excluding the shared
    template furniture.
    """
    vf = f"{crop}," if crop else ""
    raw = _ffmpeg_raw(path, f"{vf}scale={DHASH_W}:{DHASH_H}", "gray")
    if len(raw) < DHASH_W * DHASH_H:
        return 0
    bits = 0
    for row in range(DHASH_H):
        base = row * DHASH_W
        for col in range(DHASH_W - 1):
            bits <<= 1
            if raw[base + col] > raw[base + col + 1]:
                bits |= 1
    return bits


def palette(path: Path, top: int = 5) -> list[tuple[str, float]]:
    """Dominant colours as (hex, share). Coarse quantisation, not k-means —
    enough to check a declared palette, not enough to argue about."""
    raw = _ffmpeg_raw(path, f"scale={PALETTE_SIZE}:{PALETTE_SIZE}", "rgb24")
    counts: Counter = Counter()
    shift = PALETTE_BUCKET
    for i in range(0, len(raw) - 2, 3):
        r, g, b = raw[i] >> shift, raw[i + 1] >> shift, raw[i + 2] >> shift
        counts[(r, g, b)] += 1
    total = sum(counts.values()) or 1
    out: list[tuple[str, float]] = []
    for (r, g, b), n in counts.most_common(top):
        # Recentre the bucket rather than reporting its floor.
        half = (1 << shift) // 2
        rr, gg, bb = (r << shift) + half, (g << shift) + half, (b << shift) + half
        out.append((f"#{rr:02x}{gg:02x}{bb:02x}", round(n / total, 3)))
    return out


def dimensions(path: Path) -> tuple[int | None, int | None]:
    res = subprocess.run(
        [
            "ffprobe", "-v", "error", "-select_streams", "v:0",
            "-show_entries", "stream=width,height", "-of", "csv=p=0", str(path),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    parts = res.stdout.strip().split(",")
    try:
        return int(parts[0]), int(parts[1])
    except (ValueError, IndexError):
        return None, None


def load_art(path: Path, with_palette: bool = True) -> Art:
    # Filenames in the wild carry trailing spaces ("Analog Wasteland .jpeg"),
    # so strip before slugifying or nothing matches the ledger.
    title = path.stem.strip()
    return Art(
        path=path,
        slug=slugify(title),
        title=title,
        sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
        dhash=dhash(path),
        dhash_center=dhash(path, crop=CROP_CENTER),
        width=dimensions(path)[0],
        height=dimensions(path)[1],
        palette=palette(path) if with_palette else [],
    )


def index_songs(cfg: Config, with_palette: bool = True) -> dict[str, Art]:
    root = cfg.artwork_root
    songs = root / "songs"
    if not songs.exists():
        return {}
    out: dict[str, Art] = {}
    for p in sorted(songs.iterdir()):
        if p.suffix.lower() not in (".jpeg", ".jpg", ".png", ".webp"):
            continue
        art = load_art(p, with_palette=with_palette)
        out[art.slug] = art
    return out


def index_albums(cfg: Config, with_palette: bool = True) -> list[Art]:
    albums = cfg.artwork_root / "albums"
    if not albums.exists():
        return []
    return [
        load_art(p, with_palette=with_palette)
        for p in sorted(albums.iterdir())
        if p.suffix.lower() in (".jpeg", ".jpg", ".png", ".webp")
    ]


def hamming(a: int, b: int) -> int:
    return bin(a ^ b).count("1")


@dataclass
class DupePair:
    a: Art
    b: Art
    distance: int        # centre-crop distance — the one that means duplication
    template_distance: int
    exact: bool


def find_duplicates(arts: list[Art]) -> tuple[list[DupePair], list[DupePair]]:
    """Returns (duplicated_art, shared_template).

    Duplicated art is a problem. A shared template is the label's art direction
    working, and is reported separately so it is not mistaken for the former.
    """
    dupes: list[DupePair] = []
    templates: list[DupePair] = []
    for i in range(len(arts)):
        for j in range(i + 1, len(arts)):
            a, b = arts[i], arts[j]
            td = hamming(a.dhash, b.dhash)
            cd = hamming(a.dhash_center, b.dhash_center)
            if a.sha256 == b.sha256:
                dupes.append(DupePair(a, b, 0, td, exact=True))
            elif cd <= NEAR_DUPE_DISTANCE:
                dupes.append(DupePair(a, b, cd, td, exact=False))
            elif td <= TEMPLATE_DISTANCE:
                templates.append(DupePair(a, b, cd, td, exact=False))
    dupes.sort(key=lambda p: p.distance)
    templates.sort(key=lambda p: p.template_distance)
    return dupes, templates
