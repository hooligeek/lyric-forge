"""forge — the lyric-forge command line.

    python -m framework.forge bootstrap    # seed ledgers from audio on disk
    python -m framework.forge reconcile    # audio <-> ledger <-> lyric sheets
    python -m framework.forge probe        # audio facts table
    python -m framework.forge decode       # populate the canonical PCM cache
"""

from __future__ import annotations

import argparse
import json
import sys

from pathlib import Path

from . import analyze as analyze_mod
from . import artwork_cmd as artwork_cmd_mod
from . import audio as audio_mod
from . import config as config_mod
from . import fingerprint as fingerprint_mod
from . import importer as importer_mod
from . import ledger as ledger_mod
from . import lifecycle as lifecycle_mod
from . import lyrics as lyrics_mod
from . import mine as mine_mod
from . import pipeline as pipeline_mod
from . import reconcile as reconcile_mod
from . import variety as variety_mod
from .config import slugify


def _emit(args: argparse.Namespace, data: dict, formatter) -> int:
    """Structured output for agents, formatted output for humans.

    The app is driven from an AI-enabled editor as the primary case, so every
    reporting command can return JSON. The formatted view stays because a human
    reading a table is still a real use, but it is the secondary rendering of the
    same data rather than a separate code path that can drift from it.
    """
    if getattr(args, "json", False):
        print(json.dumps(data, indent=2, ensure_ascii=False, default=str))
    else:
        print(formatter(data))
    return 0


def cmd_status(args: argparse.Namespace) -> int:
    cfg = config_mod.load()
    return _emit(args, pipeline_mod.status(cfg), pipeline_mod.format_status)


def cmd_next(args: argparse.Namespace) -> int:
    cfg = config_mod.load()
    if args.band and args.band not in cfg.bands:
        print(f"unknown band: {args.band} (known: {', '.join(cfg.bands)})", file=sys.stderr)
        return 2
    data = pipeline_mod.next_actions(cfg, band=args.band)
    return _emit(args, data, pipeline_mod.format_next)


def cmd_stages(args: argparse.Namespace) -> int:
    """Document the lifecycle. An agent arriving cold needs the map, not just
    the current position."""
    data = {
        "stages": [
            {
                "id": s.id,
                "order": s.order,
                "gate": s.gate,
                "summary": s.summary,
                "requires": s.requires,
                "asks": s.asks,
            }
            for s in lifecycle_mod.STAGES
        ]
    }

    def fmt(d: dict) -> str:
        out = ["=" * 78, "LIFECYCLE", "=" * 78]
        for s in d["stages"]:
            marker = "(entry point)" if s["order"] < 0 else f"{s['order']}."
            out.append(f"{marker:<14} {s['id']:<13} gate: {s['gate']}")
            out.append(f"               {s['summary']}")
            if s["requires"]:
                out.append(f"               requires: {', '.join(s['requires'])}")
            if s["asks"]:
                out.append(f"               asks: {s['asks']}")
            out.append("")
        return "\n".join(out)

    return _emit(args, data, fmt)


def cmd_docs(args: argparse.Namespace) -> int:
    from . import docs as docs_mod

    cfg = config_mod.load()
    root = Path(args.out).expanduser() if args.out else docs_mod.DOCS
    ds = (
        docs_mod.build_framework() if args.kind == "framework"
        else docs_mod.build_catalog(cfg, root)
    )
    return _emit(args, ds.write(root), docs_mod.format_result)


def cmd_bundle(args: argparse.Namespace) -> int:
    from . import bundle as bundle_mod

    cfg = config_mod.load()
    if args.kind == "fresh":
        b = bundle_mod.build_fresh()
        root = Path(args.out).expanduser() if args.out else bundle_mod.FRESH_DIR
    else:
        bands = [args.band] if args.band else None
        if args.band and args.band not in cfg.bands:
            print(f"unknown band: {args.band}", file=sys.stderr)
            return 2
        b = bundle_mod.build_export(cfg, bands)
        root = (
            Path(args.out).expanduser() if args.out
            else bundle_mod.DIST / cfg.raw.get("label", {}).get("id", "label").lower()
        )

    result = b.write(root)
    return _emit(args, result, bundle_mod.format_result)


