"""
orchestrator.py — Project state, edit loop, and feedback history.

Manages the lifecycle: analyze → propose → revise → render.
The trace is the central artifact; it persists across revisions.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from pathlib import Path

from lib import driver, renderer, segmenter, stt
from lib.scene import Scene, load_all_scenes, scene_to_dict


# DATA MODEL

@dataclass
class FeedbackEntry:
    feedback: str
    old_order: list[int]
    new_order: list[int]
    trace_snapshot: dict  # structured trace before this revision


@dataclass
class ProjectState:
    source_video: str
    artistic_prompt: str
    model: str
    scene_order: list[int] = field(default_factory=list)
    trace: dict = field(default_factory=dict)  # keys: thesis, transitions, cut
    feedback: list[FeedbackEntry] = field(default_factory=list)


# SERIALIZATION

def _state_to_dict(state: ProjectState) -> dict:
    d = asdict(state)
    d["feedback"] = [asdict(f) for f in state.feedback]
    return d


def _state_from_dict(d: dict) -> ProjectState:
    feedback = [FeedbackEntry(**f) for f in d.pop("feedback", [])]
    # Migrate old string traces to empty dict.
    if isinstance(d.get("trace"), str):
        d["trace"] = {}
    return ProjectState(**d, feedback=feedback)


# I/O

def _orchestrator_path(project_root: Path) -> Path:
    return project_root / "orchestrator.json"


def load(project_root: Path) -> ProjectState:
    path = _orchestrator_path(project_root)
    if not path.exists():
        raise FileNotFoundError(f"No orchestrator.json found in {project_root}")
    return _state_from_dict(json.loads(path.read_text()))


def save(state: ProjectState, project_root: Path) -> None:
    _orchestrator_path(project_root).write_text(
        json.dumps(_state_to_dict(state), indent=2)
    )


# SCENE HELPERS

def _load_scenes_in_order(project_root: Path, order: list[int]) -> list[Scene]:
    """Load all scenes and return them sorted by the given order list."""
    pairs = load_all_scenes(project_root)
    by_id = {s.id: s for s, _ in pairs}
    return [by_id[i] for i in order if i in by_id]


def _all_scenes(project_root: Path) -> list[Scene]:
    return [s for s, _ in load_all_scenes(project_root)]


# PUBLIC INTERFACE

def analyze(
    video_path: str,
    project_root: Path,
    artistic_prompt: str = "",
    model: str = "claude-sonnet-4-6",
) -> ProjectState:
    """
    Segment the video, transcribe audio, and populate scene folders.

    Args:
        video_path:      path to the source video
        project_root:    directory to write scene folders and orchestrator.json
        artistic_prompt: editorial intent (can be set later via propose)
        model:           VLM model name stored in config

    Returns:
        Newly created ProjectState (not yet proposed).
    """
    print("Transcribing audio...")
    transcript = stt.transcribe(video_path)
    print(f"  {len(transcript)} transcript segment(s)")

    transcript_path = project_root / "_transcript.txt"
    project_root.mkdir(parents=True, exist_ok=True)
    with transcript_path.open("w") as f:
        for seg in transcript:
            f.write(f"[{seg['start']:.2f} --> {seg['end']:.2f}]  {seg['text']}\n")
    print(f"  Transcript saved to {transcript_path}")

    print("Segmenting video...")
    scenes = segmenter.segment(video_path, project_root, transcript=transcript)

    # Align transcript to scenes and persist updated scene data.
    scene_dicts = [scene_to_dict(s) for s in scenes]
    stt.align_to_scenes(transcript, scene_dicts)

    print(f"Done. {len(scenes)} scene(s) written to {project_root}/")

    state = ProjectState(
        source_video=video_path,
        artistic_prompt=artistic_prompt,
        model=model,
        scene_order=list(range(len(scenes))),
    )
    save(state, project_root)
    return state


def propose(
    project_root: Path,
    prompt: str,
) -> ProjectState:
    """
    Generate an editorial ordering and reasoning trace.

    Args:
        project_root: project directory (must have been analyzed first)
        prompt:       artistic/editorial intent

    Returns:
        Updated ProjectState with scene_order and trace set.
    """
    state = load(project_root)
    state.artistic_prompt = prompt

    scenes = _all_scenes(project_root)
    scene_dicts = [scene_to_dict(s) for s in scenes]

    # Load transcript from the first scene's aligned segments as a flat list.
    transcript: list[dict] = []
    for sd in scene_dicts:
        transcript.extend(sd.get("transcript_segments", []))

    print(f"Proposing edit across {len(scenes)} scene(s)...")
    order, trace = driver.reorder(scene_dicts, prompt, transcript)
    print(f"  Cut: {order}")
    print(f"  Thesis: {trace.get('thesis', '')}")

    state.scene_order = order
    state.trace = trace
    save(state, project_root)
    return state


def revise(
    project_root: Path,
    feedback: str,
) -> ProjectState:
    """
    Revise the current edit in response to user feedback.

    Args:
        project_root: project directory
        feedback:     user's feedback on the current edit

    Returns:
        Updated ProjectState with revised scene_order and trace.
    """
    state = load(project_root)

    if not state.trace:
        raise RuntimeError("No trace found — run propose() before revise().")

    scenes = _all_scenes(project_root)
    scene_dicts = [scene_to_dict(s) for s in scenes]

    old_order = list(state.scene_order)
    print(f"Revising edit (revision #{len(state.feedback) + 1})...")
    new_order, new_trace = driver.revise(state.trace, feedback, scene_dicts)
    print(f"  Cut: {old_order} → {new_order}")
    print(f"  Thesis: {new_trace.get('thesis', '')}")

    state.feedback.append(
        FeedbackEntry(
            feedback=feedback,
            old_order=old_order,
            new_order=new_order,
            trace_snapshot=state.trace,
        )
    )
    state.scene_order = new_order
    state.trace = new_trace
    save(state, project_root)
    return state


def render(
    project_root: Path,
    output_path: str,
    music_path: str | None = None,
) -> None:
    """
    Render the current edit to a video file.

    Args:
        project_root: project directory
        output_path:  destination file path
        music_path:   optional music file for beat-snapped cuts and audio mix
    """
    state = load(project_root)
    scenes = _load_scenes_in_order(project_root, state.scene_order)
    renderer.render(scenes, output_path, music_path=music_path)


def show(project_root: Path) -> dict:
    """
    Return the current scene table and trace as a dict for display.

    Returns:
        {"scenes": [...], "trace": str, "feedback_count": int}
    """
    state = load(project_root)
    scenes = _load_scenes_in_order(project_root, state.scene_order)
    return {
        "scenes": [
            {
                "position": i + 1,
                "id": s.id,
                "start_ts": s.start_ts,
                "end_ts": s.end_ts,
                "description": s.description,
            }
            for i, s in enumerate(scenes)
        ],
        "trace": state.trace,
        "feedback_count": len(state.feedback),
    }
