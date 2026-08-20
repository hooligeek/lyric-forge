"""`forge spark` — the entry point for net-new work.

Captures the raw human input, computes a brief from what the catalogue is short
of, and opens a tracked lifecycle for the song. It is the front door: everything
downstream — generation, review, render, analysis, adjudication — hangs off the
track this creates.

Two rules the design turns on.

The spark text is written to label/sparks/, which is gitignored, and **nothing
from it is copied into the committed brief**. The brief references it by id only.
Half-honouring that — a "derived summary" in the brief — would leak the rawest
input into permanent history through the back door, which is the thing keeping it
out of git was for. If the operator wants a note in the brief they write one
themselves.

The brief is *proposed*, not agreed. It is computed, so its existence proves
nothing about whether anyone assented to it; the lifecycle gate needs a human to
set `brief_confirmed`. A generated file advancing a human gate would make the
gate decorative.
"""

from __future__ import annotations

import datetime
import secrets
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from . import config as config_mod
from . import ledger as ledger_mod
from . import lifecycle as lc_mod
from . import pipeline as pipeline_mod
from .config import Config, slugify

SPARKS_DIR = config_mod.LABEL_DIR / "sparks"
BRIEFS_DIR = config_mod.LABEL_DIR / "briefs"


def make_spark_id(text: str, explicit: str | None = None) -> str:
    """Date plus an opaque suffix, unless the operator names it themselves.

    This used to build the id from the first four content words of the spark, so
    a note beginning "Third night this week the box has thermal-throttled" became
    an id spelling out "third night week box". That id then travelled into the
    committed brief filename, the ledger, the generated catalogue and its public
    HTML — ten locations, none of which the operator chose to publish.

    That is precisely the leak this module's own docstring warns about — a
    "derived summary" reaching a committed file — implemented by the function
    that was supposed to prevent it. `label/sparks/` being gitignored is
    worthless if the filename carries the content.

    An explicit `--title` is different: naming it is the operator choosing what
    becomes public, so that spelling is honoured.
    """
    today = datetime.date.today().isoformat()
    if explicit:
        return f"{today}-{slugify(explicit)}"
    # Random, not a hash of the text: a hash is stable, and a stable identifier
    # derived from private content is a confirmation oracle for anyone who can
    # guess the wording.
    return f"{today}-{secrets.token_hex(3)}"


@dataclass
class SparkResult:
    spark_id: str
    spark_path: Path
    brief_path: Path
    band: str
    track_id: str
    track_slug: str
    proposal: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        root = config_mod.REPO_ROOT
        return {
            "spark_id": self.spark_id,
            "spark_path": self.spark_path.relative_to(root).as_posix(),
            "brief_path": self.brief_path.relative_to(root).as_posix(),
            "band": self.band,
            "track_id": self.track_id,
            "track_slug": self.track_slug,
            "proposal": self.proposal,
        }


def write_spark(spark_id: str, text: str) -> Path:
    SPARKS_DIR.mkdir(parents=True, exist_ok=True)
    dest = SPARKS_DIR / f"{spark_id}.md"
    if dest.exists():
        raise FileExistsError(f"spark already exists: {dest.name}")
    dest.write_text(
        f"---\nspark_id: {spark_id}\ncaptured: {datetime.date.today().isoformat()}\n---\n\n"
        + text.strip()
        + "\n",
        encoding="utf-8",
    )
    return dest


def write_brief(spark_id: str, band: str, proposal, track_id: str) -> Path:
    BRIEFS_DIR.mkdir(parents=True, exist_ok=True)
    dest = BRIEFS_DIR / f"{spark_id}.md"

    doc = {
        "spark": spark_id,
        "band": band,
        "track_id": track_id,
        "proposed": datetime.date.today().isoformat(),
        "confirmed": False,
        "suite": proposal.suite,
        "suite_reason": proposal.suite_reason,
        "stance": proposal.stance,
        "stance_reason": proposal.stance_reason,
        "bpm": proposal.bpm,
        "bpm_reason": proposal.bpm_reason,
        "constraints": proposal.constraints,
        "avoid_count": len(proposal.avoid),
        "operator_note": "",
    }

    header = "\n".join([
        "---",
        f"# Brief for spark {spark_id}",
        "#",
        "# PROPOSED, not agreed. Every field below is computed from what this",
        "# band's catalogue is short of — change anything you disagree with, then:",
        f"#   forge spark --confirm --band {band} --track <slug>",
        "#",
        "# The spark text is deliberately NOT reproduced here. label/sparks/ is",
        "# gitignored, and copying it into a committed brief would defeat that.",
        "# `operator_note` is yours to fill with whatever you are happy to commit.",
        "",
    ])
    dest.write_text(
        header + yaml.safe_dump(doc, sort_keys=False, allow_unicode=True, width=100),
        encoding="utf-8",
    )
    return dest


