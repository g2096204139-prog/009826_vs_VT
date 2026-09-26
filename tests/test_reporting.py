from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import pandas as pd

from scripts.fetch_and_calculate import build_performance, write_outputs


class ReportingTests(unittest.TestCase):
    def test_all_report_surfaces_use_same_dates_and_observation_count(self) -> None:
        dates = pd.to_datetime(["2026-09-23", "2026-09-24"])
        px_009826 = pd.DataFrame({"close": [10.0, 10.5]}, index=dates)
        px_vt = pd.DataFrame({"close": [100.0, 101.0]}, index=dates)
        fx = pd.DataFrame({"usd_twd": [32.0, 31.0]}, index=dates)
        out = build_performance(
            px_009826,
            px_vt,
            fx,
            retrieved_at_utc="2026-09-26T00:00:00+00:00",
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "README.md").write_text(
                "# Test\n\n## 最新結果\n\nplaceholder\n\n## 資料來源\n",
                encoding="utf-8",
            )
            write_outputs(out, root=root)

            csv = pd.read_csv(root / "data/processed/performance.csv", parse_dates=["date"])
            html = (root / "reports/performance.html").read_text(encoding="utf-8")
            readme = (root / "README.md").read_text(encoding="utf-8")

            self.assertEqual(len(csv), 2)
            self.assertEqual(csv["date"].iloc[-1].date().isoformat(), "2026-09-24")
            self.assertIn("2026-09-24", html)
            self.assertIn("through=2026-09-24; observations=2", html)
            self.assertIn("2026-09-23 至 2026-09-24，共 2 個交易日", readme)
            self.assertTrue((root / "reports/performance.png").is_file())

    def test_readme_marker_mismatch_fails_instead_of_silently_skipping_update(self) -> None:
        dates = pd.to_datetime(["2026-09-24"])
        px_009826 = pd.DataFrame({"close": [10.0]}, index=dates)
        px_vt = pd.DataFrame({"close": [100.0]}, index=dates)
        fx = pd.DataFrame({"usd_twd": [32.0]}, index=dates)
        out = build_performance(px_009826, px_vt, fx)

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "README.md").write_text("# Missing result markers\n", encoding="utf-8")
            with self.assertRaisesRegex(RuntimeError, "README latest-results section markers"):
                write_outputs(out, root=root)


if __name__ == "__main__":
    unittest.main()
