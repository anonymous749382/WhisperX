"""Word-level forced alignment using torchaudio's MMS aligner (CTC-based,
multilingual — covers Hindi/Devanagari via uroman romanization, unlike the
English-only wav2vec2 aligners WhisperX ships by default).
"""
import re
import unicodedata
from dataclasses import dataclass
from typing import List

import torch
import torchaudio

_MODEL = None
_TOKENIZER = None
_ALIGNER = None
_SAMPLE_RATE = 16000


@dataclass
class Word:
    word: str
    start: float
    end: float
    confidence: float


def _load_mms():
    global _MODEL, _TOKENIZER, _ALIGNER
    if _MODEL is None:
        from torchaudio.pipelines import MMS_FA as bundle

        _MODEL = bundle.get_model(with_star=False)
        _MODEL.eval()
        _TOKENIZER = bundle.get_tokenizer()
        _ALIGNER = bundle.get_aligner()
    return _MODEL, _TOKENIZER, _ALIGNER


_LATIN_RE = re.compile(r"^[A-Za-z0-9'\-]+$")


def _needs_romanization(words: List[str]) -> bool:
    return any(not _LATIN_RE.match(w) for w in words)


_UROMANIZER = None


def _get_uromanizer():
    """uroman's python API has shifted across versions; try the known
    entry points instead of hard-coding one and breaking on a pip bump."""
    global _UROMANIZER
    if _UROMANIZER is not None:
        return _UROMANIZER

    import uroman

    if hasattr(uroman, "Uroman"):
        inst = uroman.Uroman()
        if hasattr(inst, "romanize_string"):
            _UROMANIZER = lambda s: inst.romanize_string(s)
        elif hasattr(inst, "romanize"):
            _UROMANIZER = lambda s: inst.romanize(s)
        else:
            raise RuntimeError("uroman.Uroman instance has no romanize method")
    elif hasattr(uroman, "romanize_string"):
        _UROMANIZER = lambda s: uroman.romanize_string(s)
    else:
        raise RuntimeError(
            "Unrecognized uroman API — check `python -c 'import uroman; print(dir(uroman))'`"
        )
    return _UROMANIZER


def _romanize(words: List[str]) -> List[str]:
    """Romanize non-Latin script words (Devanagari etc.) via uroman so the
    MMS CTC model's shared-alphabet dictionary can align them."""
    romanize_fn = _get_uromanizer()
    romanized = []
    for w in words:
        rw = romanize_fn(w)
        rw = unicodedata.normalize("NFKD", str(rw))
        rw = re.sub(r"[^a-zA-Z0-9']", "", rw).lower()
        romanized.append(rw if rw else "x")
    return romanized


def _normalize_latin(words: List[str]) -> List[str]:
    out = []
    for w in words:
        w2 = re.sub(r"[^a-zA-Z0-9']", "", w).lower()
        out.append(w2 if w2 else "x")
    return out


def align_segment(waveform: torch.Tensor, sample_rate: int, words: List[str]) -> List[Word]:
    """Align a list of spoken words against the given waveform slice.
    Returns word timestamps relative to the START of this waveform slice.
    """
    if not words:
        return []

    model, tokenizer, aligner = _load_mms()

    if sample_rate != _SAMPLE_RATE:
        waveform = torchaudio.functional.resample(waveform, sample_rate, _SAMPLE_RATE)

    clean_words = _romanize(words) if _needs_romanization(words) else _normalize_latin(words)

    with torch.inference_mode():
        emission, _ = model(waveform.unsqueeze(0) if waveform.dim() == 1 else waveform)
        tokens = tokenizer(clean_words)
        token_spans = aligner(emission[0], tokens)

    num_frames = emission.size(1)
    ratio = waveform.size(-1) / num_frames / _SAMPLE_RATE  # seconds per frame

    results: List[Word] = []
    for orig_word, spans in zip(words, token_spans):
        start = spans[0].start * ratio
        end = spans[-1].end * ratio
        # average per-token score as a confidence proxy
        scores = [s.score for s in spans]
        conf = float(sum(scores) / len(scores)) if scores else 0.0
        results.append(Word(word=orig_word, start=float(start), end=float(end), confidence=conf))
    return results


def align_segments(audio_path: str, segments: List, padding_sec: float = 0.35) -> List[Word]:
    """Align every ASR segment against its (padded) audio slice, then
    offset word timestamps back to the full-file (global) timeline.
    """
    full_wave, sr = torchaudio.load(audio_path)
    full_wave = full_wave.mean(dim=0)  # mono
    duration = full_wave.size(-1) / sr

    all_words: List[Word] = []
    for seg in segments:
        words = seg.text.split()
        if not words:
            continue
        pad_start = max(0.0, seg.start - padding_sec)
        pad_end = min(duration, seg.end + padding_sec)
        s_idx = int(pad_start * sr)
        e_idx = int(pad_end * sr)
        chunk = full_wave[s_idx:e_idx]
        if chunk.numel() == 0:
            continue

        try:
            aligned = align_segment(chunk, sr, words)
        except Exception as e:  # noqa: BLE001
            # Fallback: evenly distribute across the segment rather than crash the pipeline
            span = max(seg.end - seg.start, 0.05)
            step = span / len(words)
            aligned = [
                Word(word=w, start=seg.start + i * step, end=seg.start + (i + 1) * step, confidence=0.0)
                for i, w in enumerate(words)
            ]
            for w in aligned:
                w.word = w.word + ""  # already global, skip offset below
            all_words.extend(aligned)
            continue

        for w in aligned:
            w.start += pad_start
            w.end += pad_start
        all_words.extend(aligned)

    return all_words


if __name__ == "__main__":
    import sys
    import yaml
    from transcribe import transcribe

    audio = sys.argv[1]
    with open(sys.argv[2]) as f:
        cfg = yaml.safe_load(f)
    result = transcribe(audio, cfg)
    words = align_segments(audio, result.segments, cfg.get("alignment", {}).get("segment_padding_sec", 0.35))
    for w in words[:15]:
        print(f"{w.word:15s} {w.start:7.3f} - {w.end:7.3f}  conf={w.confidence:.2f}")
        
