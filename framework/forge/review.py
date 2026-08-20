"""`forge review` — scan lyrics for issues, mechanical first.

The split is the whole design. Some findings are decidable by looking: a spent
phrase reused, a bare cue where the formula requires stacking, a suite with none
of its anchors present, a section opening on a banned construction, an n-gram
shared with another track. Those are computed here, in Python, with citations —
because a model asked to check them will sometimes report that they are fine, and
an audit that sometimes lies is worse than no audit.

What is left is genuinely judgement: is the stance held for the whole piece, is
the narrator on-model, does a line contradict the substrate, is the addressee
specific. Those go to the model, via the review-lyrics prompt, **with the
mechanical findings already attached** so it does not spend its attention
re-deriving what has been measured.

Works on lyrics the system never generated. That is the point of the ad-hoc
context parameter: "make it angrier, no religious imagery, must scan at 199" is
direction for one review and cannot be encoded in a band definition.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from . import config as config_mod
from . import context as context_mod
from . import ledger as ledger_mod
from . import lyrics as lyrics_mod
from . import mine as mine_mod
from .config import Config

MAX_TAGS_PER_CUE = 6
MIN_SHARED_NGRAM = 4
LONG_WORD_SYLLABLES = 4

VOWEL_GROUP = re.compile(r"[aeiouy]+")


@dataclass
class Finding:
    severity: str      # mechanical | advisory
    rule: str
    detail: str
    quote: str | None = None
    section: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "severity": self.severity,
            "rule": self.rule,
            "detail": self.detail,
            "quote": self.quote,
            "section": self.section,
        }

    def line(self) -> str:
        head = f"[{self.rule}]"
        if self.section:
            head += f" ({self.section})"
        out = f"{head} {self.detail}"
        if self.quote:
            out += f'\n      "{self.quote}"'
        return out


# Vowel pairs that are genuinely two nuclei rather than one. A bare [aeiouy]+
# run counted "io" in "epistemological" as one, undercounting exactly the
# Latinate compounds the placement check exists to flag, while "ea" in "breath"
# was counted as two.
DIPHTHONG_SPLITS = ("io", "ia", "ea", "eo", "ua", "ue", "uo", "iu", "yi")
DIPHTHONG_JOINS = ("ea", "ai", "ay", "ee", "ei", "ey", "oa", "oo", "ou", "oy",
                   "au", "aw", "ew", "ie", "oi", "ue")


def syllables(word: str) -> int:
    """Approximate, and deliberately documented as such.

    It gates `placement-risk` at four syllables, so being wrong AT the threshold
    was the whole problem: a bare vowel-run count both under- and over-counted
    there. This is better, not exact — no rule-based counter is — which is why
    placement-risk is an ADVISORY finding and not a mechanical one.
    """
    w = re.sub(r"[^a-z]", "", word.lower())
    if not w:
        return 0
    n = len(VOWEL_GROUP.findall(w))
    # A run of two vowels is one nucleus by default; split the ones that are two.
    for pair in DIPHTHONG_SPLITS:
        if pair not in DIPHTHONG_JOINS:
            n += w.count(pair)
    # Silent terminal e, but not in -le/-ee/-ye or a one-syllable word.
    if w.endswith("e") and n > 1 and not w.endswith(("le", "ee", "ye", "ce", "ge")):
        n -= 1
    return max(1, n)


def _norm(text: str) -> str:
    return " ".join(re.findall(r"[a-z0-9']+", (text or "").lower()))


def _contains_phrase(haystack: str, needle: str) -> bool:
    """Word-boundary containment on normalised text.

    Plain `in` matched substrings, so a citable MECHANICAL rule was wrong in both
    directions: "the fire" matched inside "the fireworks", and a burned phrase
    could be missed or invented depending on neighbouring words. A rule the tool
    cites by name has to be right.
    """
    if not needle:
        return False
    return re.search(rf"(?<!\w){re.escape(needle)}(?!\w)", haystack) is not None


# ---------------------------------------------------------------------------
# mechanical checks
# ---------------------------------------------------------------------------
def check_cues(song: lyrics_mod.Song) -> list[Finding]:
    out: list[Finding] = []
    if not song.sections:
        out.append(
            Finding("mechanical", "no-cues", "No bracketed section cues found at all.")
        )
        return out

    for sec in song.sections:
        if sec.is_style:
            continue
        parts = [p.strip() for p in sec.tag.split("|")]
        if len(parts) < 2:
            out.append(
                Finding(
                    "mechanical",
                    "bare-cue",
                    "Cue has no pipe-stacked attributes; the formula requires "
                    "[Section | Genre/Era | Vocal Texture | Production Vibe].",
                    quote=f"[{sec.tag}]",
                    section=sec.name,
                )
            )
        elif len(parts) > MAX_TAGS_PER_CUE:
            out.append(
                Finding(
                    "mechanical",
                    "cue-overloaded",
                    f"{len(parts)} attributes in one cue; the ceiling is "
                    f"{MAX_TAGS_PER_CUE} before the synthesiser starts ignoring them.",
                    quote=f"[{sec.tag}]",
                    section=sec.name,
                )
            )

    names = [s.name for s in song.lyric_sections]
    if names and not any(n.startswith(("intro", "instrumental")) for n in names):
        out.append(
            Finding("advisory", "no-intro", "No intro section. Standard sheets open with one.")
        )
    if names and not any(n.startswith(("outro", "end")) for n in names):
        out.append(
            Finding("advisory", "no-outro", "No outro or end section. Standard sheets close with one.")
        )
    return out


def check_burned(song: lyrics_mod.Song, retired: dict) -> list[Finding]:
    """Spent phrases. `burned` is a decision and is hard; `candidates` are
    untriaged and are reported as advisory — flagging an untriaged phrase as a
    violation would enforce a judgement nobody has made yet."""
    out: list[Finding] = []
    body = _norm(song.plain_text())

    for phrase in retired.get("burned") or []:
        if _contains_phrase(body, _norm(phrase)):
            out.append(
                Finding("mechanical", "burned-phrase",
                        "Phrase is on the burned list.", quote=str(phrase))
            )

    canonical = {_norm(p) for p in (retired.get("canonical_hooks") or [])}
    for entry in retired.get("candidates") or []:
        phrase = _norm(entry.get("phrase", ""))
        if not phrase or phrase in canonical:
            continue
        if _contains_phrase(body, phrase):
            out.append(
                Finding("advisory", "spent-phrase-untriaged",
                        "Phrase already appears elsewhere in the catalogue and has "
                        "not been triaged into canonical or burned.",
                        quote=entry.get("phrase"))
            )

    for tic in retired.get("opening_tics") or []:
        opening = _norm(tic.get("opening", ""))
        if not opening:
            continue
        for sec in song.lyric_sections:
            if sec.sung_lines and _norm(sec.sung_lines[0]).startswith(opening):
                out.append(
                    Finding("mechanical", "opening-tic",
                            "Section opens on a construction already used to open "
                            "sections in other songs.",
                            quote=sec.sung_lines[0], section=sec.name)
                )
    return out


def check_anchors(song: lyrics_mod.Song, spec: dict, suite: str | None) -> list[Finding]:
    if not suite:
        return []
    s = (spec.get("suites") or {}).get(suite) or {}
    anchors = s.get("anchors") or []
    if not anchors:
        return []
    body = _norm(song.plain_text())
    hits = [a for a in anchors if _contains_phrase(body, _norm(a))]
    if hits:
        return []
    return [
        Finding(
            "mechanical",
            "no-suite-anchor",
            f"Suite {suite} requires at least one anchor term; none of "
            f"{', '.join(anchors)} appears.",
        )
    ]


def check_catalogue_overlap(
    cfg: Config, song: lyrics_mod.Song, band: str | None, exclude_slug: str | None
) -> list[Finding]:
    """Shared n-grams with the existing catalogue, own band and others.

    Cross-band overlap is reported separately and matters more: one band
    repeating itself has a motif, two bands sharing phrasing is the roster
    collapsing into one voice.
    """
    out: list[Finding] = []
    new_grams: set[tuple[str, ...]] = set()
    tokens = mine_mod.tokenize(song.plain_text())
    for n in range(MIN_SHARED_NGRAM, min(len(tokens), 12) + 1):
        for i in range(len(tokens) - n + 1):
            new_grams.add(tuple(tokens[i : i + n]))
    if not new_grams:
        return out

    # The label's own axioms are meant to recur across acts. Without this the
    # check reports the creed as a defect every time anyone uses it.
    canonical = [
        _norm(p) for p in (context_mod.label_spec().get("canonical_phrases") or [])
    ]

    def is_canonical(phrase: str) -> bool:
        p = _norm(phrase)
        return any(p in c or c in p for c in canonical if c)

    hits: dict[str, list[str]] = {}
    for slug, band_obj in cfg.bands.items():
        for t in ledger_mod.load_band_tracks(band_obj):
            if t.get("slug") == exclude_slug:
                continue
            rel = t.get("lyric_sheet")
            if not rel:
                continue
            path = config_mod.REPO_ROOT / rel
            if not path.exists():
                continue
            other = lyrics_mod.load_sheet(path)
            other_tokens = mine_mod.tokenize(other.plain_text())
            other_grams = set()
            for n in range(MIN_SHARED_NGRAM, min(len(other_tokens), 12) + 1):
                for i in range(len(other_tokens) - n + 1):
                    other_grams.add(tuple(other_tokens[i : i + n]))
            shared = {
                g for g in (new_grams & other_grams)
                if not is_canonical(" ".join(g))
            }
            if not shared:
                continue
            longest = max(shared, key=len)
            key = f"{slug}/{t.get('title')}"
            hits.setdefault(key, []).append(" ".join(longest))

    for key, phrases in sorted(hits.items(), key=lambda kv: -len(kv[1])):
        other_band = key.split("/", 1)[0]
        # With no band given we do not know whose voice this is, so we cannot
        # claim the overlap is self or cross. Report only what is known.
        if band is None:
            rule, severity, tail = "catalogue-overlap", "advisory", "."
        elif other_band != band:
            rule, severity, tail = (
                "cross-band-overlap",
                "mechanical",
                " — a different act, which is how the roster loses its distinct voices.",
            )
        else:
            rule, severity, tail = "self-overlap", "advisory", "."
        out.append(
            Finding(
                severity, rule, f"Shares phrasing with {key}{tail}",
                quote=max(phrases, key=len),
            )
        )
    return out


def check_register(song: lyrics_mod.Song, spec: dict, bpm: int | None) -> list[Finding]:
    """Advisory only, and grounded in this band's measured breakage profile."""
    out: list[Finding] = []
    reg = spec.get("register") or {}
    ceiling = reg.get("tempo_ceiling")
    if bpm and ceiling and bpm > ceiling:
        out.append(
            Finding(
                "mechanical",
                "above-tempo-ceiling",
                f"Target {bpm} BPM is above this voice's measured ceiling of "
                f"{ceiling}. Evidence: {str(reg.get('ceiling_evidence',''))[:200]}",
            )
        )

    breaks = " ".join(str(b) for b in (reg.get("breaks_on") or [])).lower()
    if not any(k in breaks for k in ("polysyllab", "latinate", "compound", "cluster")):
        return out

    seen: set[str] = set()
    for sec in song.lyric_sections:
        for line in sec.sung_lines:
            for word in re.findall(r"[A-Za-z'-]+", line):
                if syllables(word) >= LONG_WORD_SYLLABLES and word.lower() not in seen:
                    seen.add(word.lower())
                    out.append(
                        Finding(
                            "advisory",
                            "placement-risk",
                            f'"{word}" is {syllables(word)} syllables and this voice '
                            f"is measured to break on words of that shape. Place it "
                            f"where a slur reads as emphasis, not on a load-bearing word.",
                            quote=line,
                            section=sec.name,
                        )
                    )
    return out


