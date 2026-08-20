"""The adjudication walker: measured candidates to a signed glitch log.

This is the one HITL loop the tool must never shortcut. Which synthesis failures
are badges of honour is the Glitch Axiom, and it is a human judgement — the
analyser's job was only to make sure none were missed.

It works through a decision file rather than an interactive prompt. The app is
driven from an editor by an agent, and an agent cannot answer a TTY; a file is
also reviewable, diffable, resumable, and sane for eleven tracks at once.

    forge adjudicate --band warhead          # emit / refresh the decision file
    <edit decisions: keep | discard, optionally rename>
    forge adjudicate --band warhead --apply  # write the glitch logs

Re-running is safe: decisions already made are preserved, and only new candidates
arrive as pending.

The gate that matters most is refusal. A track whose analysis says the sheet does
not match the master has divergences that are *document differences*, not
glitches. Adjudicating those would write fiction into the archive, so the walker
declines and says why.
"""

from __future__ import annotations

import datetime
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from . import config as config_mod
from . import ledger as ledger_mod
from . import lifecycle as lc_mod
from .config import Band, Config

# Candidate types that describe a vocal or synthesis event worth judging.
# tempo-drift and clipping are included; they are real measured events, and
# whether a tempo drag counts as "human swing" is precisely the human's call.
ADJUDICABLE_TYPES = {
    "lyric-divergence",
    "lyric-insertion",
    "dropout",
    "clipping",
    "tempo-drift",
    "spectral-anomaly",
    "vocal-choke",
    "vocal-texture",
}

# Types that are findings about the project, not about the performance.
NON_GLITCH_TYPES = {"sheet-mismatch", "asr-unreliable"}

# --- triage -----------------------------------------------------------------
#
# The analyser is tuned to miss nothing, which means it reports plenty that is
# not a glitch. Silicon Kings' Better or Still came back with 49 candidates; nine
# tracks at that rate is 441 decisions, and a human asked for 441 decisions makes
# none. Presenting everything is the same failure as presenting nothing.
#
# So the walker pre-decides the obvious noise as an auto-discard — visible in the
# file, marked with its reason, and overridable — and asks only about candidates
# that could plausibly be a performance event. The distinction is not "small
# difference" versus "large": "god" for "Gaussian" is one word and is the single
# best glitch in the catalogue. It is whether the two texts mean different things.

CONTRACTIONS = {
    "wanna": "want to", "gonna": "going to", "gotta": "got to",
    "cause": "because", "cuz": "because", "coz": "because",
    "til": "until", "till": "until", "aint": "is not",
    "em": "them", "n": "and", "ya": "you", "yeah": "yea",
    "im": "i am", "ive": "i have", "dont": "do not", "cant": "cannot",
    "wont": "will not", "aint": "is not", "gimme": "give me",
    "lemme": "let me", "outta": "out of", "kinda": "kind of",
    "sorta": "sort of", "lotta": "lot of", "gettin": "getting",
}

# Below this, a single-word swap between two function words is transcription
# noise rather than a vocal event.
FUNCTION_WORDS = {
    "a", "an", "the", "and", "or", "but", "of", "to", "in", "on", "at", "for",
    "with", "is", "are", "was", "were", "be", "been", "it", "its", "that",
    "this", "you", "your", "we", "our", "i", "my", "he", "she", "they", "them",
    "from", "as", "so", "if", "then", "than", "not", "no", "do", "does", "did",
}

MAX_PRESENTED_PER_TRACK = 10
MAX_TEMPO_DRIFT_PER_TRACK = 1


def _flatten(text: str | None) -> str:
    """Reduce to comparable form: contractions expanded, everything else stripped.

    This is what separates a synthesis failure from a notation difference.
    "closed-loop" against a transcript's "closed loop" is hyphenation; "want to"
    against "wanna" is a contraction. Neither is the machine failing to sing.
    """
    import re as _re

    if not text:
        return ""
    words = _re.findall(r"[a-z0-9']+", text.lower())
    expanded: list[str] = []
    for w in words:
        w = w.replace("'", "")
        expanded.extend(CONTRACTIONS.get(w, w).split())
    return "".join(expanded)


