"""`forge certify` — the fork approval gate.

A fork is listed as approved on the template's main branch when it can carry a
catalogue all the way to generated documentation with no gaps. "Approved" has to
mean something checkable, or the list is just a list of people who asked.

So this is not a badge. It is every gate in the project run at once, plus the
completeness checks that only make sense for a whole catalogue rather than a
single track:

  structural   reconcile --strict must report zero defects
  templates    prompt lint must be clean
  evidence     no UNSOUND_EVIDENCE anywhere
  assets       every released track has audio, artwork, a lyric sheet, and a
               content hash for each binary
  brief        every released track is classified: suite and stance
  publication  every released track has a verified listening link
  pipeline     nothing is stuck waiting on a human decision
  freshness    the generated catalogue matches the ledger it describes

`released` excludes work in progress — a track mid-pipeline is not a gap, it is
work. A fork with three finished songs certifies; a fork with thirty finished
songs and one missing cover does not.

The freshness check is the one that makes the rest hold. Documentation generated
from a ledger is only trustworthy if it was generated from *this* ledger, so the
catalogue is rebuilt into a temporary directory and compared. A stale catalogue is
a false claim about the catalogue.
"""

from __future__ import annotations

import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from . import config as config_mod
from . import ledger as ledger_mod
from . import lifecycle as lc_mod
from . import reconcile as reconcile_mod
from .config import Config

# Stages at which a track is finished enough that gaps are gaps.
RELEASED = {"imported", "adjudicated", "mastered"}


def _released(stage: str) -> bool:
    return stage.split("/")[0] in RELEASED


@dataclass
class Check:
    id: str
    title: str
    passed: bool
    detail: str = ""
    gaps: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "passed": self.passed,
            "detail": self.detail,
            "gaps": self.gaps[:40],
            "gap_count": len(self.gaps),
        }


@dataclass
class Certification:
    label: str
    checks: list[Check] = field(default_factory=list)

    @property
    def approved(self) -> bool:
        return all(c.passed for c in self.checks)

    def to_dict(self) -> dict[str, Any]:
        return {
            "label": self.label,
            "approved": self.approved,
            "checks": [c.to_dict() for c in self.checks],
            "blocking": [c.id for c in self.checks if not c.passed],
        }


def _catalogue_is_fresh(cfg: Config) -> Check:
    """Regenerate into a temp directory and compare. Documentation generated from
    a ledger only means anything if it came from the ledger as it stands now."""
    from . import docs as docs_mod

    live = config_mod.REPO_ROOT / "docs" / "catalog"
    if not live.exists():
        return Check("freshness", "Catalogue is current", False,
                     "docs/catalog/ does not exist — run `forge docs catalog`")

    # Regenerate INSIDE the repo, at the same directory depth as docs/.
    #
    # A temp directory elsewhere changes the output: asset links are relative to
    # the repo root, so an out-of-tree root falls back to absolute file:// URLs
    # and adds an ASSETS-NOTE. The comparison then failed on the generator's own
    # correct behaviour rather than on staleness — a freshness check that reports
    # everything as stale is worse than none.
    # Depth matters, not just in-tree-ness. Asset links count directories from
    # the repo root to the page, so the scratch root must sit at the same depth as
    # `docs/` — one level. `.cache/certify/catalog` is three deep and produced
    # `../../../` against the committed `../../`, so every file "differed" and the
    # check reported a fresh catalogue as stale.
    scratch = config_mod.REPO_ROOT / ".certify-tmp"
    if scratch.exists():
        shutil.rmtree(scratch)
    scratch.mkdir(parents=True)
    try:
        docs_mod.build_catalog(cfg, scratch).write(scratch)
        fresh = scratch / "catalog"
        stale: list[str] = []
        for f in sorted(fresh.iterdir()):
            counterpart = live / f.name
            if not counterpart.exists():
                stale.append(f"{f.name} (missing)")
            elif counterpart.read_bytes() != f.read_bytes():
                stale.append(f"{f.name} (differs)")
        for f in sorted(live.iterdir()):
            if not (fresh / f.name).exists():
                stale.append(f"{f.name} (orphan)")
    finally:
        shutil.rmtree(scratch, ignore_errors=True)

    return Check(
        "freshness",
        "Catalogue is current",
        not stale,
        "regenerated and compared byte-for-byte"
        if not stale
        else "the committed catalogue does not match the ledger; run `forge docs catalog`",
        stale,
    )


