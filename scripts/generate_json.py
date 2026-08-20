"""Write the full-precision machine-readable JSON output."""
import json
from typing import List


def generate_json(words: List, language: str, duration: float, report, output_path: str) -> None:
    data = {
        "duration": round(duration, 3),
        "language": language,
        "words": [
            {
                "word": w.word,
                "start": round(w.start, 3),
                "end": round(w.end, 3),
                "confidence": round(w.confidence, 4),
            }
            for w in words
        ],
        "qc_report": {
            "words_processed": report.words_processed,
            "aligned_ok": report.aligned_ok,
            "low_confidence": report.low_confidence,
            "anomalies": report.anomalies,
            "average_confidence": report.average_confidence,
        },
    }
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