# ---------------------------------------------------------------------------
# orchestration
# ---------------------------------------------------------------------------
@dataclass
class Review:
    band: str | None
    track: str | None
    suite: str | None
    stance: str | None
    bpm: int | None
    era: str | None = None
    findings: list[Finding] = field(default_factory=list)
    stats: dict = field(default_factory=dict)

    @property
    def era_exempt(self) -> bool:
        return self.era == "pre-standard"

    def to_dict(self) -> dict[str, Any]:
        return {
            "band": self.band,
            "track": self.track,
            "era": self.era,
            "era_exempt": self.era_exempt,
            "suite": self.suite,
            "stance": self.stance,
            "bpm": self.bpm,
            "stats": self.stats,
            "findings": [f.to_dict() for f in self.findings],
        }


def run(
    cfg: Config,
    lyric_text: str,
    band: str | None = None,
    track: str | None = None,
) -> Review:
    song = lyrics_mod.parse(lyric_text, source="review")
    song = song[0] if song else lyrics_mod.Song(title="untitled")

    # A plain lyric file with no bracketed cues parses to zero sections, so every
    # check below examined an empty corpus and the review came back clean. "I
    # found nothing" and "there is nothing to look at" are different results, and
    # reporting the second as the first is the exact failure this tool exists to
    # correct.
    if not song.lyric_sections:
        rv = Review(band=band, track=track, suite=None, stance=None, bpm=None)
        rv.findings.append(Finding(
            "mechanical", "unparseable",
            "No bracketed section cues found, so nothing was reviewed. Every check "
            "below would examine an empty document. Add pipe-stacked cues, or pass "
            "a sheet rather than a bare lyric dump — a clean result here would be "
            "meaningless.",
        ))
        rv.stats = {"sections": 0, "sung_words": 0, "mechanical": 1, "advisory": 0,
                    "reviewed": False}
        return rv

    suite = stance = era = None
    bpm = None
    spec: dict = {}
    retired: dict = {}

    if band:
        spec = context_mod.band_spec(cfg, band)
        retired = context_mod.retired(cfg, band)
        if track:
            rows = ledger_mod.load_band_tracks(cfg.bands[band])
            row = next((t for t in rows if t.get("slug") == track), None)
            if row:
                suite = ledger_mod.get_nested(row, "matrix.suite")
                stance = ledger_mod.get_nested(row, "matrix.stance")
                bpm = ledger_mod.get_nested(row, "suno.declared_bpm")
                era = row.get("era")

    rv = Review(band=band, track=track, suite=suite, stance=stance, bpm=bpm, era=era)
    rv.findings += check_cues(song)
    if retired:
        rv.findings += check_burned(song, retired)
    if spec:
        rv.findings += check_anchors(song, spec, suite)
        rv.findings += check_register(song, spec, bpm)
    rv.findings += check_catalogue_overlap(cfg, song, band, track)

    rv.stats = {
        "sections": len(song.lyric_sections),
        "sung_words": song.word_count,
        "mechanical": sum(1 for f in rv.findings if f.severity == "mechanical"),
        "advisory": sum(1 for f in rv.findings if f.severity == "advisory"),
    }
    return rv


