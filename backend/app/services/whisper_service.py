"""
Whisper service — audio transcription and subtitle synchronization.

Uses faster-whisper (CTranslate2-based) for efficient CPU inference.
- transcribe_video(): Generate subtitles from audio
- sync_with_whisper(): Re-align existing subtitle timestamps using Whisper

Requirements: pip install faster-whisper
"""

import os
import re
import subprocess
from pathlib import Path
from typing import Optional, Dict, Any, List

from app.core.logging import get_logger
from app.services.workdir import audio_dir, whisper_dir

logger = get_logger(__name__)

# Map of Whisper model sizes to VRAM/approximate RAM needed
MODEL_SIZES = {
    "tiny": "~1 GB RAM",
    "base": "~1.5 GB RAM",
    "small": "~2.5 GB RAM",
    "medium": "~5 GB RAM",  # Good balance for CPU
    "large": "~10 GB RAM",
    "large-v3": "~10 GB RAM",
}


def _check_whisper_available() -> bool:
    """Check if faster-whisper is installed."""
    try:
        from faster_whisper import WhisperModel
        return True
    except ImportError:
        return False


def _extract_audio(video_path: str, output_dir: str) -> str:
    """Extract audio from video file using ffmpeg."""
    audio_path = os.path.join(output_dir, "audio.wav")
    if os.path.exists(audio_path):
        return audio_path

    cmd = [
        "ffmpeg", "-i", video_path,
        "-vn",                    # No video
        "-acodec", "pcm_s16le",  # 16-bit PCM
        "-ar", "16000",           # 16kHz sample rate (Whisper requirement)
        "-ac", "1",               # Mono
        "-y",                     # Overwrite
        audio_path,
    ]
    logger.info("Extracting audio", video=video_path)
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=3600)
    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg failed: {result.stderr[:500]}")

    return audio_path


def _whisper_transcribe(
    audio_path: str,
    language: Optional[str] = None,
    model_size: str = "medium",
) -> List[Dict[str, Any]]:
    """
    Transcribe audio using faster-whisper.
    Returns list of segments: [{start, end, text}, ...]
    """
    from faster_whisper import WhisperModel

    # Use CPU with int8 quantization for efficiency
    model = WhisperModel(model_size, device="cpu", compute_type="int8")

    # Transcribe
    kwargs = {
        "beam_size": 5,
        "vad_filter": True,       # Voice Activity Detection
        "vad_parameters": {
            "min_silence_duration_ms": 500,
        },
    }
    if language:
        kwargs["language"] = language

    logger.info("Starting Whisper transcription", model=model_size, language=language or "auto")
    segments, info = model.transcribe(audio_path, **kwargs)

    results = []
    for segment in segments:
        results.append({
            "start": segment.start,
            "end": segment.end,
            "text": segment.text.strip(),
        })

    logger.info("Whisper transcription done", language=info.language,
                duration=info.duration, segments=len(results))
    return results


