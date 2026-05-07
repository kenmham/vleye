"""
driver.py — VLM interface: prompt construction and structured output parsing.

All LLM calls go through lib/llm.py. Nothing here touches an API directly.
"""

import json
import re

from PIL import Image

from lib import llm, prompts


# HELPERS

def _parse_json(text: str) -> dict:
    """Strip markdown fences if present, then parse JSON."""
    text = text.strip()
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    return json.loads(text)  # type: ignore[return-value]


# PUBLIC DRIVER INTERFACE

def analyze_frame(image: Image.Image) -> dict:
    """
    Analyze a single video frame and return a structured observation.

    Returns:
        dict with keys: setting, subjects, action, composition, mood
    """
    raw = llm.vision(image, prompts.ANALYZE_USER, system=prompts.ANALYZE_SYSTEM)
    obs = _parse_json(raw)
    missing = {"setting", "subjects", "action", "composition", "mood"} - obs.keys()
    if missing:
        raise ValueError(f"analyze_frame: missing keys in response: {missing}")
    return obs


def summarize_descriptions(descriptions: list[dict]) -> str:
    """
    Synthesize a list of frame observations into a single scene description.

    Args:
        descriptions: list of observation dicts from analyze_frame

    Returns:
        Plain-text scene description.
    """
    messages = [
        {
            "role": "user",
            "content": f"Observations:\n{json.dumps(descriptions, indent=2)}\n\nWrite the scene description.",
        }
    ]
    return llm.call(messages, system=prompts.SUMMARIZE_SYSTEM, max_tokens=512).strip()


def reorder(
    scenes: list[dict],
    prompt: str,
    transcript: list[dict],
) -> tuple[list[int], dict]:
    """
    Propose an editorial ordering for the given scenes.

    Args:
        scenes:     list of dicts with keys: id, description, transcript_segments
        prompt:     artistic/editorial intent from the user
        transcript: full transcript as list of {start, end, text} dicts

    Returns:
        (scene_order, trace) where trace has keys: thesis, transitions, cut
    """
    payload = json.dumps(
        {"scenes": scenes, "transcript": transcript, "artistic_prompt": prompt},
        indent=2,
    )
    messages = [
        {"role": "user", "content": f"Edit data:\n{payload}\n\nProduce the editorial ordering."}
    ]
    trace = _parse_json(llm.call(messages, system=prompts.REORDER_SYSTEM, max_tokens=2048))
    return trace["cut"], trace


def revise(
    trace: dict,
    feedback: str,
    scenes: list[dict],
) -> tuple[list[int], dict]:
    """
    Revise an existing edit in response to user feedback.

    Args:
        trace:    the current structured trace dict (thesis, transitions, cut)
        feedback: user's feedback targeting one or more transition arrows
        scenes:   list of scene dicts (same shape as reorder input)

    Returns:
        (revised_order, updated_trace)
    """
    payload = json.dumps(
        {"current_trace": trace, "user_feedback": feedback, "scenes": scenes},
        indent=2,
    )
    messages = [
        {"role": "user", "content": f"Edit revision request:\n{payload}\n\nRevise the edit."}
    ]
    updated = _parse_json(llm.call(messages, system=prompts.REVISE_SYSTEM, max_tokens=2048))
    return updated["cut"], updated
