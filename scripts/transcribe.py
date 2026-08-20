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
