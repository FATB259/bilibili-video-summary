"""Basic validation for a per-video output directory."""
import argparse
import json
from pathlib import Path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("directory")
    args = parser.parse_args()
    root = Path(args.directory)
    raw = next(iter((root / "subtitles").glob("*.txt")), None)
    docs = list(root.rglob("*.docx"))
    if raw is None or not raw.read_text(encoding="utf-8").strip():
        raise SystemExit("FAIL: no non-empty subtitle text")
    if not docs or any(path.stat().st_size == 0 for path in docs):
        raise SystemExit("FAIL: no non-empty docx")
    index = root / "subtitles" / "index.json"
    if index.exists():
        json.loads(index.read_text(encoding="utf-8-sig"))
    print(json.dumps({"status": "success", "subtitle": str(raw), "docx_count": len(docs), "line_count": len(raw.read_text(encoding="utf-8").splitlines())}, ensure_ascii=False))


if __name__ == "__main__":
    main()