def create(
    cfg: Config,
    text: str,
    band: str,
    title: str | None = None,
    spark_id: str | None = None,
) -> SparkResult:
    sid = make_spark_id(text, spark_id or title)
    band_obj = cfg.bands[band]
    tracks = ledger_mod.load_band_tracks(band_obj)

    track_id = ledger_mod.next_id(cfg, band_obj, tracks)
    slug = slugify(title) if title else f"spark-{sid}"
    if any(t.get("slug") == slug for t in tracks):
        raise ValueError(f"a track with slug '{slug}' already exists in {band}")

    spark_path = write_spark(sid, text)
    proposal = pipeline_mod.propose(cfg, band)
    brief_path = write_brief(sid, band, proposal, track_id)

    entry = ledger_mod.blank_track(track_id, title or f"(untitled — spark {sid})", band)
    entry["slug"] = slug
    entry["era"] = "acap"
    entry["status"] = "wip"
    entry["provenance"] = {
        "spark": sid,
        "brief": brief_path.relative_to(config_mod.REPO_ROOT).as_posix(),
        "brief_confirmed": False,
        "prompt_template": None,
        "prompt_version": None,
        "model": None,
        "review": None,
    }
    entry["matrix"] = {"suite": proposal.suite, "stance": proposal.stance}
    entry["suno"] = {
        "style_prompt": None,
        "declared_bpm": proposal.bpm,
        "declared_key": None,
    }
    lc_mod.stamp(
        entry, "spark", by="forge spark",
        note=f"captured as {sid}; brief proposed and awaiting confirmation",
    )
    tracks.append(entry)
    ledger_mod.save_band_tracks(band_obj, tracks)

    return SparkResult(
        spark_id=sid,
        spark_path=spark_path,
        brief_path=brief_path,
        band=band,
        track_id=track_id,
        track_slug=slug,
        proposal=proposal.to_dict(),
    )


def confirm(cfg: Config, band: str, track_slug: str) -> dict[str, Any]:
    """Human assent to the brief. Reads the (possibly edited) brief back, so an
    operator who changed the suite or stance in the file gets what they wrote
    rather than what was proposed."""
    band_obj = cfg.bands[band]
    tracks = ledger_mod.load_band_tracks(band_obj)
    track = next((t for t in tracks if t.get("slug") == track_slug), None)
    if track is None:
        raise ValueError(f"no track '{track_slug}' in {band}")

    brief_rel = ledger_mod.get_nested(track, "provenance.brief")
    if not brief_rel:
        raise ValueError(f"{track_slug} has no brief to confirm")
    brief_path = config_mod.REPO_ROOT / brief_rel
    if not brief_path.exists():
        raise FileNotFoundError(f"brief missing: {brief_rel}")

    doc = yaml.safe_load(brief_path.read_text(encoding="utf-8")) or {}
    changed: list[str] = []
    for field, path in (("suite", "matrix"), ("stance", "matrix")):
        if doc.get(field) and doc[field] != track.get(path, {}).get(field):
            track.setdefault(path, {})[field] = doc[field]
            changed.append(f"{field} -> {doc[field]}")
    if doc.get("bpm") and doc["bpm"] != ledger_mod.get_nested(track, "suno.declared_bpm"):
        track.setdefault("suno", {})["declared_bpm"] = doc["bpm"]
        changed.append(f"bpm -> {doc['bpm']}")

    track.setdefault("provenance", {})["brief_confirmed"] = True
    doc["confirmed"] = True
    brief_path.write_text(
        brief_path.read_text(encoding="utf-8").replace(
            "confirmed: false", "confirmed: true", 1
        ),
        encoding="utf-8",
    )

    lc_mod.stamp(
        track, "brief", by="forge spark --confirm",
        note="; ".join(changed) if changed else "proposal accepted unchanged",
    )
    ledger_mod.save_band_tracks(band_obj, tracks)

    return {
        "band": band,
        "track": track_slug,
        "track_id": track.get("id"),
        "changed": changed,
        "suite": ledger_mod.get_nested(track, "matrix.suite"),
        "stance": ledger_mod.get_nested(track, "matrix.stance"),
        "bpm": ledger_mod.get_nested(track, "suno.declared_bpm"),
    }


def format_created(r: SparkResult) -> str:
    p = r.proposal
    root = config_mod.REPO_ROOT
    lines = ["=" * 78, f"SPARK CAPTURED  {r.spark_id}", "=" * 78]
    lines.append(f"spark : {r.spark_path.relative_to(root)}  (gitignored)")
    lines.append(f"brief : {r.brief_path.relative_to(root)}")
    lines.append(f"track : {r.track_id} in {r.band}  (stage: spark)")
    lines.append("")
    lines.append("-- PROPOSED BRIEF")
    lines.append(f"   stance : {p['stance']}")
    if p["stance_reason"]:
        lines.append(f"            {p['stance_reason'][:160]}")
    lines.append(f"   suite  : {p['suite']}")
    if p["suite_reason"]:
        lines.append(f"            {p['suite_reason'][:160]}")
    lines.append(f"   bpm    : {p['bpm']}")
    if p["bpm_reason"]:
        lines.append(f"            {p['bpm_reason'][:160]}")
    lines.append(f"   avoid  : {len(p['avoid'])} spent phrases")
    lines.append(f"   rules  : {len(p['constraints'])}")
    lines.append("")
    lines.append("-- NEXT")
    lines.append("   Read the brief, change what you disagree with, then:")
    lines.append(f"     forge spark --confirm --band {r.band} --track {r.track_slug}")
    lines.append("   Then generate the draft:")
    lines.append(
        f"     forge prompt render --id generate-song --band {r.band} "
        f"--spark {r.spark_path.relative_to(root)}"
    )
    return "\n".join(lines)
