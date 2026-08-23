"""Record whether a generated Word document passed visual inspection."""
import argparse
import json
from pathlib import Path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("video_output_directory")
    parser.add_argument("--status", choices=("passed", "unverified", "failed"), required=True)
    parser.add_argument("--renderer")
    parser.add_argument("--page-count", type=int)
    parser.add_argument("--reason")
    args = parser.parse_args()

    if args.status == "passed" and (
        not args.renderer or not args.page_count or args.page_count < 1
    ):
        parser.error("passed status requires --renderer and positive --page-count")
    if args.status != "passed" and not args.reason:
        parser.error("unverified or failed status requires --reason")

    root = Path(args.video_output_directory)
    docx = root / "analysis" / "notes.docx"
    if not docx.is_file():
        raise SystemExit("FAIL: analysis/notes.docx does not exist")
    destination = root / "analysis" / "visual-qa.json"
    payload = {
        "status": args.status,
        "renderer": args.renderer,
        "page_count": args.page_count,
        "reason": args.reason,
    }
    destination.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(payload, ensure_ascii=False))


if __name__ == "__main__":
    main()
