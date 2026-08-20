"""`forge status` and `forge next` — the affordance an agent arrives to.

An agent (or a returning human) opening this project cold has no idea what it
needs. Everything required to answer that already exists — burned phrases, stance
concentration, suite counts, measured tempo registers, unadjudicated glitch
candidates, sheet/master mismatches — but it is scattered across files that
nobody reads at the right moment.

`status` answers "where is everything?".
`next` answers "what should I do, and why?" — and for a new song it produces a
brief *proposal* rather than a blank prompt.

That distinction is the whole point of informed elicitation. Not:

    What do you want to write about?

but:

    Warhead is 3-for-3 on accusation and has never used procedure. Suite B is
    its core suite and its least mined. Measured tempo 152-185 with no failures,
    so there is headroom Screen-Lit Panic does not have.

Both are questions. Only one of them is worth answering.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from typing import Any

import yaml

from . import config as config_mod
from . import ledger as ledger_mod
from . import lifecycle as lc_mod
from . import variety as variety_mod
from .config import Config


# ---------------------------------------------------------------------------
# status
# ---------------------------------------------------------------------------
def status(cfg: Config) -> dict[str, Any]:
    assessments = lc_mod.assess_all(cfg)
    stages = Counter(a.stage for a in assessments)
    waiting = [a for a in assessments if a.blocked_on_human]
    flagged = [a for a in assessments if a.notes]

    # A note that applies to every track is context, not a finding. Repeating it
    # per row buries the handful of notes that are actually actionable.
    note_counts = Counter(n for a in assessments for n in a.notes)
    universal = {n for n, c in note_counts.items() if c == len(assessments)}

    return {
        "label": cfg.label_name,
        "bands": len(cfg.bands),
        "tracks": len(assessments),
        "stages": dict(stages),
        "context": sorted(universal),
        "awaiting_human": [a.to_dict() for a in waiting],
        "flagged": [
            {
                "track_id": a.track_id,
                "title": a.title,
                "notes": [n for n in a.notes if n not in universal],
            }
            for a in flagged
            if [n for n in a.notes if n not in universal]
        ],
    }


def format_status(data: dict) -> str:
    lines = ["=" * 78, f"STATUS  {data['label']}", "=" * 78]
    lines.append(f"{data['tracks']} tracks across {data['bands']} bands")
    for note in data.get("context", []):
        lines.append(f"  ({note})")
    lines.append("")
    lines.append("-- LIFECYCLE")
    for stage, n in sorted(data["stages"].items(), key=lambda kv: -kv[1]):
        lines.append(f"   {stage:<22} {n:>3}  {'#' * n}")

    waiting = data["awaiting_human"]
    lines.append("")
    lines.append(f"-- AWAITING A HUMAN DECISION  ({len(waiting)})")
    if not waiting:
        lines.append("   nothing")
    seen: set[str] = set()
    for a in waiting:
        key = a["next_stage"]
        if key in seen:
            continue
        seen.add(key)
        same = [w for w in waiting if w["next_stage"] == key]
        lines.append(f"   [{key}] {len(same)} track(s)")
        lines.append(f"     {a['next_action']}")

    flagged = data["flagged"]
    if flagged:
        lines.append("")
        lines.append(f"-- FLAGGED  ({len(flagged)})")
        for f in flagged:
            lines.append(f"   {f['track_id']} {f['title']}")
            for n in f["notes"]:
                lines.append(f"     ! {n}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# next
# ---------------------------------------------------------------------------
@dataclass
class Proposal:
    band: str
    suite: str | None = None
    suite_reason: str = ""
    stance: str | None = None
    stance_reason: str = ""
    bpm: int | None = None
    bpm_reason: str = ""
    avoid: list[str] = field(default_factory=list)
    constraints: list[str] = field(default_factory=list)
    dossier: dict = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "band": self.band,
            "suite": self.suite,
            "suite_reason": self.suite_reason,
            "stance": self.stance,
            "stance_reason": self.stance_reason,
            "bpm": self.bpm,
            "bpm_reason": self.bpm_reason,
            "avoid": self.avoid,
            "constraints": self.constraints,
            "dossier": self.dossier,
        }


def _load_band_spec(cfg: Config, slug: str) -> dict:
    path = cfg.bands[slug].band_file
    if not path.exists():
        return {}
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def _load_retired(cfg: Config, slug: str) -> dict:
    path = cfg.bands[slug].dir / "retired.yaml"
    if not path.exists():
        return {}
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def _load_stance_roster() -> dict:
    path = config_mod.LABEL_DIR / "stances.yaml"
    if not path.exists():
        return {}
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def propose(cfg: Config, slug: str) -> Proposal:
    """Build a brief proposal from what the band's catalogue is short of."""
    spec = _load_band_spec(cfg, slug)
    retired = _load_retired(cfg, slug)
    roster = _load_stance_roster()
    tracks = ledger_mod.load_band_tracks(cfg.bands[slug])

    p = Proposal(band=slug)

    # --- stance: prefer one this band has never used ------------------------
    used = Counter(
        ledger_mod.get_nested(t, "matrix.stance")
        for t in tracks
        if ledger_mod.get_nested(t, "matrix.stance")
    )
    all_stances = [s["id"] for s in roster.get("stances", [])]
    band_pref = (spec.get("stances") or {}).get("natural") or []
    priority = (spec.get("stances") or {}).get("priority")

    unused_natural = [s for s in band_pref if s not in used]
    if priority and priority not in used:
        p.stance = priority
        p.stance_reason = (
            (spec.get("stances") or {}).get("priority_reason", "").strip()
            or f"{priority} is this band's flagged priority and is unused"
        )
    elif unused_natural:
        p.stance = unused_natural[0]
        p.stance_reason = f"unused by this band, and listed among its natural modes"
    else:
        unused_any = [s for s in all_stances if s not in used]
        if unused_any:
            p.stance = unused_any[0]
            p.stance_reason = "never used anywhere on the roster"
        elif used:
            least = min(used.items(), key=lambda kv: kv[1])
            p.stance = least[0]
            p.stance_reason = f"least used by this band ({least[1]} track(s))"

    if used:
        top, n = used.most_common(1)[0]
        total = sum(used.values())
        if n / total > 0.5:
            p.constraints.append(
                f"Do not use {top}: it is {n}/{total} of this band's catalogue."
            )

    # --- suite: least mined -------------------------------------------------
    suites_defined = list((spec.get("suites") or {}).keys())
    suite_used = Counter(
        ledger_mod.get_nested(t, "matrix.suite")
        for t in tracks
        if ledger_mod.get_nested(t, "matrix.suite")
    )
    flagged_priority = [
        k for k, v in (spec.get("suites") or {}).items() if v.get("priority")
    ]
    if flagged_priority:
        p.suite = flagged_priority[0]
        detail = (spec["suites"][p.suite].get("priority_reason") or "").strip()
        p.suite_reason = detail or "flagged as this band's priority suite"
    elif suites_defined:
        unmined = [s for s in suites_defined if suite_used.get(s, 0) == 0]
        if unmined:
            p.suite = unmined[0]
            p.suite_reason = "never used"
        else:
            least = min(suites_defined, key=lambda s: suite_used.get(s, 0))
            p.suite = least
            p.suite_reason = f"least mined ({suite_used.get(least, 0)} track(s))"
    if p.suite and (spec.get("suites") or {}).get(p.suite):
        p.constraints.append(
            f"Suite {p.suite} anchors — at least one must appear: "
            + ", ".join(spec["suites"][p.suite].get("anchors") or [])
        )

    # --- tempo: from the measured register, not the nominal ------------------
    reg = spec.get("register") or {}
    ceiling = reg.get("tempo_ceiling")
    measured = [
        t.get("measured_bpm") for t in tracks if t.get("measured_bpm")
    ]
    if ceiling:
        p.bpm = int(ceiling)
        why = [f"measured ceiling {ceiling}"]
        ev = (reg.get("ceiling_evidence") or "").strip().split(".")[0]
        if ev:
            why.append(ev)
        if measured:
            why.append(
                f"existing tracks measured {min(measured):.0f}-{max(measured):.0f}"
            )
        p.bpm_reason = ". ".join(why)
    elif measured:
        p.bpm = int(sum(measured) / len(measured))
        p.bpm_reason = (
            f"no measured ceiling; mean of existing measurements "
            f"({min(measured):.0f}-{max(measured):.0f})"
        )

    # --- avoid: burned phrases and opening tics -----------------------------
    p.avoid = list(retired.get("burned") or [])
    for c in (retired.get("candidates") or [])[:12]:
        phrase = c.get("phrase")
        if phrase:
            p.avoid.append(phrase)
    for tic in (retired.get("opening_tics") or [])[:6]:
        opening = tic.get("opening")
        if opening:
            p.constraints.append(f'No section may open on "{opening} ..."')

    for rule in (spec.get("canon_rules") or [])[:6]:
        p.constraints.append(str(rule))

    # --- dossier: who is speaking ------------------------------------------
    dpath = cfg.bands[slug].dir / "dossier.md"
    band_block = spec.get("band") or {}
    p.dossier = {
        "role": band_block.get("role"),
        "posture": band_block.get("posture"),
        "disagreement": band_block.get("disagreement"),
        "dossier_path": dpath.relative_to(config_mod.REPO_ROOT).as_posix()
        if dpath.exists()
        else None,
    }
    return p


