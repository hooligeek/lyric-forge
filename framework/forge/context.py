"""Slot builders: assemble prompt context out of the repository.

The whole point is that `forge prompt render generate-song --band warhead`
produces something complete. Without this, an agent has to open the substrate,
the dossier, band.yaml, stances.yaml, retired.yaml and tracks.yaml, decide which
parts matter, and paste them together — differently every time, which is exactly
the drift the prompt library exists to prevent.

Where a suite, stance or tempo is not specified, the computed proposal from
`pipeline.propose` supplies it. That wires the elicitation engine directly into
generation: the default brief is the one the catalogue is actually short of,
rather than whatever the caller happened to think of.

One deliberate omission: the catalogue digest lists titles, spent hooks and
suites consumed, and NEVER full back-catalogue lyrics. Feeding a model its own
previous choruses makes echoing them the path of least resistance — the negative
space is the useful part.
"""

from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import Any

import yaml

from . import config as config_mod
from . import ledger as ledger_mod
from . import pipeline as pipeline_mod
from .config import Config

TAG_FORMULA = (
    "[Section | Genre/Era | Vocal Texture | Production Vibe]\n"
    "Attributes separated by the vertical pipe. Maximum six per bracket. Every "
    "section carries one — no bare cues such as [Verse] or [Chorus]."
)


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8").strip() if path.exists() else ""


def _strip_frontmatter(text: str) -> str:
    if text.startswith("---"):
        parts = text.split("---", 2)
        if len(parts) >= 3:
            return parts[2].strip()
    return text


def band_spec(cfg: Config, slug: str) -> dict:
    return yaml.safe_load(_read(cfg.bands[slug].band_file) or "{}") or {}


def stance_roster() -> dict:
    return yaml.safe_load(_read(config_mod.REPO_ROOT / "framework" / "stances.yaml") or "{}") or {}


def label_spec() -> dict:
    return yaml.safe_load(_read(config_mod.LABEL_DIR / "label.yaml") or "{}") or {}


def substrate() -> str:
    return _strip_frontmatter(_read(config_mod.LABEL_DIR / "substrate.md"))


def dossier(cfg: Config, slug: str) -> str:
    return _strip_frontmatter(_read(cfg.bands[slug].dir / "dossier.md"))


def catalogue_digest(cfg: Config, slug: str) -> str:
    """What this band has already said — titles, stances, suites and spent hooks.

    Deliberately not the lyrics. This is the negative space: what is used up.
    """
    tracks = ledger_mod.load_band_tracks(cfg.bands[slug])
    if not tracks:
        return "No catalogue yet. Nothing is spent."

    lines: list[str] = []
    for t in tracks:
        stance = ledger_mod.get_nested(t, "matrix.stance") or "?"
        suite = ledger_mod.get_nested(t, "matrix.suite") or "?"
        bpm = t.get("measured_bpm") or ledger_mod.get_nested(t, "suno.declared_bpm") or "?"
        lines.append(f"- {t.get('title')} — stance {stance}, suite {suite}, {bpm} BPM")

    stances = Counter(
        ledger_mod.get_nested(t, "matrix.stance") for t in tracks
        if ledger_mod.get_nested(t, "matrix.stance")
    )
    suites = Counter(
        ledger_mod.get_nested(t, "matrix.suite") for t in tracks
        if ledger_mod.get_nested(t, "matrix.suite")
    )
    lines.append("")
    lines.append(
        "Stance usage: "
        + ", ".join(f"{k} x{v}" for k, v in stances.most_common())
    )
    lines.append(
        "Suite usage: " + ", ".join(f"{k} x{v}" for k, v in sorted(suites.items()))
    )
    return "\n".join(lines)


def retired(cfg: Config, slug: str) -> dict:
    return yaml.safe_load(_read(cfg.bands[slug].dir / "retired.yaml") or "{}") or {}


def _register_block(spec: dict) -> str:
    reg = spec.get("register") or {}
    if not reg:
        return ""
    parts: list[str] = []
    if reg.get("tempo_ceiling"):
        parts.append(f"Tempo ceiling: {reg['tempo_ceiling']} BPM.")
    if reg.get("ceiling_evidence"):
        parts.append(f"Evidence: {str(reg['ceiling_evidence']).strip()}")
    breaks = reg.get("breaks_on") or []
    if breaks:
        parts.append("Breaks on:\n" + "\n".join(f"  - {b}" for b in breaks))
    survives = reg.get("survives") or []
    if survives:
        parts.append("Survives:\n" + "\n".join(f"  - {s}" for s in survives))
    if reg.get("placement_rule"):
        parts.append(f"Placement rule: {str(reg['placement_rule']).strip()}")
    return "\n\n".join(parts)


def _suite_slots(spec: dict, suite_id: str | None) -> dict[str, Any]:
    suites = spec.get("suites") or {}
    s = suites.get(suite_id) if suite_id else None
    if not s:
        return {}
    return {
        "suite_id": suite_id,
        "suite_name": s.get("name", ""),
        "suite_domain": str(s.get("domain", "")).strip(),
        "suite_tension": str(s.get("tension", "")).strip(),
        "suite_metaphor": str(s.get("punk_metaphor", "")).strip(),
        "suite_juxtaposition": str(s.get("juxtaposition", "")).strip(),
        "suite_anchors": s.get("anchors") or [],
        "suite_rotation": s.get("rotation") or [],
    }


def _stance_slots(stance_id: str | None) -> dict[str, Any]:
    if not stance_id:
        return {}
    for s in stance_roster().get("stances", []):
        if s.get("id") == stance_id:
            return {
                "stance_id": stance_id,
                "stance_name": s.get("name", stance_id),
                "stance_description": str(s.get("description", "")).strip(),
                "stance_marker": s.get("marker", ""),
                "stance_example": s.get("example", ""),
                "stance_caution": str(s.get("caution", "")).strip(),
            }
    return {"stance_id": stance_id, "stance_name": stance_id}