def _edit_distance(a: str, b: str) -> int:
    if a == b:
        return 0
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[-1]


def triage(candidate: dict) -> tuple[bool, str]:
    """(material, reason). False means auto-discard with the reason recorded."""
    ctype = candidate.get("type")
    anchor = candidate.get("anchor") or {}
    expected = anchor.get("phrase")
    heard = candidate.get("heard")

    if ctype in ("lyric-divergence", "lyric-insertion", "dropout"):
        fe, fh = _flatten(expected), _flatten(heard)

        if fe and fh and fe == fh:
            return False, (
                "notation only — identical once contractions are expanded and "
                "hyphenation removed; the vocal sang the written words"
            )

        ew = (expected or "").split()
        hw = (heard or "").split()
        if len(ew) == 1 and len(hw) == 1:
            a, b = ew[0].lower(), hw[0].lower()
            if a in FUNCTION_WORDS and b in FUNCTION_WORDS:
                return False, "single function word swapped for another — transcription noise"
            if _edit_distance(a, b) <= 1 and min(len(a), len(b)) <= 4:
                return False, "one-character difference on a short word — below the noise floor"

        if not fe and not fh:
            return False, "no text on either side; nothing to judge"

    if ctype == "clipping":
        conf = candidate.get("confidence") or 0
        if conf < 0.25:
            return False, (
                "brief full-scale run on an mp3 source — most likely decoder "
                "overshoot rather than a clipped master"
            )

    return True, ""


def _materiality(candidate: dict) -> float:
    """Rank material candidates so the important ones are seen first."""
    anchor = candidate.get("anchor") or {}
    expected = anchor.get("phrase") or ""
    heard = candidate.get("heard") or ""
    span = max(len(expected.split()), len(heard.split()))
    fe, fh = _flatten(expected), _flatten(heard)
    # A near-homophone that means something else is the interesting case:
    # "god" for "Gaussian", "prize" for "pride". Reward sound-alike, meaning-differ.
    divergence = _edit_distance(fe, fh) / max(1, max(len(fe), len(fh)))
    sound_alike = 1.0 - min(1.0, divergence)
    type_weight = {
        "dropout": 2.0,
        "vocal-choke": 2.0,
        "lyric-divergence": 1.5,
        "lyric-insertion": 1.2,
        "clipping": 1.0,
        "spectral-anomaly": 0.9,
        "tempo-drift": 0.5,
    }.get(candidate.get("type"), 1.0)
    return type_weight * (span + 2.0 * sound_alike)


def candidates_path(band: Band) -> Path:
    return band.dir / "glitch-candidates.yaml"


def decisions_path(band: Band) -> Path:
    return band.dir / "adjudication.yaml"


@dataclass
class TrackGate:
    slug: str
    track_id: str
    title: str
    asr_verdict: str
    adjudicable: bool
    reason: str = ""
    unverified: bool = False
    candidates: list[dict] = field(default_factory=list)


