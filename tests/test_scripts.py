import importlib.util
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "bilibili-video-summary" / "scripts"


def run_script(name, *arguments, env=None):
    return subprocess.run(
        [sys.executable, str(SCRIPTS / name), *map(str, arguments)],
        capture_output=True,
        text=True,
        encoding="utf-8",
        env=env,
        check=False,
    )


class TranscriptionTests(unittest.TestCase):
    def fake_environment(self, directory: Path, poor_coverage: bool):
        module = directory / "faster_whisper.py"
        last_end = 2.0 if poor_coverage else 9.0
        module.write_text(
            f"""
class Segment:
    def __init__(self, start, end, text):
        self.start = start
        self.end = end
        self.text = text

class Info:
    duration = 10.0
    language = 'zh'
    language_probability = 0.99

class WhisperModel:
    def __init__(self, *args, **kwargs):
        pass
    def transcribe(self, *args, **kwargs):
        return iter([Segment(0.2, {last_end}, '短视频也可以成功')]), Info()
""",
            encoding="utf-8",
        )
        environment = os.environ.copy()
        environment["PYTHONPATH"] = str(directory)
        environment["PYTHONUTF8"] = "1"
        return environment

    def test_short_complete_transcription_succeeds_without_absolute_paths(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            audio = root / "audio.m4s"
            audio.write_bytes(b"audio")
            output = root / "subtitles" / "raw.txt"
            result = run_script(
                "transcribe_local.py",
                audio,
                "--output",
                output,
                "--device",
                "cpu",
                env=self.fake_environment(root, poor_coverage=False),
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            metadata = json.loads((output.parent / "transcription.json").read_text(encoding="utf-8"))
            self.assertEqual(metadata["status"], "success")
            self.assertEqual(metadata["line_count"], 1)
            self.assertEqual(metadata["audio"], "audio.m4s")
            self.assertFalse(Path(metadata["audio"]).is_absolute())

    def test_low_timeline_coverage_returns_nonzero(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            audio = root / "audio.m4s"
            audio.write_bytes(b"audio")
            output = root / "subtitles" / "raw.txt"
            result = run_script(
                "transcribe_local.py",
                audio,
                "--output",
                output,
                "--device",
                "cpu",
                env=self.fake_environment(root, poor_coverage=True),
            )
            self.assertEqual(result.returncode, 2)
            metadata = json.loads((output.parent / "transcription.json").read_text(encoding="utf-8"))
            self.assertEqual(metadata["status"], "failed")


class OutputTests(unittest.TestCase):
    def make_inputs(self, root: Path):
        (root / "subtitles").mkdir(parents=True)
        (root / "analysis").mkdir(parents=True)
        (root / "metadata.json").write_text(
            json.dumps(
                {
                    "bvid": "BV1test00000",
                    "title": "测试视频",
                    "status": "extracted",
                    "subtitle_source": "native",
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        (root / "subtitles" / "raw.txt").write_text(
            "[0000.000 - 0003.000] 测试字幕\n", encoding="utf-8"
        )
        (root / "subtitles" / "cleaned.md").write_text(
            "测试字幕和不确定术语。\n", encoding="utf-8"
        )
        (root / "subtitles" / "native.json").write_text(
            '{"body":[{"from":0,"to":3,"content":"测试字幕"}]}',
            encoding="utf-8",
        )
        (root / "analysis" / "analysis.md").write_text(
            "# 核心结论\n- 这是测试结论。\n", encoding="utf-8"
        )

    def test_invalid_docx_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self.make_inputs(root)
            (root / "analysis" / "notes.docx").write_bytes(b"x")
            (root / "analysis" / "visual-qa.json").write_text(
                '{"status":"unverified","reason":"test"}', encoding="utf-8"
            )
            result = run_script("validate_outputs.py", root)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("not a valid OOXML", result.stderr)

    def test_docx_builder_updates_metadata_and_validates(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self.make_inputs(root)
            uncertain = root / "analysis" / "uncertain.json"
            uncertain.write_text('["不确定术语"]', encoding="utf-8")
            build = run_script(
                "build_notes_docx.py",
                "--metadata",
                root / "metadata.json",
                "--analysis",
                root / "analysis" / "analysis.md",
                "--subtitle",
                root / "subtitles" / "cleaned.md",
                "--uncertain-terms",
                uncertain,
                "--output",
                root / "analysis" / "notes.docx",
            )
            self.assertEqual(build.returncode, 0, build.stderr)
            metadata = json.loads((root / "metadata.json").read_text(encoding="utf-8"))
            self.assertEqual(metadata["status"], "completed")
            self.assertEqual(metadata["notes_document"], "analysis/notes.docx")
            validate = run_script("validate_outputs.py", root)
            self.assertEqual(validate.returncode, 0, validate.stderr)
            report = json.loads(validate.stdout)
            self.assertEqual(report["visual_qa"], "unverified")
            recorded = run_script(
                "record_visual_qa.py",
                root,
                "--status",
                "passed",
                "--renderer",
                "test-renderer",
                "--page-count",
                "2",
            )
            self.assertEqual(recorded.returncode, 0, recorded.stderr)
            revalidated = run_script("validate_outputs.py", root)
            self.assertEqual(revalidated.returncode, 0, revalidated.stderr)
            self.assertEqual(json.loads(revalidated.stdout)["visual_qa"], "passed")

    def test_failure_record_also_requires_a_valid_word_report(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "analysis").mkdir(parents=True)
            failure = root / "failures.json"
            failure.write_text(
                json.dumps(
                    {
                        "stage": "extraction",
                        "reason": "test failure",
                        "attempted_methods": ["native_subtitle_api"],
                        "suggested_action": "retry once",
                    }
                ),
                encoding="utf-8",
            )
            built = run_script(
                "build_failure_docx.py",
                "--failure",
                failure,
                "--output",
                root / "analysis" / "notes.docx",
            )
            self.assertEqual(built.returncode, 0, built.stderr)
            validated = run_script(
                "validate_outputs.py", root, "--expect", "failure"
            )
            self.assertEqual(validated.returncode, 0, validated.stderr)
            self.assertEqual(json.loads(validated.stdout)["status"], "recorded_failure")


class BatchIndexTests(unittest.TestCase):
    def test_batch_index_deduplicates_and_resumes(self):
        with tempfile.TemporaryDirectory() as temporary:
            index = Path(temporary) / "batch-index.json"
            initialized = run_script(
                "batch_index.py",
                "init",
                index,
                "BV1uUun6YEKe",
                "BV1yngn68ea3",
                "BV1uUun6YEKe",
            )
            self.assertEqual(initialized.returncode, 0, initialized.stderr)
            updated = run_script(
                "batch_index.py",
                "update",
                index,
                "BV1uUun6YEKe",
                "--status",
                "completed",
            )
            self.assertEqual(updated.returncode, 0, updated.stderr)
            pending = run_script("batch_index.py", "pending", index)
            items = json.loads(pending.stdout)
            self.assertEqual(len(items), 1)
            self.assertEqual(items[0]["bvid"], "BV1yngn68ea3")


class ExtractionHelperTests(unittest.TestCase):
    def test_bvid_and_language_selection(self):
        script = SCRIPTS / "extract_bilibili.py"
        spec = importlib.util.spec_from_file_location("extract_bilibili", script)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        self.assertEqual(
            module.normalize_bvid("https://bilibili.com/video/BV1uUun6YEKe"),
            "BV1uUun6YEKe",
        )
        selected = module.choose_subtitle(
            [{"lan": "en"}, {"lan": "zh-CN"}], ["zh"]
        )
        self.assertEqual(selected["lan"], "zh-CN")
        redacted = module.safe_error(
            module.BilibiliError("failed https://example.com/audio?token=secret")
        )
        self.assertNotIn("token=secret", redacted)

        class Headers:
            @staticmethod
            def get_content_type():
                return "audio/mp4"

        class Response(io.BytesIO):
            headers = Headers()

            def __enter__(self):
                return self

            def __exit__(self, *args):
                self.close()

        class Opener:
            @staticmethod
            def open(*args, **kwargs):
                return Response(b"streamed-audio")

        with tempfile.TemporaryDirectory() as temporary:
            destination = Path(temporary) / "audio.m4s"
            info = module.download_audio(
                Opener(),
                {
                    "dash": {
                        "audio": [
                            {
                                "bandwidth": 100,
                                "baseUrl": "https://example.com/audio",
                                "mimeType": "audio/mp4",
                            }
                        ]
                    }
                },
                destination,
                "https://www.bilibili.com/video/BV1uUun6YEKe",
            )
            self.assertEqual(destination.read_bytes(), b"streamed-audio")
            self.assertEqual(info["bytes"], len(b"streamed-audio"))
            self.assertFalse(destination.with_suffix(".m4s.part").exists())


if __name__ == "__main__":
    unittest.main()
