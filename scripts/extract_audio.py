"""Extract clean mono 16kHz PCM WAV from any input video/audio file."""
import subprocess
import sys
from pathlib import Path


def extract_audio(input_path: str, output_path: str, sample_rate: int = 16000) -> str:
    input_path = str(Path(input_path).resolve())
    output_path = str(Path(output_path).resolve())
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)

    cmd = [
        "ffmpeg", "-y",
        "-i", input_path,
        "-vn",
        "-ac", "1",
        "-ar", str(sample_rate),
        "-acodec", "pcm_s16le",
        # loudness normalization helps ASR without destroying timing info
        "-af", "loudnorm=I=-16:TP=-1.5:LRA=11",
        output_path,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg failed:\n{result.stderr[-4000:]}")
    return output_path


def get_duration(path: str) -> float:
    cmd = [
        "ffprobe", "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        str(path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"ffprobe failed:\n{result.stderr}")
    return float(result.stdout.strip())


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("usage: extract_audio.py <input> <output.wav>")
        sys.exit(1)
    out = extract_audio(sys.argv[1], sys.argv[2])
    print(f"Extracted: {out} ({get_duration(out):.2f}s)")
