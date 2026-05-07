"""
stt.py — Whisper transcription. Independent of the VLM driver.
"""

from __future__ import annotations


# PUBLIC INTERFACE

def transcribe(audio_path: str) -> list[dict]:
    """
    Transcribe an audio file using faster-whisper.

    Args:
        audio_path: path to audio or video file (ffmpeg-extractable)

    Returns:
        List of segments: [{"start": float, "end": float, "text": str}, ...]
    """
    from faster_whisper import WhisperModel  # type: ignore

    model = WhisperModel("base", device="auto", compute_type="float32")
    segments, _ = model.transcribe(audio_path, beam_size=5)

    return [
        {"start": seg.start, "end": seg.end, "text": seg.text.strip()}
        for seg in segments
    ]


def align_to_scenes(
    transcript: list[dict],
    scenes: list[dict],
) -> list[dict]:
    """
    Attach transcript segments to scenes by timestamp overlap.

    Args:
        transcript: output of transcribe()
        scenes:     list of dicts with keys: id, start_ts, end_ts

    Returns:
        scenes with an added "transcript_segments" key on each.
    """
    for scene in scenes:
        scene["transcript_segments"] = [
            seg for seg in transcript
            if seg["end"] > scene["start_ts"] and seg["start"] < scene["end_ts"]
        ]
    return scenes
