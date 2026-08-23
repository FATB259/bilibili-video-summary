"""Transcribe a local audio/video file with explicit quality signals."""
import argparse
import json
import os
import shutil
from pathlib import Path


def stamp(seconds: float) -> str:
    total_ms = round(seconds * 1000)
    h, rem = divmod(total_ms, 3_600_000)
    m, rem = divmod(rem, 60_000)
    s, ms = divmod(rem, 1_000)
    return f"{h:02d}:{m:02d}:{s:02d}.{ms:03d}"


def is_cuda_runtime_error(exc: Exception) -> bool:
    message = f"{type(exc).__name__}: {exc}".lower()
    markers = ("cuda", "cublas", "cudnn", "gpu", "driver")
    return any(marker in message for marker in markers)


def write_json(path: Path, payload: dict) -> None:
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def main():
    parser = argparse.ArgumentParser(
        description="Transcribe local media and fail when timeline coverage is insufficient."
    )
    parser.add_argument("audio")
    parser.add_argument("--output", required=True)
    parser.add_argument("--model", default="base")
    parser.add_argument("--device", default=os.environ.get("WHISPER_DEVICE", "auto"))
    parser.add_argument(
        "--language",
        default="zh",
        help="Language code such as zh/en/ja, or auto for language detection.",
    )
    parser.add_argument(
        "--min-timeline-coverage",
        type=float,
        default=0.70,
        help="Required ratio between the last subtitle end time and media duration.",
    )
    parser.add_argument(
        "--metadata-output",
        help="Defaults to transcription.json next to --output.",
    )
    args = parser.parse_args()

    if not 0 < args.min_timeline_coverage <= 1:
        parser.error("--min-timeline-coverage must be greater than 0 and at most 1")

    audio = Path(args.audio)
    if not audio.is_file():
        parser.error(f"audio file does not exist: {audio}")

    try:
        from faster_whisper import WhisperModel
    except ImportError as exc:
        raise SystemExit(
            "FAIL: faster_whisper is not installed in the current Python environment"
        ) from exc

    device = args.device
    if device == "auto":
        device = "cuda" if shutil.which("nvidia-smi") else "cpu"
    compute_type = "float16" if device == "cuda" else "int8"
    fallback_reason = None
    try:
        model = WhisperModel(args.model, device=device, compute_type=compute_type)
    except Exception as exc:
        if args.device == "auto" and device == "cuda" and is_cuda_runtime_error(exc):
            fallback_reason = f"{type(exc).__name__}: CUDA initialization failed"
            device = "cpu"
            compute_type = "int8"
            model = WhisperModel(args.model, device=device, compute_type=compute_type)
        else:
            raise

    requested_language = None if args.language.lower() == "auto" else args.language
    segments, info = model.transcribe(
        str(audio),
        language=requested_language,
        beam_size=1,
        vad_filter=True,
        condition_on_previous_text=False,
    )
    lines = []
    first_start = None
    last_end = 0.0
    speech_seconds = 0.0
    for segment in segments:
        text = segment.text.strip()
        if text:
            if first_start is None:
                first_start = float(segment.start)
            last_end = max(last_end, float(segment.end))
            speech_seconds += max(0.0, float(segment.end) - float(segment.start))
            lines.append(f"[{stamp(segment.start)} - {stamp(segment.end)}] {text}")

    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")

    media_duration = float(getattr(info, "duration", 0.0) or last_end)
    timeline_coverage = min(1.0, last_end / media_duration) if media_duration else 0.0
    status = (
        "success"
        if lines and timeline_coverage >= args.min_timeline_coverage
        else "failed"
    )
    metadata = {
        "audio": audio.name,
        "output": out.name,
        "model": args.model,
        "requested_device": args.device,
        "device": device,
        "compute_type": compute_type,
        "fallback_reason": fallback_reason,
        "requested_language": args.language,
        "detected_language": getattr(info, "language", None),
        "language_probability": getattr(info, "language_probability", None),
        "media_duration_seconds": round(media_duration, 3),
        "first_segment_start_seconds": round(first_start, 3) if first_start is not None else None,
        "last_segment_end_seconds": round(last_end, 3),
        "speech_seconds": round(speech_seconds, 3),
        "timeline_coverage": round(timeline_coverage, 4),
        "required_timeline_coverage": args.min_timeline_coverage,
        "line_count": len(lines),
        "status": status,
    }
    metadata_out = (
        Path(args.metadata_output)
        if args.metadata_output
        else out.with_name("transcription.json")
    )
    metadata_out.parent.mkdir(parents=True, exist_ok=True)
    write_json(metadata_out, metadata)
    print(json.dumps(metadata, ensure_ascii=False, indent=2))
    if status != "success":
        raise SystemExit(2)


if __name__ == "__main__":
    main()
