"""forge — the lyric-forge command line.

    python -m framework.forge bootstrap    # seed ledgers from audio on disk
    python -m framework.forge reconcile    # audio <-> ledger <-> lyric sheets
    python -m framework.forge probe        # audio facts table
    python -m framework.forge decode       # populate the canonical PCM cache
"""

from __future__ import annotations

import argparse
import sys

from pathlib import Path

from . import audio as audio_mod
from . import config as config_mod
from . import importer as importer_mod
from . import ledger as ledger_mod
from . import mine as mine_mod
from . import reconcile as reconcile_mod
from .config import slugify


def cmd_bootstrap(args: argparse.Namespace) -> int:
    cfg = config_mod.load()
    excluded = cfg.excluded_audio
    created_total = 0

    for slug, band in cfg.bands.items():
        tracks = ledger_mod.load_band_tracks(band)
        known = ledger_mod.as_dict(tracks)
        audio_dir = cfg.band_audio_dir(slug)
        files = audio_mod.find_audio(audio_dir)
        created = 0

        for p in files:
            title = p.stem
            if title in excluded:
                continue
            tslug = slugify(title)
            if tslug in known:
                continue
            tid = ledger_mod.next_id(cfg, band, tracks)
            rel = f"{cfg.bands[slug].audio_dir}/{p.name}"
            entry = ledger_mod.blank_track(tid, title, slug, audio=rel)
            try:
                entry["duration_s"] = round(audio_mod.probe(p).duration_s)
            except audio_mod.AudioError as exc:
                print(f"  ! probe failed for {p.name}: {exc}", file=sys.stderr)
            tracks.append(entry)
            known[tslug] = entry
            created += 1

        tracks.sort(key=lambda t: t.get("id") or "")
        ledger_mod.save_band_tracks(band, tracks)
        created_total += created
        print(f"{slug:20s} {len(tracks):2d} tracks ({created} new)")

    print(f"\n{created_total} new ledger entries written.")
    return 0


def cmd_reconcile(args: argparse.Namespace) -> int:
    cfg = config_mod.load()
    rep = reconcile_mod.run(cfg, probe_audio=not args.fast)
    print(reconcile_mod.format_report(rep))
    if args.strict and rep.findings:
        return 1
    return 0


def cmd_probe(args: argparse.Namespace) -> int:
    cfg = config_mod.load()
    excluded = cfg.excluded_audio
    print(f"{'BAND':<18} {'TRACK':<27} {'SECS':>6} {'KBPS':>6} {'RATE':>6} {'CH':>3}")
    total = 0.0
    count = 0
    for slug in cfg.bands:
        for p in audio_mod.find_audio(cfg.band_audio_dir(slug)):
            if p.stem in excluded:
                continue
            pr = audio_mod.probe(p)
            kbps = f"{pr.bit_rate // 1000}" if pr.bit_rate else "?"
            print(
                f"{slug:<18} {p.stem[:27]:<27} {pr.duration_s:>6.0f} {kbps:>6} "
                f"{pr.sample_rate or '?':>6} {pr.channels or '?':>3}"
            )
            total += pr.duration_s
            count += 1
    print(f"\n{count} tracks, {total/60:.1f} min total runtime")
    return 0


def cmd_decode(args: argparse.Namespace) -> int:
    cfg = config_mod.load()
    excluded = cfg.excluded_audio
    kinds = ["dsp", "asr"] if args.kind == "both" else [args.kind]
    targets = [args.band] if args.band else list(cfg.bands)
    for slug in targets:
        if slug not in cfg.bands:
            print(f"unknown band: {slug} (known: {', '.join(cfg.bands)})", file=sys.stderr)
            return 2
    # A 48 kHz/f32 stereo decode runs ~23 MB per audio-minute, so the full catalogue
    # is ~1.6 GB of cache. Gitignored and disposable, but worth not doing by accident.
    n = 0
    for slug in targets:
        for p in audio_mod.find_audio(cfg.band_audio_dir(slug)):
            if p.stem in excluded:
                continue
            tslug = slugify(p.stem)
            for kind in kinds:
                try:
                    out = audio_mod.decode(p, slug, tslug, kind=kind, force=args.force)
                except audio_mod.AudioError as exc:
                    print(f"  ! {p.name} [{kind}]: {exc}", file=sys.stderr)
                    continue
                size_mb = out.stat().st_size / 1_048_576
                print(f"{slug:<18} {p.stem[:30]:<30} {kind}  {size_mb:7.1f} MB")
            n += 1
    print(f"\ndecoded {n} tracks into {audio_mod.PCM_CACHE}")
    return 0


