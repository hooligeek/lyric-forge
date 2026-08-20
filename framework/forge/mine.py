"""Mine a band's catalogue for self-repetition.

The premise: "functional equilibrium" is not running out of *words*, it is running
out of *structural moves*. A lexicon list is a bag of words, and a model handed a
bag of words will reuse the same handful forever because those scan and rhyme
easiest. So the useful artefact is not another vocabulary list — it is a list of
phrases the band has already spent.

Repetition *within* a song is a chorus and is desirable. Repetition *across*
songs is the failure mode. So everything here counts distinct songs, never raw
occurrences.

Output is triage, not verdict: the operator promotes each hit to either a
canonical hook (deliberate, keep repeating) or a burned phrase (never again).
Only the human knows which is which.
"""

from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from . import config as config_mod
from . import ledger as ledger_mod
from . import lyrics as lyrics_mod
from .config import Band

MIN_N = 4
MAX_N = 14
WORD_RE = re.compile(r"[a-z0-9']+")

# Openings worth tracking separately: a shared first-few-words across sections in
# different songs is a syntactic tic rather than a shared phrase, and reads much
# worse than a repeated noun. "A deep lack of ___" opening three bridges is the
# canonical example.
OPENING_WORDS = 4


def tokenize(text: str) -> list[str]:
    return WORD_RE.findall(text.lower())


@dataclass
class Hit:
    phrase: str
    n: int
    songs: list[str] = field(default_factory=list)

    @property
    def song_count(self) -> int:
        return len(self.songs)


@dataclass
class MineResult:
    band: str
    song_count: int
    phrases: list[Hit] = field(default_factory=list)
    openings: list[Hit] = field(default_factory=list)
    cue_names: list[Hit] = field(default_factory=list)
    style_prompts: dict[str, list[str]] = field(default_factory=dict)


def _collect_ngrams(tokens: list[str]) -> dict[int, set[tuple[str, ...]]]:
    out: dict[int, set[tuple[str, ...]]] = {}
    for n in range(MIN_N, MAX_N + 1):
        if len(tokens) < n:
            break
        out[n] = {tuple(tokens[i : i + n]) for i in range(len(tokens) - n + 1)}
    return out


def _prune_contained(hits: list[Hit]) -> list[Hit]:
    """Drop short phrases wholly inside a longer phrase with the same reach.

    Without this, one repeated couplet reports as dozens of overlapping hits.
    """
    hits.sort(key=lambda h: (-h.n, -h.song_count))
    kept: list[Hit] = []
    for h in hits:
        covered = any(
            h.phrase in k.phrase and h.song_count <= k.song_count for k in kept
        )
        if not covered:
            kept.append(h)
    return kept


