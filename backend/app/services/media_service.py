"""
Media service — extract embedded audio tracks and subtitles from video files.

Uses ffprobe to discover tracks and ffmpeg to extract them.
This is separate from whisper_service (which does Whisper transcription)
and from scanner_service (which discovers external files).
"""

import json
import os
import subprocess
from pathlib import Path
from typing import List, Dict, Any, Optional

from app.core.logging import get_logger

logger = get_logger(__name__)


# ─── Track discovery ──────────────────────────────────────────────────────────

def _run_ffprobe(video_path: str, args: List[str]) -> str:
    """Run ffprobe and return stdout. Raises if ffprobe not available."""
    cmd = ["ffprobe", "-v", "quiet"] + args + [video_path]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    if result.returncode != 0:
        raise RuntimeError(f"ffprobe failed: {result.stderr[:300]}")
    return result.stdout


def check_ffmpeg_available() -> bool:
    """Check if both ffmpeg and ffprobe are available."""
    for tool in ("ffmpeg", "ffprobe"):
        try:
            result = subprocess.run(
                [tool, "-version"],
                capture_output=True, text=True, timeout=5,
            )
            if result.returncode != 0:
                return False
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return False
    return True


def probe_tracks(video_path: str) -> Dict[str, List[Dict[str, Any]]]:
    """
    Discover all tracks in a video file using ffprobe.

    Returns:
        {
            "audio": [
                {"index": 1, "codec": "aac", "language": "eng", "channels": 2, "title": "Stereo", "default": True},
                ...
            ],
            "subtitle": [
                {"index": 3, "codec": "subrip", "language": "eng", "title": "English", "default": True, "forced": False},
                {"index": 4, "codec": "subrip", "language": "fre", "title": "French", "default": False, "forced": False},
                ...
            ],
            "video": [
                {"index": 0, "codec": "h264", "width": 1920, "height": 1080},
                ...
            ],
        }
    """
    if not os.path.isfile(video_path):
        raise FileNotFoundError(f"Video not found: {video_path}")

    try:
        output = _run_ffprobe(video_path, [
            "-print_format", "json",
            "-show_streams",
            "-show_entries",
            "stream=index,codec_type,codec_name,codec_tag_string,"
            "language,title,default,forced,"
            "channels,sample_rate,"
            "width,height",
        ])
    except RuntimeError:
        logger.warning("ffprobe failed, returning empty tracks", path=video_path)
        return {"audio": [], "subtitle": [], "video": []}

    try:
        data = json.loads(output)
    except json.JSONDecodeError:
        return {"audio": [], "subtitle": [], "video": []}

    result: Dict[str, List[Dict[str, Any]]] = {"audio": [], "subtitle": [], "video": []}

    for stream in data.get("streams", []):
        codec_type = stream.get("codec_type", "")
        entry: Dict[str, Any] = {
            "index": stream.get("index", 0),
            "codec": stream.get("codec_name", "unknown"),
            "language": stream.get("language", "und") or "und",
            "title": stream.get("title", "") or "",
            "default": stream.get("default", False),
            "forced": stream.get("forced", False),
        }

        if codec_type == "audio":
            entry["channels"] = stream.get("channels", 2)
            entry["sample_rate"] = stream.get("sample_rate", "")
            result["audio"].append(entry)

        elif codec_type == "subtitle":
            # Map codec names to readable format info
            codec = entry["codec"]
            if codec in ("subrip", "srt", "ass", "ssa", "dvb_subtitle"):
                entry["format"] = _codec_to_format(codec)
                entry["extractable"] = True
            elif codec in ("hdmv_pgs_subtitle", "dvd_subtitle", "dvb_teletext_subtitle"):
                # Image-based subtitles — cannot extract as text
                entry["format"] = _codec_to_format(codec)
                entry["extractable"] = False
            else:
                entry["format"] = codec
                entry["extractable"] = True  # assume extractable
            result["subtitle"].append(entry)

        elif codec_type == "video":
            entry["width"] = stream.get("width", 0)
            entry["height"] = stream.get("height", 0)
            del entry["language"]
            del entry["forced"]
            result["video"].append(entry)

    logger.info(
        "Probed video tracks",
        path=video_path,
        audio=len(result["audio"]),
        subtitles=len(result["subtitle"]),
        video=len(result["video"]),
    )
    return result


def _codec_to_format(codec: str) -> str:
    """Map ffprobe codec name to human-readable subtitle format."""
    mapping = {
        "subrip": "srt",
        "srt": "srt",
        "ass": "ass",
        "ssa": "ass",
        "dvb_subtitle": "srt",
        "hdmv_pgs_subtitle": "pgs",     # image-based
        "dvd_subtitle": "vobsub",        # image-based
        "dvb_teletext_subtitle": "teletext",  # image-based
    }
    return mapping.get(codec, codec)


# ─── Subtitle extraction ────────────────────────────────────────────────────