def cmd_import_lyrics(args: argparse.Namespace) -> int:
    cfg = config_mod.load()
    if args.band not in cfg.bands:
        print(f"unknown band: {args.band} (known: {', '.join(cfg.bands)})", file=sys.stderr)
        return 2
    band = cfg.bands[args.band]

    source = Path(args.source).expanduser()
    if not source.is_absolute():
        # Convenience: a bare path is resolved against the band's audio directory,
        # which is where harvest documents get dropped alongside the mp3s.
        candidate = cfg.band_audio_dir(args.band) / source
        source = candidate if candidate.exists() else source
    if not source.exists():
        print(f"no such source: {source}", file=sys.stderr)
        return 2

    matches, unmatched, written = importer_mod.import_file(
        cfg, band, source, dry_run=not args.write
    )
    print(
        importer_mod.format_result(
            band, source, matches, unmatched, written, dry_run=not args.write
        )
    )
    return 0


def cmd_relink(args: argparse.Namespace) -> int:
    """Wire hand-authored lyric sheets into the ledger by slug."""
    cfg = config_mod.load()
    linked = 0
    for slug, band in cfg.bands.items():
        lyrics_dir = band.dir / "lyrics"
        if not lyrics_dir.exists():
            continue
        tracks = ledger_mod.load_band_tracks(band)
        changed = False
        for t in tracks:
            tslug = t.get("slug") or slugify(t.get("title", ""))
            candidate = lyrics_dir / f"{tslug}.md"
            if not candidate.exists():
                continue
            rel = candidate.relative_to(config_mod.REPO_ROOT).as_posix()
            if t.get("lyric_sheet") != rel:
                t["lyric_sheet"] = rel
                print(f"  linked {t.get('id')} {t.get('title')} -> {rel}")
                linked += 1
                changed = True
        if changed:
            ledger_mod.save_band_tracks(band, tracks)
    print(f"{linked} sheet(s) linked.")
    return 0


def cmd_mine(args: argparse.Namespace) -> int:
    cfg = config_mod.load()
    if args.label:
        print(mine_mod.format_cross(mine_mod.mine_label(cfg), limit=args.limit))
        return 0
    targets = [args.band] if args.band else list(cfg.bands)
    for slug in targets:
        if slug not in cfg.bands:
            print(f"unknown band: {slug} (known: {', '.join(cfg.bands)})", file=sys.stderr)
            return 2
    for slug in targets:
        result = mine_mod.mine_band(cfg.bands[slug])
        print(mine_mod.format_result(result, limit=args.limit))
        if args.write:
            dest = mine_mod.write_retired(cfg.bands[slug], result)
            rel = dest.relative_to(config_mod.REPO_ROOT).as_posix()
            print(f"\nwrote {rel}")
        print()
    return 0


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="forge", description="lyric-forge label toolchain")
    sub = ap.add_subparsers(dest="command", required=True)

    p = sub.add_parser("bootstrap", help="seed band ledgers from audio on disk")
    p.set_defaults(func=cmd_bootstrap)

    p = sub.add_parser("reconcile", help="check audio, ledger, and lyric sheets agree")
    p.add_argument("--fast", action="store_true", help="skip ffprobe duration checks")
    p.add_argument("--strict", action="store_true", help="exit 1 if any findings")
    p.set_defaults(func=cmd_reconcile)

    p = sub.add_parser("probe", help="print an audio facts table")
    p.set_defaults(func=cmd_probe)

    p = sub.add_parser("mine", help="find phrases the band has already spent")
    p.add_argument("--band", help="band slug (default: all)")
    p.add_argument("--label", action="store_true", help="cross-band repetition instead")
    p.add_argument("--limit", type=int, default=25, help="max rows per section")
    p.add_argument("--write", action="store_true", help="write retired.yaml triage file")
    p.set_defaults(func=cmd_mine)

    p = sub.add_parser("relink", help="wire hand-authored lyric sheets into the ledger")
    p.set_defaults(func=cmd_relink)

    p = sub.add_parser("import-lyrics", help="import lyric sheets from a harvest document")
    p.add_argument("--band", required=True, help="band slug")
    p.add_argument("--source", required=True, help="harvest document path")
    p.add_argument("--write", action="store_true", help="write sheets (default: dry run)")
    p.set_defaults(func=cmd_import_lyrics)

    p = sub.add_parser("decode", help="populate the canonical PCM cache")
    p.add_argument("--kind", choices=["dsp", "asr", "both"], default="dsp")
    p.add_argument("--band", help="limit to one band slug (default: all)")
    p.add_argument("--force", action="store_true", help="re-decode even if cached")
    p.set_defaults(func=cmd_decode)

    return ap


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return args.func(args)
    except audio_mod.AudioError as exc:
        print(f"audio error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
