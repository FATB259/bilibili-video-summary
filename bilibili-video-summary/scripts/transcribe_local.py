"""Transcribe a local audio/video file with faster-whisper base."""
import argparse
import json
import os
import shutil
from pathlib import Path

from faster_whisper import WhisperModel


def stamp(seconds: float) -> str:
    total_ms = round(seconds * 1000)
    h, rem = divmod(total_ms, 3_600_000)
    m, rem = divmod(rem, 60_000)
    s, ms = divmod(rem, 1_000)
    return f"{h:02d}:{m:02d}:{s:02d}.{ms:03d}"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("audio")
    parser.add_argument("--output", required=True)
    parser.add_argument("--model", default="base")
    parser.add_argument("--device", default=os.environ.get("WHISPER_DEVICE", "auto"))
    args = parser.parse_args()
    device = args.device
    if device == "auto":
        device = "cuda" if shutil.which("nvidia-smi") else "cpu"
    compute_type = "float16" if device == "cuda" else "int8"
    try:
        model = WhisperModel(args.model, device=device, compute_type=compute_type)
    except Exception:
        if args.device == "auto" and device == "cuda":
            device = "cpu"
            compute_type = "int8"
            model = WhisperModel(args.model, device=device, compute_type=compute_type)
        else:
            raise
    segments, info = model.transcribe(args.audio, language="zh", beam_size=1, vad_filter=True, condition_on_previous_text=False)
    lines = []
    for segment in segments:
        text = segment.text.strip()
        if text:
            lines.append(f"[{stamp(segment.start)} - {stamp(segment.end)}] {text}")
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")
    metadata = {"audio": str(Path(args.audio).resolve()), "output": str(out.resolve()), "model": args.model, "device": device, "compute_type": compute_type, "language": info.language, "line_count": len(lines), "status": "success" if len(lines) >= 20 else "failed"}
    out.with_name("transcription.json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(metadata, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