def extract_subtitle_track(
    video_path: str,
    track_index: int,
    film_id: str,
    language: str = "und",
    output_format: str = "srt",
) -> str:
    """
    Extract a single embedded subtitle track from a video file.

    Args:
        video_path: Path to the MKV/MP4 file.
        track_index: ffprobe stream index of the subtitle track.
        film_id: Film ID for workdir organization.
        language: Language code for the output filename.
        output_format: Output format (srt, ass, vtt).

    Returns:
        Path to the extracted subtitle file.
    """
    from app.services.workdir import extracted_subs_dir
    output_dir = extracted_subs_dir(film_id)

    ext = output_format if output_format in ("srt", "ass", "vtt") else "srt"
    output_path = os.path.join(output_dir, f"extracted.{language}.{ext}")

    cmd = [
        "ffmpeg",
        "-i", video_path,
        "-map", f"0:{track_index}",
        "-f", ext,
        "-y",
        output_path,
    ]

    logger.info("Extracting subtitle track", video=video_path, track=track_index, format=ext)
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)

    if result.returncode != 0:
        # Try with different output format hint
        logger.warning(
            "First extraction attempt failed, trying with stream copy",
            error=result.stderr[:200],
        )
        # Some subtitle codecs need different handling
        output_path = os.path.join(output_dir, f"extracted.{language}.srt")
        cmd = [
            "ffmpeg",
            "-i", video_path,
            "-map", f"0:{track_index}",
            "-y",
            output_path,
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        if result.returncode != 0:
            raise RuntimeError(f"ffmpeg subtitle extraction failed: {result.stderr[:500]}")

    if not os.path.isfile(output_path) or os.path.getsize(output_path) == 0:
        raise RuntimeError(f"Extraction produced empty file: {output_path}")

    logger.info("Subtitle extracted", path=output_path, track=track_index)
    return output_path


def extract_all_subtitles(
    video_path: str,
    film_id: str,
    text_only: bool = True,
) -> List[Dict[str, Any]]:
    """
    Discover and extract all text-based subtitle tracks from a video file.

    Args:
        video_path: Path to the MKV/MP4 file.
        film_id: Film ID for workdir organization.
        text_only: If True, skip image-based tracks (PGS, VobSub).

    Returns:
        List of dicts with: index, language, format, path, title, default, forced.
    """
    tracks = probe_tracks(video_path)
    subtitle_tracks = tracks.get("subtitle", [])
    results: List[Dict[str, Any]] = []

    for track in subtitle_tracks:
        if text_only and not track.get("extractable", True):
            logger.info(
                "Skipping image-based subtitle track",
                index=track["index"],
                codec=track["codec"],
            )
            continue

        lang = track.get("language", "und")
        fmt = track.get("format", "srt")

        try:
            path = extract_subtitle_track(
                video_path=video_path,
                track_index=track["index"],
                film_id=film_id,
                language=lang,
                output_format=fmt if fmt in ("srt", "ass") else "srt",
            )
            results.append({
                "index": track["index"],
                "language": lang,
                "format": fmt,
                "path": path,
                "title": track.get("title", ""),
                "default": track.get("default", False),
                "forced": track.get("forced", False),
            })
        except Exception as e:
            logger.warning(
                "Failed to extract subtitle track",
                index=track["index"],
                language=lang,
                error=str(e),
            )

    logger.info("Extracted subtitle tracks", count=len(results), video=video_path)
    return results


# ─── Audio extraction ─────────────────────────────────────────────────────────

def extract_audio_track(
    video_path: str,
    film_id: str,
    track_index: Optional[int] = None,
    language: str = "und",
    sample_rate: int = 16000,
    channels: int = 1,
) -> str:
    """
    Extract an audio track from a video file as WAV.

    If track_index is None, extracts the default audio track.
    Always converts to 16kHz mono WAV (Whisper format).

    Args:
        video_path: Path to the video file.
        film_id: Film ID for workdir organization.
        track_index: Stream index of the audio track (None = default).
        language: Language code for the filename.
        sample_rate: Output sample rate (default 16000 for Whisper).
        channels: Output channels (default 1 = mono).

    Returns:
        Path to the extracted WAV file.
    """
    from app.services.workdir import audio_dir
    output_dir = audio_dir(film_id)

    ext = "wav"
    output_path = os.path.join(output_dir, f"audio_{language}.{ext}")

    cmd = ["ffmpeg", "-i", video_path]

    # If a specific track is requested, map it
    if track_index is not None:
        cmd.extend(["-map", f"0:{track_index}"])
    # Otherwise ffmpeg picks the default audio track

    cmd.extend([
        "-vn",                        # No video
        "-acodec", "pcm_s16le",      # 16-bit PCM
        "-ar", str(sample_rate),      # Sample rate
        "-ac", str(channels),         # Channels
        "-y",                         # Overwrite
        output_path,
    ])

    logger.info("Extracting audio track", video=video_path, track=track_index, language=language)
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=3600)

    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg audio extraction failed: {result.stderr[:500]}")

    if not os.path.isfile(output_path) or os.path.getsize(output_path) == 0:
        raise RuntimeError(f"Audio extraction produced empty file: {output_path}")

    logger.info("Audio track extracted", path=output_path, track=track_index)
    return output_path


def list_audio_tracks(video_path: str) -> List[Dict[str, Any]]:
    """
    List all audio tracks in a video file.

    Returns:
        List of dicts with: index, codec, language, channels, title, default.
    """
    tracks = probe_tracks(video_path)
    return tracks.get("audio", [])


def list_subtitle_tracks(video_path: str) -> List[Dict[str, Any]]:
    """
    List all subtitle tracks in a video file (without extracting them).

    Returns:
        List of dicts with: index, codec, language, format, title, default, forced, extractable.
    """
    tracks = probe_tracks(video_path)
    return tracks.get("subtitle", [])