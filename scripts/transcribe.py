"""Segment-level transcription with faster-whisper.

We deliberately only trust faster-whisper for: (1) what words were spoken,
and (2) rough segment boundaries (for chunking long audio + offsetting).
Word-level timing is NOT taken from here -- that's align.py's job.
"""
from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class Segment:
    id: int
    start: float
    end: float
    text: str


@dataclass
class TranscriptResult:
    language: str
    duration: float
    segments: List[Segment] = field(default_factory=list)


def transcribe(audio_path: str, cfg: dict) -> TranscriptResult:
    from faster_whisper import WhisperModel

    model = WhisperModel(
        cfg.get("model", "large-v3"),
        device=cfg.get("device", "cpu"),
        compute_type=cfg.get("compute_type", "int8"),
    )

    language = cfg.get("language", "auto")
    language = None if language == "auto" else language

    segments_gen, info = model.transcribe(
        audio_path,
        language=language,
        beam_size=cfg.get("beam_size", 5),
        vad_filter=cfg.get("vad_filter", True),
        vad_parameters={"min_silence_duration_ms": cfg.get("vad_min_silence_ms", 500)},
        word_timestamps=False,  # we don't trust/use these; MMS does the real job
        condition_on_previous_text=True,
    )

    segments: List[Segment] = []
    for i, seg in enumerate(segments_gen):
        text = seg.text.strip()
        if not text:
            continue
        segments.append(Segment(id=i, start=seg.start, end=seg.end, text=text))

    return TranscriptResult(
        language=info.language,
        duration=info.duration,
        segments=segments,
    )


def segments_from_plain_text(transcript_text: str, whisper_segments: List[Segment]) -> List[Segment]:
    """Re-align an externally supplied transcript onto whisper's segment
    boundaries using word-count-proportional matching, refined with
    difflib SequenceMatcher to keep well-matched runs intact.
    """
    import difflib

    provided_words = transcript_text.split()
    whisper_words_per_seg = [len(s.text.split()) for s in whisper_segments]
    whisper_all_words = " ".join(s.text for s in whisper_segments).split()

    sm = difflib.SequenceMatcher(a=whisper_all_words, b=provided_words, autojunk=False)
    # Build a mapping: provided_word_index -> whisper_word_index (best effort)
    mapping = [-1] * len(provided_words)
    for block in sm.get_matching_blocks():
        for k in range(block.size):
            mapping[block.b + k] = block.a + k

    # cumulative whisper word offsets per segment
    seg_word_starts = []
    acc = 0
    for n in whisper_words_per_seg:
        seg_word_starts.append(acc)
        acc += n
    seg_word_ends = [s + n for s, n in zip(seg_word_starts, whisper_words_per_seg)]

    def whisper_idx_to_seg(idx: int) -> int:
        for si, (s, e) in enumerate(zip(seg_word_starts, seg_word_ends)):
            if s <= idx < e:
                return si
        return len(whisper_segments) - 1

    # assign each provided word to a segment
    assigned = [None] * len(provided_words)
    last_seg = 0
    for i, widx in enumerate(mapping):
        if widx >= 0:
            last_seg = whisper_idx_to_seg(widx)
        assigned[i] = last_seg

    new_segments: List[Segment] = []
    cursor = 0
    for si, seg in enumerate(whisper_segments):
        words = [w for w, s in zip(provided_words, assigned) if s == si]
        if not words:
            continue
        new_segments.append(Segment(id=si, start=seg.start, end=seg.end, text=" ".join(words)))
    return new_segments

def segments_from_lines(transcript_text: str, whisper_segments: List[Segment]) -> List[Segment]:
    """Guarantee exactly one output segment per non-empty input line, with
    the EXACT original line text (no reconstruction/merging). Whisper's
    segments are only used to build an approximate word-time map for
    positioning each line's audio-search window -- align.py's MMS pass
    then does the real word-level timing inside that window.
    """
    import difflib

    lines = [l.strip() for l in transcript_text.split("\n") if l.strip()]

    # Build an approximate per-word timestamp by interpolating linearly
    # within each whisper segment (whisper gives segment-level start/end only).
    whisper_all_words = []
    whisper_word_times = []  # approx (start,end) per word, global timeline
    for seg in whisper_segments:
        words = seg.text.split()
        if not words:
            continue
        span = max(seg.end - seg.start, 0.05)
        step = span / len(words)
        for i, w in enumerate(words):
            whisper_all_words.append(w)
            whisper_word_times.append((seg.start + i * step, seg.start + (i + 1) * step))

    total_duration = whisper_segments[-1].end if whisper_segments else 0.0
    total_words_all_lines = sum(len(l.split()) for l in lines) or 1

    sm = difflib.SequenceMatcher(a=whisper_all_words, b=None, autojunk=False)

    new_segments: List[Segment] = []
    cursor_word_idx = 0     # progress marker into whisper_all_words
    cursor_time = 0.0       # fallback proportional time marker
    words_seen_so_far = 0

    for line_id, line in enumerate(lines):
        line_words = line.split()
        n = len(line_words)

        sm.set_seq2(line_words)
        matches = sm.get_matching_blocks()
        # keep only matches at/after our current search position, to move forward monotonically
        matches = [m for m in matches if m.size > 0 and m.a >= cursor_word_idx - 2]

        if matches:
            first = matches[0]
            last = matches[-1]
            start_ts = whisper_word_times[first.a][0]
            end_ts = whisper_word_times[last.a + last.size - 1][1]
            cursor_word_idx = last.a + last.size
        else:
            # fallback: proportional position by word-count share of total duration
            start_ts = cursor_time
            frac = n / total_words_all_lines
            end_ts = start_ts + frac * total_duration
            cursor_time = end_ts

        # generous padding since this window is only a rough anchor —
        # align.py's own padding_sec adds more on top of this
        pad = 0.75
        start_ts = max(0.0, start_ts - pad)
        end_ts = min(total_duration, end_ts + pad)

        new_segments.append(Segment(id=line_id, start=start_ts, end=end_ts, text=line))
        words_seen_so_far += n

    return new_segments

if __name__ == "__main__":
    import sys
    import yaml

    audio = sys.argv[1]
    with open(sys.argv[2]) as f:
        cfg = yaml.safe_load(f)
    result = transcribe(audio, cfg)
    print(f"language={result.language} duration={result.duration:.1f}s segments={len(result.segments)}")
    for s in result.segments[:5]:
        print(f"  [{s.start:.2f}-{s.end:.2f}] {s.text}")