def format_review(rv: Review) -> str:
    lines = ["=" * 78, "REVIEW (mechanical)", "=" * 78]
    who = rv.band or "no band"
    if rv.track:
        who += f" / {rv.track}"
    lines.append(
        f"{who} | {rv.stats['sections']} sections, {rv.stats['sung_words']} sung words"
    )
    if rv.suite or rv.stance:
        lines.append(f"suite {rv.suite} | stance {rv.stance} | {rv.bpm} BPM")
    if rv.era_exempt:
        lines.append("")
        lines.append(
            "NOTE: era pre-standard. This track was written before the standards "
            "existed and is exempt from the format, matrix and lexicon gates — the "
            "findings below are informational, not compliance failures. A label "
            "whose axiom is 'leave the glitch in' does not retrofit its own history."
        )
    lines.append("")

    for severity, label in (("mechanical", "MECHANICAL"), ("advisory", "ADVISORY")):
        group = [f for f in rv.findings if f.severity == severity]
        lines.append(f"-- {label}  ({len(group)})")
        if not group:
            lines.append("   none")
        for f in group[:20]:
            lines.append("   " + f.line())
        if len(group) > 20:
            lines.append(f"   ... {len(group) - 20} more")
        lines.append("")

    lines.append(
        "Judgement findings — stance held, narrator on-model, substrate "
        "contradictions — are not computed here. Use --prompt to get them."
    )
    return "\n".join(lines)


