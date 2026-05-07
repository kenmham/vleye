"""
cli.py — Thin CLI wrapper around lib/orchestrator.py.

Usage:
  vleye analyze <video> [--prompt TEXT] [--model MODEL] <project>
  vleye propose <project> "<prompt>"
  vleye revise <project> "<feedback>"
  vleye render <project> <output> [--music PATH]
  vleye show <project>
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from lib import orchestrator


# COMMANDS

def cmd_analyze(args: argparse.Namespace) -> None:
    state = orchestrator.analyze(
        video_path=args.video,
        project_root=Path(args.project),
        artistic_prompt=args.prompt or "",
        model=args.model,
    )
    print(f"Analyzed {args.video}")
    print(f"Found {len(state.scene_order)} scenes → {args.project}/")


def cmd_propose(args: argparse.Namespace) -> None:
    state = orchestrator.propose(
        project_root=Path(args.project),
        prompt=args.prompt,
    )
    print(f"Proposed edit: {len(state.scene_order)} scenes")
    print(f"Order: {state.scene_order}")
    print(f"\nTrace:\n{state.trace}")


def cmd_revise(args: argparse.Namespace) -> None:
    state = orchestrator.revise(
        project_root=Path(args.project),
        feedback=args.feedback,
    )
    print(f"Revised edit: {len(state.scene_order)} scenes")
    print(f"Order: {state.scene_order}")
    print(f"\nUpdated trace:\n{state.trace}")


def cmd_render(args: argparse.Namespace) -> None:
    orchestrator.render(
        project_root=Path(args.project),
        output_path=args.output,
        music_path=args.music or None,
    )
    print(f"Rendered → {args.output}")


def cmd_show(args: argparse.Namespace) -> None:
    data = orchestrator.show(project_root=Path(args.project))

    print(f"{'#':<4} {'ID':<6} {'Start':>7} {'End':>7}  Description")
    print("-" * 72)
    for s in data["scenes"]:
        desc = s["description"][:50].replace("\n", " ")
        print(f"{s['position']:<4} {s['id']:<6} {s['start_ts']:>7.2f} {s['end_ts']:>7.2f}  {desc}")

    trace = data.get("trace") or {}
    print(f"\n--- Trace ({data['feedback_count']} revision(s)) ---")
    if not trace:
        print("(no trace yet — run propose first)")
    else:
        print(f"thesis: {trace.get('thesis', '')}\n")
        for arrow, justification in (trace.get("transitions") or {}).items():
            print(f"  {arrow}: {justification}")
        print(f"\ncut: {trace.get('cut', [])}")


# PARSER

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="vleye",
        description="Vision-language video editor.",
    )
    sub = p.add_subparsers(dest="command", required=True)

    # analyze
    a = sub.add_parser("analyze", help="Segment and describe a video.")
    a.add_argument("video", help="Path to source video.")
    a.add_argument("project", help="Project directory to create.")
    a.add_argument("--prompt", default="", help="Initial artistic prompt (optional).")
    a.add_argument("--model", default="claude-sonnet-4-6", help="VLM model name.")

    # propose
    pr = sub.add_parser("propose", help="Generate an edit with a reasoning trace.")
    pr.add_argument("project", help="Project directory.")
    pr.add_argument("prompt", help="Artistic/editorial intent.")

    # revise
    rv = sub.add_parser("revise", help="Revise the edit based on feedback.")
    rv.add_argument("project", help="Project directory.")
    rv.add_argument("feedback", help="Feedback on the current edit.")

    # render
    rn = sub.add_parser("render", help="Render the final video.")
    rn.add_argument("project", help="Project directory.")
    rn.add_argument("output", help="Output file path.")
    rn.add_argument("--music", default="", help="Optional music file path.")

    # show
    sh = sub.add_parser("show", help="Print the current scene table and trace.")
    sh.add_argument("project", help="Project directory.")

    return p


# ENTRY POINT

def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    dispatch = {
        "analyze": cmd_analyze,
        "propose": cmd_propose,
        "revise": cmd_revise,
        "render": cmd_render,
        "show": cmd_show,
    }

    try:
        dispatch[args.command](args)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