def cmd_infer(args: argparse.Namespace) -> int:
    from . import context as context_mod
    from . import inference as inf_mod
    from . import prompts as prompts_mod

    cfg = config_mod.load()
    if args.band and args.band not in cfg.bands:
        print(f"unknown band: {args.band} (known: {', '.join(cfg.bands)})", file=sys.stderr)
        return 2

    try:
        prompt = prompts_mod.load(args.id)
    except prompts_mod.PromptError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    def _read(path: str | None) -> str:
        if not path:
            return ""
        p = Path(path).expanduser()
        if not p.exists():
            raise FileNotFoundError(f"no such file: {p}")
        return p.read_text(encoding="utf-8")

    try:
        ctx = context_mod.build(
            cfg,
            band=args.band,
            track=args.track,
            spark=_read(args.spark),
            lyrics=_read(args.lyrics),
            extra_context=args.context or "",
            vision=args.vision or "",
        )
        rendered = prompts_mod.render(prompt, ctx)
    except (prompts_mod.PromptError, FileNotFoundError) as exc:
        print(str(exc), file=sys.stderr)
        return 2

    out_path = None
    if args.out:
        out_path = Path(args.out).expanduser()
    elif args.write:
        out_path = inf_mod.default_output(cfg, prompt.outputs, args.band, args.track)
        if out_path is None:
            print(
                f"--write needs a conventional destination, and there is none for "
                f"outputs '{prompt.outputs}' without --band and --track. "
                f"Pass --out explicitly.",
                file=sys.stderr,
            )
            return 2

    # --- agent mode --------------------------------------------------------
    if args.mode == "agent":
        recorded = None
        if args.record:
            if not (args.band and args.track):
                print("--record needs --band and --track", file=sys.stderr)
                return 2
            recorded = inf_mod.record_provenance(
                cfg, args.band, args.track, rendered, "agent", None, out_path
            )
            if not recorded["stage_stamped"]:
                print(
                    f"Provenance recorded, but no artefact at "
                    f"{out_path or '(no --out/--write given)'} — the stage is not "
                    f"stamped. In agent mode the output is written after this "
                    f"returns, so run --record again once it exists.",
                    file=sys.stderr,
                )
        data = {
            "mode": "agent",
            "recorded": recorded,
            "prompt": rendered.to_dict(),
            "output_path": str(out_path) if out_path else None,
            "instruction": (
                "Act on the prompt text and write the result to output_path. "
                "Then record it: forge infer --record."
            ),
        }
        if args.json:
            print(json.dumps(data, indent=2, ensure_ascii=False))
        else:
            print(rendered.text)
            if out_path:
                print(f"\n--- write your response to: {out_path}", file=sys.stderr)
        return 0

    # --- api mode ----------------------------------------------------------
    try:
        provider = inf_mod.load_provider(args.provider, args.model)
    except inf_mod.InferenceError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    if args.dry_run:
        try:
            req = inf_mod.build_request(provider, rendered.text)
        except inf_mod.InferenceError as exc:
            print(str(exc), file=sys.stderr)
            return 2
        data = {
            "mode": "api",
            "dry_run": True,
            "prompt": {k: v for k, v in rendered.to_dict().items() if k != "text"},
            "prompt_chars": len(rendered.text),
            "request": req.redacted(),
        }
        print(json.dumps(data, indent=2, ensure_ascii=False))
        return 0

    try:
        completion = inf_mod.call(provider, rendered.text)
    except inf_mod.InferenceError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    if out_path:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(completion.text, encoding="utf-8")

    if args.record:
        if not (args.band and args.track):
            print("--record needs --band and --track", file=sys.stderr)
            return 2
        inf_mod.record_provenance(
            cfg, args.band, args.track, rendered, "api", completion.model, out_path
        )

    data = {
        "mode": "api",
        "prompt": {k: v for k, v in rendered.to_dict().items() if k != "text"},
        "completion": completion.to_dict(),
        "output_path": str(out_path) if out_path else None,
    }
    if args.json:
        data["text"] = completion.text
        print(json.dumps(data, indent=2, ensure_ascii=False))
    else:
        print(completion.text)
        print(
            f"\n--- {completion.provider}/{completion.model}"
            + (f" -> {out_path}" if out_path else ""),
            file=sys.stderr,
        )
    return 0


