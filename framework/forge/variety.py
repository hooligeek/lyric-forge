"""The variety gate — the check the prose compliance protocol could not make.

The predecessor audit had six gates and every one of them measured *format*:
is the seal present, are the cues pipe-stacked, is the ledger tidy. Format
compliance is trivially satisfiable, which is why the audit returned PASS on a
catalogue where four tracks shared a BPM, a key, and a byte-identical sonic
blueprint. A label whose declared enemy is homogenisation had an auditor that
could not detect homogenisation.

This measures distribution instead: stance, suite, tempo, key, and style prompt
spread. It reports concentration, which is the actual failure mode.

Era-aware. Pre-standard tracks are counted for evidence but never failed —
they were written before any of this existed, and their repetitions are the
corpus the burned lists come from.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field

import yaml

from . import config as config_mod
from . import ledger as ledger_mod
from .config import Config

# A stance holding more than this share of a band's classified catalogue is
# flagged. Not a hard failure — a band is allowed a signature — but past this
# point the topic is rotating and the posture is not.
STANCE_CONCENTRATION = 0.50
SUITE_CONCENTRATION = 0.50


@dataclass
class BandVariety:
    slug: str
    total: int = 0
    stances: Counter = field(default_factory=Counter)
    suites: Counter = field(default_factory=Counter)
    bpms: Counter = field(default_factory=Counter)
    keys: Counter = field(default_factory=Counter)
    prompts: Counter = field(default_factory=Counter)
    unclassified: int = 0
    warnings: list[str] = field(default_factory=list)


def _load_stance_roster() -> dict:
    path = config_mod.LABEL_DIR / "stances.yaml"
    if not path.exists():
        return {}
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def run(cfg: Config) -> tuple[list[BandVariety], dict]:
    roster = _load_stance_roster()
    known = {s["id"] for s in roster.get("stances", [])}

    results: list[BandVariety] = []
    label_stances: Counter = Counter()
    label_unused: set[str] = set(known)

    for slug, band in cfg.bands.items():
        bv = BandVariety(slug=slug)
        for t in ledger_mod.load_band_tracks(band):
            bv.total += 1
            stance = ledger_mod.get_nested(t, "matrix.stance")
            suite = ledger_mod.get_nested(t, "matrix.suite")
            bpm = ledger_mod.get_nested(t, "suno.declared_bpm")
            key = ledger_mod.get_nested(t, "suno.declared_key")
            prompt = ledger_mod.get_nested(t, "suno.style_prompt")

            if stance:
                bv.stances[stance] += 1
                label_stances[stance] += 1
                label_unused.discard(stance)
                if stance not in known:
                    bv.warnings.append(f"unknown stance '{stance}' (not in stances.yaml)")
            else:
                bv.unclassified += 1
            if suite:
                bv.suites[suite] += 1
            if bpm:
                bv.bpms[bpm] += 1
            if key:
                bv.keys[key] += 1
            if prompt:
                bv.prompts[prompt] += 1

        classified = sum(bv.stances.values())
        if classified >= 3:
            top, n = bv.stances.most_common(1)[0]
            if n / classified > STANCE_CONCENTRATION:
                bv.warnings.append(
                    f"stance concentration: {top} is {n}/{classified} "
                    f"({n / classified:.0%}) of classified tracks"
                )
        suite_total = sum(bv.suites.values())
        if suite_total >= 3:
            top, n = bv.suites.most_common(1)[0]
            if n / suite_total > SUITE_CONCENTRATION:
                bv.warnings.append(
                    f"suite concentration: Suite {top} is {n}/{suite_total} "
                    f"({n / suite_total:.0%}) of tracks"
                )
        if bv.total >= 3 and len(bv.bpms) == 1:
            bv.warnings.append(
                f"every track declares {list(bv.bpms)[0]} BPM — no tempo variance"
            )
        if bv.total >= 3 and len(bv.keys) == 1:
            bv.warnings.append(
                f"every track declares {list(bv.keys)[0]} — no key variance"
            )
        if bv.total >= 3 and len(bv.prompts) == 1:
            bv.warnings.append("every track shares one style prompt — no sonic variance")

        results.append(bv)

    summary = {
        "label_stances": label_stances,
        "unused_stances": sorted(label_unused),
        "known_stances": sorted(known),
    }
    return results, summary


def format_report(results: list[BandVariety], summary: dict) -> str:
    lines: list[str] = []
    lines.append("=" * 78)
    lines.append("VARIETY GATE")
    lines.append("=" * 78)

    for bv in results:
        lines.append("")
        lines.append(f"-- {bv.slug}  ({bv.total} tracks, {bv.unclassified} unclassified)")
        if bv.stances:
            spread = ", ".join(f"{k} x{v}" for k, v in bv.stances.most_common())
            lines.append(f"   stance : {spread}")
        if bv.suites:
            spread = ", ".join(f"{k} x{v}" for k, v in sorted(bv.suites.items()))
            lines.append(f"   suite  : {spread}")
        if bv.bpms:
            spread = ", ".join(f"{k} x{v}" for k, v in sorted(bv.bpms.items()))
            lines.append(f"   bpm    : {spread}")
        if bv.keys:
            spread = ", ".join(f"{k} x{v}" for k, v in bv.keys.most_common())
            lines.append(f"   key    : {spread}")
        for w in bv.warnings:
            lines.append(f"   !! {w}")

    label = summary["label_stances"]
    total = sum(label.values())
    lines.append("")
    lines.append("-- LABEL-WIDE STANCE DISTRIBUTION")
    for stance, n in label.most_common():
        bar = "#" * n
        share = f"{n / total:.0%}" if total else "-"
        lines.append(f"   {stance:14s} {n:>2}  {share:>4}  {bar}")

    unused = summary["unused_stances"]
    if unused:
        lines.append("")
        lines.append(f"-- STANCES NEVER USED  ({len(unused)} of {len(summary['known_stances'])})")
        lines.append(f"   {', '.join(unused)}")
        lines.append("   Each is an available song the roster has never written.")
    return "\n".join(lines)
