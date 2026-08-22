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


# --- visual entries survive an audio replacement ----------------------------
#
# THE BUG: archiving moved the whole glitch_log aside, so replacing a master filed
# the ARTWORK entries under the superseded audio hash. A cover glitch that was still
# true of a file nobody had touched vanished from the live log — silently, because
# nothing was deleted. The catalogue page simply stopped mentioning a failure the
# cover still has.

def _visual(protocol="Scorched Plate"):
    return {"protocol": protocol, "type": "artwork-artefact",
            "anchor": {"region": "monitor, left edge"}}


def test_artwork_entries_are_not_archived_with_the_audio():
    t = _track()
    t["glitch_log"] = [
        {"type": "lyric-divergence", "protocol": "A", "anchor": {"timecode": "01:00"}},
        _visual(),
    ]
    result = ingest_mod._archive_superseded(t, "oldhash0000")

    assert [g["type"] for g in t["glitch_log"]] == ["artwork-artefact"], \
        "the cover entry must stay live; the image was not replaced"
    assert [g["type"] for g in t["superseded"][0]["glitch_log"]] == ["lyric-divergence"]
    assert result["glitch_entries"] == 1
    assert result["kept_visual"] == 1


def test_a_track_with_only_visual_entries_and_no_analysis_archives_nothing():
    """Nothing about the audio was ever measured, so there is nothing to supersede —
    and the cover entry is not a reason to invent an archive record."""
    t = {"id": "T-003", "analysis": None, "glitch_log": [_visual()]}
    assert ingest_mod._archive_superseded(t, "oldhash0000") is None
    assert "superseded" not in t
    assert len(t["glitch_log"]) == 1


def test_visual_entries_survive_two_replacements():
    t = _track()
    t["glitch_log"] = [
        {"type": "dropout", "protocol": "A", "anchor": {"timecode": "01:00"}},
        _visual(),
    ]
    ingest_mod._archive_superseded(t, "hash1")
    t["analysis"] = {"asr": {}}
    t["glitch_log"].append(
        {"type": "dropout", "protocol": "B", "anchor": {"timecode": "02:00"}}
    )
    ingest_mod._archive_superseded(t, "hash2")
    assert [g["protocol"] for g in t["glitch_log"]] == ["Scorched Plate"]
    assert len(t["superseded"]) == 2


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