def cmd_ingest_audio(args: argparse.Namespace) -> int:
    from . import ingest as ingest_mod

    cfg = config_mod.load()
    try:
        result = ingest_mod.ingest(
            cfg,
            args.band,
            args.track,
            Path(args.file).expanduser(),
            artwork=Path(args.artwork).expanduser() if args.artwork else None,
            replace=args.replace,
            move=args.move,
        )
    except (ingest_mod.IngestError, audio_mod.AudioError) as exc:
        print(str(exc), file=sys.stderr)
        return 2

    if args.analyze:
        # The analyser needs librosa and faster-whisper, which live in the venv.
        # Say so plainly rather than dying on an ImportError three frames deep.
        try:
            import librosa  # noqa: F401
        except ImportError:
            print(
                "\n!! --analyze needs the analysis extras. Re-run with the venv:\n"
                f"   ./.venv/bin/python -m framework.forge analyze --band {args.band} "
                f"--track {args.track} --write",
                file=sys.stderr,
            )
        else:
            rows = ledger_mod.load_band_tracks(cfg.bands[args.band])
            track = next((t for t in rows if t.get("slug") == args.track), None)
            song = None
            rel = (track or {}).get("lyric_sheet")
            if rel and (config_mod.REPO_ROOT / rel).exists():
                song = lyrics_mod.load_sheet(config_mod.REPO_ROOT / rel)
            src = cfg.audio_root / result.audio_rel
            ta = analyze_mod.analyze_track(
                src, args.band, args.track, track or {}, song, model_name=args.model
            )
            print(analyze_mod.format_track(ta, limit=6))
            result.analysed = True

    return _emit(args, result.to_dict(), lambda d: ingest_mod.format_result(result))


def cmd_review(args: argparse.Namespace) -> int:
    from . import context as context_mod
    from . import prompts as prompts_mod
    from . import review as review_mod

    cfg = config_mod.load()
    if args.band and args.band not in cfg.bands:
        print(f"unknown band: {args.band} (known: {', '.join(cfg.bands)})", file=sys.stderr)
        return 2

    # Lyrics come from an explicit file, or from the track's own sheet.
    text = ""
    if args.lyrics:
        lp = Path(args.lyrics).expanduser()
        if not lp.exists():
            print(f"no such lyrics file: {lp}", file=sys.stderr)
            return 2
        text = lp.read_text(encoding="utf-8")
    elif args.track:
        if not args.band:
            print("--track needs --band", file=sys.stderr)
            return 2
        rows = ledger_mod.load_band_tracks(cfg.bands[args.band])
        row = next((t for t in rows if t.get("slug") == args.track), None)
        if row is None:
            print(f"no track '{args.track}' in {args.band}", file=sys.stderr)
            return 2
        rel = row.get("lyric_sheet")
        if not rel:
            print(
                f"{args.track} has no lyric sheet yet. Pass --lyrics with a draft, "
                f"or generate one first.",
                file=sys.stderr,
            )
            return 2
        text = (config_mod.REPO_ROOT / rel).read_text(encoding="utf-8")
    elif not sys.stdin.isatty():
        text = sys.stdin.read()

    if not text.strip():
        print(
            "nothing to review. Provide --lyrics, --track, or pipe on stdin.",
            file=sys.stderr,
        )
        return 2

    rv = review_mod.run(cfg, text, band=args.band, track=args.track)

    if args.prompt:
        # The judgement half. Mechanical findings are injected so the model does
        # not re-derive what has already been measured.
        try:
            prompt = prompts_mod.load("review-lyrics")
        except prompts_mod.PromptError as exc:
            print(str(exc), file=sys.stderr)
            return 2
        extra = review_mod.as_prompt_context(rv)
        if args.context:
            extra = f"{args.context}\n\n{extra}"
        ctx = context_mod.build(
            cfg, band=args.band, track=args.track, lyrics=text, extra_context=extra
        )
        try:
            rendered = prompts_mod.render(prompt, ctx)
        except prompts_mod.PromptError as exc:
            print(str(exc), file=sys.stderr)
            return 2
        if args.json:
            print(json.dumps(
                {"mechanical": rv.to_dict(), "prompt": rendered.to_dict()},
                indent=2, ensure_ascii=False, default=str,
            ))
        else:
            print(rendered.text)
        return 0

    if args.record:
        if not (args.band and args.track):
            print("--record needs --band and --track", file=sys.stderr)
            return 2
        dest = review_mod.record(cfg, args.band, args.track, rv)
        rel = dest.relative_to(config_mod.REPO_ROOT).as_posix()
        if not args.json:
            print(review_mod.format_review(rv))
            print(f"\nrecorded {rel} — stage: review")
            return 0
        data = rv.to_dict()
        data["recorded"] = rel
        print(json.dumps(data, indent=2, ensure_ascii=False, default=str))
        return 0

    return _emit(args, rv.to_dict(), lambda d: review_mod.format_review(rv))


