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
ACAP_REQUIRED = [
    ("suno.style_prompt", "Suno style prompt"),
    ("suno.declared_bpm", "declared BPM"),
    ("suno.declared_key", "declared key"),
    ("matrix.suite", "matrix suite"),
    ("matrix.stance", "rhetorical stance"),
]

# Wanted for every track regardless of era: these are recoverable and the whole
# backfill goal is to have them.
ALWAYS_WANTED = [
    ("lyric_sheet", "lyric sheet"),
]


@dataclass
class Finding:
    kind: str
    band: str
    subject: str
    detail: str

    def __str__(self) -> str:
        return f"[{self.kind}] {self.band}/{self.subject}: {self.detail}"


@dataclass
class Report:
    findings: list[Finding] = field(default_factory=list)
    stats: dict = field(default_factory=dict)

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


def run(cfg: Config, probe_audio: bool = True, check_hashes: bool = True) -> Report:
    rep = Report()
    _check_yaml_validity(rep)

    if check_hashes:
        from . import fingerprint as fp_mod

        for track_id, field, detail in fp_mod.check_drift(cfg):
            rep.add("ASSET_DRIFT", field, track_id, detail)

    excluded = cfg.excluded_audio
    total_tracks = 0
    total_audio = 0
    with_sheet = 0

    for slug, band in cfg.bands.items():
        tracks = ledger_mod.load_band_tracks(band)
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

            if tslug not in audio_by_slug:
                rep.add("PHANTOM_TRACK", slug, subject, "ledger entry with no audio file")
            elif probe_audio:
                actual = audio_mod.probe(audio_by_slug[tslug]).duration_s
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

            art = t.get("artwork")
            if not art:
                rep.add("NO_ARTWORK", slug, subject, "no cover art linked")
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
                rep.add("NO_LYRIC_SHEET", slug, subject, "no lyric sheet on disk")

            era = t.get("era") or "pre-standard"
            required = list(ALWAYS_WANTED)
            if era == "acap":
                required += ACAP_REQUIRED
            for path, human in required:
                if path == "lyric_sheet":
                    continue  # handled above with existence checking
                if ledger_mod.get_nested(t, path) in (None, "", []):
                    rep.add("MISSING_FIELD", slug, subject, f"{human} not set (era: {era})")

        # --- lyric sheets with no ledger entry -------------------------------
        lyrics_dir = band.dir / "lyrics"
        if lyrics_dir.exists():
            for p in sorted(lyrics_dir.glob("*.md")):
                if p.stem not in by_slug:
                    rep.add("ORPHAN_SHEET", slug, p.name, "lyric sheet with no ledger entry")

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
