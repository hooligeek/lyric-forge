"""Stage derivation.

The invariant this module exists to hold: a track's stage is derived from what
actually exists, never read from a field someone has to remember to update. A
recorded stage that disagrees with reality is worse than no stage at all, so the
stored value is read only to report the disagreement.
"""

from __future__ import annotations

import pytest

from framework.forge import lifecycle as lc

ORDER = ["spark", "brief", "draft", "review", "sheet",
         "rendered", "analysed", "adjudicated", "mastered"]


def track_at(stage: str) -> dict:
    """A track carrying exactly the fields needed to satisfy `stage` and no more."""
    i = ORDER.index(stage)
    t: dict = {"id": "T-001", "title": "A Song", "band": "a-band"}
    prov: dict = {}
    matrix: dict = {}
    suno: dict = {}
    if i >= 0:
        prov["spark"] = "2026-08-20-abc123"
    if i >= 1:
        prov["brief_confirmed"] = True
        matrix.update(suite="B", stance="procedure")
    if i >= 2:
        prov["draft"] = "draft.md"
        prov["prompt_template"] = "generate-song@3"
    if i >= 3:
        prov["review"] = "review.json"
    if i >= 4:
        t["lyric_sheet"] = "sheets/a-song.md"
        suno.update(style_prompt="1979 hardcore", declared_bpm=172)
    if i >= 5:
        t.update(audio="a-song.mp3", audio_sha256="deadbeef")
    if i >= 6:
        t["analysis"] = {"dsp": {"peak": -0.1}}
    if i >= 7:
        t["glitch_log"] = [{"protocol": "Signal Bleed"}]
    if prov:
        t["provenance"] = prov
    if matrix:
        t["matrix"] = matrix
    if suno:
        t["suno"] = suno
    return t


# --- _has -------------------------------------------------------------------
#
# THE BUG: `False is not in (None, "", [], {})`, so an unset boolean flag read as
# present and advanced the gate it was meant to hold. `brief_confirmed: false`
# means "proposed, not agreed", and the tool reported the brief as agreed. Falsy
# is absent.

@pytest.mark.parametrize("value,present", [
    (False, False),         # the regression
    (None, False),
    ("", False),
    ([], False),
    ({}, False),
    (True, True),
    ("something", True),
    (["one"], True),
    ({"k": "v"}, True),
    (0, True),              # see the dedicated test below
    (172, True),
])
def test_has_treats_falsy_as_absent(value, present):
    assert lc._has({"field": value}, "field") is present


def test_zero_counts_as_present():
    """Documented rather than asserted as desirable.

    Only `False` is special-cased, so a numeric 0 reads as a value. No stage
    requirement is a number where 0 would be meaningful, so this is currently
    harmless — but it is the same shape as the `False` bug and worth pinning so a
    change is deliberate.
    """
    assert lc._has({"declared_bpm": 0}, "declared_bpm") is True


def test_has_walks_nested_paths():
    assert lc._has({"provenance": {"spark": "x"}}, "provenance.spark") is True
    assert lc._has({"provenance": {}}, "provenance.spark") is False
    assert lc._has({}, "provenance.spark") is False
    assert lc._has({"provenance": {"spark": False}}, "provenance.spark") is False


def test_an_unconfirmed_brief_does_not_advance_the_gate():
    """The end-to-end form of the bug above.

    The brief proposal is computed and written automatically, so its existence
    proves nothing about agreement. Only a human setting the flag distinguishes
    "proposed" from "agreed" — and letting a generated file advance a human gate
    would make the gate decorative.
    """
    t = track_at("brief")
    t["provenance"]["brief_confirmed"] = False
    a = lc.assess(t)
    assert a.stage == "spark"
    assert a.next_stage == "brief"
    assert a.blocked_on_human is True
    assert "provenance.brief_confirmed" in a.missing


# --- derivation -------------------------------------------------------------

@pytest.mark.parametrize("stage,expected_next", [
    ("spark", "brief"),
    ("brief", "draft"),
    ("draft", "review"),
    ("review", "sheet"),
    ("sheet", "rendered"),
    ("rendered", "analysed"),
    ("analysed", "adjudicated"),
])
def test_stage_is_derived_from_what_exists(stage, expected_next):
    a = lc.assess(track_at(stage))
    assert a.stage == stage
    assert a.next_stage == expected_next


def test_an_empty_track_asks_for_a_spark_first():
    a = lc.assess({"id": "T-002"})
    assert a.next_stage == "spark"
    assert a.blocked_on_human is True


def test_the_walk_stops_at_the_first_gap_rather_than_skipping_it():
    """A later stage being satisfied must not promote a track past an earlier gap.

    `mastered` requires nothing at all, so a walk that took the furthest
    *satisfied* stage rather than the furthest *contiguous* one would mark every
    track complete.
    """
    t = track_at("spark")
    t["glitch_log"] = [{"protocol": "x"}]     # a much later requirement, met early
    a = lc.assess(t)
    assert a.stage == "spark"
    assert a.next_stage == "brief"


def test_human_and_machine_gates_are_reported_correctly():
    assert lc.assess(track_at("brief")).blocked_on_human is False   # next is draft
    assert lc.assess(track_at("draft")).blocked_on_human is True    # next is review