def track_slots(cfg: Config, band: str, track_slug: str) -> dict[str, Any]:
    """Slots for a specific track: title, transcript verdict, and the measured
    candidates awaiting judgement.

    Without these the adjudicate-glitch prompt cannot render, which is the whole
    reason it exists — an agent reasoning about how to name a failure needs the
    evidence, not a description of the evidence.
    """
    from . import adjudicate as adj_mod

    tracks = ledger_mod.load_band_tracks(cfg.bands[band])
    track = next((t for t in tracks if t.get("slug") == track_slug), None)
    if track is None:
        return {}

    analysis = track.get("analysis") or {}
    verdict = ((analysis.get("asr") or {}).get("verdict")) or ""

    doc = adj_mod.build_decisions(cfg, band)
    entry = (doc.get("tracks") or {}).get(track_slug) or {}
    rows = [r for r in (entry.get("candidates") or []) if not r.get("auto")]

    rendered: list[str] = []
    for i, r in enumerate(rows, 1):
        bits = [f"{i}. [{r.get('timecode')}] {r.get('type')}"]
        if r.get("section"):
            bits.append(f"section: {r['section']}")
        if r.get("expected"):
            bits.append(f'expected: "{r["expected"]}"')
        if r.get("heard"):
            bits.append(f'heard: "{r["heard"]}"')
        if r.get("also_at"):
            bits.append(f"recurs at: {', '.join(str(t) for t in r['also_at'])}")
        if r.get("confidence") is not None:
            bits.append(f"confidence: {r['confidence']}")
        rendered.append("\n   ".join(bits))

    return {
        "track_title": track.get("title", track_slug),
        "asr_verdict": verdict,
        "candidates": "\n\n".join(rendered),
    }


def build(
    cfg: Config,
    *,
    band: str | None = None,
    track: str | None = None,
    suite: str | None = None,
    stance: str | None = None,
    bpm: int | None = None,
    spark: str = "",
    lyrics: str = "",
    extra_context: str = "",
    vision: str = "",
) -> dict[str, Any]:
    """Assemble every slot any prompt might want. Unused keys are harmless."""
    label = label_spec().get("label") or {}
    ctx: dict[str, Any] = {
        "label_name": label.get("name", ""),
        "label_axiom": label.get("axiom", ""),
        "substrate": substrate(),
        "tag_formula": TAG_FORMULA,
        # Sparks are stored with frontmatter for their id; the model wants the
        # note, not the bookkeeping.
        "spark": _strip_frontmatter(spark.strip()),
        "lyrics": lyrics.strip(),
        "extra_context": extra_context.strip(),
        "vision": vision.strip(),
        "stance_roster": "\n".join(
            f"- **{s['id']}** — {str(s.get('description','')).strip().splitlines()[0]}"
            for s in stance_roster().get("stances", [])
        ),
    }

    if not band:
        return ctx

    spec = band_spec(cfg, band)
    bblock = spec.get("band") or {}
    sonic = spec.get("sonic") or {}

    # Precedence: explicit argument, then the track's own confirmed brief, then
    # the computed proposal.
    #
    # The track must outrank the proposal. An operator who confirmed a brief with
    # a different tempo has made a decision, and generating against the original
    # proposal instead would make confirmation decorative — the gate would record
    # assent and then be ignored.
    proposal = pipeline_mod.propose(cfg, band)
    confirmed: dict[str, Any] = {}
    if track:
        tracks = ledger_mod.load_band_tracks(cfg.bands[band])
        row = next((t for t in tracks if t.get("slug") == track), None)
        if row and ledger_mod.get_nested(row, "provenance.brief_confirmed"):
            confirmed = {
                "suite": ledger_mod.get_nested(row, "matrix.suite"),
                "stance": ledger_mod.get_nested(row, "matrix.stance"),
                "bpm": ledger_mod.get_nested(row, "suno.declared_bpm"),
            }

    suite = suite or confirmed.get("suite") or proposal.suite
    stance = stance or confirmed.get("stance") or proposal.stance
    bpm = bpm or confirmed.get("bpm") or proposal.bpm

    ctx.update(
        {
            "band_slug": band,
            "band_name": bblock.get("name", band),
            "band_role": bblock.get("role", ""),
            "band_posture": bblock.get("posture", ""),
            "band_position": bblock.get("disagreement", ""),
            "band_facet_note": str(bblock.get("facet_note", "")).strip(),
            "dossier": dossier(cfg, band),
            "genre": sonic.get("genre", ""),
            "style_prompt": str(sonic.get("style_prompt", "")).strip(),
            "vocal": str(sonic.get("vocal", "")).strip(),
            "bpm_target": bpm,
            "bpm_reason": (
                "set on the confirmed brief for this track"
                if confirmed.get("bpm") == bpm
                else proposal.bpm_reason
            ),
            "register": _register_block(spec),
            "glitch_protocol": (spec.get("glitch_protocol") or {}).get("name", ""),
            "glitch_reading": str(
                (spec.get("glitch_protocol") or {}).get("reading", "")
            ).strip(),
            "song_map": sonic.get("song_map") or [],
            "canon_rules": spec.get("canon_rules") or [],
            "catalogue_digest": catalogue_digest(cfg, band),
            "avoid": proposal.avoid,
            "constraints": proposal.constraints,
            "suite_reason": proposal.suite_reason,
            "stance_reason": proposal.stance_reason,
        }
    )
    ctx.update(_suite_slots(spec, suite))
    ctx.update(_stance_slots(stance))
    if track:
        ctx.update(track_slots(cfg, band, track))
    return ctx
