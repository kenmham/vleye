# Provider switch — change this string to swap backends.
# Options: "anthropic" | "openai" | "google"
PROVIDER = "anthropic"

MODEL = "claude-sonnet-4-6"

import base64
import io
import os
from pathlib import Path

from dotenv import load_dotenv
from PIL import Image

load_dotenv(Path(__file__).parent.parent / ".env")

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")


# INTERNAL HELPERS

def _image_to_b64(image: Image.Image) -> str:
    buf = io.BytesIO()
    image.save(buf, format="JPEG")
    return base64.b64encode(buf.getvalue()).decode()


# ANTHROPIC

def _call_anthropic(messages: list[dict], system: str, max_tokens: int) -> str:
    import anthropic  # type: ignore

    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    response = client.messages.create(
        model=MODEL,
        system=system,
        messages=messages,  # type: ignore[arg-type]
        max_tokens=max_tokens,
    )
    block = response.content[0]
    if block.type != "text":
        raise ValueError(f"Expected text block, got {block.type!r}")
    return block.text


def _vision_anthropic(image: Image.Image, prompt: str, system: str, max_tokens: int) -> str:
    import anthropic  # type: ignore

    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    kwargs: dict = dict(
        model=MODEL,
        max_tokens=max_tokens,
        messages=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": "image/jpeg",
                            "data": _image_to_b64(image),
                        },
                    },
                    {"type": "text", "text": prompt},
                ],
            }
        ],  # type: ignore[arg-type]
    )
    if system:
        kwargs["system"] = system
    response = client.messages.create(**kwargs)
    block = response.content[0]
    if block.type != "text":
        raise ValueError(f"Expected text block, got {block.type!r}")
    return block.text


# OPENAI (SCAFFOLD)

def _call_openai(_messages: list[dict], _system: str, _max_tokens: int) -> str:
    raise NotImplementedError("OpenAI provider not yet implemented")


def _vision_openai(_image: Image.Image, _prompt: str, _system: str, _max_tokens: int) -> str:
    raise NotImplementedError("OpenAI vision not yet implemented")


# GOOGLE (SCAFFOLD)

def _call_google(_messages: list[dict], _system: str, _max_tokens: int) -> str:
    raise NotImplementedError("Google provider not yet implemented")


def _vision_google(_image: Image.Image, _prompt: str, _system: str, _max_tokens: int) -> str:
    raise NotImplementedError("Google vision not yet implemented")


# PUBLIC INTERFACE — CALLED BY DRIVER.PY ONLY

def call(
    messages: list[dict],
    system: str = "",
    max_tokens: int = 2048,
) -> str:
    """Send a text conversation and return the assistant reply."""
    match PROVIDER:
        case "anthropic":
            return _call_anthropic(messages, system, max_tokens)
        case "openai":
            return _call_openai(messages, system, max_tokens)
        case "google":
            return _call_google(messages, system, max_tokens)
        case _:
            raise ValueError(f"Unknown provider: {PROVIDER!r}")


def vision(
    image: Image.Image,
    prompt: str,
    system: str = "",
    max_tokens: int = 1024,
) -> str:
    """Send an image + prompt and return the assistant reply."""
    match PROVIDER:
        case "anthropic":
            return _vision_anthropic(image, prompt, system, max_tokens)
        case "openai":
            return _vision_openai(image, prompt, system, max_tokens)
        case "google":
            return _vision_google(image, prompt, system, max_tokens)
        case _:
            raise ValueError(f"Unknown provider: {PROVIDER!r}")