def mine_band(band: Band) -> MineResult:
    tracks = ledger_mod.load_band_tracks(band)
    songs: list[tuple[str, lyrics_mod.Song]] = []

    for t in tracks:
        rel = t.get("lyric_sheet")
        if not rel:
            continue
        path = config_mod.REPO_ROOT / rel
        if not path.exists():
            continue
        songs.append((t.get("title") or path.stem, lyrics_mod.load_sheet(path)))

    result = MineResult(band=band.slug, song_count=len(songs))
    if len(songs) < 2:
        return result

    # --- repeated phrases across songs ----------------------------------------
    per_song: dict[str, dict[int, set[tuple[str, ...]]]] = {}
    for title, song in songs:
        per_song[title] = _collect_ngrams(tokenize(song.plain_text()))

    phrase_songs: dict[tuple[str, ...], set[str]] = defaultdict(set)
    for title, grams in per_song.items():
        for _n, s in grams.items():
            for g in s:
                phrase_songs[g].add(title)

    hits = [
        Hit(phrase=" ".join(g), n=len(g), songs=sorted(t))
        for g, t in phrase_songs.items()
        if len(t) >= 2
    ]
    result.phrases = _prune_contained(hits)

    # --- shared section openings (syntactic tics) -----------------------------
    opening_songs: dict[tuple[str, ...], set[str]] = defaultdict(set)
    for title, song in songs:
        for sec in song.lyric_sections:
            if not sec.lines:
                continue
            toks = tokenize(sec.lines[0])
            if len(toks) >= OPENING_WORDS:
                opening_songs[tuple(toks[:OPENING_WORDS])].add(title)
    result.openings = sorted(
        (
            Hit(phrase=" ".join(g), n=len(g), songs=sorted(t))
            for g, t in opening_songs.items()
            if len(t) >= 2
        ),
        key=lambda h: -h.song_count,
    )

    # --- reused cue names ------------------------------------------------------
    cue_songs: dict[str, set[str]] = defaultdict(set)
    for title, song in songs:
        for sec in song.lyric_sections:
            cue_songs[sec.name].add(title)
    result.cue_names = sorted(
        (
            Hit(phrase=name, n=0, songs=sorted(t))
            for name, t in cue_songs.items()
            if len(t) >= 2
        ),
        key=lambda h: -h.song_count,
    )

    # --- style prompt uniformity ----------------------------------------------
    prompts: dict[str, list[str]] = defaultdict(list)
    for t in tracks:
        sp = ledger_mod.get_nested(t, "suno.style_prompt")
        if sp:
            prompts[sp].append(t.get("title") or t.get("id"))
    result.style_prompts = dict(prompts)

    return result


@dataclass
class CrossHit:
    phrase: str
    n: int
    bands: list[str] = field(default_factory=list)
    songs: list[str] = field(default_factory=list)

    @property
    def band_count(self) -> int:
        return len(self.bands)


def mine_label(cfg) -> list[CrossHit]:
    """Find phrases that cross *band* boundaries.

    This is the check that matters most once the roster premise is "five facets
    of one person". Warhead repeating Warhead is a band with a motif. Warhead
    sounding like Silicon Kings is the roster collapsing into a single voice —
    and it is invisible to per-band mining.

    Deliberate label-wide axioms will surface here too. That is correct: the
    operator needs to see them and confirm they are intentional, rather than
    have the tool decide.
    """
    songs: list[tuple[str, str, lyrics_mod.Song]] = []  # (band, title, song)
    for slug, band in cfg.bands.items():
        for t in ledger_mod.load_band_tracks(band):
            rel = t.get("lyric_sheet")
            if not rel:
                continue
            path = config_mod.REPO_ROOT / rel
            if path.exists():
                songs.append((slug, t.get("title") or path.stem, lyrics_mod.load_sheet(path)))

    owners: dict[tuple[str, ...], set[tuple[str, str]]] = defaultdict(set)
    for band_slug, title, song in songs:
        for _n, grams in _collect_ngrams(tokenize(song.plain_text())).items():
            for g in grams:
                owners[g].add((band_slug, title))

    hits: list[Hit] = []
    meta: dict[str, tuple[list[str], list[str]]] = {}
    for g, refs in owners.items():
        bands = sorted({b for b, _ in refs})
        if len(bands) < 2:
            continue
        phrase = " ".join(g)
        hits.append(Hit(phrase=phrase, n=len(g), songs=sorted(f"{b}/{t}" for b, t in refs)))
        meta[phrase] = (bands, sorted(f"{b}/{t}" for b, t in refs))

    pruned = _prune_contained(hits)
    out = [
        CrossHit(phrase=h.phrase, n=h.n, bands=meta[h.phrase][0], songs=meta[h.phrase][1])
        for h in pruned
    ]
    out.sort(key=lambda c: (-c.band_count, -c.n))
    return out


