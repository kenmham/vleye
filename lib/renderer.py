"""
renderer.py — FFmpeg assembly of scenes into a final video.

Optionally snaps cuts to beat onsets via librosa.
All video processing is delegated to FFmpeg subprocess calls.
"""

from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path

from lib.scene import Scene


# BEAT DETECTION

def _detect_beats(music_path: str) -> list[float]:
    """Return a sorted list of beat onset timestamps in seconds."""
    import librosa  # type: ignore
    import numpy as np

    y, sr = librosa.load(music_path, mono=True)
    _, beat_frames = librosa.beat.beat_track(y=y, sr=sr)
    return librosa.frames_to_time(beat_frames, sr=sr).tolist()


def _snap_to_beat(timestamp: float, beats: list[float], max_drift: float = 0.5) -> float:
    """
    Return the nearest beat to timestamp, but only if it's within max_drift seconds.
    Otherwise return timestamp unchanged.
    """
    if not beats:
        return timestamp
    nearest = min(beats, key=lambda b: abs(b - timestamp))
    return nearest if abs(nearest - timestamp) <= max_drift else timestamp


# FFMPEG HELPERS

def _build_concat_list(scene_clips: list[Path], list_path: Path) -> None:
    """Write an FFmpeg concat demuxer file."""
    with list_path.open("w") as f:
        for clip in scene_clips:
            f.write(f"file '{clip.resolve()}'\n")


def _trim_scene(
    source_video: str,
    start_ts: float,
    end_ts: float,
    out_path: Path,
) -> None:
    """Extract a scene segment from the source video into out_path."""
    subprocess.run(
        [
            "ffmpeg", "-y",
            "-ss", str(start_ts),
            "-to", str(end_ts),
            "-i", source_video,
            "-c", "copy",
            str(out_path),
        ],
        capture_output=True,
        check=True,
    )


def _concat(list_path: Path, output_path: str, reencode: bool = False) -> None:
    """Concatenate clips listed in list_path into output_path."""
    video_codec = "libx264" if reencode else "copy"
    audio_codec = "aac" if reencode else "copy"
    subprocess.run(
        [
            "ffmpeg", "-y",
            "-f", "concat",
            "-safe", "0",
            "-i", str(list_path),
            "-c:v", video_codec,
            "-c:a", audio_codec,
            output_path,
        ],
        capture_output=True,
        check=True,
    )


def _mix_audio(video_path: str, music_path: str, output_path: str) -> None:
    """Mix music track under the video's original audio and write to output_path."""
    subprocess.run(
        [
            "ffmpeg", "-y",
            "-i", video_path,
            "-i", music_path,
            "-filter_complex",
            "[0:a]volume=1.0[orig];[1:a]volume=0.4[music];[orig][music]amix=inputs=2:duration=first[aout]",
            "-map", "0:v",
            "-map", "[aout]",
            "-c:v", "copy",
            "-c:a", "aac",
            output_path,
        ],
        capture_output=True,
        check=True,
    )


# PUBLIC INTERFACE

def render(
    scenes: list[Scene],
    output_path: str,
    music_path: str | None = None,
) -> None:
    """
    Assemble scenes in order and write the final video to output_path.

    Args:
        scenes:      list of Scene objects in desired edit order
        output_path: destination file path for the rendered video
        music_path:  optional music file; if provided, cuts are snapped to
                     beat onsets and the track is mixed under the original audio
    """
    beats: list[float] = []
    if music_path:
        beats = _detect_beats(music_path)

    with tempfile.TemporaryDirectory() as tmp:
        tmp_dir = Path(tmp)
        clips: list[Path] = []

        for i, scene in enumerate(scenes):
            start_ts = scene.start_ts
            end_ts = scene.end_ts

            if beats:
                start_ts = _snap_to_beat(start_ts, beats)
                end_ts = _snap_to_beat(end_ts, beats)

            # Ensure the snapped window has positive duration.
            if end_ts <= start_ts:
                end_ts = scene.end_ts

            clip_path = tmp_dir / f"clip_{i:03d}.mp4"
            _trim_scene(scene.source_video, start_ts, end_ts, clip_path)
            clips.append(clip_path)

        list_path = tmp_dir / "concat.txt"
        _build_concat_list(clips, list_path)

        if music_path:
            # Concat first, then mix audio so we only run the filter once.
            concat_path = tmp_dir / "concat_raw.mp4"
            _concat(list_path, str(concat_path), reencode=True)
            _mix_audio(str(concat_path), music_path, output_path)
        else:
            _concat(list_path, output_path)
