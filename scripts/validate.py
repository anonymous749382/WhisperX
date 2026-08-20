"""Post-alignment validation: sanity-check word timings and produce a
human-readable QC report, flagging (not silently dropping) anomalies.
"""
from dataclasses import dataclass, asdict
from typing import List


@dataclass
class ValidationReport:
    words_processed: int
    aligned_ok: int
    low_confidence: int
    anomalies: int
    average_confidence: float
    issues: list


def validate_words(words: List, duration: float, cfg: dict) -> ValidationReport:
    min_dur = cfg.get("min_word_duration", 0.02)
    max_dur = cfg.get("max_word_duration", 3.0)
    max_gap = cfg.get("max_gap_flag", 2.0)
    low_conf_th = cfg.get("low_confidence_threshold", 0.55)

    issues = []
    low_conf = 0
    anomalies = 0
    confidences = []

    # sort defensively by start time, fix any inversions
    words = sorted(words, key=lambda w: w.start)

    prev_end = 0.0
    for i, w in enumerate(words):
        confidences.append(w.confidence)

        if w.start < 0 or w.end > duration + 0.5:
            issues.append(f"word[{i}] '{w.word}' outside media bounds ({w.start:.2f}-{w.end:.2f})")
            anomalies += 1

        if w.end <= w.start:
            issues.append(f"word[{i}] '{w.word}' start>=end ({w.start:.2f}-{w.end:.2f})")
            anomalies += 1
            w.end = w.start + min_dur

        dur = w.end - w.start
        if dur < min_dur:
            issues.append(f"word[{i}] '{w.word}' suspiciously short ({dur:.3f}s)")
            anomalies += 1
        if dur > max_dur:
            issues.append(f"word[{i}] '{w.word}' suspiciously long ({dur:.3f}s)")
            anomalies += 1

        if w.start < prev_end - 0.01:
            issues.append(f"word[{i}] '{w.word}' overlaps previous word by {prev_end - w.start:.3f}s")
            anomalies += 1

        gap = w.start - prev_end
        if gap > max_gap:
            issues.append(f"gap of {gap:.2f}s before word[{i}] '{w.word}'")

        if w.confidence < low_conf_th:
            low_conf += 1

        prev_end = w.end

    avg_conf = sum(confidences) / len(confidences) if confidences else 0.0

    return ValidationReport(
        words_processed=len(words),
        aligned_ok=len(words) - anomalies,
        low_confidence=low_conf,
        anomalies=anomalies,
        average_confidence=round(avg_conf, 4),
        issues=issues,
    )


def print_report(report: ValidationReport, max_issues_shown: int = 20) -> None:
    print("--- Alignment QC Report ---")
    print(f"Words processed:          {report.words_processed}")
    print(f"Aligned successfully:     {report.aligned_ok}")
    print(f"Low-confidence words:     {report.low_confidence}")
    print(f"Potential timing anomalies: {report.anomalies}")
    print(f"Average confidence:       {report.average_confidence}")
    if report.issues:
        print(f"\nFirst {min(max_issues_shown, len(report.issues))} issues:")
        for issue in report.issues[:max_issues_shown]:
            print(f"  - {issue}")