def as_prompt_context(rv: Review) -> str:
    """The mechanical findings, formatted for injection into the judgement prompt
    so the model does not spend attention re-deriving what has been measured."""
    if not rv.findings:
        return "No mechanical findings. Every computable check passed."
    out = ["The following have ALREADY been checked mechanically. Do not repeat them; "
           "assess only what a measurement cannot."]
    for severity, label in (("mechanical", "MECHANICAL"), ("advisory", "ADVISORY")):
        group = [f for f in rv.findings if f.severity == severity]
        if not group:
            continue
        out.append("")
        out.append(f"{label}:")
        for f in group[:25]:
            out.append(f"- {f.line()}")
    return "\n".join(out)


def record(cfg: Config, band: str, track: str, rv: Review) -> Path:
    from . import lifecycle as lc_mod

    dest_dir = cfg.bands[band].dir / "reviews"
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / f"{track}.md"

    doc = yaml.safe_dump(rv.to_dict(), sort_keys=False, allow_unicode=True, width=100)
    dest.write_text(
        f"---\n# Mechanical review of {track}\n# Judgement findings are not in here — "
        f"they require a model and are recorded separately.\n\n" + doc,
        encoding="utf-8",
    )

    rows = ledger_mod.load_band_tracks(cfg.bands[band])
    row = next((t for t in rows if t.get("slug") == track), None)
    if row is not None:
        row.setdefault("provenance", {})["review"] = (
            dest.relative_to(config_mod.REPO_ROOT).as_posix()
        )
        lc_mod.stamp(
            row, "review", by="forge review --record",
            note=f"{rv.stats['mechanical']} mechanical, {rv.stats['advisory']} advisory",
        )
        ledger_mod.save_band_tracks(cfg.bands[band], rows)
    return dest
