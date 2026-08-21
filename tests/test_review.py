"""Mechanical review checks.

Everything here is decidable without a model, which is the whole split: checkable
things are checked in code and only genuine judgement is delegated. A mechanical
check that fires on correct work is worse than no check, because it trains the
author to ignore the report.
"""

from __future__ import annotations

import pytest

from framework.forge import lyrics, review


def _findings(doc: str, rule: str) -> list:
    (song,) = lyrics.parse("## TRACK 01: T\n\n" + doc)
    return [f for f in review.check_cues(song) if f.rule == rule]


# --- the bare-cue rule ------------------------------------------------------
#
# THE BUG: a terminator was being held to the section formula. `[End | Genre/Era |
# Vocal Texture | Production Vibe]` is nonsense — nothing is performed there, it
# marks where performance stops. Eleven committed sheets close on a bare `[End]`
# and it is the house convention for three of the five acts, so the check was
# telling authors to break their own band's convention to satisfy a rule that was
# never about them.

def test_a_bare_terminator_is_not_a_bare_cue():
    doc = "[Verse | punk 1994 | nasal, dry | palm-muted]\nalpha\n[End]\n"
    assert _findings(doc, "bare-cue") == []


def test_a_genuinely_bare_section_cue_is_still_flagged():
    """The negative control. Exempting terminators must not exempt everything."""
    doc = "[Verse | punk 1994 | nasal, dry | palm-muted]\nalpha\n[Chorus]\nbeta\n[End]\n"
    found = _findings(doc, "bare-cue")
    assert len(found) == 1
    assert "[Chorus]" in found[0].quote


@pytest.mark.parametrize("cue", ["[End]", "[end]", "[  End  ]"])
def test_terminator_forms_are_exempt_whatever_the_casing(cue):
    """The exemption reads TERMINATOR_RE rather than keeping a second list of
    closing words that could drift from the parser's."""
    doc = "[Verse | punk | dry | flat]\nalpha\n" + cue + "\n"
    assert _findings(doc, "bare-cue") == []


def test_ending_is_not_a_terminator_and_never_was():
    """Boundary worth pinning. TERMINATOR_RE is anchored with a word boundary, so
    "Ending" does not match it — and SECTION_WORD_RE does not match it either, so
    `[Ending]` is not read as a cue at all. A test asserting it were exempt would
    have passed vacuously and proved nothing.
    """
    assert not lyrics.TERMINATOR_RE.match("Ending")
    assert lyrics.is_cue_line("[Ending]") is False


def test_a_style_section_is_exempt_too():
    """Pre-existing behaviour, pinned so the terminator change did not disturb it."""
    doc = "[Style: fast melodic hardcore, 180 BPM]\n[Verse | punk | dry | flat]\nalpha\n"
    assert _findings(doc, "bare-cue") == []
