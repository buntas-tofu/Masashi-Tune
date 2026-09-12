"""Reasoning separation and artifact extraction.

Two documented leak modes (2026-07-08, both stacks): think-blocks arriving
inside the content channel, and reasoning that runs to the token limit with no
verdict at all. strip_think handles the first; an empty result after stripping
is the signature of the second, which judge() treats as a named retry, never a
silent gap.
"""

import json
import re

THINK_BLOCK = re.compile(r"<think>.*?</think>", re.S | re.I)
FENCE = re.compile(r"```(?:json)?\s*(.*?)```", re.S | re.I)


def strip_think(text: str) -> str:
    if not text:
        return ""
    out = THINK_BLOCK.sub("", text)
    low = out.lower()
    if "</think>" in low:
        out = out[low.rfind("</think>") + len("</think>"):]
    elif "<think>" in low:
        # unclosed think: everything from the tag on is deliberation
        out = out[: low.find("<think>")]
    return out.strip()


def extract_json(text: str):
    """Best-effort JSON artifact extraction: fenced block first, then the first
    balanced object or array in the text. Raises ValueError when nothing parses."""
    if not text or not text.strip():
        raise ValueError("empty verdict channel (reasoning-only reply)")
    candidates = [m.group(1).strip() for m in FENCE.finditer(text)]
    candidates.append(text.strip())
    for cand in candidates:
        try:
            return json.loads(cand)
        except json.JSONDecodeError:
            pass
    for opener, closer in (("[", "]"), ("{", "}")):
        start = text.find(opener)
        while start != -1:
            depth, in_str, esc = 0, False, False
            for i in range(start, len(text)):
                ch = text[i]
                if in_str:
                    if esc:
                        esc = False
                    elif ch == "\\":
                        esc = True
                    elif ch == '"':
                        in_str = False
                    continue
                if ch == '"':
                    in_str = True
                elif ch == opener:
                    depth += 1
                elif ch == closer:
                    depth -= 1
                    if depth == 0:
                        try:
                            return json.loads(text[start:i + 1])
                        except json.JSONDecodeError:
                            break
            start = text.find(opener, start + 1)
    raise ValueError("no parseable JSON in verdict channel")
