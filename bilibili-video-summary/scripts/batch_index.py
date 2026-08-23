"""Create and update a resumable batch-index.json file."""
import argparse
import json
import re
from datetime import datetime, timezone
from pathlib import Path


STATUSES = (
    "pending",
    "extracting",
    "transcribing",
    "analyzing",
    "completed",
    "failed",
)
BVID_PATTERN = re.compile(r"BV[0-9A-Za-z]{10}", re.IGNORECASE)
WINDOWS_ABSOLUTE_PATH = re.compile(r"^[A-Za-z]:[\\/]")


def now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def load_index(path: Path) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except FileNotFoundError as exc:
        raise SystemExit(f"FAIL: batch index does not exist: {path}") from exc
    except json.JSONDecodeError as exc:
        raise SystemExit(f"FAIL: invalid batch index JSON: {exc}") from exc
    if data.get("schema_version") != 1 or not isinstance(data.get("items"), list):
        raise SystemExit("FAIL: unsupported batch index schema")
    return data


def save_index(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    data["updated_at"] = now()
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    temporary.replace(path)


def inferred_bvid(source: str):
    match = BVID_PATTERN.search(source)
    if not match:
        return None
    raw = match.group(0)
    return "BV" + raw[2:]


def init_index(path: Path, sources: list[str]) -> dict:
    existing = load_index(path) if path.exists() else None
    existing_by_source = {
        item["source_ref"]: item for item in (existing or {}).get("items", [])
    }
    unique_sources = []
    seen = set()
    for source in sources:
        normalized = source.strip()
        if normalized and normalized not in seen:
            unique_sources.append(normalized)
            seen.add(normalized)
    if not unique_sources:
        raise SystemExit("FAIL: no sources were supplied")

    timestamp = now()
    items = []
    for order, source in enumerate(unique_sources, 1):
        item = existing_by_source.get(source)
        if item is None:
            item = {
                "order": order,
                "source_ref": source,
                "bvid": inferred_bvid(source),
                "title": None,
                "status": "pending",
                "attempts": 0,
                "last_error": None,
                "output_directory": None,
                "updated_at": timestamp,
            }
        else:
            item["order"] = order
        items.append(item)

    data = {
        "schema_version": 1,
        "created_at": (existing or {}).get("created_at", timestamp),
        "updated_at": timestamp,
        "items": items,
    }
    save_index(path, data)
    return data


def find_item(data: dict, key: str) -> dict:
    matches = [
        item
        for item in data["items"]
        if item.get("source_ref") == key or item.get("bvid") == key
    ]
    if not matches:
        raise SystemExit(f"FAIL: no batch item matches {key}")
    if len(matches) > 1:
        raise SystemExit(f"FAIL: multiple batch items match {key}")
    return matches[0]


def update_item(path: Path, args) -> dict:
    data = load_index(path)
    item = find_item(data, args.key)
    if args.output_directory and WINDOWS_ABSOLUTE_PATH.match(args.output_directory):
        raise SystemExit("FAIL: output_directory must be relative")
    if args.status in ("extracting", "transcribing") and item["status"] not in (
        "extracting",
        "transcribing",
    ):
        item["attempts"] = int(item.get("attempts", 0)) + 1
    item["status"] = args.status
    if args.bvid:
        item["bvid"] = inferred_bvid(args.bvid) or args.bvid
    if args.title is not None:
        item["title"] = args.title
    if args.output_directory is not None:
        item["output_directory"] = args.output_directory
    item["last_error"] = args.error if args.status == "failed" else None
    item["updated_at"] = now()
    save_index(path, data)
    return item


def pending_items(path: Path, include_failed: bool) -> list[dict]:
    data = load_index(path)
    resumable = {"pending", "extracting", "transcribing", "analyzing"}
    if include_failed:
        resumable.add("failed")
    return [item for item in data["items"] if item["status"] in resumable]


def summary(path: Path) -> dict:
    data = load_index(path)
    counts = {status: 0 for status in STATUSES}
    for item in data["items"]:
        counts[item["status"]] = counts.get(item["status"], 0) + 1
    return {"total": len(data["items"]), "counts": counts}


def main():
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)

    init_parser = subparsers.add_parser("init")
    init_parser.add_argument("index")
    init_parser.add_argument("sources", nargs="*")
    init_parser.add_argument("--source-file")

    update_parser = subparsers.add_parser("update")
    update_parser.add_argument("index")
    update_parser.add_argument("key")
    update_parser.add_argument("--status", choices=STATUSES, required=True)
    update_parser.add_argument("--bvid")
    update_parser.add_argument("--title")
    update_parser.add_argument("--output-directory")
    update_parser.add_argument("--error")

    pending_parser = subparsers.add_parser("pending")
    pending_parser.add_argument("index")
    pending_parser.add_argument("--include-failed", action="store_true")

    summary_parser = subparsers.add_parser("summary")
    summary_parser.add_argument("index")

    args = parser.parse_args()
    path = Path(args.index)
    if args.command == "init":
        sources = list(args.sources)
        if args.source_file:
            sources.extend(
                Path(args.source_file).read_text(encoding="utf-8-sig").splitlines()
            )
        result = init_index(path, sources)
    elif args.command == "update":
        result = update_item(path, args)
    elif args.command == "pending":
        result = pending_items(path, args.include_failed)
    else:
        result = summary(path)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
