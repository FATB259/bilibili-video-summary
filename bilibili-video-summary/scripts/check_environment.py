"""Check local dependencies before Bilibili extraction and transcription."""
import argparse
import importlib.util
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


def command_info(name: str) -> dict:
    path = shutil.which(name)
    if not path:
        return {"available": False}
    result = {"available": True, "command": name}
    try:
        completed = subprocess.run(
            [path, "--version"],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
        first_line = (completed.stdout or completed.stderr).splitlines()
        result["version"] = first_line[0].strip() if first_line else None
    except (OSError, subprocess.SubprocessError) as exc:
        result["version_error"] = type(exc).__name__
    return result


def module_info(name: str) -> dict:
    spec = importlib.util.find_spec(name)
    return {"available": spec is not None, "module": name}


def gpu_info() -> dict:
    path = shutil.which("nvidia-smi")
    if not path:
        return {"available": False}
    try:
        completed = subprocess.run(
            [
                path,
                "--query-gpu=name,driver_version,memory.total",
                "--format=csv,noheader,nounits",
            ],
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return {"available": False, "error": type(exc).__name__}
    if completed.returncode != 0:
        return {"available": False, "error": "nvidia-smi returned non-zero"}
    rows = [row.strip() for row in completed.stdout.splitlines() if row.strip()]
    return {"available": bool(rows), "gpus": rows}


def disk_info(path: Path) -> dict:
    path.mkdir(parents=True, exist_ok=True)
    usage = shutil.disk_usage(path)
    writable = False
    try:
        with tempfile.NamedTemporaryFile(dir=path, prefix=".write-test-", delete=True):
            writable = True
    except OSError:
        writable = False
    return {
        "writable": writable,
        "free_gib": round(usage.free / (1024**3), 2),
    }


def try_load_model(model_name: str, requested_device: str) -> dict:
    try:
        from faster_whisper import WhisperModel
    except ImportError:
        return {"loaded": False, "error": "faster_whisper is not installed"}

    device = requested_device
    if device == "auto":
        device = "cuda" if shutil.which("nvidia-smi") else "cpu"
    compute_type = "float16" if device == "cuda" else "int8"
    try:
        WhisperModel(model_name, device=device, compute_type=compute_type)
        return {
            "loaded": True,
            "model": model_name,
            "device": device,
            "compute_type": compute_type,
        }
    except Exception as exc:
        return {
            "loaded": False,
            "model": model_name,
            "device": device,
            "compute_type": compute_type,
            "error": f"{type(exc).__name__}: {str(exc)[:240]}",
        }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-root", default="outputs")
    parser.add_argument("--require-transcription", action="store_true")
    parser.add_argument("--require-docx", action="store_true")
    parser.add_argument("--require-client", action="store_true")
    parser.add_argument("--load-model", action="store_true")
    parser.add_argument("--model", default="base")
    parser.add_argument("--device", choices=("auto", "cuda", "cpu"), default="auto")
    args = parser.parse_args()

    report = {
        "python": {
            "available": True,
            "version": ".".join(str(part) for part in sys.version_info[:3]),
        },
        "faster_whisper": module_info("faster_whisper"),
        "python_docx": module_info("docx"),
        "ffmpeg": command_info("ffmpeg"),
        "node": command_info("node"),
        "gpu": gpu_info(),
        "output": disk_info(Path(args.output_root)),
    }
    if args.load_model:
        report["model_load"] = try_load_model(args.model, args.device)

    failures = []
    warnings = []
    if sys.version_info < (3, 10):
        failures.append("Python 3.10 or newer is required")
    if report["output"]["free_gib"] < 2:
        warnings.append("less than 2 GiB is free in the output location")
    if not report["output"]["writable"]:
        failures.append("the output location is not writable")
    if not report["ffmpeg"]["available"]:
        warnings.append("ffmpeg is unavailable; some audio conversions may fail")
    if not report["node"]["available"]:
        warnings.append("node is unavailable; the Bilibili client watch-later adapter cannot run")
        if args.require_client:
            failures.append("Node.js is required for the watch-later client adapter")
    if args.require_transcription and not report["faster_whisper"]["available"]:
        failures.append("faster_whisper is required for local transcription")
    if args.require_docx and not report["python_docx"]["available"]:
        failures.append("python-docx is required for deterministic Word generation")
    if args.load_model and not report["model_load"]["loaded"]:
        failures.append("the requested Whisper model could not be loaded")

    report["warnings"] = warnings
    report["failures"] = failures
    report["status"] = "failed" if failures else ("warning" if warnings else "success")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if failures:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
