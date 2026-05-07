"""
segmenter.py — Frame diff, binary search boundary refinement, scene construction.

Three stages:
  1. Sparse phash sampling across the video — pure compute, no LLM.
  2. Binary search on candidate change regions using analyze_frame.
  3. Scene construction: group contiguous observations, emit Scene objects.

Frame extraction uses FFmpeg subprocess calls into a TemporaryDirectory.
No cv2 anywhere.
"""

from __future__ import annotations

import json
import math
import subprocess
import tempfile
from pathlib import Path

import imagehash  # type: ignore
from PIL import Image

from lib import driver, scene as scene_mod
from lib.scene import Observation, Scene


# CONSTANTS

_PHASH_THRESHOLD = 10       # hash distance above which a frame pair is a candidate boundary
_MIN_BOUNDARY_GAP = 0.2     # seconds — stop binary search when window is this narrow
_SAMPLE_K = 4.0             # scaling factor for sparse interval formula
_FRAMES_PER_THUMBNAIL = 1   # frames to extract for the scene thumbnail (middle frame)


# FFMPEG HELPERS

def _probe_duration(video_path: str) -> float:
    """Return video duration in seconds via ffprobe."""
    result = subprocess.run(
        [
            "ffprobe", "-v", "error",
            "-show_entries", "format=duration",
            "-of", "json",
            video_path,
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    return float(json.loads(result.stdout)["format"]["duration"])


def _probe_fps(video_path: str) -> float:
    """Return video frame rate as a float via ffprobe."""
    result = subprocess.run(
        [
            "ffprobe", "-v", "error",
            "-select_streams", "v:0",
            "-show_entries", "stream=r_frame_rate",
            "-of", "json",
            video_path,
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    rate_str = json.loads(result.stdout)["streams"][0]["r_frame_rate"]
    num, den = rate_str.split("/")
    return float(num) / float(den)


def _extract_frame(
    video_path: str,
    timestamp: float,
    out_path: Path,
    max_long_edge: int = 512,
) -> Image.Image:
    """
    Extract a single frame at the given timestamp, resize to max_long_edge on
    the long edge, and write a compressed JPEG. Keeps token cost low for VLM calls.
    """
    subprocess.run(
        [
            "ffmpeg", "-y",
            "-ss", str(timestamp),
            "-i", video_path,
            "-frames:v", "1",
            # Scale so the longest edge is max_long_edge; keep aspect ratio.
            "-vf", f"scale='if(gt(iw,ih),{max_long_edge},-2)':'if(gt(iw,ih),-2,{max_long_edge})'",
            "-q:v", "4",
            str(out_path),
        ],
        capture_output=True,
        check=True,
    )
    return Image.open(out_path).convert("RGB")


# SAMPLING

def _sample_interval(duration: float) -> float:
    """Sparse sampling interval in seconds: clamp(log(duration) * k, 1, 3)."""
    return max(1.0, min(3.0, math.log(max(duration, 1.0)) * _SAMPLE_K))


# OBSERVATION CACHE

def _analyze_cached(
    video_path: str,
    frame_index: int,
    timestamp: float,
    tmp_dir: Path,
) -> Observation:
    """Return cached observation or analyze the frame and cache the result."""
    cached = scene_mod.get_observation(video_path, frame_index)
    if cached is not None:
        return cached

    print(f"    Analyzing frame at {timestamp:.2f}s...")
    frame_path = tmp_dir / f"frame_{frame_index}.jpg"
    image = _extract_frame(video_path, timestamp, frame_path)
    raw = driver.analyze_frame(image)

    obs = Observation(
        frame_index=frame_index,
        timestamp=timestamp,
        setting=raw["setting"],
        subjects=raw["subjects"] if isinstance(raw["subjects"], list) else [raw["subjects"]],
        action=raw["action"],
        composition=raw["composition"],
        mood=raw["mood"],
    )
    # Patch source_video onto the observation so the pool key is correct.
    obs.__dict__["source_video"] = video_path
    scene_mod.put_observation(obs)
    return obs


# SCENE CHANGE DETECTION

def _diverge(obs_a: Observation, obs_b: Observation) -> bool:
    """
    Heuristic: two observations describe different scenes if their settings differ.
    Setting is the most stable descriptor within a scene.
    """
    def _tokens(s: str) -> set[str]:
        return set(s.lower().split())

    a_tokens = _tokens(obs_a.setting)
    b_tokens = _tokens(obs_b.setting)
    if not a_tokens or not b_tokens:
        return False
    overlap = len(a_tokens & b_tokens) / max(len(a_tokens), len(b_tokens))
    return overlap < 0.4


# BINARY SEARCH BOUNDARY REFINEMENT

def _find_boundary(
    video_path: str,
    start_ts: float,
    end_ts: float,
    start_obs: Observation,
    end_obs: Observation,
    fps: float,
    tmp_dir: Path,
) -> float:
    """
    Recursively narrow the boundary between two scenes.
    Returns the timestamp just after the last frame of the earlier scene.
    """
    if end_ts - start_ts < _MIN_BOUNDARY_GAP:
        return end_ts

    mid_ts = (start_ts + end_ts) / 2
    mid_idx = round(mid_ts * fps)
    mid_obs = _analyze_cached(video_path, mid_idx, mid_ts, tmp_dir)

    if _diverge(start_obs, mid_obs):
        # Change is in the first half.
        return _find_boundary(video_path, start_ts, mid_ts, start_obs, mid_obs, fps, tmp_dir)
    else:
        # Change is in the second half.
        return _find_boundary(video_path, mid_ts, end_ts, mid_obs, end_obs, fps, tmp_dir)


# SCENE CONSTRUCTION

def _build_scenes(
    video_path: str,
    boundary_timestamps: list[float],
    duration: float,
    fps: float,
    tmp_dir: Path,
    project_root: Path,
) -> list[Scene]:
    """
    Given a sorted list of boundary timestamps, build Scene objects by sampling
    observations within each segment, synthesizing a description, and saving
    each scene to disk immediately.
    """
    edges = [0.0] + sorted(boundary_timestamps) + [duration]
    scenes: list[Scene] = []

    for i, (start_ts, end_ts) in enumerate(zip(edges, edges[1:])):
        mid_ts = (start_ts + end_ts) / 2
        sample_tss = [start_ts + (end_ts - start_ts) * frac for frac in (0.2, 0.5, 0.8)]

        observations: list[Observation] = []
        for ts in sample_tss:
            idx = round(ts * fps)
            obs = _analyze_cached(video_path, idx, ts, tmp_dir)
            observations.append(obs)

        description = driver.summarize_descriptions(
            [o.__dict__ for o in observations]
        )

        thumb_path = tmp_dir / f"thumb_{i}.jpg"
        thumbnail = _extract_frame(video_path, mid_ts, thumb_path)

        s = Scene(
            id=i,
            source_video=video_path,
            start_frame=round(start_ts * fps),
            end_frame=round(end_ts * fps),
            start_ts=start_ts,
            end_ts=end_ts,
            description=description,
        )

        # Save immediately so progress survives a crash.
        scene_mod.save_scene(s, observations, thumbnail, project_root)
        print(f"    Scene {s.id}: {s.start_ts:.1f}–{s.end_ts:.1f}s — {description[:60]}...")
        scenes.append(s)

    return scenes


# PUBLIC INTERFACE

def segment(
    video_path: str,
    project_root: Path,
    transcript: list[dict] | None = None,
) -> list[Scene]:
    """
    Segment a video into scenes and write scene folders to project_root.

    Args:
        video_path:   path to the source video
        project_root: directory to write scene_NNN/ folders into
        transcript:   optional list of {start, end, text} segments used as
                      a secondary boundary signal (mid-sentence → not a cut)

    Returns:
        List of Scene objects in order.
    """
    duration = _probe_duration(video_path)
    fps = _probe_fps(video_path)
    interval = _sample_interval(duration)

    # Build a set of timestamps where transcript sentences straddle the cut —
    # these are very unlikely to be real scene boundaries.
    mid_sentence_ranges: list[tuple[float, float]] = []
    if transcript:
        for seg in transcript:
            mid_sentence_ranges.append((seg["start"] + 0.1, seg["end"] - 0.1))

    def _is_mid_sentence(ts: float) -> bool:
        return any(s < ts < e for s, e in mid_sentence_ranges)

    print(f"  Duration: {duration:.1f}s  FPS: {fps:.0f}  Sample interval: {interval:.1f}s")

    with tempfile.TemporaryDirectory() as tmp:
        tmp_dir = Path(tmp)

        # STAGE 1: sparse phash sampling
        timestamps = [i * interval for i in range(int(duration / interval) + 1)
                      if i * interval < duration]

        print(f"  Stage 1: extracting {len(timestamps)} sample frames...")
        frames: list[tuple[float, Image.Image]] = []
        for ts in timestamps:
            path = tmp_dir / f"sample_{ts:.3f}.jpg"
            img = _extract_frame(video_path, ts, path)
            frames.append((ts, img))

        # Compute phash differences between consecutive sampled frames.
        candidate_regions: list[tuple[float, float]] = []
        for (ts_a, img_a), (ts_b, img_b) in zip(frames, frames[1:]):
            dist = imagehash.phash(img_a) - imagehash.phash(img_b)
            if dist >= _PHASH_THRESHOLD and not _is_mid_sentence((ts_a + ts_b) / 2):
                candidate_regions.append((ts_a, ts_b))
        print(f"  {len(candidate_regions)} candidate boundary region(s)")

        # STAGE 2: binary search refinement on each candidate region
        print(f"  Stage 2: refining boundaries with VLM...")
        boundary_timestamps: list[float] = []
        for start_ts, end_ts in candidate_regions:
            start_idx = round(start_ts * fps)
            end_idx = round(end_ts * fps)
            start_obs = _analyze_cached(video_path, start_idx, start_ts, tmp_dir)
            end_obs = _analyze_cached(video_path, end_idx, end_ts, tmp_dir)

            if _diverge(start_obs, end_obs):
                boundary = _find_boundary(
                    video_path, start_ts, end_ts, start_obs, end_obs, fps, tmp_dir
                )
                boundary_timestamps.append(boundary)
                print(f"    Boundary confirmed at {boundary:.2f}s")
            else:
                print(f"    Region {start_ts:.1f}–{end_ts:.1f}s: same scene, skipped")

        # STAGE 3: build scenes and write to disk incrementally
        n_scenes = len(boundary_timestamps) + 1
        print(f"  Stage 3: describing {n_scenes} scene(s)...")
        project_root.mkdir(parents=True, exist_ok=True)
        result = _build_scenes(video_path, boundary_timestamps, duration, fps, tmp_dir, project_root)

    return result