def test_missing_lists_only_what_is_actually_absent():
    t = track_at("review")
    t["lyric_sheet"] = "sheets/a.md"          # one of sheet's three requirements
    a = lc.assess(t)
    assert a.next_stage == "sheet"
    assert set(a.missing) == {"suno.style_prompt", "suno.declared_bpm"}


# --- the terminal stage -----------------------------------------------------

def test_adjudicated_is_never_a_derived_stage():
    """Documented, because it surprised the author.

    `mastered` has no requirements, so the moment `adjudicated` is satisfied the
    walk also satisfies `mastered` and reports that instead. There is no reachable
    state whose derived stage is the string "adjudicated".
    """
    a = lc.assess(track_at("adjudicated"))
    assert a.stage == "mastered"
    assert a.next_stage is None
    assert a.next_action == "Complete."


def test_a_track_with_no_glitches_found_never_reaches_mastered():
    """A latent gap, pinned so it is not discovered by accident.

    `adjudicated` requires a non-empty `glitch_log`. A track that went through the
    whole pipeline and legitimately had every candidate discarded has
    `glitch_log: []`, which reads as absent — so it stalls at `analysed` and can
    never be counted as a release.
    """
    t = track_at("analysed")
    t["glitch_log"] = []
    a = lc.assess(t)
    assert a.stage == "analysed"
    assert a.next_stage == "adjudicated"
    assert lc.is_released(a.stage) is False


# --- the imported path ------------------------------------------------------
#
# Derived, not declared: a track is legacy if it has finished artefacts and no
# spark. That is a fact about the filesystem, which is the point.

def test_a_track_with_artefacts_but_no_spark_is_imported():
    a = lc.assess({"id": "T-003", "lyric_sheet": "sheets/old.md"})
    assert a.stage == "imported"
    assert a.next_stage == "rendered"


def test_an_imported_track_is_not_asked_for_a_spark_or_a_brief():
    """It already has a finished song; demanding a brief for done work is noise."""
    a = lc.assess({
        "id": "T-004",
        "lyric_sheet": "sheets/old.md",
        "audio": "old.mp3",
        "audio_sha256": "cafe",
    })
    assert a.stage == "imported/rendered"
    assert a.next_stage == "analysed"


def test_a_fully_finished_imported_track_is_complete():
    a = lc.assess({
        "id": "T-005",
        "lyric_sheet": "sheets/old.md",
        "audio": "old.mp3",
        "audio_sha256": "cafe",
        "analysis": {"dsp": {}},
        "glitch_log": [{"protocol": "x"}],
    })
    assert a.stage == "imported/mastered"
    assert a.next_stage is None


def test_having_a_spark_keeps_a_track_off_the_imported_path():
    t = track_at("sheet")
    a = lc.assess(t)
    assert not a.stage.startswith("imported")


# --- stored versus derived --------------------------------------------------
#
# THE BUG: `imported` used to be read from the stored field, so hand-setting
# `lifecycle.stage: imported` on a fully-specified track pushed it down the legacy
# path and misdirected `next`. The stored value was load-bearing in exactly the
# case where it disagreed with reality.

def test_a_stale_stored_stage_is_reported_not_obeyed():
    t = track_at("sheet")
    t["lifecycle"] = {"stage": "mastered"}
    a = lc.assess(t)
    assert a.stage == "sheet", "the stored value must not win"
    assert any("records 'mastered'" in n for n in a.notes)
    assert any("derived value is authoritative" in n for n in a.notes)


def test_a_stored_stage_that_agrees_produces_no_note():
    t = track_at("sheet")
    t["lifecycle"] = {"stage": "sheet"}
    assert lc.assess(t).notes == []


def test_a_compound_derived_stage_is_not_a_disagreement():
    """'imported' stored against 'imported/rendered' derived is the same claim."""
    a = lc.assess({
        "id": "T-006",
        "lyric_sheet": "s.md",
        "audio": "a.mp3",
        "audio_sha256": "cafe",
        "lifecycle": {"stage": "imported"},
    })
    assert a.stage == "imported/rendered"
    assert a.notes == []


def test_a_stored_stage_cannot_push_a_track_onto_the_imported_path():
    t = track_at("sheet")
    t["lifecycle"] = {"stage": "imported"}
    a = lc.assess(t)
    assert a.stage == "sheet"
    assert a.next_stage == "rendered"


# --- release classification -------------------------------------------------
#
# Shared by `certify` and the catalogue generator. They used to hold separate
# notions of this and disagreed: the catalogue counted 22 tracks where
# certification checked 21, and a brief with no audio rendered as a release.

@pytest.mark.parametrize("stage,released", [
    ("imported", True),
    ("mastered", True),
    ("adjudicated", True),
    ("imported/rendered", True),      # an imported track is a finished song
    ("imported/mastered", True),
    ("spark", False),
    ("brief", False),
    ("draft", False),
    ("review", False),
    ("sheet", False),
    ("rendered", False),
    ("analysed", False),
    ("", False),
    (None, False),
])
def test_is_released(stage, released):
    assert lc.is_released(stage) is released


def test_a_brief_is_not_a_release():
    """The end-to-end form: this is exactly the state WH-004 was in when the
    catalogue counted it as the label's 22nd track."""
    assert lc.is_released(lc.assess(track_at("brief")).stage) is False
