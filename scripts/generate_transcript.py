"""Paragraph-style story transcript from word-level aligned output.

Consecutive words jinke beech ka gap `paragraph_gap_sec` se zyada hai,
unpe naya paragraph shuru ho jaata hai (jaise natural speech pause /
scene break). Baaki sab ek hi paragraph me join ho jaate hain.
"""
from typing import List


def generate_transcript(words: List, output_path: str, paragraph_gap_sec: float = 1.5) -> None:
    if not words:
        open(output_path, "w", encoding="utf-8").close()
        return

    paragraphs = []
    current = [words[0].word]
    for prev, w in zip(words, words[1:]):
        gap = w.start - prev.end
        if gap > paragraph_gap_sec:
            paragraphs.append(" ".join(current))
            current = [w.word]
        else:
            current.append(w.word)
    paragraphs.append(" ".join(current))

    with open(output_path, "w", encoding="utf-8") as f:
        f.write("\n\n".join(paragraphs) + "\n")
