from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import pandas as pd

from scripts.fetch_and_calculate import build_performance, compute_vt_total_return, write_outputs
from scripts.update_sources import parse_distribution_rows


class ReportingTests(unittest.TestCase):
    @staticmethod
    def empty_distributions() -> pd.DataFrame:
        return pd.DataFrame(columns=["ex_date", "distribution_per_share_usd"])

    def test_official_vanguard_distribution_row_is_parsed(self) -> None:
        rows = [
            ["TYPE", "$/SHARE", "PAYABLE DATE", "RECORD DATE", "EX-DIVIDEND DATE"],
            ["Income", "$0.408400", "09/22/2026", "09/18/2026", "09/18/2026"],
        ]
        parsed = parse_distribution_rows(rows)
        self.assertEqual(len(parsed), 1)
        self.assertEqual(parsed[0]["ex_date"], "2026-09-18")
        self.assertAlmostEqual(parsed[0]["distribution_per_share_usd"], 0.4084)

    def test_dividend_reinvestment_uses_full_us_calendar(self) -> None:
        us_dates = pd.to_datetime(["2026-09-17", "2026-09-18", "2026-09-21"])
        px_vt = pd.DataFrame({"close": [100.0, 99.0, 100.0]}, index=us_dates)
        distributions = pd.DataFrame({
            "ex_date": ["2026-09-18"],
            "distribution_per_share_usd": [1.0],
        })
        tr = compute_vt_total_return(px_vt, distributions)
        self.assertAlmostEqual(tr.iloc[1]["VT_total_return_usd_index"], 100.0)
        self.assertAlmostEqual(tr.iloc[2]["VT_total_return_usd_index"], 10000 / 99)

        # The US ex-date is absent from the TWSE/CBC comparison calendar.
        common_dates = pd.to_datetime(["2026-09-17", "2026-09-21"])
        px_009826 = pd.DataFrame({"close": [10.0, 10.1]}, index=common_dates)
        fx = pd.DataFrame({"usd_twd": [32.0, 32.0]}, index=common_dates)
        out = build_performance(px_009826, px_vt, fx, distributions)
        self.assertAlmostEqual(out.iloc[-1]["VT_index"], 10000 / 99)

    def test_no_distributions_matches_price_return(self) -> None:
        dates = pd.to_datetime(["2026-09-23", "2026-09-24"])
        px_009826 = pd.DataFrame({"close": [10.0, 10.5]}, index=dates)
        px_vt = pd.DataFrame({"close": [100.0, 101.0]}, index=dates)
        fx = pd.DataFrame({"usd_twd": [32.0, 31.0]}, index=dates)
        out = build_performance(px_009826, px_vt, fx, self.empty_distributions())
        self.assertAlmostEqual(out["VT_index"].iloc[-1], out["VT_price_index"].iloc[-1])
        self.assertAlmostEqual(out["VT_index"].iloc[0], 100.0)

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "README.md").write_text(
                "# Test\n\n## 最新結果\n\nplaceholder\n\n## 資料來源\n",
                encoding="utf-8",
            )
            write_outputs(out, root=root)
            csv = pd.read_csv(root / "data/processed/performance.csv", parse_dates=["date"])
            readme = (root / "README.md").read_text(encoding="utf-8")
            html = (root / "reports/performance.html").read_text(encoding="utf-8")
            self.assertEqual(len(csv), 2)
            self.assertEqual(csv["date"].iloc[-1].date().isoformat(), "2026-09-24")
            self.assertIn("共同完整資料：2026-09-23 至 2026-09-24，共 2 個交易日", readme)
            self.assertIn("VT（含息總報酬", readme)
            self.assertIn(r"VT\uff08\u542b\u606f\u7e3d\u5831\u916c\uff09", html)
            self.assertTrue((root / "reports/performance.png").is_file())

    def test_missing_ex_date_close_fails_closed(self) -> None:
        dates = pd.to_datetime(["2026-09-17", "2026-09-21"])
        px_vt = pd.DataFrame({"close": [100.0, 101.0]}, index=dates)
        distributions = pd.DataFrame({
            "ex_date": ["2026-09-18"],
            "distribution_per_share_usd": [1.0],
        })
        with self.assertRaisesRegex(RuntimeError, "no matching Vanguard close"):
            compute_vt_total_return(px_vt, distributions)

    def test_readme_marker_mismatch_fails_closed(self) -> None:
        dates = pd.to_datetime(["2026-09-24"])
        px_009826 = pd.DataFrame({"close": [10.0]}, index=dates)
        px_vt = pd.DataFrame({"close": [100.0]}, index=dates)
        fx = pd.DataFrame({"usd_twd": [32.0]}, index=dates)
        out = build_performance(px_009826, px_vt, fx, self.empty_distributions())
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "README.md").write_text("# Missing result markers\n", encoding="utf-8")
            with self.assertRaisesRegex(RuntimeError, "README latest-results section markers"):
                write_outputs(out, root=root)


if __name__ == "__main__":
    unittest.main()
