"""Pipeline orchestrator.

Modes:
  1) video/audio only              -> ASR (faster-whisper) + MMS alignment
  2) video/audio + transcript.txt  -> reuse given text, re-segment onto ASR
                                       boundaries, then MMS alignment
  3) video/audio + existing.srt    -> reuse given text+coarse timing as
                                       segments directly, then MMS alignment
                                       (refines timestamps, keeps your text)
"""
import argparse
import re
import sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).parent))

from extract_audio import extract_audio, get_duration
from transcribe import transcribe, segments_from_plain_text, Segment
from align import align_segments
from validate import validate_words, print_report
from generate_json import generate_json
from generate_srt import generate_srt
from generate_ass import generate_subtitle_ass, generate_karaoke_ass


def parse_srt(path: str):
    content = Path(path).read_text(encoding="utf-8")
    blocks = re.split(r"\n\s*\n", content.strip())
    time_re = re.compile(
        r"(\d+):(\d+):(\d+)[,.](\d+)\s*-->\s*(\d+):(\d+):(\d+)[,.](\d+)"
    )

    def to_sec(h, m, s, frac):
        frac = frac.ljust(3, "0")[:3]
        return int(h) * 3600 + int(m) * 60 + int(s) + int(frac) / 1000.0

    segments = []
    for i, block in enumerate(blocks):
        lines = [l for l in block.splitlines() if l.strip()]
        if len(lines) < 2:
            continue
        m = None
        text_start_idx = None
        for idx, line in enumerate(lines):
            m = time_re.search(line)
            if m:
                text_start_idx = idx + 1
                break
        if not m:
            continue
        start = to_sec(*m.groups()[0:4])
        end = to_sec(*m.groups()[4:8])
        text = " ".join(lines[text_start_idx:]).strip()
        if text:
            segments.append(Segment(id=i, start=start, end=end, text=text))
    return segments


def run(args, cfg):
    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    wav_path = out_dir / "audio.wav"
    print("[1/5] Extracting audio...")
    extract_audio(args.input, str(wav_path), cfg.get("alignment", {}).get("sample_rate", 16000))
    duration = get_duration(str(wav_path))
    print(f"      duration = {duration:.2f}s")

    language = cfg.get("language", "auto")

    if args.srt:
        print("[2/5] Using provided SRT for text + coarse segmentation (skipping ASR)...")
        segments = parse_srt(args.srt)
        if language == "auto":
            language = "unknown"
    elif args.transcript:
        print("[2/5] Running ASR for segmentation, then remapping provided transcript text...")
        asr_result = transcribe(str(wav_path), cfg)
        language = asr_result.language if language == "auto" else language
        transcript_text = Path(args.transcript).read_text(encoding="utf-8")
        segments = segments_from_plain_text(transcript_text, asr_result.segments)
    else:
        print("[2/5] Running ASR (faster-whisper)...")
        asr_result = transcribe(str(wav_path), cfg)
        language = asr_result.language if language == "auto" else language
        segments = asr_result.segments
        print(f"      {len(segments)} segments, language={language}")

    print("[3/5] Running forced alignment (MMS)...")
    words = align_segments(
        str(wav_path), segments, cfg.get("alignment", {}).get("segment_padding_sec", 0.35)
    )
    print(f"      {len(words)} words aligned")

    print("[4/5] Validating...")
    report = validate_words(words, duration, cfg.get("validation", {}))
    print_report(report)

    print("[5/5] Writing outputs...")
    generate_json(words, language, duration, report, str(out_dir / "output.json"))
    generate_srt(words, cfg.get("subtitle", {}), str(out_dir / "output.srt"))
    generate_subtitle_ass(words, cfg.get("subtitle", {}), str(out_dir / "subtitle.ass"))
    generate_karaoke_ass(words, cfg.get("subtitle", {}), str(out_dir / "karaoke.ass"))

    print(f"\nDone. Outputs in {out_dir}/")
    print("  output.json  output.srt  subtitle.ass  karaoke.ass")


def main():
    p = argparse.ArgumentParser(description="Word-level forced-alignment subtitle generator")
    p.add_argument("input", help="video or audio file")
    p.add_argument("--transcript", help="existing transcript.txt to reuse (optional)")
    p.add_argument("--srt", help="existing .srt to refine timing for (optional)")
    p.add_argument("--config", default=str(Path(__file__).parent.parent / "config.yaml"))
    p.add_argument("--output-dir", default="output")
    args = p.parse_args()

    if args.transcript and args.srt:
        p.error("--transcript and --srt are mutually exclusive")

    with open(args.config) as f:
        cfg = yaml.safe_load(f)

    run(args, cfg)


if __name__ == "__main__":
    main()