def format_cross(hits: list[CrossHit], limit: int = 30) -> str:
    lines: list[str] = []
    lines.append("=" * 78)
    lines.append("CROSS-BAND REPETITION  (phrases shared between different acts)")
    lines.append("=" * 78)
    if not hits:
        lines.append("None. Every act's phrasing is its own.")
        return "\n".join(lines)
    for c in hits[:limit]:
        lines.append(f"  [{c.band_count} bands] \"{c.phrase}\"")
        lines.append(f"             {', '.join(c.songs)}")
    if len(hits) > limit:
        lines.append(f"  ... {len(hits) - limit} more")
    lines.append("")
    lines.append("Triage: a shared label axiom belongs here and is intentional.")
    lines.append("Anything else is the roster converging on one voice.")
    return "\n".join(lines)


def format_result(r: MineResult, limit: int = 25) -> str:
    lines: list[str] = []
    lines.append("=" * 78)
    lines.append(f"REPETITION MINE  {r.band}  ({r.song_count} songs with lyrics)")
    lines.append("=" * 78)

    if r.song_count < 2:
        lines.append("Need at least two songs with lyric sheets to compare.")
        return "\n".join(lines)

    lines.append("")
    lines.append(f"-- PHRASES REUSED ACROSS SONGS  ({len(r.phrases)} after pruning)")
    if not r.phrases:
        lines.append("   none")
    for h in r.phrases[:limit]:
        lines.append(f"   [{h.song_count} songs] \"{h.phrase}\"")
        lines.append(f"              {', '.join(h.songs)}")
    if len(r.phrases) > limit:
        lines.append(f"   ... {len(r.phrases) - limit} more")

    lines.append("")
    lines.append(f"-- SHARED SECTION OPENINGS  ({len(r.openings)})")
    if not r.openings:
        lines.append("   none")
    for h in r.openings[:limit]:
        lines.append(f"   [{h.song_count} songs] \"{h.phrase} ...\"  ({', '.join(h.songs)})")

    lines.append("")
    lines.append(f"-- CUE NAMES REUSED  ({len(r.cue_names)})")
    for h in r.cue_names[:limit]:
        lines.append(f"   [{h.song_count} songs] {h.phrase}")

    lines.append("")
    lines.append("-- STYLE PROMPT SPREAD")
    for prompt, titles in r.style_prompts.items():
        lines.append(f"   [{len(titles)} tracks] {prompt[:88]}")
    if len(r.style_prompts) == 1 and r.song_count > 1:
        lines.append("   ^ every track shares one style prompt: no sonic variance to audit")

    return "\n".join(lines)


def write_retired(band: Band, r: MineResult) -> Path:
    """Emit a triage file. Everything lands in `candidates` — the operator moves
    entries into `canonical_hooks` or `burned`, and only `burned` is enforced."""
    dest = band.dir / "retired.yaml"

    existing: dict = {}
    if dest.exists():
        existing = yaml.safe_load(dest.read_text(encoding="utf-8")) or {}

    already = set(existing.get("burned") or []) | set(existing.get("canonical_hooks") or [])

    candidates = [
        {"phrase": h.phrase, "songs": h.songs}
        for h in r.phrases
        if h.phrase not in already
    ]
    tics = [
        {"opening": h.phrase, "songs": h.songs}
        for h in r.openings
        if h.phrase not in already
    ]

    doc = {
        "band": band.slug,
        "canonical_hooks": existing.get("canonical_hooks") or [],
        "burned": existing.get("burned") or [],
        "candidates": candidates,
        "opening_tics": tics,
    }
    header = (
        "---\n"
        f"# {band.slug} — spent-phrase registry. Generated by `forge mine`.\n"
        "#\n"
        "# canonical_hooks: deliberate repetition. Brand slogans, recurring motifs.\n"
        "#                  Compiled into the notebook bundle as ALLOWED.\n"
        "# burned:          spent. Compiled into the bundle as FORBIDDEN.\n"
        "# candidates:      awaiting triage. Move each into one of the two lists above.\n"
        "# opening_tics:    shared section openings — syntactic ruts, not vocabulary.\n"
    )
    dest.write_text(
        header + yaml.safe_dump(doc, sort_keys=False, allow_unicode=True, width=100),
        encoding="utf-8",
    )
    return dest
