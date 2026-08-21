"""Audio analysis — measured truth to sit alongside perceptual notes.

Four passes, cheapest first:

  1. DSP        clipping runs, loudness envelope, dropouts
  2. rhythm     global tempo, local tempo drift
  3. tonal      key estimate from chroma
  4. ASR + diff transcript against intended lyrics, word-aligned with timecodes

The fourth is the one that matters. Every glitch in the catalogue was logged by
ear, retroactively, mostly without timecodes — and where timecodes exist they
came from a notebook with no ability to measure time. A word-level diff between
what the sheet says and what the model actually sang produces the same table
automatically, with real timestamps.

Everything here emits CANDIDATES, never verdicts. The Glitch Axiom is a human
judgement about which failures are badges of honour; automating that judgement
would gut the idea. The tool's job is to ensure nothing is missed, not to decide.

On mp3 input: tempo, key and transcription are unaffected by ~190 kbps encoding.
Clipping detection is degraded — mp3 decode overshoot produces false positives —
so clipping is reported with a confidence caveat and weighted toward long runs.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any

from . import audio as audio_mod
from . import lyrics as lyrics_mod

# --- thresholds -------------------------------------------------------------
CLIP_LEVEL = 0.9995          # float32 decode; overshoot above 1.0 is possible
CLIP_MIN_RUN = 4             # consecutive samples before it counts
DROPOUT_DB = -45.0           # frame loudness floor for "nothing here"
DROPOUT_MIN_S = 0.35
TEMPO_DRIFT_PCT = 0.06       # local vs median inter-beat interval
DIFF_MIN_WORDS = 1           # report divergences of at least this many words

# Below this word accuracy the sheet and the master are not the same arrangement,
# and per-word divergences become noise: SequenceMatcher on two genuinely
# different texts emits dozens of enormous replace blocks that look like glitches
# and are not. Report the mismatch once, loudly, and stop.
SHEET_MATCH_FLOOR = 0.62
# Transcript word count as a fraction of the sheet's. Below this the model simply
# did not hear the vocal, and no conclusion about the sheet is available.
ASR_COVERAGE_FLOOR = 0.75
# A glitch is a local event. A divergence longer than this is a structural
# difference between documents, not a vocal choke.
GLITCH_MAX_SPAN = 12

MAJOR_PROFILE = [6.35, 2.23, 3.48, 2.33, 4.38, 4.09, 2.52, 5.19, 2.39, 3.66, 2.29, 2.88]
MINOR_PROFILE = [6.33, 2.68, 3.52, 5.38, 2.60, 3.53, 2.54, 4.75, 3.98, 2.69, 3.34, 3.17]
PITCHES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]


def _fmt_tc(seconds: float) -> str:
    m, s = divmod(max(0.0, seconds), 60)
    return f"{int(m):02d}:{s:05.2f}"


@dataclass
class Candidate:
    type: str
    timecode: str
    seconds: float
    section: str | None = None
    expected: str | None = None
    heard: str | None = None
    detail: str = ""
    confidence: float | None = None

    def to_dict(self) -> dict:
        d: dict[str, Any] = {
            "type": self.type,
            "anchor": {
                "section": self.section,
                "phrase": self.expected,
                "timecode": self.timecode,
            },
            "timecode_verified": True,
            "source": "forge-measured",
            "detail": self.detail,
        }
        if self.heard is not None:
            d["heard"] = self.heard
        if self.confidence is not None:
            d["confidence"] = round(self.confidence, 3)
        return d


# ---------------------------------------------------------------------------
# 1. DSP
# ---------------------------------------------------------------------------
def dsp_pass(wav: Path) -> tuple[dict, list[Candidate]]:
    import numpy as np
    import soundfile as sf

    data, sr = sf.read(str(wav), dtype="float32", always_2d=True)
    mono = data.mean(axis=1)
    n = len(mono)
    peak = float(np.max(np.abs(mono))) if n else 0.0

    # Clipping: runs of samples at or above the ceiling.
    over = np.abs(mono) >= CLIP_LEVEL
    runs: list[tuple[int, int]] = []
    if over.any():
        idx = np.flatnonzero(np.diff(over.astype(np.int8)))
        edges = np.concatenate(([0] if over[0] else [], idx + 1, [n]))
        for i in range(0, len(edges) - 1):
            a, b = int(edges[i]), int(edges[i + 1])
            if over[a] and (b - a) >= CLIP_MIN_RUN:
                runs.append((a, b))
    runs.sort(key=lambda r: r[1] - r[0], reverse=True)

    # Frame loudness for dropout detection.
    hop = int(sr * 0.025)
    frames = max(1, n // hop)
    rms = np.array([
        math.sqrt(float(np.mean(np.square(mono[i * hop : (i + 1) * hop]) + 1e-12)))
        for i in range(frames)
    ])
    db = 20.0 * np.log10(rms + 1e-12)
    median_db = float(np.median(db))

    dropouts: list[tuple[float, float]] = []
    quiet = db < DROPOUT_DB
    start = None
    for i, q in enumerate(quiet):
        if q and start is None:
            start = i
        elif not q and start is not None:
            dur = (i - start) * hop / sr
            if dur >= DROPOUT_MIN_S:
                dropouts.append((start * hop / sr, dur))
            start = None
    if start is not None:
        dur = (len(quiet) - start) * hop / sr
        if dur >= DROPOUT_MIN_S:
            dropouts.append((start * hop / sr, dur))

    cands: list[Candidate] = []
    for a, b in runs[:6]:
        t = a / sr
        samples = b - a
        cands.append(
            Candidate(
                type="clipping",
                timecode=_fmt_tc(t),
                seconds=t,
                detail=(
                    f"{samples} consecutive samples at full scale "
                    f"({samples / sr * 1000:.1f} ms). NOTE: source is mp3 — decoder "
                    f"overshoot can produce false positives; long runs are more "
                    f"trustworthy than short ones."
                ),
                confidence=min(1.0, samples / (sr * 0.01)),
            )
        )
    # Ignore leading/trailing silence, which is not a dropout.
    duration = n / sr
    for t, dur in dropouts:
        if t < 1.0 or t + dur > duration - 1.0:
            continue
        cands.append(
            Candidate(
                type="dropout",
                timecode=_fmt_tc(t),
                seconds=t,
                detail=f"{dur:.2f}s below {DROPOUT_DB:.0f} dB mid-track",
            )
        )

    metrics = {
        "duration_s": round(duration, 3),
        "peak": round(peak, 4),
        "peak_dbfs": round(20 * math.log10(peak + 1e-12), 2),
        "median_frame_dbfs": round(median_db, 2),
        "clipped_runs": len(runs),
        "clipped_samples": int(sum(b - a for a, b in runs)),
        "dropouts": len([d for d in dropouts if 1.0 < d[0] < duration - 1.0]),
    }
    return metrics, cands


# ---------------------------------------------------------------------------
# 2. rhythm
# ---------------------------------------------------------------------------
def load_analysis_signal(wav: Path, sr: int = 22050):
    """Load and resample once per track.

    rhythm_pass and tonal_pass each used to call librosa.load themselves, which
    meant three full reads of a ~46 MB float32 WAV and two 48k->22.05k resamples
    per track. That, not transcription, dominated runtime: the GPU sat at 0%
    while one CPU core resampled. Loading once cut the per-track cost roughly
    threefold.
    """
    import librosa

    y, out_sr = librosa.load(str(wav), sr=sr, mono=True)
    return y, out_sr


def rhythm_pass(
    wav: Path,
    seed_bpm: float | None,
    signal: tuple | None = None,
    declared_bpm: float | None = None,
) -> tuple[dict, list[Candidate]]:
    """Measure tempo, and compare it against a declaration ONLY if there is one.

    seed_bpm and declared_bpm are different things and used to be the same
    argument. A band's nominal tempo is a legitimate prior for the beat tracker,
    but it is not a declaration about a track — so computing an error against it
    produced lines like "21.4% off" for a song that never declared a tempo at all.
    That is a miss reported against a default nobody aimed at, which is the same
    fabrication this module exists to prevent, wearing a percentage sign.

    Where there is no declaration: no relation, no error, tempo_locked is None
    rather than False. None means "not assessed"; False would claim the comparison
    ran and failed.
    """
    import librosa
    import numpy as np

    y, sr = signal if signal is not None else load_analysis_signal(wav)
    onset = librosa.onset.onset_strength(y=y, sr=sr)

    # Seed the tracker with the declared tempo when we have one. Unseeded beat
    # tracking on fast D-beat locks onto the wrong metrical level routinely —
    # Confident Ignorance at a declared 170 tracked to 112, which is neither 170
    # nor its half. An unseeded global tempo is not usable as evidence here, and
    # worse, a mis-locked grid makes every inter-beat interval look like drift.
    kwargs: dict[str, Any] = {"onset_envelope": onset, "sr": sr, "units": "time"}
    if seed_bpm:
        kwargs["start_bpm"] = float(seed_bpm)
    tempo, beats = librosa.beat.beat_track(**kwargs)
    tempo = float(np.atleast_1d(tempo)[0])

    metrics: dict[str, Any] = {
        "detected_bpm": round(tempo, 1),
        "beats": int(len(beats)),
        "seeded": bool(seed_bpm),
        "seed_bpm": round(float(seed_bpm), 1) if seed_bpm else None,
    }
    cands: list[Candidate] = []

    tempo_locked = False
    if declared_bpm:  # a real declaration, never the band nominal
        # Half/double-time detection is a reporting artefact, not a disagreement —
        # D-beat at 170 is routinely reported at 85.
        ratios = {
            "match": abs(tempo - declared_bpm) / declared_bpm,
            "half": abs(tempo * 2 - declared_bpm) / declared_bpm,
            "double": abs(tempo / 2 - declared_bpm) / declared_bpm,
        }
        best = min(ratios, key=ratios.get)
        metrics["declared_bpm"] = declared_bpm
        metrics["tempo_relation"] = best
        metrics["tempo_error_pct"] = round(ratios[best] * 100, 1)
        tempo_locked = ratios[best] < 0.06
        metrics["tempo_locked"] = tempo_locked
    else:
        metrics["declared_bpm"] = None
        metrics["tempo_relation"] = None
        metrics["tempo_error_pct"] = None
        metrics["tempo_locked"] = None
        metrics["note"] = (
            "no declared BPM for this track; the detected value stands on its own "
            "and is not compared against anything. A band nominal is a seeding "
            "prior, not a declaration."
        )

    if len(beats) > 8:
        ibi = np.diff(beats)
        med = float(np.median(ibi))
        dev = np.abs(ibi - med) / med
        metrics["ibi_median_s"] = round(med, 4)
        metrics["ibi_stdev_s"] = round(float(np.std(ibi)), 4)
        metrics["ibi_cv"] = round(float(np.std(ibi) / (med + 1e-12)), 4)

        # Only emit drift candidates when the grid is trustworthy. On a mis-locked
        # grid these are beat-tracker artefacts, and reporting them as tempo drift
        # would be exactly the invented-timecode problem this module exists to fix.
        if tempo_locked:
            duration = float(len(y)) / sr
            order = np.argsort(dev)[::-1]
            emitted = 0
            for i in order:
                if dev[i] < TEMPO_DRIFT_PCT or emitted >= 4:
                    break
                t = float(beats[i])
                # Beat tracking is unreliable in the first and last couple of
                # seconds — count-ins, feedback swells and fade-outs all read as
                # enormous local deviation. Those are not performance drift.
                if t < 2.0 or t > duration - 2.0:
                    continue
                emitted += 1
                local = 60.0 / float(ibi[i]) if ibi[i] > 0 else 0.0
                cands.append(
                    Candidate(
                        type="tempo-drift",
                        timecode=_fmt_tc(t),
                        seconds=t,
                        detail=(
                            f"inter-beat interval {dev[i] * 100:.1f}% off median "
                            f"(local {local:.0f} BPM vs {60.0 / med:.0f} BPM)"
                        ),
                        confidence=float(min(1.0, dev[i] / 0.25)),
                    )
                )
        else:
            metrics["drift_suppressed"] = (
                "beat grid did not lock to the declared tempo; local deviations are "
                "tracker artefacts and are not reported"
            )
    return metrics, cands


# ---------------------------------------------------------------------------
# 3. tonal
# ---------------------------------------------------------------------------
def tonal_pass(wav: Path, signal: tuple | None = None) -> dict:
    import librosa
    import numpy as np

    y, sr = signal if signal is not None else load_analysis_signal(wav)
    chroma = librosa.feature.chroma_cqt(y=y, sr=sr)
    profile = chroma.mean(axis=1)
    profile = profile / (profile.sum() + 1e-12)

    def corr(a: list[float], b) -> float:
        a_arr = np.array(a, dtype=float)
        a_arr = (a_arr - a_arr.mean()) / (a_arr.std() + 1e-12)
        b_arr = (b - b.mean()) / (b.std() + 1e-12)
        return float(np.dot(a_arr, b_arr) / len(a_arr))

    scores: list[tuple[float, str]] = []
    for i in range(12):
        rot = np.roll(profile, -i)
        scores.append((corr(MAJOR_PROFILE, rot), f"{PITCHES[i]} major"))
        scores.append((corr(MINOR_PROFILE, rot), f"{PITCHES[i]} minor"))
    scores.sort(reverse=True)
    best, runner = scores[0], scores[1]
    return {
        "detected_key": best[1],
        "key_confidence": round(float(best[0]), 3),
        "key_runner_up": runner[1],
        "key_margin": round(float(best[0] - runner[0]), 3),
    }


# ---------------------------------------------------------------------------
# 4. ASR + diff
# ---------------------------------------------------------------------------
_MODEL_CACHE: dict[tuple[str, str], Any] = {}
_CUDA_PRELOADED = False


def _preload_cuda_libs() -> None:
    """Load the pip-installed NVIDIA runtime libraries by absolute path.

    CTranslate2 links cuBLAS and cuDNN at inference time, not at model
    construction — so a model will build happily on CUDA and then fail with
    "libcublas.so.12 is not found" the moment it decodes. The libraries are
    present, just not on the loader path, because pip puts them under
    site-packages/nvidia/*/lib rather than anywhere ld looks.

    Preloading them into the process by absolute path avoids making callers set
    LD_LIBRARY_PATH before launching, which is easy to forget and invisible when
    it silently falls back to CPU.
    """
    global _CUDA_PRELOADED
    if _CUDA_PRELOADED:
        return
    import ctypes
    import sys

    root = Path(sys.prefix) / "lib"
    for libdir in sorted(root.glob("python3*/site-packages/nvidia/*/lib")):
        for so in sorted(libdir.glob("lib*.so*")):
            try:
                ctypes.CDLL(str(so), mode=ctypes.RTLD_GLOBAL)
            except OSError:
                pass  # ordering matters and some fail until a dependency lands
    _CUDA_PRELOADED = True


def get_model(name: str = "large-v3", device: str = "auto"):
    from faster_whisper import WhisperModel

    if device == "auto":
        _preload_cuda_libs()
        try:
            key = (name, "cuda")
            if key not in _MODEL_CACHE:
                _MODEL_CACHE[key] = WhisperModel(name, device="cuda", compute_type="float16")
            return _MODEL_CACHE[key]
        except Exception:
            device = "cpu"
    key = (name, device)
    if key not in _MODEL_CACHE:
        _MODEL_CACHE[key] = WhisperModel(name, device=device, compute_type="int8")
    return _MODEL_CACHE[key]


@dataclass
class Word:
    text: str
    start: float
    end: float
    prob: float = 1.0


def transcribe(wav: Path, model_name: str = "large-v3") -> tuple[list[Word], dict]:
    model = get_model(model_name)
    segments, info = model.transcribe(
        str(wav),
        word_timestamps=True,
        vad_filter=False,          # VAD eats screamed vocals
        beam_size=5,
        condition_on_previous_text=False,  # stops one bad line cascading
    )
    words: list[Word] = []
    for seg in segments:
        for w in seg.words or []:
            words.append(
                Word(
                    text=w.word.strip(),
                    start=float(w.start),
                    end=float(w.end),
                    prob=float(getattr(w, "probability", 1.0) or 1.0),
                )
            )
    meta = {
        "model": model_name,
        "language": getattr(info, "language", None),
        "transcript_words": len(words),
    }
    return words, meta


def _norm(tokens: list[str]) -> list[str]:
    import re

    out = []
    for t in tokens:
        clean = re.sub(r"[^a-z0-9']+", "", t.lower())
        if clean:
            out.append(clean)
    return out


def _section_index(song: lyrics_mod.Song) -> list[tuple[str, int, int]]:
    """(section name, first word index, last word index) over the sung corpus."""
    spans: list[tuple[str, int, int]] = []
    cursor = 0
    for sec in song.lyric_sections:
        words = _norm(" ".join(sec.sung_lines).split())
        if not words:
            continue
        spans.append((sec.name, cursor, cursor + len(words) - 1))
        cursor += len(words)
    return spans


def _section_for(spans: list[tuple[str, int, int]], i: int) -> str | None:
    for name, a, b in spans:
        if a <= i <= b:
            return name
    return None


def diff_pass(words: list[Word], song: lyrics_mod.Song) -> tuple[dict, list[Candidate]]:
    expected_raw = song.plain_text().split()
    expected = _norm(expected_raw)
    heard = _norm([w.text for w in words])
    # Map normalised heard index -> original Word, for timecodes.
    heard_words: list[Word] = []
    for w in words:
        if _norm([w.text]):
            heard_words.append(w)

    spans = _section_index(song)
    sm = SequenceMatcher(None, expected, heard, autojunk=False)
    ops = sm.get_opcodes()
    matched = sum(n2 - n1 for tag, n1, n2, _, _ in ops if tag == "equal")

    cands: list[Candidate] = []
    for tag, i1, i2, j1, j2 in ops:
        if tag == "equal":
            continue
        exp_span = expected[i1:i2]
        got_span = heard[j1:j2]
        if max(len(exp_span), len(got_span)) < DIFF_MIN_WORDS:
            continue
        # Timecode: start of the heard span, or the nearest heard word if the
        # span is a pure deletion.
        if j1 < len(heard_words):
            t = heard_words[j1].start
            probs = [w.prob for w in heard_words[j1:j2]] or [heard_words[j1].prob]
        elif heard_words:
            t = heard_words[-1].end
            probs = [heard_words[-1].prob]
        else:
            continue
        kind = {
            "replace": "lyric-divergence",
            "delete": "dropout",
            "insert": "lyric-insertion",
        }[tag]
        cands.append(
            Candidate(
                type=kind,
                timecode=_fmt_tc(t),
                seconds=t,
                section=_section_for(spans, i1),
                expected=" ".join(exp_span) or None,
                heard=" ".join(got_span) or None,
                detail=f"{tag}: {len(exp_span)} expected / {len(got_span)} heard",
                confidence=1.0 - (sum(probs) / len(probs)),
            )
        )

    accuracy = matched / len(expected) if expected else 0.0

    # Separate local events (candidate glitches) from structural differences
    # (the sheet is not this arrangement).
    glitches = [
        c for c in cands
        if max(len((c.expected or "").split()), len((c.heard or "").split())) <= GLITCH_MAX_SPAN
    ]
    structural = [c for c in cands if c not in glitches]

    # Coverage discriminates the two very different reasons accuracy can be low.
    #
    #   ASR failure     the model heard far fewer words than the sheet contains,
    #                   and what it did hear is gibberish. Screamed 170-200 BPM
    #                   hardcore does this reliably: "comment section police never
    #                   touch the faders" came back as "street hate warriors
    #                   processed craft hours", 130 words heard against 221.
    #   sheet mismatch  the model heard a comparable or greater number of words,
    #                   and they are coherent and on-model — a genuinely different
    #                   arrangement. Deterministic Drift returned whole rhyming
    #                   couplets absent from its sheet.
    #
    # Conflating them would have the tool report a correct sheet as wrong purely
    # because the vocal is fast, which is worse than saying nothing.
    coverage = len(heard) / len(expected) if expected else 0.0

    metrics = {
        "expected_words": len(expected),
        "heard_words": len(heard),
        "matched_words": matched,
        "word_accuracy": round(accuracy, 3),
        "asr_coverage": round(coverage, 3),
        "divergences": len(cands),
        "local_divergences": len(glitches),
        "structural_divergences": len(structural),
    }

    if accuracy < SHEET_MATCH_FLOOR:
        asr_failed = coverage < ASR_COVERAGE_FLOOR
        # Coverage is a proxy for coherence, not a measure of it. Near the
        # threshold the two causes are genuinely indistinguishable by counting —
        # MINE! came back at exactly 0.75 coverage with coherent rhyming material
        # absent from its sheet, while Lazy at 0.59 came back as word salad. Say so
        # rather than letting a borderline number read as a determination.
        borderline = abs(coverage - ASR_COVERAGE_FLOOR) <= 0.10
        metrics["verdict"] = "asr-unreliable" if asr_failed else "sheet-mismatch"
        if borderline:
            metrics["verdict"] += "-borderline"
        metrics["sheet_matches_master"] = None if asr_failed else False

        biggest = max(
            structural or glitches,
            key=lambda c: len((c.heard or "").split()),
            default=None,
        )
        if asr_failed:
            lead = Candidate(
                type="asr-unreliable",
                timecode="00:00.00",
                seconds=0.0,
                detail=(
                    f"transcript covers only {coverage:.0%} of the sheet's word count "
                    f"({len(heard)} heard vs {len(expected)} expected) at "
                    f"{accuracy:.0%} accuracy. The model did not hear most of the "
                    f"vocal, so NOTHING can be concluded about the sheet from this "
                    f"run — neither that it is wrong nor that these are glitches. "
                    f"Expected for fast screamed delivery. Re-run at a lower tempo "
                    f"band or verify by ear."
                    + (
                        " BORDERLINE: coverage is close to the threshold, so this "
                        "could equally be a genuinely different arrangement. Listen "
                        "before concluding either way."
                        if borderline else ""
                    )
                ),
                confidence=1.0 - coverage,
            )
            return metrics, [lead]

        lead = Candidate(
            type="sheet-mismatch",
            timecode=biggest.timecode if biggest else "00:00.00",
            seconds=biggest.seconds if biggest else 0.0,
            detail=(
                f"word accuracy {accuracy:.0%} but transcript coverage {coverage:.0%} "
                f"({matched}/{len(expected)} matched, {len(heard)} heard). The model "
                f"heard plenty — it heard different words. The sheet and the master "
                f"are not the same arrangement. Resolve the document before reading "
                f"any divergence below as a glitch."
                + (
                    " BORDERLINE: coverage is close to the ASR-failure threshold, so "
                    "poor transcription cannot be ruled out. Listen before concluding."
                    if borderline else ""
                )
            ),
            confidence=1.0 - accuracy,
        )
        return metrics, [lead] + structural[:4]

    metrics["verdict"] = "ok"
    metrics["sheet_matches_master"] = True

    # Longest first — those are the real events.
    glitches.sort(
        key=lambda c: -(len((c.expected or "").split()) + len((c.heard or "").split()))
    )
    return metrics, glitches


# ---------------------------------------------------------------------------
# orchestration
# ---------------------------------------------------------------------------
@dataclass
class TrackAnalysis:
    track_id: str
    title: str
    metrics: dict = field(default_factory=dict)
    candidates: list[Candidate] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "metrics": self.metrics,
            "candidate_count": len(self.candidates),
        }


def analyze_track(
    src_mp3: Path,
    band_slug: str,
    slug: str,
    track: dict,
    song: lyrics_mod.Song | None,
    model_name: str = "large-v3",
    do_asr: bool = True,
    fallback_bpm: float | None = None,
) -> TrackAnalysis:
    ta = TrackAnalysis(track_id=track.get("id", "?"), title=track.get("title", slug))

    dsp_wav = audio_mod.decode(src_mp3, band_slug, slug, kind="dsp")
    m, c = dsp_pass(dsp_wav)
    ta.metrics["dsp"] = m
    ta.candidates += c

    # Eleven of twenty-one tracks carry no declared BPM. The band's nominal tempo
    # from band.yaml is a legitimate prior for seeding the beat tracker; record
    # which source was used so a seeded result is never mistaken for a declared one.
    declared = (track.get("suno") or {}).get("declared_bpm")
    seed = declared or fallback_bpm
    signal = load_analysis_signal(dsp_wav)
    m, c = rhythm_pass(dsp_wav, seed, signal=signal, declared_bpm=declared)
    m["bpm_source"] = "track" if declared else ("band_nominal" if fallback_bpm else None)
    ta.metrics["rhythm"] = m
    ta.candidates += c

    ta.metrics["tonal"] = tonal_pass(dsp_wav, signal=signal)
    declared_key = (track.get("suno") or {}).get("declared_key")
    if declared_key:
        ta.metrics["tonal"]["declared_key"] = declared_key
        ta.metrics["tonal"]["key_agrees"] = (
            declared_key.strip().lower() == ta.metrics["tonal"]["detected_key"].lower()
        )

    if do_asr and song is not None:
        asr_wav = audio_mod.decode(src_mp3, band_slug, slug, kind="asr")
        words, meta = transcribe(asr_wav, model_name)
        dm, dc = diff_pass(words, song)
        ta.metrics["asr"] = {**meta, **dm}
        ta.candidates += dc

    return ta


def format_track(ta: TrackAnalysis, limit: int = 8) -> str:
    lines: list[str] = []
    lines.append(f"-- {ta.track_id}  {ta.title}")
    d = ta.metrics.get("dsp", {})
    r = ta.metrics.get("rhythm", {})
    t = ta.metrics.get("tonal", {})
    a = ta.metrics.get("asr", {})

    lines.append(
        f"   dsp    peak {d.get('peak_dbfs')} dBFS | clipped runs {d.get('clipped_runs')} "
        f"| dropouts {d.get('dropouts')}"
    )
    rel = r.get("tempo_relation")
    if r.get("declared_bpm"):
        against = (
            f" vs {r.get('declared_bpm')} declared"
            + (f" ({rel}, {r.get('tempo_error_pct')}% off)" if rel else "")
        )
    else:
        # Say what seeded it, and do not imply a comparison that did not happen.
        seed = r.get("seed_bpm")
        against = f", undeclared (seeded {seed})" if seed else ", undeclared and unseeded"
    lines.append(
        f"   rhythm {r.get('detected_bpm')} BPM detected{against} "
        f"| ibi sd {r.get('ibi_stdev_s')}s"
    )
    agree = t.get("key_agrees")
    agree_txt = "" if agree is None else ("  AGREES" if agree else "  DISAGREES")
    lines.append(
        f"   tonal  {t.get('detected_key')} (margin {t.get('key_margin')}) "
        f"vs {t.get('declared_key', 'undeclared')} declared{agree_txt}"
    )
    if a:
        lines.append(
            f"   asr    {a.get('word_accuracy')} accuracy | "
            f"{a.get('asr_coverage')} coverage "
            f"({a.get('matched_words')}/{a.get('expected_words')} matched, "
            f"{a.get('heard_words')} heard) | verdict: {a.get('verdict')}"
        )
    for c in ta.candidates[:limit]:
        if c.type in ("lyric-divergence", "dropout", "lyric-insertion") and c.expected:
            lines.append(
                f"     [{c.timecode}] {c.type} in {c.section or '?'}: "
                f'expected "{c.expected}" heard "{c.heard}"'
            )
        else:
            lines.append(f"     [{c.timecode}] {c.type}: {c.detail[:90]}")
    if len(ta.candidates) > limit:
        lines.append(f"     ... {len(ta.candidates) - limit} more candidates")
    return "\n".join(lines)
