"""`forge artwork` — link cover art into the ledger and report on it."""

from __future__ import annotations

from . import artwork as art_mod
from . import ledger as ledger_mod
from .config import Config, slugify


def run(cfg: Config, write: bool = False, with_palette: bool = True) -> str:
    lines: list[str] = []
    songs = art_mod.index_songs(cfg, with_palette=with_palette)
    albums = art_mod.index_albums(cfg, with_palette=with_palette)

    lines.append("=" * 78)
    lines.append("ARTWORK")
    lines.append("=" * 78)
    lines.append(
        f"{len(songs)} song covers, {len(albums)} album covers "
        f"in {cfg.artwork_root}"
    )

    linked = 0
    missing: list[str] = []
    claimed: set[str] = set()

    for slug, band in cfg.bands.items():
        tracks = ledger_mod.load_band_tracks(band)
        changed = False
        for t in tracks:
            tslug = t.get("slug") or slugify(t.get("title", ""))
            art = songs.get(tslug)
            if art is None:
                missing.append(f"{slug}/{t.get('title')}")
                continue
            claimed.add(tslug)
            rel = f"songs/{art.path.name}"
            if t.get("artwork") != rel:
                t["artwork"] = rel
                linked += 1
                changed = True
        if changed and write:
            ledger_mod.save_band_tracks(band, tracks)

    orphans = [a for s, a in songs.items() if s not in claimed]

    lines.append("")
    lines.append(f"-- LINKED  {linked} newly linked" + ("" if write else " (dry run)"))
    if missing:
        lines.append("")
        lines.append(f"-- TRACKS WITH NO COVER  ({len(missing)})")
        for m in missing:
            lines.append(f"   {m}")
    if orphans:
        lines.append("")
        lines.append(f"-- COVERS WITH NO TRACK  ({len(orphans)})")
        for a in orphans:
            lines.append(f"   {a.path.name}")

    # --- duplicates ---------------------------------------------------------
    dupes, templates = art_mod.find_duplicates(list(songs.values()))
    lines.append("")
    lines.append(f"-- DUPLICATED ARTWORK  ({len(dupes)})")
    lines.append("   Measured on the central subject area, excluding the shared")
    lines.append("   template furniture. These are the same picture twice.")
    if not dupes:
        lines.append("   none")
    for d in dupes:
        kind = (
            "IDENTICAL FILE"
            if d.exact
            else f"same subject art (centre hamming {d.distance})"
        )
        lines.append(f"   [{kind}]  {d.a.title}  <->  {d.b.title}")

    lines.append("")
    lines.append(f"-- SHARED TEMPLATE  ({len(templates)} pairs)")
    lines.append("   Same layout, different subject art. This is art direction")
    lines.append("   working as intended, not repetition — reported so it is not")
    lines.append("   mistaken for duplication.")
    by_band: dict[str, int] = {}
    for t in templates:
        key = " / ".join(sorted({t.a.title.split()[0], t.b.title.split()[0]}))
        by_band[key] = by_band.get(key, 0) + 1
    lines.append(f"   {len(templates)} pairs across the catalogue")

    # --- resolution ---------------------------------------------------------
    sizes: dict[str, list[str]] = {}
    for a in list(songs.values()) + albums:
        sizes.setdefault(a.size_label, []).append(a.title)
    lines.append("")
    lines.append("-- RESOLUTION")
    for size, titles in sorted(sizes.items(), key=lambda kv: -len(kv[1])):
        lines.append(f"   {size:<12} {len(titles)} images")
        if size != "?" and int(size.split("x")[0]) < 640:
            lines.append(
                f"     ^ below 640px. Fine for a thumbnail, too small for a release "
                f"or a print. Affects: {', '.join(titles[:6])}"
            )

    if with_palette:
        lines.append("")
        lines.append("-- DOMINANT PALETTE (top 3 per album cover)")
        for a in albums:
            swatches = "  ".join(f"{hexv} {share:.0%}" for hexv, share in a.palette[:3])
            lines.append(f"   {a.title[:44]:<44} {swatches}")

    return "\n".join(lines)