def cmd_spark(args: argparse.Namespace) -> int:
    from . import spark as spark_mod

    cfg = config_mod.load()

    if args.confirm:
        if not (args.band and args.track):
            print("--confirm needs --band and --track", file=sys.stderr)
            return 2
        if args.band not in cfg.bands:
            print(f"unknown band: {args.band}", file=sys.stderr)
            return 2
        try:
            data = spark_mod.confirm(cfg, args.band, args.track)
        except (ValueError, FileNotFoundError) as exc:
            print(str(exc), file=sys.stderr)
            return 2

        def fmt(d: dict) -> str:
            out = [f"Brief confirmed for {d['track_id']} ({d['track']})."]
            out.append(
                f"  suite {d['suite']} | stance {d['stance']} | {d['bpm']} BPM"
            )
            if d["changed"]:
                out.append("  operator changes: " + "; ".join(d["changed"]))
            else:
                out.append("  proposal accepted unchanged")
            out.append("  stage: brief. Next: generate the draft.")
            return "\n".join(out)

        return _emit(args, data, fmt)

    # --- capture -----------------------------------------------------------
    text = ""
    if args.file:
        fp = Path(args.file).expanduser()
        if not fp.exists():
            print(f"no such file: {fp}", file=sys.stderr)
            return 2
        text = fp.read_text(encoding="utf-8")
    elif args.text:
        text = args.text
    elif not sys.stdin.isatty():
        text = sys.stdin.read()

    if not text.strip():
        print(
            "nothing to capture. Provide --text, --file, or pipe on stdin.",
            file=sys.stderr,
        )
        return 2

    if not args.band:
        # Not an error — show the comparison so the choice is informed rather
        # than arbitrary. This is the same elicitation principle as `next`.
        data = pipeline_mod.next_actions(cfg, band=None)
        print(
            "No --band given. Nothing captured yet — pick a band, informed by "
            "what each is short of:\n",
            file=sys.stderr,
        )
        print(pipeline_mod.format_next(data))
        return 2

    if args.band not in cfg.bands:
        print(f"unknown band: {args.band} (known: {', '.join(cfg.bands)})", file=sys.stderr)
        return 2

    try:
        result = spark_mod.create(
            cfg, text, args.band, title=args.title, spark_id=args.id
        )
    except (FileExistsError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        return 2

    return _emit(args, result.to_dict(), lambda d: spark_mod.format_created(result))


def cmd_adjudicate(args: argparse.Namespace) -> int:
    from . import adjudicate as adj_mod

    cfg = config_mod.load()
    targets = [args.band] if args.band else list(cfg.bands)
    for slug in targets:
        if slug not in cfg.bands:
            print(f"unknown band: {slug} (known: {', '.join(cfg.bands)})", file=sys.stderr)
            return 2

    if args.apply:
        results = []
        for slug in targets:
            try:
                results.append(adj_mod.apply_decisions(cfg, slug))
            except FileNotFoundError as exc:
                print(str(exc), file=sys.stderr)
                return 2
        data = {"applied": results}

        def fmt(d: dict) -> str:
            out = ["=" * 78, "ADJUDICATION APPLIED", "=" * 78]
            for r in d["applied"]:
                out.append(
                    f"{r['band']:<18} kept {r['kept']}, discarded {r['discarded']}, "
                    f"pending {r['pending']}, stamped {len(r['stamped'])}"
                )
                for ref in r["refused"]:
                    out.append(f"   refused {ref['track']}: {ref['reason'][:90]}")
            if any(r["pending"] for r in d["applied"]):
                out.append("")
                out.append(
                    "Tracks with pending candidates were left unstamped. Partial "
                    "adjudication is not adjudication — they stay visible in status."
                )
            return "\n".join(out)

        return _emit(args, data, fmt)

    docs = []
    for slug in targets:
        doc = adj_mod.build_decisions(cfg, slug)
        if args.write:
            dest = adj_mod.write_decisions(cfg, slug, doc)
            doc["_written"] = dest.relative_to(config_mod.REPO_ROOT).as_posix()
        docs.append(doc)

    if args.json:
        print(json.dumps({"bands": docs}, indent=2, ensure_ascii=False, default=str))
        return 0
    for doc in docs:
        print(adj_mod.format_decisions(doc))
        if doc.get("_written"):
            print(f"\nwrote {doc['_written']}")
        print()
    return 0


def cmd_prompt(args: argparse.Namespace) -> int:
    from . import context as context_mod
    from . import prompts as prompts_mod

    if args.action == "list":
        data = {"prompts": [p.to_dict() for p in prompts_mod.load_all()]}

        def fmt(d: dict) -> str:
            out = ["=" * 78, "PROMPT LIBRARY", "=" * 78]
            for p in d["prompts"]:
                out.append(f"{p['ref']:<24} {p['title']}")
                out.append(f"{'':<24} outputs: {p['outputs']}  runtimes: {', '.join(p['runtimes'])}")
                out.append(f"{'':<24} requires {len(p['requires'])}, optional {len(p['optional'])}")
                out.append("")
            return "\n".join(out)

        return _emit(args, data, fmt)

    if args.action == "lint":
        problems: dict[str, list[str]] = {}
        for p in prompts_mod.load_all():
            found = prompts_mod.lint(p)
            if found:
                problems[p.ref] = found
        data = {"problems": problems, "clean": not problems}

        def fmt(d: dict) -> str:
            if d["clean"]:
                return "All prompts consistent: every slot used is declared, every slot declared is used."
            out = ["PROMPT LINT"]
            for ref, items in d["problems"].items():
                out.append(f"  {ref}")
                for i in items:
                    out.append(f"    ! {i}")
            return "\n".join(out)

        print(fmt(data) if not args.json else json.dumps(data, indent=2))
        return 1 if problems else 0

    if not args.id:
        print("--id is required for show/render", file=sys.stderr)
        return 2

    try:
        prompt = prompts_mod.load(args.id)
    except prompts_mod.PromptError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    if args.action == "show":
        print(prompt.body if not args.json else json.dumps(prompt.to_dict(), indent=2))
        return 0

    # render
    cfg = config_mod.load()
    if args.band and args.band not in cfg.bands:
        print(f"unknown band: {args.band} (known: {', '.join(cfg.bands)})", file=sys.stderr)
        return 2

    lyrics = ""
    if args.lyrics:
        lp = Path(args.lyrics).expanduser()
        if not lp.exists():
            print(f"no such lyrics file: {lp}", file=sys.stderr)
            return 2
        lyrics = lp.read_text(encoding="utf-8")

    spark = ""
    if args.spark:
        sp = Path(args.spark).expanduser()
        if not sp.exists():
            print(f"no such spark file: {sp}", file=sys.stderr)
            return 2
        spark = sp.read_text(encoding="utf-8")

    ctx = context_mod.build(
        cfg,
        band=args.band,
        track=args.track,
        suite=args.suite,
        stance=args.stance,
        bpm=args.bpm,
        spark=spark,
        lyrics=lyrics,
        extra_context=args.context or "",
        vision=args.vision or "",
    )
    try:
        rendered = prompts_mod.render(prompt, ctx)
    except prompts_mod.PromptError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    if args.json:
        print(json.dumps(rendered.to_dict(), indent=2, ensure_ascii=False))
    else:
        print(rendered.text)
    return 0


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
    rep = reconcile_mod.run(cfg, probe_audio=not args.fast, check_hashes=not args.no_hash)
    print(reconcile_mod.format_report(rep))
    if args.strict and rep.defects:
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


def cmd_artwork(args: argparse.Namespace) -> int:
    cfg = config_mod.load()
    print(
        artwork_cmd_mod.run(
            cfg, write=args.write, with_palette=not args.no_palette
        )
    )
    return 0


def cmd_fingerprint(args: argparse.Namespace) -> int:
    cfg = config_mod.load()
    print(fingerprint_mod.run(cfg, write=args.write))
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


def cmd_variety(args: argparse.Namespace) -> int:
    cfg = config_mod.load()
    results, summary = variety_mod.run(cfg)
    print(variety_mod.format_report(results, summary))
    if args.strict and any(bv.warnings for bv in results):
        return 1
    return 0


def cmd_analyze(args: argparse.Namespace) -> int:
    """Analysis is slow enough (minutes per track) that progress must be
    observable while it runs. Everything is echoed to .cache/analyze.log,
    line-buffered and unbuffered on stdout, so `tail -f` works and a piped
    stdout cannot swallow it."""
    import time

    import yaml

    cfg = config_mod.load()
    log_path = config_mod.CACHE_DIR / "analyze.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log = log_path.open("a", encoding="utf-8", buffering=1)

    def say(msg: str = "") -> None:
        print(msg, flush=True)
        log.write(f"{msg}\n")

    say("")
    say(f"### analyze started {time.strftime('%Y-%m-%d %H:%M:%S')}  model={args.model}")
    targets = [args.band] if args.band else list(cfg.bands)
    for slug in targets:
        if slug not in cfg.bands:
            print(f"unknown band: {slug} (known: {', '.join(cfg.bands)})", file=sys.stderr)
            return 2

    for slug in targets:
        band = cfg.bands[slug]
        tracks = ledger_mod.load_band_tracks(band)
        say("=" * 78)
        say(f"ANALYSE  {slug}")
        say("=" * 78)
        cand_doc: dict = {"band": slug, "tracks": {}}
        changed = False

        # Band nominal tempo as a seeding prior for tracks with no declared BPM.
        fallback_bpm = None
        bf = band.band_file
        if bf.exists():
            spec = yaml.safe_load(bf.read_text(encoding="utf-8")) or {}
            fallback_bpm = (spec.get("sonic") or {}).get("bpm_nominal")

        for t in tracks:
            tslug = t.get("slug")
            if args.track and tslug != args.track:
                continue
            audio_rel = t.get("audio")
            if not audio_rel:
                print(f"-- {t.get('id')} {t.get('title')}: no audio", file=sys.stderr)
                continue
            src = cfg.audio_root / audio_rel

            song = None
            sheet = t.get("lyric_sheet")
            if sheet:
                sp = config_mod.REPO_ROOT / sheet
                if sp.exists():
                    song = lyrics_mod.load_sheet(sp)

            say(f"-> [{time.strftime('%H:%M:%S')}] {t.get('id')} {t.get('title')} "
                f"({t.get('duration_s')}s) analysing...")
            t0 = time.time()
            try:
                ta = analyze_mod.analyze_track(
                    src, slug, tslug, t, song,
                    model_name=args.model, do_asr=not args.no_asr,
                    fallback_bpm=fallback_bpm,
                )
            except Exception as exc:
                print(f"-- {t.get('id')} {t.get('title')}: FAILED {exc}", file=sys.stderr)
                continue

            say(analyze_mod.format_track(ta, limit=args.limit))
            say(f"   [{time.strftime('%H:%M:%S')}] done in {time.time() - t0:.0f}s")
            say()

            if args.write:
                t["analysis"] = ta.to_dict()["metrics"]
                cand_doc["tracks"][tslug] = [c.to_dict() for c in ta.candidates]
                changed = True

        if args.write and changed:
            ledger_mod.save_band_tracks(band, tracks)
            dest = band.dir / "glitch-candidates.yaml"
            header = "\n".join([
                "---",
                f"# {slug} — measured glitch candidates from `forge analyze`.",
                "#",
                "# CANDIDATES, not verdicts. The Glitch Axiom is a human judgement about",
                "# which failures are badges of honour; promote entries into the track's",
                "# glitch_log in tracks.yaml by hand, naming them under the band protocol.",
                "",
            ])
            dest.write_text(
                header + yaml.safe_dump(cand_doc, sort_keys=False, allow_unicode=True, width=100),
                encoding="utf-8",
            )
            say(f"wrote {dest.relative_to(config_mod.REPO_ROOT).as_posix()}")
    say(f"### analyze finished {time.strftime('%Y-%m-%d %H:%M:%S')}")
    log.close()
    return 0


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="forge", description="lyric-forge label toolchain")
    sub = ap.add_subparsers(dest="command", required=True)

    # The three orientation commands. An agent opening this project cold should
    # be able to answer "where is everything", "what should I do", and "what is
    # the process" without reading the source.
    p = sub.add_parser("status", help="where every track sits in the lifecycle")
    p.add_argument("--json", action="store_true", help="structured output")
    p.set_defaults(func=cmd_status)

    p = sub.add_parser("next", help="outstanding decisions, plus a brief proposal")
    p.add_argument("--band", help="limit to one band")
    p.add_argument("--json", action="store_true", help="structured output")
    p.set_defaults(func=cmd_next)

    p = sub.add_parser("stages", help="describe the lifecycle and its gates")
    p.add_argument("--json", action="store_true", help="structured output")
    p.set_defaults(func=cmd_stages)

    p = sub.add_parser("docs", help="generate documentation")
    p.add_argument("kind", choices=["framework", "catalog"])
    p.add_argument("--out", help="destination (e.g. a wiki clone)")
    p.add_argument("--json", action="store_true", help="structured output")
    p.set_defaults(func=cmd_docs)

    p = sub.add_parser("bundle", help="compile a NotebookLM bundle")
    p.add_argument("kind", choices=["fresh", "export"])
    p.add_argument("--band", help="export: limit to one band")
    p.add_argument("--out", help="destination directory")
    p.add_argument("--json", action="store_true", help="structured output")
    p.set_defaults(func=cmd_bundle)

    p = sub.add_parser("infer", help="run a prompt: via the surrounding agent, or an API")
    p.add_argument("--id", required=True, help="prompt id")
    p.add_argument("--mode", choices=["agent", "api"], default="agent")
    p.add_argument("--band", help="band slug")
    p.add_argument("--track", help="track slug")
    p.add_argument("--spark", help="path to a spark file")
    p.add_argument("--lyrics", help="path to lyrics")
    p.add_argument("--vision", help="vision text, for derive-band")
    p.add_argument("--context", help="ad-hoc direction")
    p.add_argument("--provider", choices=["anthropic", "openai", "google"],
                   help="override the configured provider (api mode)")
    p.add_argument("--model", help="override the configured model (api mode)")
    p.add_argument("--out", help="write the result here")
    p.add_argument("--write", action="store_true",
                   help="write to the conventional destination for this output type")
    p.add_argument("--record", action="store_true",
                   help="record prompt/model provenance and stamp the draft stage")
    p.add_argument("--dry-run", action="store_true",
                   help="api mode: show the request that would be sent, send nothing")
    p.add_argument("--json", action="store_true", help="structured output")
    p.set_defaults(func=cmd_infer)

    p = sub.add_parser("ingest-audio", help="file a render against a track and hash it")
    p.add_argument("--band", required=True, help="band slug")
    p.add_argument("--track", required=True, help="track slug")
    p.add_argument("--file", required=True, help="the rendered audio")
    p.add_argument("--artwork", help="cover art for the same track")
    p.add_argument("--replace", action="store_true",
                   help="supersede existing audio, archiving its analysis")
    p.add_argument("--move", action="store_true", help="move rather than copy the source")
    p.add_argument("--analyze", action="store_true", help="measure it immediately")
    p.add_argument("--model", default="large-v3", help="whisper model for --analyze")
    p.add_argument("--json", action="store_true", help="structured output")
    p.set_defaults(func=cmd_ingest_audio)

    p = sub.add_parser("review", help="scan lyrics for issues; mechanical checks computed")
    p.add_argument("--lyrics", help="path to lyrics (any source, need not be ours)")
    p.add_argument("--band", help="band slug — enables burned lists, anchors, register")
    p.add_argument("--track", help="track slug — reads its sheet and its brief")
    p.add_argument("--context", help="ad-hoc direction for this review")
    p.add_argument("--prompt", action="store_true", help="emit the judgement prompt")
    p.add_argument("--record", action="store_true", help="save the review, advance the stage")
    p.add_argument("--json", action="store_true", help="structured output")
    p.set_defaults(func=cmd_review)

    p = sub.add_parser("spark", help="capture raw input and open a tracked song")
    p.add_argument("--text", help="the spark, inline")
    p.add_argument("--file", help="the spark, from a file")
    p.add_argument("--band", help="band slug (omit to see a comparison first)")
    p.add_argument("--title", help="provisional title, if you have one")
    p.add_argument("--id", help="override the generated spark id")
    p.add_argument("--confirm", action="store_true", help="confirm a proposed brief")
    p.add_argument("--track", help="track slug, for --confirm")
    p.add_argument("--json", action="store_true", help="structured output")
    p.set_defaults(func=cmd_spark)

    p = sub.add_parser("adjudicate", help="judge measured glitch candidates")
    p.add_argument("--band", help="band slug (default: all)")
    p.add_argument("--write", action="store_true", help="write/refresh the decision file")
    p.add_argument("--apply", action="store_true", help="write kept candidates to glitch logs")
    p.add_argument("--json", action="store_true", help="structured output")
    p.set_defaults(func=cmd_adjudicate)

    p = sub.add_parser("prompt", help="the prompt library: list, show, lint, render")
    p.add_argument("action", choices=["list", "show", "lint", "render"])
    p.add_argument("--id", help="prompt id, for show/render")
    p.add_argument("--band", help="band slug — fills band, dossier, suite, register slots")
    p.add_argument("--track", help="track slug — fills candidates, verdict (for adjudicate-glitch)")
    p.add_argument("--suite", help="override the proposed suite")
    p.add_argument("--stance", help="override the proposed stance")
    p.add_argument("--bpm", type=int, help="override the proposed tempo")
    p.add_argument("--lyrics", help="path to a lyric file (for review/compile)")
    p.add_argument("--spark", help="path to a spark file")
    p.add_argument("--vision", help="vision text (for derive-band)")
    p.add_argument("--context", help="ad-hoc direction for this run")
    p.add_argument("--json", action="store_true", help="structured output")
    p.set_defaults(func=cmd_prompt)

    p = sub.add_parser("bootstrap", help="seed band ledgers from audio on disk")
    p.set_defaults(func=cmd_bootstrap)

    p = sub.add_parser("reconcile", help="check audio, ledger, and lyric sheets agree")
    p.add_argument("--fast", action="store_true", help="skip ffprobe duration checks")
    p.add_argument("--no-hash", action="store_true", help="skip asset drift checks")
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

    p = sub.add_parser("analyze", help="measure audio: dsp, tempo, key, transcript diff")
    p.add_argument("--band", help="band slug (default: all)")
    p.add_argument("--track", help="single track slug")
    p.add_argument("--model", default="large-v3", help="whisper model (default: large-v3)")
    p.add_argument("--no-asr", action="store_true", help="skip transcription and diff")
    p.add_argument("--limit", type=int, default=8, help="candidates shown per track")
    p.add_argument("--write", action="store_true", help="write metrics + candidate files")
    p.set_defaults(func=cmd_analyze)

    p = sub.add_parser("variety", help="stance/suite/tempo distribution across the catalogue")
    p.add_argument("--strict", action="store_true", help="exit 1 on any warning")
    p.set_defaults(func=cmd_variety)

    p = sub.add_parser("artwork", help="link cover art and report duplicates/palette")
    p.add_argument("--write", action="store_true", help="write artwork paths to the ledger")
    p.add_argument("--no-palette", action="store_true", help="skip palette extraction")
    p.set_defaults(func=cmd_artwork)

    p = sub.add_parser("fingerprint", help="hash audio and artwork into the ledger")
    p.add_argument("--write", action="store_true", help="record hashes")
    p.set_defaults(func=cmd_fingerprint)

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
