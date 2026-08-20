"""One-off migration: bring committed assets onto the repo naming convention.

The convention, already established by label/bands/<band-slug>/lyrics/<track-slug>.md:

    label/audio/<band-slug>/<track-slug>.mp3
    label/artwork/songs/<track-slug>.jpeg
    label/artwork/albums/<band-slug>/<project-slug>.jpeg
    label/sources/<band-slug>/<name>.md

The assets arrived from Suno and a Google Drive export and diverged six ways:
snake_case directories, a missing separator in `screenlit_panic`, a misspelling in
`the_skalgoritms`, trailing spaces before three extensions, `&` and `!` inside
filenames, and `Warehead` for `Warhead` on an album cover.

Slugs are read from the ledger rather than re-derived, so an audio file, its cover
and its lyric sheet all end up addressable by exactly the same string.

Uses `git mv` so history follows the rename, and argument lists rather than a
shell so `MINE!.mp3` and `The Prompt & The Pulse.mp3` need no quoting.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from framework.forge import config as config_mod  # noqa: E402
from framework.forge import ledger as ledger_mod  # noqa: E402
from framework.forge.config import slugify  # noqa: E402

REPO = config_mod.REPO_ROOT
LABEL = config_mod.LABEL_DIR

# Album cover filename -> (band slug, project slug). Spelled out rather than
# derived: "HITL" would slugify to "hitl" correctly but "Warehead" would carry the
# typo straight through, and a silent typo is exactly what this pass is for.
ALBUMS = {
    "Roots-Futuria-Above-The-Static.jpeg": ("roots-futuria", "above-the-static"),
    "Screen-Lit-Panic-Purist-Protocol.jpeg": ("screen-lit-panic", "purist-protocol"),
    "Silicon-Kings-Systemic-Obsolescence.jpeg": ("silicon-kings", "systemic-obsolescence"),
    "The-Skalgorithms-HITL.jpeg": ("the-skalgorithms", "hitl"),
    "Warehead-The-Copper-Grid.jpeg": ("warhead", "the-copper-grid"),
}

# Harvest sources: old flattened name -> (band slug, clean name).
SOURCES = {
    "roots_futuria--lyrics": ("roots-futuria", "lyric-dump.md"),
    "screenlit_panic--screen-lit-panic-master-vision-v3.md": (
        "screen-lit-panic",
        "master-vision-v3.md",
    ),
    "silicon_kings--context_harvest": ("silicon-kings", "context-harvest.md"),
    "the_skalgoritms--the-skalgorithms-master-vision-v3.md": (
        "the-skalgorithms",
        "master-vision-v3.md",
    ),
    "warhead--context_harvest": ("warhead", "context-harvest.md"),
}


def git_mv(src: Path, dst: Path, dry: bool) -> None:
    rel_src = src.relative_to(REPO)
    rel_dst = dst.relative_to(REPO)
    if rel_src == rel_dst:
        return
    print(f"  {rel_src}\n    -> {rel_dst}")
    if dry:
        return
    dst.parent.mkdir(parents=True, exist_ok=True)
    res = subprocess.run(
        ["git", "mv", "--", str(rel_src), str(rel_dst)],
        cwd=REPO, capture_output=True, text=True, check=False,
    )
    if res.returncode != 0:
        # Untracked files (or a case-only rename) need a plain move.
        src.rename(dst)


def main(dry: bool) -> int:
    cfg = config_mod.load()
    print("=" * 78)
    print("NORMALISE ASSET NAMES" + ("  (dry run)" if dry else ""))
    print("=" * 78)

    # --- audio + song covers, driven by the ledger -------------------------
    for slug, band in cfg.bands.items():
        tracks = ledger_mod.load_band_tracks(band)
        changed = False
        print(f"\n-- {slug}")
        for t in tracks:
            tslug = t.get("slug") or slugify(t.get("title", ""))

            old_audio = t.get("audio")
            if old_audio:
                src = LABEL / "audio" / old_audio
                dst = LABEL / "audio" / slug / f"{tslug}{src.suffix.lower()}"
                if src.exists():
                    git_mv(src, dst, dry)
                    t["audio"] = f"{slug}/{dst.name}"
                    changed = True

            old_art = t.get("artwork")
            if old_art:
                src = LABEL / "artwork" / old_art
                dst = LABEL / "artwork" / "songs" / f"{tslug}{src.suffix.lower()}"
                if src.exists():
                    git_mv(src, dst, dry)
                    t["artwork"] = f"songs/{dst.name}"
                    changed = True

        if changed and not dry:
            ledger_mod.save_band_tracks(band, tracks)

    # --- album covers ------------------------------------------------------
    print("\n-- album covers")
    albums = LABEL / "artwork" / "albums"
    for old, (band_slug, project) in ALBUMS.items():
        src = albums / old
        if src.exists():
            git_mv(src, albums / band_slug / f"{project}.jpeg", dry)

    # --- harvest sources ---------------------------------------------------
    print("\n-- harvest sources")
    sources = LABEL / "sources"
    for old, (band_slug, name) in SOURCES.items():
        src = sources / old
        if src.exists():
            git_mv(src, sources / band_slug / name, dry)

    # --- prune emptied directories ----------------------------------------
    if not dry:
        for d in sorted((LABEL / "audio").iterdir(), reverse=True):
            if d.is_dir() and not any(d.iterdir()):
                d.rmdir()
                print(f"\n  removed empty {d.relative_to(REPO)}")

    print("\nDone." + ("  Re-run with --write to apply." if dry else ""))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(dry="--write" not in sys.argv))
