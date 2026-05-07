"""
scene.py — Scene data model and folder I/O.
"""

from __future__ import annotations

import json
import shutil
from dataclasses import dataclass, field, asdict
from pathlib import Path

from PIL import Image


# DATA MODEL

@dataclass
class Observation:
    frame_index: int
    timestamp: float
    setting: str
    subjects: list[str]
    action: str
    composition: str
    mood: str


@dataclass
class Scene:
    id: int
    source_video: str
    start_frame: int
    end_frame: int
    start_ts: float
    end_ts: float
    description: str = ""
    transcript_segments: list[dict] = field(default_factory=list)


# OBSERVATION POOL — GLOBAL CACHE KEYED BY (SOURCE_VIDEO, FRAME_INDEX)

_pool: dict[tuple[str, int], Observation] = {}


def get_observation(source_video: str, frame_index: int) -> Observation | None:
    return _pool.get((source_video, frame_index))


def put_observation(obs: Observation) -> None:
    _pool[(obs.source_video if hasattr(obs, "source_video") else "", obs.frame_index)] = obs


def load_pool(observations_path: Path) -> None:
    """Load observations from a .jsonl file into the global pool."""
    if not observations_path.exists():
        return
    with observations_path.open() as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            data = json.loads(line)
            obs = Observation(**data)
            _pool[(data.get("source_video", ""), obs.frame_index)] = obs


# SCENE FOLDER I/O

def save_scene(scene: Scene, observations: list[Observation], thumbnail: Image.Image, root: Path) -> Path:
    """
    Write a scene to disk.

    Layout:
        root/scene_NNN/
            meta.json
            description.txt
            thumbnail.jpg
            observations.jsonl

    Returns the scene folder path.
    """
    folder = root / f"scene_{scene.id:03d}"
    folder.mkdir(parents=True, exist_ok=True)

    meta = {
        "id": scene.id,
        "source_video": scene.source_video,
        "start_frame": scene.start_frame,
        "end_frame": scene.end_frame,
        "start_ts": scene.start_ts,
        "end_ts": scene.end_ts,
    }
    (folder / "meta.json").write_text(json.dumps(meta, indent=2))
    (folder / "description.txt").write_text(scene.description)
    thumbnail.save(folder / "thumbnail.jpg", format="JPEG")

    with (folder / "observations.jsonl").open("w") as f:
        for obs in observations:
            f.write(json.dumps(asdict(obs)) + "\n")

    return folder


def load_scene(folder: Path) -> tuple[Scene, list[Observation]]:
    """
    Load a scene and its observations from a scene folder.

    Returns:
        (Scene, list[Observation])
    """
    meta = json.loads((folder / "meta.json").read_text())
    description = (folder / "description.txt").read_text()

    scene = Scene(
        id=meta["id"],
        source_video=meta["source_video"],
        start_frame=meta["start_frame"],
        end_frame=meta["end_frame"],
        start_ts=meta["start_ts"],
        end_ts=meta["end_ts"],
        description=description,
    )

    observations: list[Observation] = []
    obs_path = folder / "observations.jsonl"
    if obs_path.exists():
        with obs_path.open() as f:
            for line in f:
                line = line.strip()
                if line:
                    observations.append(Observation(**json.loads(line)))

    return scene, observations


def load_all_scenes(project_root: Path) -> list[tuple[Scene, list[Observation]]]:
    """Load all scene folders from a project directory, sorted by scene ID."""
    folders = sorted(project_root.glob("scene_*"), key=lambda p: p.name)
    return [load_scene(f) for f in folders]


def scene_to_dict(scene: Scene) -> dict:
    """Serialize a Scene to a plain dict suitable for driver.reorder / driver.revise."""
    return {
        "id": scene.id,
        "description": scene.description,
        "start_ts": scene.start_ts,
        "end_ts": scene.end_ts,
        "transcript_segments": scene.transcript_segments,
    }
