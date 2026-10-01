from __future__ import annotations

import json
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from unittest.mock import patch


SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from acquire_bilibili import compact_metadata, source_url  # noqa: E402
from extract_frames import parse_timestamp, timestamp_name  # noqa: E402
from init_job import main as init_job_main  # noqa: E402
from make_contact_sheet import frame_label  # noqa: E402
from run_pipeline import main as pipeline_main  # noqa: E402
from validate_delivery import check_dependency_coverage, check_figure_captions  # noqa: E402


def write_srt(path: Path, count: int = 6) -> None:
    blocks = []
    for index in range(count):
        start = index * 10
        end = (index + 1) * 10
        blocks.append(
            f"{index + 1}\n"
            f"00:{start // 60:02d}:{start % 60:02d},000 --> "
            f"00:{end // 60:02d}:{end % 60:02d},000\n"
            f"这里解释第 {index + 1} 个关键机制，因为它会影响最终结果。"
        )
    path.write_text("\n\n".join(blocks) + "\n", encoding="utf-8")


class AcquisitionTests(unittest.TestCase):
    def test_source_accepts_bvid_and_rejects_unrelated_hosts(self) -> None:
        self.assertEqual(
            source_url("BV1ABC123"),
            "https://www.bilibili.com/video/BV1ABC123",
        )
        with self.assertRaises(ValueError):
            source_url("https://example.com/video/BV1ABC123")

    def test_compact_metadata_keeps_only_workflow_fields(self) -> None:
        compact = compact_metadata(
            {
                "id": "BV1ABC123",
                "title": "Demo",
                "duration": 42,
                "formats": [
                    {
                        "format_id": "1080p",
                        "ext": "mp4",
                        "height": 1080,
                        "url": "sensitive-and-large",
                    }
                ],
                "subtitles": {"zh-CN": []},
            }
        )
        self.assertEqual(compact["title"], "Demo")
        self.assertEqual(compact["subtitles"], ["zh-CN"])
        self.assertEqual(compact["formats"][0]["height"], 1080)
        self.assertNotIn("url", compact["formats"][0])


class FrameToolTests(unittest.TestCase):
    def test_timestamp_parsing_and_names_are_stable(self) -> None:
        self.assertEqual(parse_timestamp("01:02:03.5"), 3723.5)
        self.assertEqual(parse_timestamp("02:03"), 123.0)
        self.assertEqual(timestamp_name(123.456), "00-02-03-456")
        self.assertEqual(
            frame_label(Path("frame_0001.jpg"), 1, {"frame_0001.jpg": 120}),
            "00:02:00",
        )


class ValidationTests(unittest.TestCase):
    def test_dependency_checks_are_per_ecosystem(self) -> None:
        fence = chr(96) * 3
        text = (
            "pip install requests\n"
            f"{fence}python\nimport requests\n{fence}\n"
            f"{fence}typescript\nimport express from 'express'\n{fence}\n"
        )
        errors = check_dependency_coverage(text)
        self.assertEqual(len(errors), 1)
        self.assertIn("JavaScript/TypeScript", errors[0])

    def test_python_standard_library_does_not_require_install_command(self) -> None:
        fence = chr(96) * 3
        self.assertEqual(
            check_dependency_coverage(f"{fence}python\nimport pathlib\n{fence}"),
            [],
        )

    def test_every_figure_requires_its_own_caption(self) -> None:
        text = (
            "![a](../assets/figures/a.jpg)\n"
            "*图 1：第一张图，画面时间 01:20。*\n\n"
            "![b](../assets/figures/b.jpg)\n"
        )
        errors = check_figure_captions(text)
        self.assertEqual(len(errors), 1)
        self.assertIn("line 4", errors[0])

    def test_figure_numbers_must_be_sequential(self) -> None:
        text = (
            "![a](a.jpg)\n*图 1：第一张图，画面时间 01:20。*\n\n"
            "![b](b.jpg)\n*图 3：第二张图，画面时间 01:30。*\n"
        )
        self.assertIn("uniquely numbered", " ".join(check_figure_captions(text)))

    def test_cover_image_does_not_require_numbered_caption(self) -> None:
        text = "# Demo\n![cover](../assets/cover/cover.jpg)\n"
        self.assertEqual(check_figure_captions(text), [])


class PipelineTests(unittest.TestCase):
    def test_init_job_preserves_layout_and_adds_hotspot_work_directory(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            argv = [
                "init_job.py",
                "--workspace",
                directory,
                "--bvid",
                "BV1ABC123",
                "--part",
                "1",
            ]
            with patch.object(sys, "argv", argv), redirect_stdout(StringIO()):
                self.assertEqual(init_job_main(), 0)
            job_root = Path(directory) / "output" / "BV1ABC123_P1"
            self.assertTrue((job_root / "source" / "media").is_dir())
            self.assertTrue((job_root / "deliverables" / "docs").is_dir())
            self.assertTrue((job_root / "work" / "hotspots").is_dir())

    def test_pipeline_runs_additive_hotspot_path_and_checkpoints(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            job_root = Path(directory)
            transcript = job_root / "work" / "transcript"
            transcript.mkdir(parents=True)
            srt = transcript / "transcript.srt"
            write_srt(srt)
            argv = [
                "run_pipeline.py",
                "--job-root",
                str(job_root),
                "--hotspots",
            ]
            with patch.object(sys, "argv", argv), redirect_stdout(StringIO()):
                self.assertEqual(pipeline_main(), 0)

            state = json.loads(
                (job_root / "work" / "pipeline-state.json").read_text(
                    encoding="utf-8"
                )
            )
            self.assertEqual(state["stages"]["slice_transcript"]["status"], "completed")
            self.assertEqual(state["stages"]["build_inventory"]["status"], "completed")
            self.assertEqual(state["stages"]["extract_hotspots"]["status"], "completed")
            self.assertTrue(
                (job_root / "work" / "hotspots" / "hotspot-candidates.json").is_file()
            )

            with patch.object(sys, "argv", argv), redirect_stdout(StringIO()):
                self.assertEqual(pipeline_main(), 0)
            resumed = json.loads(
                (job_root / "work" / "pipeline-state.json").read_text(
                    encoding="utf-8"
                )
            )
            self.assertEqual(resumed["stages"]["slice_transcript"]["status"], "skipped")
            self.assertEqual(resumed["stages"]["build_inventory"]["status"], "skipped")
            self.assertEqual(resumed["stages"]["extract_hotspots"]["status"], "skipped")


if __name__ == "__main__":
    unittest.main()
