"""Group word-level timestamps into readable SRT cues (configurable)."""
from typing import List


def _fmt_srt_time(t: float) -> str:
    if t < 0:
        t = 0
    h = int(t // 3600)
    m = int((t % 3600) // 60)
    s = int(t % 60)
    ms = int(round((t - int(t)) * 1000))
    if ms == 1000:
        ms = 0
        s += 1
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def group_words_into_cues(words: List, cfg: dict) -> List[dict]:
    max_words = cfg.get("max_words_per_line", 8) * cfg.get("max_lines", 2)
    max_duration = cfg.get("max_duration", 5.0)
    max_gap = cfg.get("max_gap_new_line_sec", 0.6)

    cues = []
    current = []

    def flush():
        if current:
            cues.append({
                "start": current[0].start,
                "end": current[-1].end,
                "words": list(current),
            })

    prev_end = None
    for w in words:
        starts_new = False
        if current:
            gap = w.start - prev_end
            dur_if_added = w.end - current[0].start
            word_count = len(current) + 1
            if gap > max_gap or dur_if_added > max_duration or word_count > max_words:
                starts_new = True
            # sentence-ending punctuation forces a break too
            if current[-1].word.rstrip().endswith((".", "?", "!", "।")):
                starts_new = True

        if starts_new:
            flush()
            current = []

        current.append(w)
        prev_end = w.end

    flush()
    return cues


def generate_srt(words: List, cfg: dict, output_path: str) -> None:
    cues = group_words_into_cues(words, cfg)
    lines = []
    for i, cue in enumerate(cues, start=1):
        text = " ".join(w.word for w in cue["words"])
        lines.append(str(i))
        lines.append(f"{_fmt_srt_time(cue['start'])} --> {_fmt_srt_time(cue['end'])}")
        lines.append(text)
        lines.append("")
    with open(output_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