def _gate(track: dict, raw_candidates: list[dict]) -> TrackGate:
    analysis = track.get("analysis") or {}
    verdict = ((analysis.get("asr") or {}).get("verdict")) or "unknown"
    g = TrackGate(
        slug=track.get("slug") or "",
        track_id=track.get("id") or "?",
        title=track.get("title") or "",
        asr_verdict=verdict,
        adjudicable=True,
    )

    if verdict.startswith("sheet-mismatch"):
        g.adjudicable = False
        g.reason = (
            "Analysis says the lyric sheet and the master are different "
            "arrangements. The divergences measured here are differences between "
            "two documents, not synthesis failures — adjudicating them would "
            "record fiction in the glitch log. Resolve the sheet first, re-run "
            "analyze, then adjudicate."
        )
        return g

    if verdict.startswith("asr-unreliable"):
        g.unverified = True
        g.reason = (
            "Transcription did not hear enough of the vocal to conclude anything. "
            "Candidates below are unverified: judge them by ear or leave them "
            "pending. Keeping one on this evidence alone would be a guess."
        )

    pool = [c for c in raw_candidates if c.get("type") in ADJUDICABLE_TYPES]

    material: list[dict] = []
    for c in pool:
        ok, reason = triage(c)
        c = dict(c)
        c["_material"] = ok
        c["_triage_reason"] = reason
        material.append(c)

    keepers = [c for c in material if c["_material"]]
    keepers.sort(key=_materiality, reverse=True)

    # A chorus repeats, so its glitch repeats. "analog" heard as "and a lot of"
    # at 01:50 and again at 01:55 is one judgement, not two — collapse identical
    # expected/heard pairs and carry the other timecodes along as evidence.
    grouped: list[dict] = []
    seen: dict[tuple[str, str], dict] = {}
    for c in keepers:
        anchor = c.get("anchor") or {}
        key = (_flatten(anchor.get("phrase")), _flatten(c.get("heard")))
        if key in seen and any(key):
            primary = seen[key]
            primary.setdefault("_also_at", []).append(anchor.get("timecode"))
            continue
        seen[key] = c
        grouped.append(c)
    keepers = grouped

    # Tempo drift is real but rarely the interesting event, and four per track
    # crowds out everything else. Keep the worst, auto-discard the rest.
    drift_seen = 0
    for c in keepers:
        if c.get("type") == "tempo-drift":
            drift_seen += 1
            if drift_seen > MAX_TEMPO_DRIFT_PER_TRACK:
                c["_material"] = False
                c["_triage_reason"] = (
                    "further tempo deviation on a track that already has one "
                    "flagged; kept in the analysis, not queued for judgement"
                )

    keepers = [c for c in keepers if c["_material"]]
    for c in keepers[MAX_PRESENTED_PER_TRACK:]:
        c["_material"] = False
        c["_triage_reason"] = (
            f"beyond the {MAX_PRESENTED_PER_TRACK} most material candidates on "
            f"this track; flip to keep if you disagree with the ranking"
        )

    # Material first, in rank order, then the auto-discards for the record.
    g.candidates = [c for c in keepers if c["_material"]] + [
        c for c in material if not c["_material"]
    ]
    return g


def _propose_name(candidate: dict, protocol: str) -> str:
    """The band's protocol name is the label. That is not a limitation — a
    protocol is a single reframing per act, and every existing hand-written entry
    in the catalogue uses exactly this. The human can qualify it."""
    return protocol or "unnamed"


def _band_protocol(cfg: Config, slug: str) -> tuple[str, str]:
    spec = yaml.safe_load(
        cfg.bands[slug].band_file.read_text(encoding="utf-8")
    ) if cfg.bands[slug].band_file.exists() else {}
    gp = (spec or {}).get("glitch_protocol") or {}
    return gp.get("name", ""), str(gp.get("reading", "")).strip()


