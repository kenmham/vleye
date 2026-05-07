"""
serve.py — FastAPI backend for the vleye GUI.

Serves the React build from gui/dist/ and exposes a JSON API
that wraps lib/orchestrator.py.

Usage:
  python serve.py --project ./my_project [--port 7842]
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from lib import orchestrator

# PROJECT ROOT — set once at startup via CLI args.
_project_root: Path | None = None


def get_project() -> Path:
    if _project_root is None:
        raise RuntimeError("Project root not set.")
    return _project_root


# APP

app = FastAPI(title="vleye")

GUI_DIST = Path(__file__).parent / "gui" / "dist"


# API MODELS

class ProposeRequest(BaseModel):
    prompt: str


class ReviseRequest(BaseModel):
    feedback: str


class ReorderRequest(BaseModel):
    order: list[int]


class RenderRequest(BaseModel):
    output: str
    music: str = ""


# API ROUTES

@app.get("/api/state")
def get_state() -> dict:
    try:
        return orchestrator.show(get_project())
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))


@app.get("/api/video")
def get_video() -> FileResponse:
    state = orchestrator.load(get_project())
    video_path = Path(state.source_video)
    if not video_path.exists():
        raise HTTPException(status_code=404, detail="Source video not found")
    return FileResponse(str(video_path), media_type="video/mp4")


@app.get("/api/thumbnail/{scene_id}")
def get_thumbnail(scene_id: int) -> FileResponse:
    thumb = get_project() / f"scene_{scene_id:03d}" / "thumbnail.jpg"
    if not thumb.exists():
        raise HTTPException(status_code=404, detail=f"Thumbnail not found for scene {scene_id}")
    return FileResponse(str(thumb), media_type="image/jpeg")


@app.post("/api/propose")
def api_propose(body: ProposeRequest) -> dict:
    try:
        state = orchestrator.propose(get_project(), body.prompt)
        return {"order": state.scene_order, "trace": state.trace}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/revise")
def api_revise(body: ReviseRequest) -> dict:
    try:
        state = orchestrator.revise(get_project(), body.feedback)
        return {"order": state.scene_order, "trace": state.trace}
    except RuntimeError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/reorder")
def api_reorder(body: ReorderRequest) -> dict:
    """Persist a manual drag-to-reorder without invoking the LLM."""
    try:
        state = orchestrator.load(get_project())
        state.scene_order = body.order
        orchestrator.save(state, get_project())
        return {"order": state.scene_order}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/render")
def api_render(body: RenderRequest) -> dict:
    try:
        orchestrator.render(
            get_project(),
            body.output,
            music_path=body.music or None,
        )
        return {"output": body.output}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# STATIC — serve React build; fall back to index.html for client-side routing

if GUI_DIST.exists():
    app.mount("/assets", StaticFiles(directory=str(GUI_DIST / "assets")), name="assets")

@app.get("/{full_path:path}")
def serve_spa(full_path: str) -> FileResponse:
    index = GUI_DIST / "index.html"
    if not index.exists():
        raise HTTPException(status_code=404, detail="GUI not built. Run: cd gui && npm run build")
    return FileResponse(str(index))


# ENTRY POINT

def main() -> None:
    global _project_root

    parser = argparse.ArgumentParser(description="vleye GUI server.")
    parser.add_argument("--project", required=True, help="Path to the vleye project directory.")
    parser.add_argument("--port", type=int, default=7842)
    parser.add_argument("--host", default="127.0.0.1")
    args = parser.parse_args()

    _project_root = Path(args.project).resolve()
    if not _project_root.exists():
        print(f"Error: project directory does not exist: {_project_root}", file=sys.stderr)
        sys.exit(1)

    print(f"Serving project: {_project_root}")
    print(f"Open http://{args.host}:{args.port}")
    uvicorn.run(app, host=args.host, port=args.port)


if __name__ == "__main__":
    main()
