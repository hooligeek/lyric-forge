"""Lyric sheet parsing, normalisation, and emission.

The source material arrives in whatever shape a notebook happened to produce:
`#### TRACK 01: TITLE`, `Track 5: Title`, `\\#\\#\\# 1\\. Title` with markdown
escapes intact, or a ruler-delimited dump with every section flattened onto one
line. Rather than write a parser per dialect, this segments on the structural
invariant that actually holds across all of them: a song is a run of bracketed
section cues, and it is preceded by its title.

Everything downstream (the Whisper diff especially) needs the lyric body as an
ordered list of (section_tag, lines) pairs, so that is what this produces.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

# NotebookLM leaves citation artefacts inline in two shapes: [cite: 2] and bare
# numeric refs like [79] or [4, 18, 29, 76]. Only all-numeric brackets are
# stripped, so `[Verse | ...]` is never touched.
CITE_RE = re.compile(r"\s*\[cite:[^\]]*\]")
NUMREF_RE = re.compile(r"\s*\[\d+(?:\s*,\s*\d+)*\]")

# Google Docs exports escape markdown: \[Verse\], \#\#\# 1\. Title, \*(WIP)\*
UNESCAPE_RE = re.compile(r"\\([\[\]#*_`.!|>-])")

# Structural words that identify a bracketed line as a section cue. These appear
# anywhere in the cue's first pipe-segment, not just at the start: the source
# material uses `[Dense Verse 1 | ...]`, `[Anthemic Chorus | ...]`,
# `[Grievance-Driven Chorus | ...]`, `[Meltdown Bridge | ...]`. Requiring the
# keyword to lead would silently drop most of a song.
SECTION_WORDS = (
    "intro|verse|pre-chorus|prechorus|chorus|bridge|outro|drop|end|hook|breakdown|"
    "interlude|refrain|solo|instrumental|gang vocals|spoken|style"
)
SECTION_WORD_RE = re.compile(rf"\b(?:{SECTION_WORDS})\b", re.IGNORECASE)
CUE_LINE_RE = re.compile(r"^\s*\[")

# Word-boundary matched so 'introspective' does not read as an intro cue.
OPENER_WORD_RE = re.compile(r"\b(style|intro)\b", re.IGNORECASE)

# A bare [End] closes the song. Without this, whatever follows the last song in a
# harvest document — "4. RECENT CREATIVE DISCOVERIES" and several paragraphs of
# prose — gets appended to the final section as if it were lyrics.
TERMINATOR_RE = re.compile(r"^\s*end\b", re.IGNORECASE)

# Document structure also closes a section. Most sheets end on [Outro] rather
# than [End], so without this the next track's seal, metadata block, and sonic
# blueprint all land inside the previous song's outro. Lyrics never contain
# markdown headings or horizontal rules, so this is safe and catches every
# between-track preamble regardless of which fields a given harvest emitted.
STRUCTURE_RE = re.compile(
    r"^\s*(#{1,6}\s|[-=*_~]{3,}\s*$)",
    re.IGNORECASE,
)

# No lyric line is this long. Prose paragraphs are.
MAX_LYRIC_LINE = 300

# A line that is nothing but a parenthetical is a stage direction, not a lyric.
PAREN_ONLY_RE = re.compile(r"^\s*[\(\[][^)\]]*[\)\]]\s*$")

# Lines that are metadata furniture in a harvest document, never lyrics or titles.
#
# These are GENERIC document-structure markers only. Label-specific banner text
# used to live here — "VECTOR SOUL RECORDS", "LABEL OFFICER STAMP" — which put one
# label's private vocabulary inside the framework and falsified the claim that
# `framework/` is liftable into any project untouched. A different label's harvest
# would also have parsed worse, because its own banners were not listed.
#
# Per-label markers now come from `label.yaml: import.furniture_markers` and are
# merged in at parse time by `extra_furniture()`.
GENERIC_FURNITURE = (
    r"-{5,}|={5,}|\*{3,}|"
    r"BAND ID|DOCUMENT CLASS|COMPLIANCE (REVISION|STATUS)|PROJECT:|CATALOG:|"
    r"Track Title|BPM ?/ ?Key|Suno Style|Lyrical Matrix Origin|Compilation|"
    r"Completion Status|Standardized Tempo|Musical Key|Creation Date|"
    r"Release Quarter|STATUS|STYLE|TEMPO|BPM|KEY|SUITE|MATRIX|GLITCH|VERSION|"
    r"PRIMARY|SONIC|PRODUCTION|ANOMAL|PRESERV|💿|🎼|🎤|⚠️|"
    r"###? ?(RELEASE|PRODUCTION|SONIC|LYRIC|COMPLETE)"
)

FURNITURE_RE = re.compile(rf"^\s*({GENERIC_FURNITURE})", re.IGNORECASE)


def set_label_furniture(markers: list[str]) -> None:
    """Extend the furniture pattern with this label's own banner text.

    Called from config load. Keeps label vocabulary out of the framework while
    still letting a label describe the documents it actually has to import.
    """
    global FURNITURE_RE
    extra = "|".join(re.escape(m) for m in markers if m)
    pattern = f"{GENERIC_FURNITURE}|{extra}" if extra else GENERIC_FURNITURE
    FURNITURE_RE = re.compile(rf"^\s*({pattern})", re.IGNORECASE)

# Title candidates in priority tiers. An explicit "TRACK 01: X" heading always
# beats a bare capitalised line, because harvest documents put metadata lines
# ("STATUS: Remediated/Active") between the heading and the first cue — and those
# look exactly like bare titles to a naive backward scan.
TITLE_TIERS: list[list[re.Pattern[str]]] = [
    [  # tier 1: explicit track headings
        re.compile(r"^\s*#{0,6}\s*TRACK\s*\d+\s*:\s*(.+?)\s*$", re.IGNORECASE),
        re.compile(r"^\s*#{0,6}\s*Track\s*\d+\s*:\s*(.+?)\s*$", re.IGNORECASE),
        re.compile(r"^\s*#{1,6}\s*\d+\s*[.)]\s*(.+?)\s*$"),
    ],
    [  # tier 2: any markdown heading
        re.compile(r"^\s*#{1,6}\s+(.+?)\s*$"),
    ],
    [  # tier 3: a bare ALL-CAPS or short standalone line
        re.compile(r"^\s*([A-Z0-9][A-Z0-9 '&!?.,\-()]{2,})\s*$"),
    ],
]

# Trailing decorations on a title: "(ACAP-v3.1 Remediated Master)", "*(WIP)*",
# "(Pt. 1: The Infrastructure Grievance)" -> keep Pt. N, drop the rest.
TITLE_CLEAN_RE = re.compile(
    r"\s*[\(\[]\s*(ACAP[^)\]]*|v[\d.]+[^)\]]*|WIP|Remediated[^)\]]*|"
    r"Mastered[^)\]]*|Archived[^)\]]*)\s*[\)\]]\s*",
    re.IGNORECASE,
)


@dataclass
class Section:
    tag: str                       # full bracket contents, verbatim
    lines: list[str] = field(default_factory=list)

    @property
    def name(self) -> str:
        """First pipe-segment, lowercased: '[Verse | fast d-beat...]' -> 'verse'."""
        return self.tag.split("|")[0].strip().rstrip(":").lower()

    @property
    def is_style(self) -> bool:
        return self.name.startswith("style")

    @property
    def sung_lines(self) -> list[str]:
        """Lines that are actually performed.

        A line wholly wrapped in parentheses is a production or performance note
        — "(Spoken)", "(Fast D-beat drum fill, feedback swell)", "(Grinding
        Lemmy-esque bass solo ripping through the mix)". They belong in the sheet
        because they go into Suno's lyric box, but they are not words anyone
        sings, so they must not reach the transcript diff (where they would read
        as divergences) or the repetition miner (where shared stage directions
        read as shared phrases).
        """
        return [ln for ln in self.lines if not PAREN_ONLY_RE.match(ln)]

    @property
    def word_count(self) -> int:
        return sum(len(ln.split()) for ln in self.sung_lines)


@dataclass
class Song:
    title: str
    sections: list[Section] = field(default_factory=list)
    meta: dict = field(default_factory=dict)
    source: str = ""

    @property
    def lyric_sections(self) -> list[Section]:
        return [s for s in self.sections if not s.is_style]

    @property
    def word_count(self) -> int:
        return sum(s.word_count for s in self.lyric_sections)

    def plain_text(self) -> str:
        """Sung words only — no cues, no stage directions. The diff target
        for transcription and the corpus for repetition mining."""
        out: list[str] = []
        for s in self.lyric_sections:
            out.extend(s.sung_lines)
        return "\n".join(out)


def clean_text(raw: str) -> str:
    txt = raw.replace("\r\n", "\n").replace("\r", "\n")
    txt = CITE_RE.sub("", txt)
    txt = NUMREF_RE.sub("", txt)
    txt = UNESCAPE_RE.sub(r"\1", txt)
    # Google Docs non-breaking spaces and smart quotes trip the regexes.
    txt = txt.replace("\u00a0", " ").replace("\u2019", "'").replace("\u2018", "'")
    return txt


def _clean_title(t: str) -> str:
    t = t.strip().strip("*_#").strip()
    # Vision docs quote titles and annex the genre: '"Context Window" (Ska-Punk)'.
    t = re.sub(r"^[\"'“”]+|[\"'“”]+$", "", t.strip()).strip()
    t = re.sub(r"\s*\((?:[^)]*(?:ska|punk|hardcore|reggae|metal|beat|anthem|"
               r"instrumental|tempo|bpm)[^)]*)\)\s*", " ", t, flags=re.IGNORECASE)
    t = re.sub(r"\s*[\[\(]\s*\d*\s*$", "", t)   # dangling '[20' or '('
    t = re.sub(r"^[\"'“”]+|[\"'“”]+$", "", t.strip()).strip()
    t = TITLE_CLEAN_RE.sub(" ", t)
    # Emphasis markers can survive the parenthetical strip: '*(WIP)*' -> '*'.
    t = t.replace("**", " ").replace("*", " ").replace("_", " ")
    t = t.strip(" :-—")
    return re.sub(r"\s{2,}", " ", t).strip()


def is_cue_line(stripped: str) -> bool:
    """A bracketed line whose first pipe-segment names a song section."""
    if not CUE_LINE_RE.match(stripped):
        return False
    head = stripped[1:].split("|", 1)[0].split("]", 1)[0]
    return bool(SECTION_WORD_RE.search(head))


def is_opener(tag: str) -> bool:
    """Does this cue open a song? Checked against the first pipe-segment only,
    so a verse whose attributes mention an intro does not split the song."""
    head = tag.split("|", 1)[0]
    return bool(OPENER_WORD_RE.search(head))


def _find_title(lines: list[str], before: int) -> str | None:
    """Walk backwards from a song opener looking for its title, by priority tier.

    Each tier sweeps the whole window before the next is tried, so an explicit
    'TRACK 02: IRON MIND' twenty lines up wins over a 'STATUS: Active' line two
    lines up.
    """
    window = []
    for i in range(before - 1, max(-1, before - 30), -1):
        ln = lines[i].strip()
        if not ln or FURNITURE_RE.match(ln) or is_cue_line(ln):
            continue
        window.append(ln)

    for tier in TITLE_TIERS:
        for ln in window:
            for pat in tier:
                m = pat.match(ln)
                if m:
                    cand = _clean_title(m.group(1))
                    if cand and len(cand) > 1 and not FURNITURE_RE.match(cand):
                        return cand

    # Last resort: the nearest short standalone line.
    for ln in window:
        if len(ln) < 60 and not ln.endswith((":", ".")):
            cand = _clean_title(ln)
            if cand and len(cand) > 1 and not FURNITURE_RE.match(cand):
                return cand
    return None


def _split_flattened(line: str) -> list[tuple[str, str]]:
    """Handle the one-line dialect: '[Cue | ...] lyric lyric [Cue2 | ...] more'.

    Returns (tag, trailing_text) pairs. Depth-tracking rather than a regex,
    because cue attributes themselves can contain brackets.
    """
    out: list[tuple[str, str]] = []
    i = 0
    while i < len(line):
        if line[i] != "[":
            i += 1
            continue
        depth = 0
        j = i
        while j < len(line):
            if line[j] == "[":
                depth += 1
            elif line[j] == "]":
                depth -= 1
                if depth == 0:
                    break
            j += 1
        if j >= len(line):
            break
        tag = line[i + 1 : j].strip()
        nxt = line.find("[", j + 1)
        trailing = line[j + 1 : nxt if nxt != -1 else len(line)].strip()
        out.append((tag, trailing))
        i = j + 1 if nxt == -1 else nxt
    return out


def parse(raw: str, source: str = "") -> list[Song]:
    """Extract every song in a document."""
    lines = clean_text(raw).split("\n")
    songs: list[Song] = []
    current: Song | None = None
    current_section: Section | None = None
    seen_opener = False
    dormant = False  # past a terminator: ignore body text until the next opener

    def flush_section() -> None:
        nonlocal current_section
        if current and current_section is not None:
            current.sections.append(current_section)
        current_section = None

    for idx, line in enumerate(lines):
        stripped = line.strip()
        if not stripped:
            continue

        # Structure closes the current section and suspends body capture until
        # the next song opener. Checked before everything else so it applies
        # whatever state we are in.
        if STRUCTURE_RE.match(stripped):
            flush_section()
            dormant = True
            continue

        cues = _split_flattened(stripped) if is_cue_line(stripped) else []

        if cues:
            opener = is_opener(cues[0][0])

            # A new song begins on an opener, but only once we've already banked
            # one — otherwise the first [Intro] would close the song it opens.
            if opener and seen_opener and current and current.lyric_sections:
                flush_section()
                songs.append(current)
                current = None

            if current is None:
                title = _find_title(lines, idx) or f"Untitled {len(songs) + 1}"
                current = Song(title=title, source=source)
                seen_opener = False

            # Any cue puts us back in lyric territory — dormancy only ever
            # suppresses the prose that sits *between* cues.
            dormant = False
            if opener:
                seen_opener = True

            for tag, trailing in cues:
                flush_section()
                current_section = Section(tag=tag)
                if trailing:
                    current_section.lines.append(trailing)
                if TERMINATOR_RE.match(tag):
                    dormant = True
            continue

        # Non-cue line: lyric body if we're inside a live section, else furniture.
        if current is not None and current_section is not None and not dormant:
            if FURNITURE_RE.match(stripped):
                continue
            if stripped.startswith("#"):
                continue
            # A markdown code fence is document furniture, never something sung.
            # Five imported sheets carried a stray closing fence from their
            # original harvest and it was captured as a lyric line, which put it in
            # plain_text() and inflated word_count by one on each of them.
            #
            # Scope, checked rather than assumed: the transcript diff was NOT
            # affected. `analyze` tokenises to [a-z0-9']+, which drops the fence
            # entirely — Iron Mind's stored expected_words was 353 while its
            # word_count read 354, and the 353 was right. The visible damage was to
            # the rendered catalogue, where an odd number of fences inside a fenced
            # block made whole tracks disappear from the page.
            if stripped.startswith("```"):
                continue
            if len(stripped) > MAX_LYRIC_LINE:
                # Silently dropping it made a truncated import look complete.
                # Record it on the song so callers can surface it.
                current.meta.setdefault("dropped_long_lines", []).append(
                    stripped[:80] + "..."
                )
                continue
            current_section.lines.append(stripped)

    flush_section()
    if current and current.lyric_sections:
        songs.append(current)
    return songs


SHEET_TEMPLATE = """---
band: {band}
track_id: {track_id}
title: {title}
slug: {slug}
document_class: LYRIC_SHEET_STANDARD
era: {era}
imported_from: {source}
---

# {title}

## Lyrics

{body}
"""


def emit_sheet(song: Song, band: str, track_id: str, slug: str, era: str) -> str:
    blocks: list[str] = []
    for s in song.sections:
        blocks.append(f"[{s.tag}]")
        if s.lines:
            blocks.append("\n".join(s.lines))
        blocks.append("")
    return SHEET_TEMPLATE.format(
        band=band,
        track_id=track_id,
        title=song.title,
        slug=slug,
        era=era,
        source=song.source or "unknown",
        body="\n".join(blocks).rstrip() + "\n",
    )


def load_sheet(path: Path) -> Song:
    """Read back a sheet this module wrote."""
    txt = path.read_text(encoding="utf-8")
    title = path.stem
    m = re.search(r"^title:\s*(.+)$", txt, re.MULTILINE)
    if m:
        title = m.group(1).strip()
    body = txt.split("## Lyrics", 1)[-1]
    songs = parse(body, source=str(path))
    if songs:
        songs[0].title = title
        return songs[0]
    return Song(title=title, source=str(path))
