"""Generate .ass subtitle files.

subtitle.ass -> plain readable cues (same grouping as SRT)
karaoke.ass  -> \\k tags whose duration comes from actual word timestamps,
                never from (line_duration / word_count).
"""
from typing import List

from generate_srt import group_words_into_cues

HEADER = """[Script Info]
Title: {title}
ScriptType: v4.00+
WrapStyle: 0
ScaledBorderAndShadow: yes
YCbCr Matrix: TV.601
PlayResX: 1280
PlayResY: 720

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,Noto Sans,48,&H00FFFFFF,&H000000FF,&H00000000,&H80000000,0,0,0,0,100,100,0,0,1,2,1,2,40,40,40,1
Style: Karaoke,Noto Sans,48,&H00FFFFFF,&H0000D7FF,&H00000000,&H80000000,0,0,0,0,100,100,0,0,1,2,1,2,40,40,40,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""


def _fmt_ass_time(t: float) -> str:
    if t < 0:
        t = 0
    h = int(t // 3600)
    m = int((t % 3600) // 60)
    s = int(t % 60)
    cs = int(round((t - int(t)) * 100))
    if cs == 100:
        cs = 0
        s += 1
    return f"{h:d}:{m:02d}:{s:02d}.{cs:02d}"


def generate_subtitle_ass(words: List, cfg: dict, output_path: str, title: str = "Subtitle") -> None:
    cues = group_words_into_cues(words, cfg)
    lines = [HEADER.format(title=title)]
    for cue in cues:
        text = " ".join(w.word for w in cue["words"])
        lines.append(
            f"Dialogue: 0,{_fmt_ass_time(cue['start'])},{_fmt_ass_time(cue['end'])},Default,,0,0,0,,{text}"
        )
    with open(output_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


def generate_karaoke_ass(words: List, cfg: dict, output_path: str, title: str = "Karaoke") -> None:
    cues = group_words_into_cues(words, cfg)
    lines = [HEADER.format(title=title)]
    for cue in cues:
        parts = []
        for w in cue["words"]:
            k_cs = max(1, round((w.end - w.start) * 100))  # centiseconds, real duration
            parts.append(f"{{\\k{k_cs}}}{w.word} ")
        text = "".join(parts).rstrip()
        lines.append(
            f"Dialogue: 0,{_fmt_ass_time(cue['start'])},{_fmt_ass_time(cue['end'])},Karaoke,,0,0,0,,{text}"
        )
    with open(output_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
