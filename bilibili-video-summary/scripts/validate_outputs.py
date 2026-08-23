"""Validate successful or failed per-video output artifacts."""
import argparse
import json
import re
import zipfile
from pathlib import Path
from xml.etree import ElementTree


WINDOWS_ABSOLUTE_PATH = re.compile(r"^[A-Za-z]:[\\/]")
UNC_PATH = re.compile(r"^\\\\")
WORD_NAMESPACE = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"


def load_json(path: Path, expected_type):
    if not path.is_file():
        raise SystemExit(f"FAIL: missing {path.name}")
    try:
        value = json.loads(path.read_text(encoding="utf-8-sig"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise SystemExit(f"FAIL: invalid JSON in {path.name}: {exc}") from exc
    if not isinstance(value, expected_type):
        type_name = getattr(expected_type, "__name__", str(expected_type))
        raise SystemExit(f"FAIL: {path.name} must contain {type_name}")
    return value


def require_text(path: Path) -> str:
    if not path.is_file():
        raise SystemExit(f"FAIL: missing {path.as_posix()}")
    try:
        content = path.read_text(encoding="utf-8-sig").strip()
    except UnicodeDecodeError as exc:
        raise SystemExit(f"FAIL: {path.name} is not valid UTF-8") from exc
    if not content:
        raise SystemExit(f"FAIL: empty {path.as_posix()}")
    return content


def find_absolute_paths(value, location="$"):
    findings = []
    if isinstance(value, dict):
        for key, child in value.items():
            findings.extend(find_absolute_paths(child, f"{location}.{key}"))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            findings.extend(find_absolute_paths(child, f"{location}[{index}]"))
    elif isinstance(value, str) and (
        WINDOWS_ABSOLUTE_PATH.match(value) or UNC_PATH.match(value)
    ):
        findings.append(location)
    return findings


def validate_docx(path: Path) -> dict:
    if not path.is_file():
        raise SystemExit(f"FAIL: missing {path.as_posix()}")
    if not zipfile.is_zipfile(path):
        raise SystemExit("FAIL: notes.docx is not a valid OOXML ZIP archive")
    try:
        with zipfile.ZipFile(path) as archive:
            corrupt_member = archive.testzip()
            if corrupt_member:
                raise SystemExit(
                    f"FAIL: notes.docx contains a corrupt member: {corrupt_member}"
                )
            required = {"[Content_Types].xml", "word/document.xml"}
            missing = sorted(required.difference(archive.namelist()))
            if missing:
                raise SystemExit(
                    f"FAIL: notes.docx is missing required OOXML members: {missing}"
                )
            document_xml = archive.read("word/document.xml")
    except zipfile.BadZipFile as exc:
        raise SystemExit(f"FAIL: invalid notes.docx: {exc}") from exc

    try:
        root = ElementTree.fromstring(document_xml)
    except ElementTree.ParseError as exc:
        raise SystemExit(f"FAIL: invalid word/document.xml: {exc}") from exc
    text_nodes = root.findall(f".//{{{WORD_NAMESPACE}}}t")
    text = "".join(node.text or "" for node in text_nodes).strip()
    if not text:
        raise SystemExit("FAIL: notes.docx has no readable document text")
    return {"docx_bytes": path.stat().st_size, "docx_text_chars": len(text)}


def validate_visual_qa(path: Path) -> str:
    visual_qa = load_json(path, dict)
    visual_status = visual_qa.get("status")
    if visual_status not in ("passed", "unverified"):
        raise SystemExit(f"FAIL: unacceptable visual QA status: {visual_status!r}")
    if visual_status == "passed":
        if not visual_qa.get("renderer") or int(visual_qa.get("page_count") or 0) < 1:
            raise SystemExit(
                "FAIL: passed visual QA requires renderer and positive page_count"
            )
    elif not visual_qa.get("reason"):
        raise SystemExit("FAIL: unverified visual QA requires a reason")
    absolute_paths = find_absolute_paths(visual_qa)
    if absolute_paths:
        raise SystemExit(
            "FAIL: visual-qa.json contains absolute local paths at "
            + ", ".join(absolute_paths)
        )
    return visual_status


def validate_success(root: Path) -> dict:
    metadata = load_json(root / "metadata.json", dict)
    raw = require_text(root / "subtitles" / "raw.txt")
    cleaned = require_text(root / "subtitles" / "cleaned.md")
    analysis = require_text(root / "analysis" / "analysis.md")
    docx_info = validate_docx(root / "analysis" / "notes.docx")
    visual_status = validate_visual_qa(root / "analysis" / "visual-qa.json")

    if metadata.get("status") not in (None, "success", "completed"):
        raise SystemExit(
            f"FAIL: metadata status is not successful: {metadata.get('status')!r}"
        )
    for required_key in ("bvid", "title"):
        if not str(metadata.get(required_key, "")).strip():
            raise SystemExit(f"FAIL: metadata.json is missing {required_key}")

    absolute_paths = find_absolute_paths(metadata)
    if absolute_paths:
        raise SystemExit(
            "FAIL: metadata.json contains absolute local paths at "
            + ", ".join(absolute_paths)
        )

    transcription_path = root / "subtitles" / "transcription.json"
    transcription = None
    if transcription_path.exists():
        transcription = load_json(transcription_path, dict)
        if transcription.get("status") != "success":
            raise SystemExit("FAIL: transcription.json does not report success")
        coverage = float(transcription.get("timeline_coverage", 0))
        required = float(transcription.get("required_timeline_coverage", 0.70))
        if coverage < required:
            raise SystemExit(
                f"FAIL: transcription timeline coverage {coverage:.3f} < {required:.3f}"
            )
        transcription_paths = find_absolute_paths(transcription)
        if transcription_paths:
            raise SystemExit(
                "FAIL: transcription.json contains absolute local paths at "
                + ", ".join(transcription_paths)
            )

    subtitle_source = metadata.get("subtitle_source")
    if subtitle_source == "native":
        load_json(root / "subtitles" / "native.json", dict)
        if transcription is not None:
            raise SystemExit("FAIL: native subtitle output must not include transcription.json")
    elif subtitle_source == "local_whisper":
        if transcription is None:
            raise SystemExit("FAIL: local_whisper output requires transcription.json")
    else:
        raise SystemExit(f"FAIL: unsupported subtitle_source: {subtitle_source!r}")

    claims_path = root / "analysis" / "claims.json"
    if claims_path.exists():
        load_json(claims_path, (dict, list))
    uncertain_path = root / "analysis" / "uncertain-terms.json"
    if uncertain_path.exists():
        uncertain_terms = load_json(uncertain_path, list)
        if not all(isinstance(item, str) and item.strip() for item in uncertain_terms):
            raise SystemExit("FAIL: uncertain-terms.json must contain non-empty strings")

    return {
        "status": "success",
        "bvid": metadata["bvid"],
        "subtitle_lines": len(raw.splitlines()),
        "cleaned_chars": len(cleaned),
        "analysis_chars": len(analysis),
        "has_transcription": transcription is not None,
        "visual_qa": visual_status,
        **docx_info,
    }


def validate_failure(root: Path) -> dict:
    failure = load_json(root / "failures.json", dict)
    required = ("stage", "reason", "attempted_methods", "suggested_action")
    missing = [key for key in required if not failure.get(key)]
    if missing:
        raise SystemExit(f"FAIL: failures.json is missing fields: {missing}")
    if not isinstance(failure["attempted_methods"], list):
        raise SystemExit("FAIL: attempted_methods must be a list")
    absolute_paths = find_absolute_paths(failure)
    if absolute_paths:
        raise SystemExit(
            "FAIL: failures.json contains absolute local paths at "
            + ", ".join(absolute_paths)
        )
    docx_info = validate_docx(root / "analysis" / "notes.docx")
    visual_status = validate_visual_qa(root / "analysis" / "visual-qa.json")
    return {
        "status": "recorded_failure",
        "stage": failure["stage"],
        "visual_qa": visual_status,
        **docx_info,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("directory")
    parser.add_argument(
        "--expect",
        choices=("success", "failure"),
        default="success",
        help="Validate completed outputs or a recorded failure.",
    )
    args = parser.parse_args()
    root = Path(args.directory)
    if not root.is_dir():
        raise SystemExit(f"FAIL: output directory does not exist: {root}")
    result = validate_success(root) if args.expect == "success" else validate_failure(root)
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
