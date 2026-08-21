"""The lyric parser state machine.

Every test here locks down a bug that actually shipped. The parser is the riskiest
module in the project for one reason: when it fails it fails *silently*. A dropped
section does not raise, it just produces a shorter song, and nothing downstream can
tell the difference between "the song is short" and "we lost half of it". Three of
the four bugs below were found by reading output, not by reading code.
"""

from __future__ import annotations

import pytest

from framework.forge import lyrics


@pytest.fixture(autouse=True)
def _restore_furniture():
    """`set_label_furniture` mutates a module global. Put it back."""
    original = lyrics.FURNITURE_RE
    yield
    lyrics.FURNITURE_RE = original


# --- cue recognition --------------------------------------------------------
#
# THE BUG: the section keyword was anchored to the start of the bracket, so
# `[Dense Verse 1 | ...]` did not read as a cue. The source material almost never
# leads with the bare keyword, so this silently dropped most of every song. The
# fix was to search the whole first pipe-segment.

@pytest.mark.parametrize("line", [
    "[Verse]",
    "[Verse | fast d-beat, no cymbals]",
    "[Dense Verse 1 | wall of guitar]",
    "[Anthemic Chorus | gang vocals]",
    "[Grievance-Driven Chorus]",
    "[Meltdown Bridge | feedback swell]",
    "[Pre-Chorus | build]",
    "[Gang Vocals | shouted]",
    "  [Outro | fade out]",
])
def test_cue_keyword_is_found_anywhere_in_the_first_segment(line):
    assert lyrics.is_cue_line(line) is True


@pytest.mark.parametrize("line", [
    "a plain lyric line",
    "[Not A Cue At All]",
    "[Speaker | verse]",          # keyword is past the pipe: attributes, not a cue
    "",
    "   ",
])
def test_non_cues_are_rejected(line):
    assert lyrics.is_cue_line(line) is False


# --- openers ----------------------------------------------------------------
#
# A new song begins on an opener, so a false positive here splits one song into
# two. Matched on word boundaries specifically so "introspective" is not an intro.

@pytest.mark.parametrize("tag,expected", [
    ("Intro", True),
    ("Intro | slow build", True),
    ("Style", True),
    ("Style | 1979 punk", True),
    ("Introspective Verse", False),   # 'intro' inside a longer word
    ("Verse", False),
    ("Verse | intro-like feel", False),  # opener word is past the pipe
    ("Chorus", False),
])
def test_is_opener(tag, expected):
    assert lyrics.is_opener(tag) is expected


# --- terminators ------------------------------------------------------------
#
# THE BUG: `[End]` did not stop capture, so everything after the last song in a
# harvest document — headings, prose, several paragraphs of commentary — was
# appended to the final section as lyrics. One song measured 771 words and was
# actually 349.

def test_end_cue_stops_body_capture():
    doc = """## TRACK 01: TEST TITLE

[Intro | slow]
first sung line
[Verse | fast]
second sung line
[End]
4. RECENT CREATIVE DISCOVERIES
This is prose commentary that must never be captured as lyrics.
Neither should this paragraph.
"""
    (song,) = lyrics.parse(doc)
    body = song.plain_text()
    assert "first sung line" in body
    assert "second sung line" in body
    assert "prose commentary" not in body
    assert "RECENT CREATIVE DISCOVERIES" not in body
    assert song.word_count == 6  # three words x two lines


def test_a_cue_after_a_terminator_wakes_the_parser_back_up():
    """Dormancy suppresses prose between cues; it must not swallow a real section."""
    doc = """## TRACK 01: T

[Intro | x]
alpha
[End]
stray prose here
[Verse | y]
beta
"""
    (song,) = lyrics.parse(doc)
    assert "beta" in song.plain_text()
    assert "stray prose" not in song.plain_text()


# --- document structure -----------------------------------------------------
#
# THE BUG: most sheets end on `[Outro]` rather than `[End]`, so the next track's
# metadata block and sonic blueprint landed inside the previous song's outro. This
# was reported by the user as "roots futuria's lyrics don't look formatted like the
# rest" — the parser was not wrong about the cues, it was wrong about where the
# song stopped.

