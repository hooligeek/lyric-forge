"""Three-way reconciliation: audio on disk <-> ledger <-> lyric sheets.

This is the gate that the prose compliance protocol could not implement. A model
asked to "verify the seal on all key assets" will report PASS for files it never
opened. This checks the filesystem.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from . import audio as audio_mod
from . import config as config_mod
from . import ledger as ledger_mod
from .config import Config, slugify

# Era-aware: a pre-standard track is not expected to carry matrix/stance data,
# so nagging about it would be noise. See label.yaml: eras.
#
# `suno.declared_key` is deliberately NOT here. Suno does not emit a key, and the
# tonal pass is documented as unusable on this material — it agreed with the
# declared key on 1 of 4 tracks that share one. So the only way to satisfy a
# required declared_key is to invent it, and a gate that can only be cleared by
# guessing manufactures exactly the fabrication the rest of this file exists to
# catch. It stays an optional field: recorded where a real one exists, absent
# otherwise, and never demanded.
ACAP_REQUIRED = [
    ("suno.style_prompt", "Suno style prompt"),
    ("suno.declared_bpm", "declared BPM"),
    ("matrix.suite", "matrix suite"),
    ("matrix.stance", "rhetorical stance"),
    # The caption Suno carries alongside each song. It is published metadata the
    # label writes and then loses, which makes it the same class of thing as the
    # style prompt: an input that shaped a release and existed nowhere in the
    # repository. Required for current-era work only, so the pre-standard
    # catalogue is exempt by construction rather than by exception — nothing is
    # backfilled and no rule needs a carve-out.
    ("suno.caption", "Suno caption"),
]

# Suno's own limit. A caption over this is rejected at the platform, so a ledger
# holding one is describing a release that cannot exist as described.
SUNO_CAPTION_MAX = 500

# Wanted for every track regardless of era: these are recoverable and the whole
# backfill goal is to have them.
ALWAYS_WANTED = [
    ("lyric_sheet", "lyric sheet"),
]

# Stages before a render exists. Tracks here legitimately have no audio, cover or
# finished lyrics, so asset checks are skipped rather than reported as gaps.
PRE_RENDER_STAGES = {"spark", "brief", "draft", "review", "sheet"}


@dataclass
class Finding:
    kind: str
    band: str
    subject: str
    detail: str

    def __str__(self) -> str:
        return f"[{self.kind}] {self.band}/{self.subject}: {self.detail}"


# Reported for visibility but not a defect: a song still being written has no
# audio yet, and `--strict` failing on that would make the gate unusable in CI
# for exactly the work the tool exists to support.
INFORMATIONAL = {"IN_PROGRESS", "WIP_GAP"}

# Stages at which a track claims to be finished, and its assets are therefore
# expected to be complete. Before this, a missing cover or uncompiled sheet is
# work not yet done rather than a defect — a render arrives from Suno before its
# art does, and a sheet gets compiled after the take is chosen.
FINISHED_STAGES = {"imported", "adjudicated", "mastered"}


def _is_finished(stage: str) -> bool:
    # `imported/analysed` and friends are composite labels for legacy tracks.
    return stage.split("/")[0] in FINISHED_STAGES or stage in FINISHED_STAGES


@dataclass
class Report:
    findings: list[Finding] = field(default_factory=list)
    stats: dict = field(default_factory=dict)

    @property
    def defects(self) -> list[Finding]:
        return [f for f in self.findings if f.kind not in INFORMATIONAL]

    def add(self, kind: str, band: str, subject: str, detail: str) -> None:
        self.findings.append(Finding(kind, band, subject, detail))

    def by_kind(self) -> dict[str, list[Finding]]:
        out: dict[str, list[Finding]] = {}
        for f in self.findings:
            out.setdefault(f.kind, []).append(f)
        return out


def _check_yaml_validity(rep: Report) -> None:
    """Every YAML file under label/ must parse.

    Added after two hand-authored band.yaml files broke on the same mistake:
    a list item containing an unquoted colon (`- Declare \\`voice: human\\``) or
    opening with a quote and continuing in plain text. Both produce a scanner
    error a long way from the real line, and both silently disabled the band's
    whole definition until something happened to read it.
    """
    import yaml

    for path in sorted(config_mod.LABEL_DIR.rglob("*.yaml")):
        try:
            yaml.safe_load(path.read_text(encoding="utf-8"))
        except yaml.YAMLError as exc:
            rel = path.relative_to(config_mod.REPO_ROOT).as_posix()
            mark = getattr(exc, "problem_mark", None)
            where = f" at line {mark.line + 1}" if mark else ""
            rep.add(
                "INVALID_YAML",
                path.parent.name,
                rel,
                f"{getattr(exc, 'problem', 'parse error')}{where}",
            )


def _check_evidence_integrity(rep: Report, slug: str, subject: str, t: dict) -> None:
    """Enforce the invariants AGENTS.md states.

    They were written down and nothing checked them, which is the same posture as
    the prose compliance protocol this project replaced: a document asserting
    standards with no mechanism behind it. These are all decidable.
    """
    analysis = t.get("analysis")
    log = t.get("glitch_log") or []

    for i, g in enumerate(log):
        anchor = g.get("anchor") or {}
        src = g.get("source")
        verified = g.get("timecode_verified")
        tc = anchor.get("timecode")
        where = f"glitch_log[{i}]"

        # A measured entry must carry a verified timecode; that is what
        # "measured" means.
        if src == "forge-measured" and not (verified and tc):
            rep.add("UNSOUND_EVIDENCE", slug, subject,
                    f"{where} claims source 'forge-measured' but "
                    f"timecode={tc!r}, verified={verified!r}")

        # A perceptual entry must NOT claim verification. The original catalogue
        # carried round timecodes from a notebook with no ability to measure time.
        if src == "notebook-perceptual" and verified:
            rep.add("UNSOUND_EVIDENCE", slug, subject,
                    f"{where} is perceptual yet marked timecode_verified: true")

        # A verified timecode with no analysis to have produced it is fabricated.
        if verified and tc and not analysis:
            rep.add("UNSOUND_EVIDENCE", slug, subject,
                    f"{where} carries a verified timecode but the track has no "
                    f"analysis block. Nothing measured it.")

    # A glitch log with no audio at all cannot have been observed.
    if log and not t.get("audio"):
        rep.add("UNSOUND_EVIDENCE", slug, subject,
                f"{len(log)} glitch entries on a track with no audio — a glitch "
                f"log is written after a render, never before")


def run(cfg: Config, probe_audio: bool = True, check_hashes: bool = True) -> Report:
    rep = Report()
    _check_yaml_validity(rep)
    if any(f.kind == "INVALID_YAML" for f in rep.findings):
        # Stop here. Everything below reads those files, so continuing meant the
        # process died on the malformed YAML *after* computing the diagnostic and
        # before printing it — rc=1 with zero output.
        rep.stats = {"aborted": "unparseable label data"}
        return rep

    if check_hashes:
        from . import fingerprint as fp_mod

        try:
            for track_id, field, detail in fp_mod.check_drift(cfg):
                rep.add("ASSET_DRIFT", field, track_id, detail)
        except ledger_mod.LedgerError as exc:
            # This ran before the per-band guard and so raised first.
            rep.add("INVALID_LEDGER", "-", "ledger", str(exc))
            return rep

    # Every track id on the label, so `suno.derived_from` can be checked against
    # reality. Built up front because a clone may reference any track, not only one
    # of its own band's.
    known_ids: set[str] = set()
    parent_of: dict[str, str] = {}
    try:
        for _slug, _band in cfg.bands.items():
            for _t in ledger_mod.load_band_tracks(_band):
                if _t.get("id"):
                    known_ids.add(str(_t["id"]))
    except ledger_mod.LedgerError:
        pass  # reported below by the per-band pass

    excluded = cfg.excluded_audio
    total_tracks = 0
    total_audio = 0
    with_sheet = 0

    for slug, band in cfg.bands.items():
        try:
            tracks = ledger_mod.load_band_tracks(band)
        except ledger_mod.LedgerError as exc:
            rep.add("INVALID_LEDGER", slug, band.tracks_file.name, str(exc))
            continue
        by_slug = ledger_mod.as_dict(tracks)
        total_tracks += len(tracks)

        audio_dir = cfg.band_audio_dir(slug)
        if not audio_dir.exists():
            rep.add("MISSING_AUDIO_DIR", slug, audio_dir.name, f"no such directory: {audio_dir}")
            audio_files = []
        else:
            audio_files = audio_mod.find_audio(audio_dir)

        # --- audio present but not in the ledger -----------------------------
        audio_by_slug: dict[str, Path] = {}
        for p in audio_files:
            title = p.stem
            if title in excluded:
                continue
            total_audio += 1
            aslug = slugify(title)
            audio_by_slug[aslug] = p
            if aslug not in by_slug:
                rep.add("ORPHAN_AUDIO", slug, title, "audio on disk with no ledger entry")

        # --- ledger entries checked against disk ----------------------------
        for t in tracks:
            tslug = t.get("slug") or slugify(t.get("title", ""))
            subject = t.get("title") or tslug

            # A song that has not been rendered yet has no audio, no cover and
            # possibly no lyrics, and that is correct rather than a finding.
            # Demanding assets from a track at the spark stage would make the
            # tool unusable for new work — the thing it exists to support.
            stage = ledger_mod.get_nested(t, "lifecycle.stage") or "imported"
            finished = _is_finished(stage)

            def gap(kind: str, detail: str) -> None:
                """An asset gap is a defect only once the track claims to be done."""
                if finished:
                    rep.add(kind, slug, subject, detail)
                else:
                    rep.add(
                        "WIP_GAP", slug, subject,
                        f"{detail} (stage '{stage}' — expected before mastered)",
                    )

            if stage in PRE_RENDER_STAGES:
                rep.add(
                    "IN_PROGRESS",
                    slug,
                    subject,
                    f"at stage '{stage}' — asset checks skipped until rendered",
                )
                continue

            if tslug not in audio_by_slug:
                rep.add("PHANTOM_TRACK", slug, subject, "ledger entry with no audio file")
            elif probe_audio:
                # Defence in depth: the zero-byte failure got through because
                # every layer independently agreed with a measurement of zero.
                try:
                    actual = audio_mod.probe(audio_by_slug[tslug]).duration_s
                except audio_mod.AudioError as exc:
                    rep.add("UNPLAYABLE_AUDIO", slug, subject, str(exc))
                    actual = None
                if actual is None:
                    pass
                else:
                    declared = t.get("duration_s")
                    if declared is None:
                        rep.add("NO_DURATION", slug, subject, f"actual is {actual:.0f}s")
                    elif abs(float(declared) - actual) > 1.0:
                        rep.add(
                            "DURATION_DRIFT",
                            slug,
                            subject,
                            f"ledger says {declared}s, audio is {actual:.0f}s",
                        )

            # Naming convention: one slug addresses every asset a track has.
            # Assets arrive from Suno and image exports with spaces, ampersands,
            # exclamation marks and trailing whitespace, and a name that drifts
            # from the slug quietly breaks the addressing the whole ledger relies
            # on — so it is checked rather than assumed.
            expected_audio = f"{slug}/{tslug}"
            actual_audio = t.get("audio")
            if actual_audio and Path(actual_audio).with_suffix("").as_posix() != expected_audio:
                rep.add(
                    "ASSET_NAMING",
                    slug,
                    subject,
                    f"audio is {actual_audio}, convention is {expected_audio}<ext>",
                )
            actual_art = t.get("artwork")
            if actual_art and Path(actual_art).with_suffix("").as_posix() != f"songs/{tslug}":
                rep.add(
                    "ASSET_NAMING",
                    slug,
                    subject,
                    f"artwork is {actual_art}, convention is songs/{tslug}<ext>",
                )

            _check_evidence_integrity(rep, slug, subject, t)

            art = t.get("artwork")
            if not art:
                gap("NO_ARTWORK", "no cover art linked")
            elif not (cfg.artwork_root / art).exists():
                rep.add(
                    "BROKEN_ARTWORK_REF", slug, subject, f"artwork points at missing {art}"
                )

            sheet = t.get("lyric_sheet")
            sheet_ok = False
            if sheet:
                sheet_path = config_mod.REPO_ROOT / sheet
                if sheet_path.exists():
                    sheet_ok = True
                    with_sheet += 1
                else:
                    rep.add("BROKEN_SHEET_REF", slug, subject, f"lyric_sheet points at missing {sheet}")
            if not sheet_ok:
                gap("NO_LYRIC_SHEET", "no lyric sheet on disk")

            # A dangling artwork prompt is reported but its absence is not a gap.
            # Not every cover came from a prompt — imported work predates the
            # practice — so requiring one would fabricate a standard backwards over
            # the catalogue. A path that points at nothing is a different matter:
            # that is a claim the repo cannot support.
            art_prompt = t.get("artwork_prompt")
            if art_prompt and not (config_mod.REPO_ROOT / art_prompt).exists():
                rep.add(
                    "BROKEN_ARTWORK_PROMPT_REF", slug, subject,
                    f"artwork_prompt points at missing {art_prompt}",
                )

            era = t.get("era") or "pre-standard"
            required = list(ALWAYS_WANTED)
            if era == cfg.current_era:
                required += ACAP_REQUIRED
            for path, human in required:
                if path == "lyric_sheet":
                    continue  # handled above with existence checking
                if ledger_mod.get_nested(t, path) in (None, "", []):
                    gap("MISSING_FIELD", f"{human} not set (era: {era})")

            # --- clone lineage -------------------------------------------
            # Unrecorded is fine and is the default. A recorded value that points
            # at nothing is not: that is a provenance claim the repo cannot
            # support, which is worse than admitting the lineage is unknown.
            derived = ledger_mod.get_nested(t, "suno.derived_from")
            if derived:
                derived = str(derived)
                tid = str(t.get("id"))
                if derived == tid:
                    rep.add("BROKEN_LINEAGE_REF", slug, subject,
                            "derived_from points at itself")
                elif derived != "origin" and derived not in known_ids:
                    rep.add("BROKEN_LINEAGE_REF", slug, subject,
                            f"derived_from '{derived}' is not 'origin' and not a "
                            f"known track id")
                elif derived != "origin":
                    parent_of[tid] = derived

            # --- the measurement reached the field that is read ------------
            # `measured_bpm` is read by docs, variety, pipeline and context, and
            # for a long time was written by nothing: the analyser recorded
            # detected_bpm and the summary field stayed null, so newly analysed
            # tracks silently had no tempo anywhere it mattered. A derived field
            # that nothing populates is indistinguishable from a missing
            # measurement, so check that the bridge held.
            detected = ledger_mod.get_nested(t, "analysis.rhythm.detected_bpm")
            if detected and not t.get("measured_bpm"):
                rep.add("UNPROPAGATED_MEASUREMENT", slug, subject,
                        f"analysis measured {detected} BPM but measured_bpm is unset; "
                        f"re-run analyze --write")

            caption = ledger_mod.get_nested(t, "suno.caption")
            if caption and len(str(caption)) > SUNO_CAPTION_MAX:
                rep.add(
                    "CAPTION_TOO_LONG", slug, subject,
                    f"caption is {len(str(caption))} characters; Suno's limit is "
                    f"{SUNO_CAPTION_MAX}",
                )

        # --- lyric sheets with no ledger entry -------------------------------
        lyrics_dir = band.dir / "lyrics"
        if lyrics_dir.exists():
            for p in sorted(lyrics_dir.glob("*.md")):
                if p.stem not in by_slug:
                    rep.add("ORPHAN_SHEET", slug, p.name, "lyric sheet with no ledger entry")

    # --- lineage cycles -----------------------------------------------------
    # A clone chain has to terminate at an origin. A cycle means the ledger claims
    # a render is descended from itself, which is not a lineage, and it would hang
    # any future walk of the chain.
    for start in sorted(parent_of):
        seen = {start}
        node = start
        while node in parent_of:
            node = parent_of[node]
            if node in seen:
                rep.add("LINEAGE_CYCLE", "-", start,
                        f"derived_from chain loops back on itself at {node}")
                break
            seen.add(node)

    rep.stats = {
        "bands": len(cfg.bands),
        "ledger_tracks": total_tracks,
        "audio_files": total_audio,
        "with_lyric_sheet": with_sheet,
    }
    return rep


def format_report(rep: Report) -> str:
    lines: list[str] = []
    s = rep.stats
    lines.append("=" * 72)
    lines.append("LEDGER RECONCILIATION")
    lines.append("=" * 72)
    if s.get("aborted"):
        lines.append(f"ABORTED: {s['aborted']} — nothing else could be checked.")
    else:
        lines.append(
            f"bands: {s.get('bands')}   ledger tracks: {s.get('ledger_tracks')}   "
            f"audio files: {s.get('audio_files')}   with lyric sheet: {s.get('with_lyric_sheet')}"
        )
    lines.append("")

    grouped = rep.by_kind()
    if not grouped:
        lines.append("No findings. Ledger, audio, and lyric sheets agree.")
        return "\n".join(lines)

    for kind in sorted(grouped, key=lambda k: (-len(grouped[k]), k)):
        items = grouped[kind]
        lines.append(f"-- {kind}  ({len(items)})")
        for f in items:
            lines.append(f"   {f.band}/{f.subject}: {f.detail}")
        lines.append("")
    return "\n".join(lines)
