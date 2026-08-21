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
from . import lifecycle as lc_mod
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
    lineage: Counter = field(default_factory=Counter)
    unclassified: int = 0
    warnings: list[str] = field(default_factory=list)


def _load_stance_roster() -> dict:
    path = config_mod.REPO_ROOT / "framework" / "stances.yaml"
    if not path.exists():
        return {}
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def _uniform(counter: Counter, total: int) -> bool:
    """True only when one value is shared by EVERY track, not merely by every
    track that happens to have one.

    Three tracks with no declared tempo and one declaring 172 is not uniformity.
    """
    return total >= 3 and len(counter) == 1 and sum(counter.values()) == total


def _warn_prompt_concentration(bv: BandVariety) -> None:
    """One shared style prompt across a band means different things depending on
    whether those tracks are clones, so the warning has to say which.

    Extracted from run() to be testable without constructing a whole label. The
    three branches are the three states of suno.derived_from.
    """
    if _uniform(bv.prompts, bv.total):
        # Say WHY, where the ledger knows. A band whose tracks are clones of one
        # render is sonically identical for a reason no rewording can touch, and
        # a warning that only mentions the prompt implies a remedy that would
        # not work. Where lineage is unrecorded, say that too rather than
        # implying the prompt is the whole story.
        clones = sum(n for k, n in bv.lineage.items() if k != "origin")
        if clones:
            bv.warnings.append(
                f"every track shares one style prompt — no sonic variance. "
                f"{clones} of {bv.total} are recorded as clones of another "
                f"render, so the prompt describes the sound rather than causing "
                f"it; rewording it will not vary anything"
            )
        elif not bv.lineage:
            bv.warnings.append(
                "every track shares one style prompt — no sonic variance. "
                "Clone lineage is unrecorded, so whether the prompt caused this "
                "sound or merely describes it cannot be told from here"
            )
        else:
            bv.warnings.append(
                "every track shares one style prompt — no sonic variance"
            )


def run(cfg: Config) -> tuple[list[BandVariety], dict]:
    roster = _load_stance_roster()
    known = {s["id"] for s in roster.get("stances", [])}

    results: list[BandVariety] = []
    label_stances: Counter = Counter()
    label_unused: set[str] = set(known)

    for slug, band in cfg.bands.items():
        bv = BandVariety(slug=slug)
        for t in ledger_mod.load_band_tracks(band):
            # Work in progress is not variety. A brief has no lyrics, no key and
            # no style prompt, so it cannot contribute to a distribution — but its
            # stance was being counted as used, which struck that stance off the
            # never-written list while no song carrying it existed.
            #
            # That mattered beyond the count: `pipeline.next_actions` reads this to
            # decide what to suggest writing, and the never-written stances are the
            # available songs. An unwritten brief would steer the roster away from
            # the exact gap it was created to fill.
            if not lc_mod.is_released(lc_mod.assess(t).stage):
                continue
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
            lineage = ledger_mod.get_nested(t, "suno.derived_from")
            if lineage:
                bv.lineage[str(lineage)] += 1

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
        # Coverage, not just distinctness.
        #
        # THE BUG: these read len(counter) == 1, which counts distinct values among
        # the tracks that HAVE one. Warhead has a declared tempo on 1 of 4 tracks,
        # and this reported "every track declares 172 BPM — no tempo variance".
        # That is a false statement about three tracks that declare nothing, and it
        # is the same failure this module was built to catch: a figure that reads as
        # a measurement and is not one. Sparse data is a coverage gap, which
        # reconcile already reports; it is not evidence of homogeneity.
        if _uniform(bv.bpms, bv.total):
            bv.warnings.append(
                f"every track declares {list(bv.bpms)[0]} BPM — no tempo variance"
            )
        if _uniform(bv.keys, bv.total):
            bv.warnings.append(
                f"every track declares {list(bv.keys)[0]} — no key variance"
            )
        _warn_prompt_concentration(bv)

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