@pytest.mark.parametrize("closer", [
    "### RELEASE METADATA",
    "## Production notes",
    "---",
    "====",
    "***",
])
def test_document_structure_closes_the_section(closer):
    doc = f"""## TRACK 01: T

[Outro | fade]
the last sung line
{closer}
STATUS: Remediated/Active
Prose about the release that is not a lyric.
"""
    (song,) = lyrics.parse(doc)
    body = song.plain_text()
    assert "the last sung line" in body
    assert "Prose about the release" not in body
    assert "Remediated" not in body


# --- stage directions -------------------------------------------------------
#
# A parenthetical-only line goes into Suno's lyric box but nobody sings it. It has
# to stay in the sheet and stay out of the transcript diff (where it reads as a
# divergence) and the repetition miner (where shared stage directions read as
# shared phrases).

def test_sung_lines_excludes_parenthetical_only_lines():
    s = lyrics.Section(tag="Verse | x", lines=[
        "(Spoken)",
        "hold the perimeter",
        "(Grinding bass solo ripping through the mix)",
        "the panel is hot",
        "[muffled]",
    ])
    assert s.sung_lines == ["hold the perimeter", "the panel is hot"]
    assert s.word_count == 7


def test_parentheses_inside_a_line_are_kept():
    """Only a *wholly* parenthetical line is a direction."""
    s = lyrics.Section(tag="Verse", lines=["hold the line (again) now"])
    assert s.sung_lines == ["hold the line (again) now"]


def test_plain_text_drops_style_sections_and_cues():
    doc = """## TRACK 01: T

[Style | 1979 hardcore, 200 bpm]
this is a style directive not a lyric
[Verse | x]
(Spoken)
real words here
"""
    (song,) = lyrics.parse(doc)
    assert song.plain_text() == "real words here"


# --- furniture and the liftability claim ------------------------------------
#
# THE BUG: one label's banner text ("VECTOR SOUL RECORDS", "LABEL OFFICER STAMP")
# was hardcoded in this module, which falsified the claim that `framework/` lifts
# into any project untouched — and parsed a *different* label's harvest worse,
# because its banners were not in the list.

def test_framework_contains_no_label_vocabulary():
    """The load-bearing test for the framework/label split."""
    for private in ("VECTOR SOUL", "LABEL OFFICER", "AUTHENTICITY ENVELOPE"):
        assert private.lower() not in lyrics.GENERIC_FURNITURE.lower()


def test_generic_furniture_is_filtered_by_default():
    doc = """## TRACK 01: T

[Verse | x]
a real lyric
BPM/Key: 172 / A minor
DOCUMENT CLASS: whatever
another real lyric
"""
    (song,) = lyrics.parse(doc)
    body = song.plain_text()
    assert body == "a real lyric\nanother real lyric"


def test_label_furniture_is_opt_in():
    doc = """## TRACK 01: T

[Verse | x]
a real lyric
MY PRIVATE BANNER
"""
    before = lyrics.parse(doc)[0].plain_text()
    assert "MY PRIVATE BANNER" in before, "unknown banners are lyrics until declared"

    lyrics.set_label_furniture(["MY PRIVATE BANNER"])
    after = lyrics.parse(doc)[0].plain_text()
    assert after == "a real lyric"


def test_set_label_furniture_keeps_the_generic_markers():
    lyrics.set_label_furniture(["MY PRIVATE BANNER"])
    doc = """## TRACK 01: T

[Verse | x]
a real lyric
DOCUMENT CLASS: still furniture
MY PRIVATE BANNER
"""
    assert lyrics.parse(doc)[0].plain_text() == "a real lyric"


def test_set_label_furniture_with_no_markers_is_harmless():
    lyrics.set_label_furniture([])
    doc = "## T\n\n[Verse | x]\na real lyric\nDOCUMENT CLASS: x\n"
    assert lyrics.parse(doc)[0].plain_text() == "a real lyric"


# --- long lines -------------------------------------------------------------
#
# Silently dropping an over-long line made a truncated import look complete, so
# the drop is recorded on the song where a caller can surface it.