def run(cfg: Config) -> Certification:
    cert = Certification(label=cfg.label_name)

    # --- structural --------------------------------------------------------
    rep = reconcile_mod.run(cfg)
    defects = rep.defects
    cert.checks.append(Check(
        "structural", "reconcile --strict is clean", not defects,
        f"{len(rep.findings)} findings, {len(defects)} of them defects",
        [str(f) for f in defects],
    ))

    unsound = [f for f in rep.findings if f.kind == "UNSOUND_EVIDENCE"]
    cert.checks.append(Check(
        "evidence", "No unsound evidence", not unsound,
        "every glitch entry's claimed provenance is internally consistent"
        if not unsound else "entries claim measurement that nothing performed",
        [str(f) for f in unsound],
    ))

    # --- templates ---------------------------------------------------------
    from . import prompts as prompts_mod

    problems: list[str] = []
    for p in prompts_mod.load_all():
        problems += [f"{p.ref}: {x}" for x in prompts_mod.lint(p)]
    cert.checks.append(Check(
        "templates", "Prompt library is consistent", not problems,
        f"{len(prompts_mod.load_all())} templates checked", problems,
    ))

    # --- per-track completeness -------------------------------------------
    missing_assets: list[str] = []
    unclassified: list[str] = []
    unlinked: list[str] = []
    released = 0

    for slug, band in cfg.bands.items():
        for t in ledger_mod.load_band_tracks(band):
            stage = lc_mod.assess(t).stage
            if not _released(stage):
                continue
            released += 1
            ref = f"{t.get('id')} {t.get('title')}"
            for field_name, label in (
                ("audio", "audio"), ("audio_sha256", "audio hash"),
                ("artwork", "artwork"), ("artwork_sha256", "artwork hash"),
                ("lyric_sheet", "lyric sheet"),
            ):
                if not t.get(field_name):
                    missing_assets.append(f"{ref}: no {label}")
            # Era-aware, like every other gate. A pre-standard track predates the
            # matrix, so demanding a suite for it would mean inventing a
            # classification — the same fabrication the era system exists to
            # prevent. Classification is kept where it was recoverable; it is not
            # required where it would have to be made up.
            if t.get("era") == cfg.current_era:
                if not ledger_mod.get_nested(t, "matrix.suite"):
                    unclassified.append(f"{ref}: no suite")
                if not ledger_mod.get_nested(t, "matrix.stance"):
                    unclassified.append(f"{ref}: no stance")
            if not ledger_mod.get_nested(t, "suno.url"):
                unlinked.append(f"{ref}: no listening link")
            elif not ledger_mod.get_nested(t, "suno.url_verified"):
                unlinked.append(f"{ref}: link present but unverified")

    cert.checks.append(Check(
        "assets", "Every released track has its assets", not missing_assets,
        f"{released} released tracks checked", missing_assets,
    ))
    cert.checks.append(Check(
        "brief", "Every released track is classified", not unclassified,
        "suite and stance recorded", unclassified,
    ))
    cert.checks.append(Check(
        "publication", "Every released track has a verified link", not unlinked,
        "constructed links do not count — an id is evidence, a URL built from "
        "one is an assumption", unlinked,
    ))

    # --- documents match masters -------------------------------------------
    mismatched: list[str] = []
    for slug, band in cfg.bands.items():
        for t in ledger_mod.load_band_tracks(band):
            if not _released(lc_mod.assess(t).stage):
                continue
            verdict = ((t.get("analysis") or {}).get("asr") or {}).get("verdict", "")
            if not verdict.startswith("sheet-mismatch"):
                continue
            # A KNOWN, RECORDED discrepancy is documentation rather than a gap.
            # Some sheets are demonstrably the draft rather than the take, and the
            # true lyrics may no longer exist. Requiring them to be recovered
            # would make certification impossible for honest reasons; letting them
            # pass silently would make it meaningless. So: acknowledge it in the
            # ledger, with a reason, and it appears in the catalogue where anyone
            # reading can see it.
            ack = t.get("sheet_mismatch_acknowledged")
            if isinstance(ack, dict) and str(ack.get("reason", "")).strip():
                continue
            mismatched.append(
                f"{t.get('id')} {t.get('title')}: transcript says the sheet is a "
                f"different arrangement from the master, and this is not "
                f"acknowledged in the ledger"
            )
    cert.checks.append(Check(
        "documents", "Every sheet matches its master", not mismatched,
        "checked against the measured transcript diff, where one exists",
        mismatched,
    ))

    # --- pipeline ----------------------------------------------------------
    acknowledged: set[str] = set()
    for slug, band in cfg.bands.items():
        for t in ledger_mod.load_band_tracks(band):
            ack = t.get("sheet_mismatch_acknowledged")
            if isinstance(ack, dict) and str(ack.get("reason", "")).strip():
                acknowledged.add(t.get("id"))

    # A track whose mismatch is acknowledged is not "stuck": the adjudication
    # walker refuses it by design, so it could never advance, and reporting a
    # permanent design decision as an outstanding task is noise.
    waiting = [
        a for a in lc_mod.assess_all(cfg)
        if a.blocked_on_human and a.track_id not in acknowledged
    ]
    cert.checks.append(Check(
        "pipeline", "Nothing is stuck awaiting a decision", not waiting,
        "no track is blocked on a human gate",
        [f"{a.track_id} {a.title} -> {a.next_stage}" for a in waiting],
    ))

    # --- freshness ---------------------------------------------------------
    cert.checks.append(_catalogue_is_fresh(cfg))
    return cert


def format_result(cert: Certification) -> str:
    lines = ["=" * 78, f"CERTIFY  {cert.label}", "=" * 78]
    width = max(len(c.title) for c in cert.checks)
    for c in cert.checks:
        mark = "PASS" if c.passed else "FAIL"
        lines.append(f"  [{mark}] {c.title:<{width}}  {c.detail}")
        for g in c.gaps[:6]:
            lines.append(f"         - {g}")
        if len(c.gaps) > 6:
            lines.append(f"         ... {len(c.gaps) - 6} more")
    lines.append("")
    if cert.approved:
        lines.append("APPROVED — this fork carries its catalogue to generated")
        lines.append("documentation with no gaps, and may be listed on the template's")
        lines.append("main branch.")
    else:
        blocking = [c.id for c in cert.checks if not c.passed]
        lines.append(f"NOT APPROVED — blocking: {', '.join(blocking)}")
        lines.append("")
        lines.append("Every gap above is a specific, fixable thing. Nothing here is a")
        lines.append("judgement about the music.")
    return "\n".join(lines)