def next_actions(cfg: Config, band: str | None = None) -> dict[str, Any]:
    """Outstanding work first, then a proposal for new work."""
    assessments = lc_mod.assess_all(cfg)
    if band:
        assessments = [a for a in assessments if a.band == band]

    outstanding = [a.to_dict() for a in assessments if a.blocked_on_human]

    targets = [band] if band else list(cfg.bands)
    proposals = [propose(cfg, slug).to_dict() for slug in targets]

    var_results, var_summary = variety_mod.run(cfg)
    return {
        "outstanding": outstanding,
        "proposals": proposals,
        "unused_stances_label_wide": var_summary.get("unused_stances", []),
    }


def format_next(data: dict) -> str:
    lines = ["=" * 78, "NEXT", "=" * 78]

    out = data["outstanding"]
    lines.append(f"-- OUTSTANDING HUMAN DECISIONS  ({len(out)})")
    if not out:
        lines.append("   none — the pipeline is not waiting on you")
    for a in out[:10]:
        lines.append(f"   {a['track_id']} {a['title']}  -> {a['next_stage']}")
        lines.append(f"     {a['next_action']}")
    if len(out) > 10:
        lines.append(f"   ... {len(out) - 10} more")

    lines.append("")
    lines.append("-- PROPOSED BRIEF FOR NEW WORK")
    for p in data["proposals"]:
        lines.append("")
        lines.append(f"   {p['band']}  ({p['dossier'].get('role') or '?'})")
        if p["dossier"].get("disagreement"):
            lines.append(f"     position : {p['dossier']['disagreement']}")
        lines.append(f"     stance   : {p['stance']}")
        if p["stance_reason"]:
            lines.append(f"                {p['stance_reason'][:150]}")
        lines.append(f"     suite    : {p['suite']}")
        if p["suite_reason"]:
            lines.append(f"                {p['suite_reason'][:150]}")
        lines.append(f"     bpm      : {p['bpm']}")
        if p["bpm_reason"]:
            lines.append(f"                {p['bpm_reason'][:150]}")
        if p["avoid"]:
            lines.append(f"     avoid    : {len(p['avoid'])} spent phrases")
            for phrase in p["avoid"][:4]:
                lines.append(f'                "{phrase}"')
        if p["constraints"]:
            lines.append(f"     rules    : {len(p['constraints'])}")
            for c in p["constraints"][:3]:
                lines.append(f"                - {str(c)[:120]}")

    unused = data.get("unused_stances_label_wide") or []
    if unused:
        lines.append("")
        lines.append(f"-- STANCES UNUSED LABEL-WIDE: {', '.join(unused)}")
    return "\n".join(lines)