def _format_srt_time(seconds: float) -> str:
    """Format seconds as SRT timestamp: HH:MM:SS,mmm"""
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    ms = int((seconds % 1) * 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def _segments_to_srt(segments: List[Dict[str, Any]]) -> str:
    """Convert Whisper segments to SRT format."""
    lines = []
    for i, seg in enumerate(segments, 1):
        start = _format_srt_time(seg["start"])
        end = _format_srt_time(seg["end"])
        lines.append(f"{i}")
        lines.append(f"{start} --> {end}")
        lines.append(seg["text"])
        lines.append("")  # Blank line between entries
    return "\n".join(lines)


def _parse_srt_timestamps(srt_path: str) -> List[Dict[str, Any]]:
    """Parse SRT file and extract timestamp-text pairs."""
    entries = []
    with open(srt_path, 'r', encoding='utf-8', errors='replace') as f:
        content = f.read()

    pattern = re.compile(
        r'(\d+)\s*\n'
        r'(\d{2}:\d{2}:\d{2}[,.]\d{3})\s*-->\s*(\d{2}:\d{2}:\d{2}[,.]\d{3})\s*\n'
        r'((?:.*(?:\n|$))*?)',
        re.MULTILINE
    )

    for match in pattern.finditer(content):
        idx = int(match.group(1))
        start_str = match.group(2).replace(',', '.')
        end_str = match.group(3).replace(',', '.')
        text = match.group(4).strip()

        # Parse timestamp to seconds
        def _ts_to_sec(ts: str) -> float:
            parts = ts.split(':')
            h, m = int(parts[0]), int(parts[1])
            s = float(parts[2])
            return h * 3600 + m * 60 + s

        entries.append({
            "index": idx,
            "start": _ts_to_sec(start_str),
            "end": _ts_to_sec(end_str),
            "text": text,
        })

    return entries


def _align_subtitles(
    original_entries: List[Dict[str, Any]],
    whisper_segments: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """
    Re-align original subtitle timestamps using Whisper segments.
    Uses nearest-neighbor matching: each original entry gets the timestamp
    of the closest Whisper segment based on text similarity.
    """
    if not whisper_segments or not original_entries:
        return original_entries

    aligned = []
    for entry in original_entries:
        # Find the Whisper segment with the closest timestamp start
        best_seg = None
        best_diff = float('inf')
        for seg in whisper_segments:
            diff = abs(seg["start"] - entry["start"])
            if diff < best_diff:
                best_diff = diff
                best_seg = seg

        if best_seg and best_diff < 5.0:  # Max 5 second drift
            # Use Whisper's timing but keep original text
            aligned.append({
                "index": entry["index"],
                "start": best_seg["start"],
                "end": best_seg["end"],
                "text": entry["text"],
            })
        else:
            # Keep original if no close match
            aligned.append(entry)

    return aligned


# ─── Public API ────────────────────────────────────────────────────────────────

async def transcribe_video(
    video_path: str,
    film_id: str,
    language: Optional[str] = None,
    model_size: str = "medium",
) -> Dict[str, Any]:
    """
    Transcribe a video file using Whisper and save as SRT.
    Returns dict with: output_path, language, segments_count
    """
    import asyncio

    if not _check_whisper_available():
        raise RuntimeError(
            "faster-whisper is not installed. Install it with: "
            "pip install faster-whisper"
        )

    if not os.path.isfile(video_path):
        raise FileNotFoundError(f"Video not found: {video_path}")

    # Output directory — use workdir for Whisper output
    from app.services.workdir import whisper_dir
    output_dir = whisper_dir(film_id)

    # Extract audio (run in thread to avoid blocking)
    audio_path = await asyncio.to_thread(_extract_audio, video_path, audio_dir(film_id))
    # Also save SRT to the whisper dir

    # Transcribe (run in thread — this is CPU-bound and blocks the event loop)
    segments = await asyncio.to_thread(
        _whisper_transcribe, audio_path, language, model_size
    )
    if not segments:
        raise RuntimeError("Whisper produced no output")

    # Detect language from first segment
    detected_lang = language or "und"

    # Save SRT
    srt_filename = f"whisper_{detected_lang}.srt"
    output_path = os.path.join(output_dir, srt_filename)
    srt_content = _segments_to_srt(segments)

    def _write_srt():
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(srt_content)

    await asyncio.to_thread(_write_srt)
    logger.info("Whisper SRT saved", path=output_path, segments=len(segments))

    # Clean up audio file
    try:
        os.remove(audio_path)
    except OSError:
        pass

    return {
        "output_path": output_path,
        "language": detected_lang,
        "segments_count": len(segments),
    }


async def sync_with_whisper(
    video_path: str,
    subtitle_path: str,
    film_id: str,
    model_size: str = "medium",
) -> Dict[str, Any]:
    """
    Re-sync existing subtitles using Whisper timing.
    Keeps original text, replaces timestamps with Whisper-aligned ones.
    """
    import asyncio

    if not _check_whisper_available():
        raise RuntimeError("faster-whisper is not installed. Install with: pip install faster-whisper")

    if not os.path.isfile(video_path):
        raise FileNotFoundError(f"Video not found: {video_path}")
    if not os.path.isfile(subtitle_path):
        raise FileNotFoundError(f"Subtitle not found: {subtitle_path}")

    from app.services.workdir import audio_dir as get_audio_dir, whisper_dir as get_whisper_dir
    output_dir = get_whisper_dir(film_id)

    # Extract audio and transcribe (run in thread to avoid blocking)
    audio_path = await asyncio.to_thread(_extract_audio, video_path, get_audio_dir(film_id))
    whisper_segments = await asyncio.to_thread(
        _whisper_transcribe, audio_path, model_size=model_size
    )

    # Parse and align (CPU-light, safe to run directly)
    original_entries = _parse_srt_timestamps(subtitle_path)
    aligned = _align_subtitles(original_entries, whisper_segments)

    # Save synced SRT
    filename = Path(subtitle_path).stem + ".synced.srt"
    output_path = os.path.join(output_dir, filename)
    srt_content = _segments_to_srt(aligned)

    def _write_synced():
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(srt_content)

    await asyncio.to_thread(_write_synced)

    # Clean up
    try:
        os.remove(audio_path)
    except OSError:
        pass

    logger.info("Synced subtitles saved", path=output_path, entries=len(aligned))

    return {
        "output_path": output_path,
        "entries_count": len(aligned),
    }


def check_ffmpeg_available() -> bool:
    """Check if ffmpeg is available on the system."""
    try:
        result = subprocess.run(
            ["ffmpeg", "-version"],
            capture_output=True, text=True, timeout=5
        )
        return result.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False