def test_a_code_fence_is_not_a_lyric():
    """THE BUG: five imported sheets carried a stray closing fence from their
    original harvest, and it was captured as a sung line.

    That put it in plain_text() and inflated word_count by one on each of them.
    The transcript diff was NOT affected — `analyze` tokenises to [a-z0-9']+ and
    drops the fence, which was verified against the stored counts rather than
    assumed. The damage was to the rendered catalogue: an odd number of fences
    inside a fenced block made whole tracks vanish from the page.
    """
    fence = chr(96) * 3
    doc = f"""## TRACK 01: T

[Verse | x]
a real lyric
{fence}
"""
    (song,) = lyrics.parse(doc)
    assert song.plain_text() == "a real lyric"
    assert song.word_count == 3


def test_over_long_lines_are_recorded_not_silently_dropped():
    prose = "word " * 100  # >300 chars
    doc = f"""## TRACK 01: T

[Verse | x]
a real lyric
{prose}
"""
    (song,) = lyrics.parse(doc)
    assert song.plain_text() == "a real lyric"
    assert len(song.meta["dropped_long_lines"]) == 1
    assert song.meta["dropped_long_lines"][0].endswith("...")


# --- titles -----------------------------------------------------------------
#
# THE BUG: a naive backward scan grabbed "STATUS: Remediated/Active" as the title,
# because harvest documents put metadata between the heading and the first cue and
# those lines look exactly like bare titles. Fixed with priority tiers.

def test_explicit_track_heading_beats_a_nearer_metadata_line():
    doc = """## TRACK 02: IRON MIND
STATUS: Remediated/Active
COMPLETION STATUS: done

[Intro | slow]
a line
"""
    (song,) = lyrics.parse(doc)
    assert song.title == "IRON MIND"


def test_untitled_fallback_is_numbered():
    (song,) = lyrics.parse("[Intro | x]\na line\n")
    assert song.title == "Untitled 1"


# --- multiple songs ---------------------------------------------------------

def test_an_opener_starts_a_new_song_but_not_the_first_one():
    doc = """## TRACK 01: FIRST

[Intro | x]
song one line
[Verse | x]
more of song one

## TRACK 02: SECOND

[Intro | x]
song two line
"""
    songs = lyrics.parse(doc)
    assert [s.title for s in songs] == ["FIRST", "SECOND"]
    assert "song two line" not in songs[0].plain_text()
    assert "song one line" not in songs[1].plain_text()


# --- flattened dialect ------------------------------------------------------

def test_one_line_dialect_is_split_into_sections():
    doc = "## T\n\n[Intro | x] first bit [Verse | y] second bit\n"
    (song,) = lyrics.parse(doc)
    assert [s.name for s in song.sections] == ["intro", "verse"]
    assert song.plain_text() == "first bit\nsecond bit"


# --- text cleaning ----------------------------------------------------------

@pytest.mark.parametrize("raw,expected", [
    ("a line [cite: 2]", "a line"),
    ("a line [79]", "a line"),
    ("a line [4, 18, 29]", "a line"),
    (r"\[Verse\]", "[Verse]"),
    (r"\#\#\# 1\. Title", "### 1. Title"),
])
def test_clean_text(raw, expected):
    assert lyrics.clean_text(raw) == expected


def test_clean_text_leaves_real_cues_alone():
    """Only all-numeric brackets are citation noise."""
    assert lyrics.clean_text("[Verse | fast]") == "[Verse | fast]"

def test_clean_text_normalises_invisible_characters():
    """Built with chr() on purpose.

    A non-breaking space and smart quotes are invisible in a source file. Written
    literally, an editor normalising them would make this test vacuous without it
    ever failing -- and these three characters are exactly what breaks the parser
    regexes when a document comes out of Google Docs.
    """
    nbsp, rsquo, lsquo = chr(0x00A0), chr(0x2019), chr(0x2018)
    assert lyrics.clean_text("nb" + nbsp + "space") == "nb space"
    assert lyrics.clean_text("smart" + rsquo + "s quote") == "smart's quote"
    assert lyrics.clean_text(lsquo + "quoted" + rsquo) == "'quoted'"
