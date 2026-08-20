"""The song lifecycle: spark to final analysis, with the gate at each transition.

The ledger previously recorded only end state — a track was "mastered" and that
was all anyone knew. This makes the path explicit, so the question "why is this
song like this?" has an answer, and so the app can compute what a project needs
next instead of the human having to remember.

Each stage declares what must exist for a track to be *in* it, who moves it
forward (machine or human), and what to ask the human for when the gate is
theirs. That last field is what makes elicitation informed rather than a form.

Legacy tracks enter at `imported`, not at `mastered`. They genuinely did not go
through this pipeline and inventing a spark for them would be fabricating
provenance — the same discipline as `era: pre-standard`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

from . import ledger as ledger_mod

MACHINE = "machine"
HUMAN = "human"


@dataclass(frozen=True)
class Stage:
    id: str
    order: int
    gate: str                    # who advances out of this stage
    summary: str
    requires: list[str] = field(default_factory=list)   # ledger paths that must be set
    asks: str = ""               # what to elicit when the gate is HUMAN


# Ordered. `imported` sits outside the sequence at order -1: it is an entry
# point, not a step, and must never be treated as progress toward mastered.
STAGES: list[Stage] = [
    Stage(
        id="imported",
        order=-1,
        gate=MACHINE,
        summary="Brought in from outside the pipeline. No spark, no brief, no provenance.",
        requires=["lyric_sheet"],
    ),
    Stage(
        id="spark",
        order=0,
        gate=HUMAN,
        summary="Raw human input captured — the fused idea, before it is a plan.",
        requires=["provenance.spark"],
        asks=(
            "The raw thing. An argument you had, a phrase, an image, a line you "
            "cannot place. Do not tidy it — the tidying is the next stage's job."
        ),
    ),
    Stage(
        id="brief",
        order=1,
        gate=HUMAN,
        summary="Band, suite, stance, constraints and tempo target agreed.",
        # brief_confirmed, not just brief: the proposal is computed and written
        # automatically, so its existence proves nothing about agreement. Only a
        # human setting the flag distinguishes "proposed" from "agreed", and
        # letting a generated file advance a human gate would make the gate
        # decorative.
        requires=["provenance.brief_confirmed", "matrix.suite", "matrix.stance"],
        asks=(
            "Confirm or change the proposed band, suite, stance and tempo. The "
            "proposal is computed from what the catalogue is short of, so "
            "overriding it is a deliberate choice rather than a default."
        ),
    ),
    Stage(
        id="draft",
        order=2,
        gate=MACHINE,
        summary="Lyrics generated against the brief.",
        # A draft is not a compiled sheet. Requiring lyric_sheet here collapsed
        # three distinct stages — draft, review, sheet — into one, and meant a
        # track could not be at `draft` without already being past it.
        requires=["provenance.draft", "provenance.prompt_template"],
    ),
    Stage(
        id="review",
        order=3,
        gate=HUMAN,
        summary="Mechanical and judgement findings raised and resolved.",
        requires=["provenance.review"],
        asks=(
            "Each finding needs accept or override. Mechanical findings cite the "
            "rule they broke; judgement findings quote the line they are about. "
            "An override is recorded, not silently dropped."
        ),
    ),
    Stage(
        id="sheet",
        order=4,
        gate=HUMAN,
        summary="Approved for render: style prompt, stacked cues, declared tempo.",
        requires=["lyric_sheet", "suno.style_prompt", "suno.declared_bpm"],
        asks=(
            "Approve the sheet for Suno. This fixes the style prompt and the "
            "declared tempo, which the analyser will later measure against."
        ),
    ),
    Stage(
        id="rendered",
        order=5,
        gate=HUMAN,
        summary="Audio returned from Suno and ingested.",
        requires=["audio", "audio_sha256"],
        asks="Drop the rendered mp3 in and it will be hashed, decoded and matched to this track.",
    ),
    Stage(
        id="analysed",
        order=6,
        gate=MACHINE,
        summary="Measured: clipping, tempo, key, transcript diff against the sheet.",
        requires=["analysis"],
    ),
    Stage(
        id="adjudicated",
        order=7,
        gate=HUMAN,
        summary="Glitch candidates judged and named under the band protocol.",
        requires=["glitch_log"],
        asks=(
            "Keep, discard or rename each measured candidate. Which failures are "
            "badges of honour is the one judgement the tool must never make for "
            "you — that is the Glitch Axiom."
        ),
    ),
    Stage(
        id="mastered",
        order=8,
        gate=MACHINE,
        summary="Done.",
        requires=[],
    ),
]

BY_ID = {s.id: s for s in STAGES}
SEQUENCE = [s for s in sorted(STAGES, key=lambda s: s.order) if s.order >= 0]


def _has(track: dict, path: str) -> bool:
    value = ledger_mod.get_nested(track, path)
    # `False is not in (None, "", [], {})`, so an unset boolean flag read as
    # present and advanced the gate it was supposed to hold. brief_confirmed:
    # false meant "proposed, not agreed" and the tool reported the brief as
    # agreed. Falsy is absent.
    if value is False:
        return False
    return value not in (None, "", [], {})


@dataclass
class Assessment:
    track_id: str
    title: str
    band: str
    stage: str
    gate: str
    satisfied: list[str] = field(default_factory=list)
    missing: list[str] = field(default_factory=list)
    next_stage: str | None = None
    next_action: str = ""
    blocked_on_human: bool = False
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "track_id": self.track_id,
            "title": self.title,
            "band": self.band,
            "stage": self.stage,
            "gate": self.gate,
            "next_stage": self.next_stage,
            "next_action": self.next_action,
            "blocked_on_human": self.blocked_on_human,
            "missing": self.missing,
            "notes": self.notes,
        }


def assess(track: dict) -> Assessment:
    """Where is this track, and what does it need?

    Stage is derived from what actually exists on disk and in the ledger rather
    than read from a field that someone has to remember to update. A recorded
    stage that disagrees with reality is worse than no stage at all.
    """
    # The stored stage is NOT an input to the derivation.
    #
    # It used to be: `imported` was read from the field, so hand-setting
    # `lifecycle.stage: imported` on a fully-specified track pushed it down the
    # legacy path and misdirected `next`. That contradicted the documented
    # invariant — "stage is derived from what exists on disk" — by making the
    # stored value load-bearing in exactly the case where it disagreed. It is now
    # read only to report a mismatch.
    declared = ledger_mod.get_nested(track, "lifecycle.stage")
    a = Assessment(
        track_id=track.get("id") or "?",
        title=track.get("title") or "",
        band=track.get("band") or "",
        stage="imported",
        gate=MACHINE,
    )

    # Walk the sequence and find the furthest stage whose requirements all hold.
    reached = None
    for stage in SEQUENCE:
        if all(_has(track, p) for p in stage.requires):
            reached = stage
        else:
            break

    # Derived, not declared: a track is legacy if it has finished artefacts but
    # no spark. That is a fact about the filesystem, which is the point.
    imported = not _has(track, "provenance.spark") and (
        _has(track, "lyric_sheet") or _has(track, "audio")
    )

    # An imported track already has a finished song. Walking it from stage 0
    # would demand a spark and a brief for work that is done — so its remaining
    # path starts at the render, which it already has, and the only thing that can
    # still be asked of it is adjudication.
    candidates = SEQUENCE
    if imported:
        a.stage = "imported"
        candidates = [s for s in SEQUENCE if s.order >= BY_ID["rendered"].order]
        reached = None
        for stage in candidates:
            if all(_has(track, p) for p in stage.requires):
                reached = stage
            else:
                break

    if reached is not None:
        a.stage = reached.id if not imported else f"imported/{reached.id}"

    # Determine the next unmet stage and what it wants.
    for stage in candidates:
        if all(_has(track, p) for p in stage.requires):
            continue
        a.next_stage = stage.id
        a.gate = stage.gate
        a.missing = [p for p in stage.requires if not _has(track, p)]
        a.blocked_on_human = stage.gate == HUMAN
        a.next_action = stage.asks or stage.summary
        break
    else:
        a.next_stage = None
        a.next_action = "Complete."

    if declared and declared != a.stage and not a.stage.startswith(f"{declared}/"):
        a.notes.append(
            f"lifecycle.stage records '{declared}' but the files on disk derive "
            f"'{a.stage}'. The derived value is authoritative; the stored one is a "
            f"stale or hand-edited stamp."
        )

    # Cross-checks the stage machine cannot see from requirements alone.
    analysis = track.get("analysis") or {}
    asr = analysis.get("asr") or {}
    if asr.get("verdict", "").startswith("sheet-mismatch"):
        a.notes.append(
            "Analysis says the sheet does not match the master. Resolve the "
            "document before adjudicating anything as a glitch."
        )
    if asr.get("verdict", "").startswith("asr-unreliable"):
        a.notes.append(
            "Transcription did not hear enough of the vocal to conclude anything. "
            "Adjudicate by ear or not at all."
        )
    rhythm = analysis.get("rhythm") or {}
    # Only a genuine declaration can disagree with a measurement. Where the seed
    # came from the band's nominal tempo, the "declared" figure is the analyser's
    # own prior — flagging that as a conflict would be reporting a guess back as
    # a finding.
    if rhythm.get("tempo_locked") is False and rhythm.get("bpm_source") == "track":
        a.notes.append(
            f"Declared tempo disagrees with measurement "
            f"({rhythm.get('detected_bpm')} detected vs {rhythm.get('declared_bpm')} "
            f"declared). One of them is wrong."
        )
    elif rhythm.get("tempo_locked") is False:
        a.notes.append(
            f"No declared BPM; measured {rhythm.get('detected_bpm')} did not lock to "
            f"the band nominal. Worth declaring the real tempo."
        )
    return a


def assess_all(cfg) -> list[Assessment]:
    out: list[Assessment] = []
    for slug, band in cfg.bands.items():
        for t in ledger_mod.load_band_tracks(band):
            out.append(assess(t))
    return out


def stamp(track: dict, stage: str, by: str, note: str = "") -> None:
    """Record a transition. History is append-only."""
    import datetime

    lc = track.setdefault("lifecycle", {})
    lc["stage"] = stage
    history = lc.setdefault("history", [])
    history.append(
        {
            "stage": stage,
            "at": datetime.date.today().isoformat(),
            "by": by,
            **({"note": note} if note else {}),
        }
    )
