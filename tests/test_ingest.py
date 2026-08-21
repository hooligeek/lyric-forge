"""Superseding a render.

Re-rendering is normal, and the analysis and glitch log measured against the old
master do not apply to the new one. They are archived under the old hash rather than
deleted, because a timecode measured against a file that no longer exists is still
evidence of what that file did.
"""

from __future__ import annotations

import pytest

from framework.forge import ingest as ingest_mod


def _track(**kw):
    t = {
        "id": "T-001",
        "analysis": {"asr": {"word_accuracy": 0.9}},
        "glitch_log": [{"protocol": "X", "anchor": {"timecode": "01:00"}}],
    }
    t.update(kw)
    return t


# --- the null-versus-missing trap -------------------------------------------
#
# THE BUG: this used `track.setdefault("superseded", [])`. "superseded" is in
# TRACK_FIELDS, so a normalised track carries the key with value None rather than
# not carrying it — setdefault only inserts when the key is ABSENT, so it returned
# the None and .append() raised AttributeError mid-replace.
#
# It aborted safely only because the archive runs before the file copy. Reversed,
# the new master would have been on disk with the ledger still describing the old
# one, which is the worst state this project can be in.

@pytest.mark.parametrize("existing,label", [
    (None, "key present but null — the normalised shape, and the bug"),
    ("__absent__", "key genuinely missing"),
    ([], "empty list already there"),
])
def test_archiving_works_whatever_shape_superseded_is_in(existing, label):
    t = _track()
    if existing != "__absent__":
        t["superseded"] = existing
    result = ingest_mod._archive_superseded(t, "oldhash0000")
    assert isinstance(t["superseded"], list), label
    assert len(t["superseded"]) == 1
    assert result["glitch_entries"] == 1
    assert result["had_analysis"] is True


def test_archiving_appends_rather_than_overwriting():
    """A track re-rendered twice keeps both prior states."""
    t = _track(superseded=[{"audio_sha256": "first", "reason": "earlier swap"}])
    ingest_mod._archive_superseded(t, "secondhash")
    assert len(t["superseded"]) == 2
    assert t["superseded"][0]["audio_sha256"] == "first"
    assert t["superseded"][1]["audio_sha256"] == "secondhash"


def test_the_live_fields_are_cleared_so_stale_measurements_cannot_be_read():
    """The whole point: after a replace, nothing claims to describe the new audio."""
    t = _track()
    ingest_mod._archive_superseded(t, "oldhash0000")
    assert t["analysis"] is None
    assert t["glitch_log"] == []


def test_the_archive_carries_what_it_superseded():
    t = _track()
    ingest_mod._archive_superseded(t, "oldhash0000")
    record = t["superseded"][0]
    assert record["audio_sha256"] == "oldhash0000"
    assert record["analysis"]["asr"]["word_accuracy"] == 0.9
    assert len(record["glitch_log"]) == 1
    assert "does not apply to the new one" in record["reason"]
    assert record["superseded_on"]


def test_archiving_a_track_with_nothing_measured_writes_no_record():
    """Replacing audio on a never-analysed track must not invent an archive entry
    claiming something was superseded.

    Returns None rather than an empty record, which the signature says (`dict |
    None`) and which is the right contract: there was nothing to supersede, so
    there is nothing to say about it.
    """
    t = {"id": "T-002", "analysis": None, "glitch_log": []}
    assert ingest_mod._archive_superseded(t, "oldhash0000") is None
    assert "superseded" not in t, "no archive key should be created"
