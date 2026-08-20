"""Triage heuristics and the adjudication gate.

Triage decides what a human is asked about. Both failure directions are expensive
and neither announces itself: discard too much and a real synthesis failure is
buried in an auto-discard list nobody reads; discard too little and one track
produces 49 decisions, nine tracks produce 441, and a human asked for 441 decisions
makes none.

The line is not "small difference" versus "large". "god" for "Gaussian" is one word
and is the best glitch in the reference catalogue. It is whether the two texts mean
different things.
"""

from __future__ import annotations

import pytest

from framework.forge import adjudicate as adj


def cand(ctype="lyric-divergence", phrase=None, heard=None, timecode="01:50", **kw):
    c = {
        "type": ctype,
        "anchor": {"timecode": timecode, "phrase": phrase},
        "heard": heard,
    }
    c.update(kw)
    return c


# --- flattening -------------------------------------------------------------
#
# This is the whole basis of "notation difference versus vocal event".

@pytest.mark.parametrize("text,expected", [
    ("closed-loop", "closedloop"),
    ("closed loop", "closedloop"),
    ("Closed Loop", "closedloop"),
    ("want to", "wantto"),
    ("wanna", "wantto"),            # contraction expanded
    ("gonna", "goingto"),
    ("don't", "donot"),
    ("under my own sky!", "undermyownsky"),
    ("", ""),
    (None, ""),
])
def test_flatten(text, expected):
    assert adj._flatten(text) == expected


@pytest.mark.parametrize("a,b,expected", [
    ("", "", 0),
    ("abc", "abc", 0),
    ("abc", "abd", 1),
    ("abc", "ab", 1),
    ("ab", "abc", 1),
    ("kitten", "sitting", 3),
    ("", "abc", 3),
])
def test_edit_distance(a, b, expected):
    assert adj._edit_distance(a, b) == expected


# --- triage: auto-discards --------------------------------------------------

def test_hyphenation_is_notation_not_a_glitch():
    material, reason = adj.triage(cand(phrase="closed-loop", heard="closed loop"))
    assert material is False
    assert "notation only" in reason


def test_contraction_is_notation_not_a_glitch():
    material, reason = adj.triage(cand(phrase="want to", heard="wanna"))
    assert material is False
    assert "notation only" in reason


def test_function_word_swap_is_transcription_noise():
    material, reason = adj.triage(cand(phrase="the", heard="a"))
    assert material is False
    assert "function word" in reason


def test_one_character_difference_on_a_short_word_is_below_the_floor():
    material, reason = adj.triage(cand(phrase="cold", heard="bold"))
    assert material is False
    assert "one-character" in reason


def test_nothing_on_either_side_is_not_judgeable():
    material, reason = adj.triage(cand(phrase=None, heard=None))
    assert material is False
    assert "nothing to judge" in reason


def test_low_confidence_clipping_on_an_mp3_is_decoder_overshoot():
    material, reason = adj.triage(cand(ctype="clipping", confidence=0.1))
    assert material is False
    assert "decoder" in reason


# --- triage: the ones that must survive -------------------------------------
#
# These are the regression tests that matter. Every one of them is a real entry in
# the reference catalogue, and a triage rule that swallowed any of them would be
# deleting the most valuable output the analyser produces.

@pytest.mark.parametrize("phrase,heard", [
    ("Gaussian", "god"),                 # one word, and the best glitch in the set
    ("analog", "and a lot of"),          # a word the song is named after
    ("algorithms", "all the rhythms"),
    ("the network hums", "when wet water comes"),
    ("anthropogenic drought", "the edge of Virginia"),
    ("pride", "prize"),                  # distance 1 but too long to be noise
])
def test_meaning_changing_divergences_are_material(phrase, heard):
    material, reason = adj.triage(cand(phrase=phrase, heard=heard))
    assert material is True, f"{phrase!r} -> {heard!r} was discarded: {reason}"
    assert reason == ""


def test_the_short_word_floor_does_not_extend_to_longer_words():
    """'pride'/'prize' is edit distance 1, but min length 5 is past the floor of 4.

    The floor exists for genuine transcription slop on tiny words, not to swallow
    near-homophones that mean something else.
    """
    assert adj._edit_distance("pride", "prize") == 1
    assert adj.triage(cand(phrase="pride", heard="prize"))[0] is True
    # ...whereas at four characters it is noise.
    assert adj.triage(cand(phrase="cold", heard="bold"))[0] is False


def test_high_confidence_clipping_is_material():
    assert adj.triage(cand(ctype="clipping", confidence=0.8))[0] is True


def test_a_function_word_against_a_content_word_is_material():
    """Both sides must be function words for it to be noise."""
    assert adj.triage(cand(phrase="the", heard="death"))[0] is True


# --- candidate identity -----------------------------------------------------

def test_key_is_stable_across_runs():
    c = cand(phrase="analog", heard="and a lot of")
    assert adj._key(c) == adj._key(dict(c))


