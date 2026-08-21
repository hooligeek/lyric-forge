"""Clone lineage — `suno.derived_from`.

Why this field exists: for most of the reference catalogue the real generative
input was not a style prompt at all, it was "clone of that other render, lyrics
swapped". The prompt recorded against those tracks described the sound instead of
causing it, and nothing in the ledger said so. A whole band could be sonically
identical for a reason no amount of rewording would fix, and the variety report
would keep implying that rewording was the fix.

Three states on purpose, and the distinction is the point:

    None          unrecorded — absence of evidence
    "origin"      generated from text, first of its lineage
    "<TRACK-ID>"  cloned from that render

`None` and `"origin"` are NOT the same claim. Collapsing them would turn "we never
asked" into "we established there was no parent".
"""

from __future__ import annotations

import pytest

from framework.forge import variety as variety_mod


# --- uniformity needs coverage, not just distinctness -----------------------
#
# THE BUG: the no-variance checks read len(counter) == 1, which counts distinct
# values among the tracks that HAVE one. Warhead declares a tempo on 1 of 4 tracks
# and the report said "every track declares 172 BPM — no tempo variance". A false
# statement about three tracks that declare nothing, produced by the module whose
# whole purpose is catching figures that read as measurements and are not.

@pytest.mark.parametrize("counts,total,uniform", [
    ({"172": 4}, 4, True),           # genuinely every track
    ({"172": 1}, 4, False),          # the bug: 1 of 4 declared
    ({"172": 3}, 4, False),          # partial coverage is not uniformity
    ({"172": 2, "185": 2}, 4, False),  # real variance
    ({"172": 3}, 3, True),
    ({"172": 2}, 2, False),          # below the floor of three
    ({}, 4, False),                  # nothing declared at all
])
def test_uniform_requires_full_coverage(counts, total, uniform):
    from collections import Counter
    assert variety_mod._uniform(Counter(counts), total) is uniform


# --- variety's warning changes with what lineage says -----------------------
#
# This is the behaviour the field was added for. The same measured fact — one style
# prompt across a band — means different things and implies different remedies
# depending on whether those tracks are clones.

def _band_variety(lineage_values):
    bv = variety_mod.BandVariety(slug="test-band")
    bv.total = len(lineage_values)
    bv.prompts["one shared prompt"] = len(lineage_values)
    for v in lineage_values:
        if v:
            bv.lineage[v] += 1
    return bv


def test_clones_are_named_as_the_cause():
    """When the ledger knows they are clones, say so and say rewording won't help."""
    bv = _band_variety(["origin", "T-001", "T-001"])
    variety_mod._warn_prompt_concentration(bv)
    (warning,) = [w for w in bv.warnings if "sonic variance" in w]
    assert "clones" in warning
    assert "will not vary anything" in warning


def test_unrecorded_lineage_admits_it_cannot_tell():
    """Evidence or abstain. With no lineage recorded, the cause is unknown."""
    bv = _band_variety([None, None, None])
    variety_mod._warn_prompt_concentration(bv)
    (warning,) = [w for w in bv.warnings if "sonic variance" in w]
    assert "unrecorded" in warning
    assert "cannot be told" in warning


def test_all_origins_leaves_the_prompt_as_the_story():
    """Every track generated from text, all sharing one prompt: the prompt IS it."""
    bv = _band_variety(["origin", "origin", "origin"])
    variety_mod._warn_prompt_concentration(bv)
    (warning,) = [w for w in bv.warnings if "sonic variance" in w]
    assert "clones" not in warning
    assert "unrecorded" not in warning


def test_a_band_with_prompt_variety_gets_no_warning_at_all():
    bv = variety_mod.BandVariety(slug="test-band")
    bv.total = 3
    bv.prompts["a"] = 2
    bv.prompts["b"] = 1
    variety_mod._warn_prompt_concentration(bv)
    assert not [w for w in bv.warnings if "sonic variance" in w]


def test_two_tracks_is_too_few_to_call_it():
    """Below three, one shared prompt is not evidence of anything."""
    bv = _band_variety(["origin", "T-001"])
    variety_mod._warn_prompt_concentration(bv)
    assert not [w for w in bv.warnings if "sonic variance" in w]
