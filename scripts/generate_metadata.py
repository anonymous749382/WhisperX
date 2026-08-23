"""Plain-text word-level timestamp metadata file (human-readable)."""
from typing import List


def _fmt(t: float) -> str:
    h = int(t // 3600)
    m = int((t % 3600) // 60)
    s = t % 60
    return f"{h:02d}:{m:02d}:{s:06.3f}"


def generate_metadata(words: List, output_path: str) -> None:
    lines = [
        f"[{_fmt(w.start)} --> {_fmt(w.end)}]\t{w.word}\tconf={w.confidence:.3f}"
        for w in words
    ]
    with open(output_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + ("\n" if lines else ""))