def build_decisions(cfg: Config, slug: str) -> dict[str, Any]:
    """Emit or refresh the decision file, preserving decisions already made."""
    band = cfg.bands[slug]
    protocol, reading = _band_protocol(cfg, slug)

    raw = {}
    cpath = candidates_path(band)
    if cpath.exists():
        raw = (yaml.safe_load(cpath.read_text(encoding="utf-8")) or {}).get("tracks") or {}

    existing: dict[str, Any] = {}
    dpath = decisions_path(band)
    if dpath.exists():
        prior = yaml.safe_load(dpath.read_text(encoding="utf-8")) or {}
        existing = prior.get("tracks") or {}

    doc: dict[str, Any] = {
        "band": slug,
        "glitch_protocol": protocol,
        "protocol_reading": reading,
        "refreshed": datetime.date.today().isoformat(),
        "tracks": {},
    }

    for t in ledger_mod.load_band_tracks(band):
        tslug = t.get("slug")
        if not tslug:
            continue
        gate = _gate(t, raw.get(tslug) or [])
        if not gate.candidates and gate.adjudicable:
            continue

        prior_track = existing.get(tslug) or {}
        prior_by_key = {
            _key(c): c for c in (prior_track.get("candidates") or [])
        }

        entry: dict[str, Any] = {
            "track_id": gate.track_id,
            "title": gate.title,
            "asr_verdict": gate.asr_verdict,
            "adjudicable": gate.adjudicable,
        }
        if gate.reason:
            entry["reason"] = gate.reason
        if gate.unverified:
            entry["evidence_quality"] = "unverified"

        rows: list[dict[str, Any]] = []
        for c in gate.candidates:
            anchor = c.get("anchor") or {}
            row = {
                "type": c.get("type"),
                "timecode": anchor.get("timecode"),
                "section": anchor.get("section"),
                "expected": anchor.get("phrase"),
                "heard": c.get("heard"),
                "confidence": c.get("confidence"),
                "detail": c.get("detail"),
                "also_at": c.get("_also_at") or None,
                "proposed_name": _propose_name(c, protocol),
                "decision": "pending" if c.get("_material", True) else "discard",
                "name": None,
                "note": None,
            }
            if not c.get("_material", True):
                # Pre-decided, not hidden. Recorded with its reason so the
                # judgement stays auditable and can be overridden.
                row["auto"] = True
                row["auto_reason"] = c.get("_triage_reason", "")
            prior_row = prior_by_key.get(_key(c))
            if prior_row:
                for f in ("decision", "name", "note"):
                    if prior_row.get(f) not in (None, "", "pending"):
                        row[f] = prior_row[f]
            rows.append(row)

        entry["candidates"] = rows
        doc["tracks"][tslug] = entry

    return doc


def _key(candidate: dict) -> str:
    """Stable identity for a candidate across re-runs."""
    anchor = candidate.get("anchor") or candidate
    return "|".join(
        str(x) for x in (
            candidate.get("type"),
            anchor.get("timecode"),
            anchor.get("phrase") or anchor.get("section"),
        )
    )


def write_decisions(cfg: Config, slug: str, doc: dict) -> Path:
    dest = decisions_path(cfg.bands[slug])
    header = "\n".join([
        "---",
        f"# {slug} — glitch adjudication.",
        "#",
        "# Set `decision:` to keep or discard on each candidate. Optionally set",
        "# `name:` to override the proposed protocol name, and `note:` to record",
        "# why. Then run: forge adjudicate --band " + slug + " --apply",
        "#",
        "# Re-running without --apply preserves every decision already made and",
        "# adds only new candidates as pending.",
        "",
    ])
    dest.write_text(
        header + yaml.safe_dump(doc, sort_keys=False, allow_unicode=True, width=100),
        encoding="utf-8",
    )
    return dest


