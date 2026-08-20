"""Audio probing and canonical decoding.

Why decode at all, when the source is already mp3?

Not for quality — decoding lossy audio to WAV recovers nothing, the artefacts
are baked in at encode time. The reason is *timestamp alignment*. Every analysis
library brings its own mp3 decoder, and mp3 carries encoder delay/padding that
decoders handle differently, so the same event can land tens of milliseconds
apart depending on which tool read the file. Since the whole point of the
analyser is cross-referencing acoustic events against lyric events ("the vocal
chokes at 2:14 on the word 'substance'"), everything must read one canonical PCM
decode produced once, by one decoder.

The 16 kHz mono ASR derivative is resampled from the 48 kHz canonical WAV rather
than from the mp3, for the same reason: two decodes of the same mp3 are not
guaranteed to be sample-aligned, but a resample of one decode is.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

from .config import CACHE_DIR

PCM_CACHE = CACHE_DIR / "pcm"

# Canonical DSP target: native Suno rate, stereo, 32-bit float. Float avoids
# clamping decoder overshoot, which matters because overshoot past 0 dBFS is
# itself a clipping signal we want to measure rather than silently truncate.
DSP_ARGS = ["-ac", "2", "-ar", "48000", "-c:a", "pcm_f32le"]
ASR_ARGS = ["-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le"]


class AudioError(RuntimeError):
    pass


@dataclass(frozen=True)
class Probe:
    path: Path
    duration_s: float
    bit_rate: int | None
    sample_rate: int | None
    channels: int | None
    codec: str | None


def require_ffmpeg() -> None:
    for tool in ("ffmpeg", "ffprobe"):
        if shutil.which(tool) is None:
            raise AudioError(f"{tool} not found on PATH")


def probe(path: Path) -> Probe:
    require_ffmpeg()
    if not path.exists():
        raise AudioError(f"missing audio: {path}")

    def _q(args: list[str]) -> list[str]:
        out = subprocess.run(
            ["ffprobe", "-v", "error", *args, "-of", "csv=p=0", str(path)],
            capture_output=True,
            text=True,
            check=False,
        )
        return [ln for ln in out.stdout.strip().splitlines() if ln.strip()]

    dur = _q(["-show_entries", "format=duration"])
    # Select the audio stream explicitly: Suno mp3s carry an embedded cover-art
    # (mjpeg) stream, which otherwise shows up as a second row and corrupts parsing.
    st = _q(
        [
            "-select_streams",
            "a:0",
            "-show_entries",
            "stream=sample_rate,channels,codec_name,bit_rate",
        ]
    )
    fields = st[0].split(",") if st else []

    def _int(v: str | None) -> int | None:
        try:
            return int(v) if v not in (None, "", "N/A") else None
        except ValueError:
            return None

    duration = float(dur[0]) if dur else 0.0
    codec = fields[0] if len(fields) > 0 and fields[0] else None

    # Fail loudly on a file with nothing in it.
    #
    # This returned duration_s=0.0 and a null codec, which propagated as a
    # *measurement*: ingest recorded duration_s: 0, the declared and measured
    # values then agreed at zero, the hash matched (of empty), and
    # `reconcile --strict` reported a clean catalogue at rc=0 — after the file
    # had overwritten a real master and archived its analysis as superseded.
    #
    # That is the predecessor's "PASS for files that do not exist" reproduced
    # inside the tool built to end it. An absent measurement must never be
    # indistinguishable from a measurement of zero.
    if not codec or duration <= 0.0:
        raise AudioError(
            f"{path.name} has no decodable audio stream "
            f"(codec={codec or 'none'}, duration={duration}s, "
            f"{path.stat().st_size} bytes). Refusing to treat this as audio."
        )

    return Probe(
        path=path,
        duration_s=duration,
        codec=codec,
        sample_rate=_int(fields[1]) if len(fields) > 1 else None,
        channels=_int(fields[2]) if len(fields) > 2 else None,
        bit_rate=_int(fields[3]) if len(fields) > 3 else None,
    )


def _stamp_path(dest: Path) -> Path:
    return dest.with_suffix(dest.suffix + ".stamp.json")


def _is_fresh(src: Path, dest: Path) -> bool:
    stamp = _stamp_path(dest)
    if not (dest.exists() and stamp.exists()):
        return False
    try:
        rec = json.loads(stamp.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    st = src.stat()
    return rec.get("size") == st.st_size and rec.get("mtime") == int(st.st_mtime)


def _write_stamp(src: Path, dest: Path) -> None:
    st = src.stat()
    _stamp_path(dest).write_text(
        json.dumps({"source": str(src), "size": st.st_size, "mtime": int(st.st_mtime)}),
        encoding="utf-8",
    )


def decode(src: Path, band: str, slug: str, kind: str = "dsp", force: bool = False) -> Path:
    """Decode to canonical PCM in the cache, returning the WAV path.

    kind='dsp' -> 48 kHz stereo f32 (measurement)
    kind='asr' -> 16 kHz mono s16, resampled from the dsp decode (transcription)
    """
    require_ffmpeg()
    out_dir = PCM_CACHE / band
    out_dir.mkdir(parents=True, exist_ok=True)

    dsp_dest = out_dir / f"{slug}.dsp.wav"
    if force or not _is_fresh(src, dsp_dest):
        _run_ffmpeg(src, dsp_dest, DSP_ARGS)
        _write_stamp(src, dsp_dest)

    if kind == "dsp":
        return dsp_dest

    if kind != "asr":
        raise AudioError(f"unknown decode kind: {kind}")

    asr_dest = out_dir / f"{slug}.asr.wav"
    if force or not _is_fresh(dsp_dest, asr_dest):
        _run_ffmpeg(dsp_dest, asr_dest, ASR_ARGS)
        _write_stamp(dsp_dest, asr_dest)
    return asr_dest


def _run_ffmpeg(src: Path, dest: Path, args: list[str]) -> None:
    # -vn drops the embedded cover art; without it ffmpeg tries to mux a video
    # stream into a WAV container and fails.
    cmd = ["ffmpeg", "-nostdin", "-y", "-v", "error", "-i", str(src), "-vn", *args, str(dest)]
    res = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if res.returncode != 0:
        raise AudioError(f"ffmpeg failed for {src.name}: {res.stderr.strip()[:400]}")


def find_audio(dirpath: Path) -> list[Path]:
    if not dirpath.exists():
        return []
    return sorted(p for p in dirpath.iterdir() if p.suffix.lower() == ".mp3")
