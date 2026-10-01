from __future__ import annotations

import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from unittest.mock import patch


SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from extract_hotspots import (  # noqa: E402
    Window,
    build_windows,
    main,
    score_window,
    select_candidates,
)
from slice_transcript import Entry  # noqa: E402


class ExtractHotspotsTests(unittest.TestCase):
    def test_high_value_explanation_scores_above_filler(self) -> None:
        important = Window(
            0,
            60_000,
            (
                Entry(0, 30_000, "这里的核心机制是缓存，因为它可以避免重复请求。"),
                Entry(30_000, 60_000, "关键区别是只更新已经失效的数据。"),
            ),
        )
        filler = Window(
            70_000,
            130_000,
            (
                Entry(70_000, 100_000, "欢迎大家点赞投币收藏关注。"),
                Entry(100_000, 130_000, "感谢观看，我们下期再见。"),
            ),
        )

        important_score, _ = score_window(important, [])
        filler_score, filler_signals = score_window(filler, [])

        self.assertGreater(important_score, filler_score)
        self.assertIn("low_value", filler_signals)

    def test_windows_are_bounded_and_deduplicated(self) -> None:
        entries = [
            Entry(index * 10_000, (index + 1) * 10_000, f"字幕 {index}")
            for index in range(12)
        ]

        windows = build_windows(
            entries, window_seconds=60, stride_seconds=30, min_seconds=30
        )

        self.assertEqual(len(windows), 4)
        self.assertTrue(all(window.duration_seconds >= 30 for window in windows))
        self.assertEqual(
            len({(window.start_ms, window.end_ms) for window in windows}),
            len(windows),
        )

    def test_candidate_selection_removes_heavy_overlap(self) -> None:
        first = Window(0, 90_000, (Entry(0, 90_000, "核心解释"),))
        overlapping = Window(
            30_000, 120_000, (Entry(30_000, 120_000, "另一个解释"),)
        )
        separate = Window(
            150_000, 240_000, (Entry(150_000, 240_000, "独立主题"),)
        )
        scored = [
            (first, 10.0, {}, ["缓存"]),
            (overlapping, 9.0, {}, ["请求"]),
            (separate, 8.0, {}, ["部署"]),
        ]

        selected = select_candidates(scored, count=3, max_overlap=0.35)

        self.assertEqual([item[0] for item in selected], [first, separate])

    def test_cli_writes_candidates_inside_job_work_directory(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            job_root = Path(directory)
            transcript_dir = job_root / "work" / "transcript"
            transcript_dir.mkdir(parents=True)
            srt = transcript_dir / "transcript.srt"
            srt.write_text(
                "\n\n".join(
                    [
                        (
                            f"{index + 1}\n"
                            f"00:{index * 10 // 60:02d}:{index * 10 % 60:02d},000 --> "
                            f"00:{(index + 1) * 10 // 60:02d}:{(index + 1) * 10 % 60:02d},000\n"
                            f"这里解释第 {index + 1} 个关键机制，因为它会影响最终结果。"
                        )
                        for index in range(6)
                    ]
                )
                + "\n",
                encoding="utf-8",
            )
            argv = [
                "extract_hotspots.py",
                "--job-root",
                str(job_root),
                "--count",
                "2",
                "--window-seconds",
                "40",
                "--stride-seconds",
                "20",
                "--min-seconds",
                "20",
            ]

            with patch.object(sys, "argv", argv), redirect_stdout(StringIO()):
                self.assertEqual(main(), 0)

            output = job_root / "work" / "hotspots" / "hotspot-candidates.json"
            self.assertTrue(output.is_file())
            self.assertIn('"review_required": true', output.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