def apply_decisions(cfg: Config, slug: str) -> dict[str, Any]:
    """Write kept candidates into each track's glitch_log and stamp the stage."""
    band = cfg.bands[slug]
    dpath = decisions_path(band)
    if not dpath.exists():
        raise FileNotFoundError(
            f"no decision file at {dpath.relative_to(config_mod.REPO_ROOT)}. "
            f"Run `forge adjudicate --band {slug}` first."
        )
    doc = yaml.safe_load(dpath.read_text(encoding="utf-8")) or {}
    protocol = doc.get("glitch_protocol") or ""
    tracks_doc = doc.get("tracks") or {}

    tracks = ledger_mod.load_band_tracks(band)
    by_slug = {t.get("slug"): t for t in tracks}

    result = {
        "band": slug,
        "kept": 0,
        "discarded": 0,
        "pending": 0,
        "refused": [],
        "stamped": [],
    }

    for tslug, entry in tracks_doc.items():
        track = by_slug.get(tslug)
        if track is None:
            continue
        if not entry.get("adjudicable", True):
            result["refused"].append(
                {"track": tslug, "reason": entry.get("reason", "")}
            )
            continue

        rows = entry.get("candidates") or []
        pending = [r for r in rows if r.get("decision") == "pending"]
        if pending:
            result["pending"] += len(pending)
            # Partial adjudication is not adjudication. Leaving the stage
            # unstamped keeps the track visible in `status` instead of quietly
            # looking finished with half its candidates unjudged.
            continue

        log = list(track.get("glitch_log") or [])
        for r in rows:
            if r.get("decision") != "keep":
                result["discarded"] += 1
                continue
            log.append(
                {
                    "protocol": r.get("name") or r.get("proposed_name") or protocol,
                    "type": r.get("type"),
                    "anchor": {
                        "section": r.get("section"),
                        "phrase": r.get("expected"),
                        "timecode": r.get("timecode"),
                    },
                    "timecode_verified": True,
                    "source": "forge-measured",
                    "description": _describe(r),
                    "preservation": r.get("note") or "Kept in the mix.",
                    "preserved": True,
                    **(
                        {"evidence_quality": "unverified"}
                        if entry.get("evidence_quality") == "unverified"
                        else {}
                    ),
                }
            )
            result["kept"] += 1

        track["glitch_log"] = log
        lc_mod.stamp(
            track,
            "adjudicated",
            by="forge adjudicate --apply",
            note=f"{len([r for r in rows if r.get('decision') == 'keep'])} of "
                 f"{len(rows)} measured candidates kept",
        )
        result["stamped"].append(tslug)

    ledger_mod.save_band_tracks(band, tracks)
    return result


def _describe(row: dict) -> str:
    exp, heard = row.get("expected"), row.get("heard")
    if exp and heard:
        return f'Expected "{exp}", heard "{heard}".'
    if row.get("detail"):
        return str(row["detail"]).split(". NOTE:")[0].strip()
    return f"{row.get('type')} at {row.get('timecode')}."


def format_decisions(doc: dict) -> str:
    lines = ["=" * 78, f"ADJUDICATION  {doc.get('band')}", "=" * 78]
    protocol = doc.get("glitch_protocol")
    if protocol:
        lines.append(f"protocol: {protocol}")
    tracks = doc.get("tracks") or {}
    if not tracks:
        lines.append("")
        lines.append("No candidates. Nothing to adjudicate.")
        return "\n".join(lines)

    refused = {k: v for k, v in tracks.items() if not v.get("adjudicable", True)}
    open_tracks = {k: v for k, v in tracks.items() if v.get("adjudicable", True)}

    for tslug, entry in open_tracks.items():
        rows = entry.get("candidates") or []
        asked = [r for r in rows if not r.get("auto")]
        auto = [r for r in rows if r.get("auto")]
        pending = sum(1 for r in asked if r.get("decision") == "pending")
        lines.append("")
        lines.append(
            f"-- {entry['track_id']} {entry['title']}  "
            f"({pending} to judge, {len(auto)} auto-discarded of {len(rows)})"
        )
        if entry.get("evidence_quality") == "unverified":
            lines.append(f"   !! {entry.get('reason', '')}")
        for r in asked:
            mark = {"keep": "+", "discard": "-", "pending": "?"}.get(r.get("decision"), "?")
            head = f"   {mark} [{r.get('timecode')}] {r.get('type')}"
            if r.get("section"):
                head += f" in {r['section']}"
            lines.append(head)
            if r.get("expected"):
                lines.append(f'       expected "{str(r["expected"])[:70]}"')
            if r.get("heard"):
                lines.append(f'       heard    "{str(r["heard"])[:70]}"')
            if r.get("also_at"):
                lines.append(
                    f"       recurs at {', '.join(str(t) for t in r['also_at'])}"
                )

    if refused:
        lines.append("")
        lines.append(f"-- REFUSED  ({len(refused)})")
        for tslug, entry in refused.items():
            lines.append(f"   {entry['track_id']} {entry['title']}  [{entry['asr_verdict']}]")
            lines.append(f"     {entry.get('reason','')}")

    return "\n".join(lines)
