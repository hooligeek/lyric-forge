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


# --- render length ---------------------------------------------------------
#
# Coverage alone conflates two different failures: an unintelligible vocal, and a
# render that was never given long enough and dropped material. Those need opposite
# responses — fix the delivery, or ask for a longer arrangement — so the duration is
# what tells them apart.
#
# The first version of this check measured the wrong thing. It asked whether the
# SHEET was long for the band, and it was not: a released track on the same act
# carries 285 words at 3:35. The sheet was fine, the render was short, and a check
# built on the wrong theory reported nothing at all.

SHEET_HEAD = "---\nband: b\n---\n\n## Lyrics\n\n[Verse | a | b | c]\n"


def _sheet_text(words: int) -> str:
    """Ten words per line.

    One giant line gets dropped by the parser's MAX_LYRIC_LINE guard and the sheet
    then counts zero words — which is how an earlier version of this helper made a
    working check look broken. Test data has to be as realistic as the seam it
    exercises.
    """
    lines = [" ".join(["word"] * 10) for _ in range(words // 10)]
    if words % 10:
        lines.append(" ".join(["word"] * (words % 10)))
    return SHEET_HEAD + "\n".join(lines) + "\n"


def _band(tmp_path, refs, subject_words, subject_dur, monkeypatch):
    """A band whose reference tracks have real sheets on disk.

    Real files rather than a patched `exists`, because the check reads the
    filesystem and stubbing that seam would hide exactly the class of mistake this
    helper exists to catch.
    """
    rows = []
    for i, (words, dur) in enumerate(refs):
        (tmp_path / f"ref{i}.md").write_text(_sheet_text(words), encoding="utf-8")
        rows.append({"slug": f"ref{i}", "lyric_sheet": f"ref{i}.md", "duration_s": dur})
    (tmp_path / "subject.md").write_text(_sheet_text(subject_words), encoding="utf-8")
    rows.append({"slug": "subject", "lyric_sheet": "subject.md",
                 "duration_s": subject_dur})

    monkeypatch.setattr(review.config_mod, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(review.ledger_mod, "load_band_tracks", lambda band: rows)
    cfg = type("Cfg", (), {"bands": {"b": object()}})()
    song = type("S", (), {"word_count": subject_words})()
    return cfg, song


# Rates taken from the real catalogue: 285w/3:35, 400w/4:01, 236w/2:41 — roughly
# 80, 100 and 88 words per minute.
REFS = [(285, 215), (400, 241), (236, 161)]


@pytest.mark.parametrize("dur,fires", [
    (114, True),    # 1:54 — the real case. 288 words need 2.9 min at the fastest rate
    (180, False),   # 3:00 — comfortably enough
    (174, False),   # 2:54 — just enough
])
def test_render_too_short_fires_only_when_the_words_cannot_fit(
    tmp_path, monkeypatch, dur, fires
):
    cfg, song = _band(tmp_path, REFS, 288, dur, monkeypatch)
    found = review.check_render_length(cfg, song, "b", "subject")
    assert bool(found) is fires
    if fires:
        assert "nowhere to go" in found[0].detail
        assert found[0].severity == "advisory"


def test_it_measures_against_the_fastest_rate_not_the_average(tmp_path, monkeypatch):
    """Best case for the render, so the finding stays conservative. Measured against
    the average it would fire on songs that could plausibly have fitted."""
    cfg, song = _band(tmp_path, REFS, 288, 175, monkeypatch)
    assert review.check_render_length(cfg, song, "b", "subject") == []


def test_it_abstains_without_enough_evidence(tmp_path, monkeypatch):
    """Two reference tracks is not a measured rate. Saying nothing beats guessing."""
    cfg, song = _band(tmp_path, REFS[:2], 288, 60, monkeypatch)
    assert review.check_render_length(cfg, song, "b", "subject") == []


def test_it_abstains_before_a_render_exists(tmp_path, monkeypatch):
    """No duration means nothing to compare against — which is the case the first
    version of this check got wrong by trying to judge a sheet pre-render."""
    cfg, song = _band(tmp_path, REFS, 288, None, monkeypatch)
    assert review.check_render_length(cfg, song, "b", "subject") == []


def test_it_abstains_with_no_band_or_no_track(tmp_path, monkeypatch):
    cfg, song = _band(tmp_path, REFS, 288, 114, monkeypatch)
    assert review.check_render_length(cfg, song, None, "subject") == []
    assert review.check_render_length(cfg, song, "b", None) == []