def test_key_separates_different_timecodes():
    a = cand(phrase="analog", timecode="01:50")
    b = cand(phrase="analog", timecode="02:10")
    assert adj._key(a) != adj._key(b)


# --- the gate ---------------------------------------------------------------

def track(verdict="ok", **kw):
    t = {
        "slug": "a-song",
        "id": "T-001",
        "title": "A Song",
        "analysis": {"asr": {"verdict": verdict}},
    }
    t.update(kw)
    return t


def test_sheet_mismatch_refuses_adjudication_entirely():
    """Divergences between two documents are not synthesis failures.

    Adjudicating them would write fiction into the glitch log, so the gate refuses
    rather than presenting them.
    """
    g = adj._gate(track(verdict="sheet-mismatch: 0.41"), [cand(phrase="a", heard="b")])
    assert g.adjudicable is False
    assert "different" in g.reason and "arrangements" in g.reason


def test_unreliable_transcription_is_flagged_but_still_adjudicable():
    """Judge by ear or leave pending — but the tool does not conclude on its own."""
    g = adj._gate(
        track(verdict="asr-unreliable: coverage 0.30"),
        [cand(phrase="Gaussian", heard="god")],
    )
    assert g.adjudicable is True
    assert g.unverified is True
    assert "unverified" in g.reason


def test_a_clean_verdict_carries_no_caveat():
    g = adj._gate(track(), [cand(phrase="Gaussian", heard="god")])
    assert g.adjudicable is True
    assert g.unverified is False
    assert g.reason == ""


def test_non_adjudicable_types_never_reach_the_human():
    g = adj._gate(track(), [
        cand(ctype="sheet-mismatch", phrase="a", heard="b"),
        cand(ctype="asr-unreliable", phrase="a", heard="b"),
        cand(ctype="not-a-real-type", phrase="a", heard="b"),
    ])
    assert g.candidates == []


def test_a_repeated_chorus_glitch_is_one_judgement_not_several():
    """THE BUG this guards: a chorus repeats, so its glitch repeats.

    The same expected/heard pair at three timecodes is one decision. The other
    timecodes ride along as evidence rather than becoming separate questions.
    """
    g = adj._gate(track(), [
        cand(phrase="analog", heard="and a lot of", timecode="01:50"),
        cand(phrase="analog", heard="and a lot of", timecode="01:55"),
        cand(phrase="analog", heard="and a lot of", timecode="02:40"),
    ])
    material = [c for c in g.candidates if c["_material"]]
    assert len(material) == 1
    assert sorted(material[0]["_also_at"]) == ["01:55", "02:40"]


def test_dedup_is_on_flattened_text_so_notation_does_not_split_a_group():
    g = adj._gate(track(), [
        cand(phrase="closed-loop", heard="close the loop", timecode="00:10"),
        cand(phrase="closed loop", heard="close the loop", timecode="00:20"),
    ])
    material = [c for c in g.candidates if c["_material"]]
    assert len(material) == 1


def test_only_the_worst_tempo_drift_is_queued():
    """Four drift findings per track crowd out everything else."""
    g = adj._gate(track(), [
        cand(ctype="tempo-drift", phrase="s1", timecode="00:10"),
        cand(ctype="tempo-drift", phrase="s2", timecode="00:20"),
        cand(ctype="tempo-drift", phrase="s3", timecode="00:30"),
    ])
    material = [c for c in g.candidates if c["_material"]]
    assert len(material) == adj.MAX_TEMPO_DRIFT_PER_TRACK
    discarded = [c for c in g.candidates if not c["_material"]]
    assert any("further tempo deviation" in c["_triage_reason"] for c in discarded)


def test_presentation_is_capped_but_nothing_is_thrown_away():
    """Beyond the cap they are still in the file, marked, and flippable."""
    many = [
        cand(phrase=f"phrase number {i}", heard=f"heard number {i}", timecode=f"00:{i:02d}")
        for i in range(adj.MAX_PRESENTED_PER_TRACK + 6)
    ]
    g = adj._gate(track(), many)
    material = [c for c in g.candidates if c["_material"]]
    assert len(material) == adj.MAX_PRESENTED_PER_TRACK
    assert len(g.candidates) == len(many)   # every candidate is still present
    beyond = [c for c in g.candidates if not c["_material"]]
    assert all(c["_triage_reason"] for c in beyond), "a discard must carry its reason"


def test_every_auto_discard_records_why():
    """An unexplained discard is indistinguishable from a bug."""
    g = adj._gate(track(), [
        cand(phrase="closed-loop", heard="closed loop"),
        cand(phrase="the", heard="a", timecode="00:20"),
        cand(phrase="cold", heard="bold", timecode="00:30"),
    ])
    assert g.candidates, "the discards must remain visible in the file"
    for c in g.candidates:
        assert c["_material"] is False
        assert c["_triage_reason"].strip()
