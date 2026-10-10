from __future__ import annotations

import csv
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch

from scripts.data_quality import FILES, build_summary, inspect_sources
from scripts import update_sources


class QualityTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        source = self.root / "data/source"
        source.mkdir(parents=True)
        common = ["2026-09-17", "2026-09-18", "2026-09-21", "2026-10-02", "2026-10-08"]
        for name, (key, fields, positive, label) in FILES.items():
            with (source / name).open("w", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=fields)
                writer.writeheader()
                if key == "ex_date":
                    writer.writerow(dict(ex_date="2026-09-18", distribution_per_share_usd="0.4084", payable_date="2026-09-22", record_date="2026-09-18", type="Income", source=label, source_url="https://advisors.vanguard.com/investments/products/vt/vanguard-total-world-stock-etf", retrieved_at_utc="2026-10-09T16:26:44+00:00"))
                else:
                    dates = sorted(common + (["2026-09-25", "2026-09-28"] if name == "vt_vanguard.csv" else []))
                    for day in dates:
                        row = {field: "10.08" for field in fields}
                        row.update(date=day, source=label)
                        if "volume" in row:
                            row["volume"] = "100"
                        if "usd_twd" in row:
                            row["usd_twd"] = "32.438"
                        writer.writerow(row)
        processed = self.root / "data/processed"
        processed.mkdir()
        fields = ["date", "009826_close", "usd_twd", "VT_close_usd", "VT_distribution_usd", "VT_total_return_usd_index", "VT_close_twd", "009826_index", "VT_index", "VT_price_index", "difference_pp", "retrieved_at_utc"]
        with (processed / "performance.csv").open("w", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fields)
            writer.writeheader()
            for day in common:
                row = {field: "100" for field in fields}
                row.update(date=day, VT_distribution_usd="0", difference_pp="0", retrieved_at_utc="2026-10-09T16:27:04+00:00")
                writer.writerow(row)
        (self.root / "README.md").write_text("## 最新結果\n\n- 共同完整資料：2026-09-17 至 2026-10-08，共 5 個交易日\n- 009826：100.0000\n- VT：100.0000\n\n## 資料來源\n")

    def tearDown(self):
        self.temp.cleanup()

    def test_existing_snapshot_and_event_freshness(self):
        summary = build_summary(self.root, date(2026, 10, 10))
        self.assertEqual(summary["errors"], [])
        self.assertEqual(summary["common"]["latest_date"], "2026-10-08")
        self.assertIn("2026-10-02", summary["common"]["dates"])
        distribution = summary["sources"]["vt_distributions.csv"]
        self.assertEqual(distribution["latest_observation_date"], "2026-09-18")
        self.assertEqual(distribution["age_calendar_days"], 1)
        self.assertEqual(summary["sources"]["009826_twse.csv"]["absent_relative_to_other_sources"], ["2026-09-25", "2026-09-28"])
        self.assertIn("NOT_VERIFIED", summary["calendar_validation"])

    def test_duplicate_nan_missing_and_future_fail(self):
        path = self.root / "data/source/usdtwd_cbc.csv"
        original = path.read_text()
        cases = [original + original.splitlines()[1] + "\n", original.replace("32.438", "nan"), original.replace("32.438", ""), original.replace("2026-09-17", "2026-10-11")]
        for content in cases:
            with self.subTest(content=content[:90]):
                path.write_text(content)
                self.assertTrue(inspect_sources(path.parent, date(2026, 10, 10))["errors"])

    def test_stale_price_source_fails(self):
        summary = inspect_sources(self.root / "data/source", date(2026, 10, 20))
        self.assertTrue(any("age" in item for item in summary["errors"]))

    def test_unmatched_dividend_fails(self):
        path = self.root / "data/source/vt_distributions.csv"
        path.write_text(path.read_text().replace("2026-09-18", "2026-09-19"))
        self.assertTrue(any("ex-dates without prices" in item for item in inspect_sources(path.parent, date(2026, 10, 10))["errors"]))

    def test_processed_dropped_date_fails(self):
        path = self.root / "data/processed/performance.csv"
        lines = path.read_text().splitlines()
        path.write_text("\n".join(lines[:2] + lines[3:]) + "\n")
        self.assertIn("Processed dates do not equal the full source intersection", build_summary(self.root, date(2026, 10, 10))["errors"])

    def test_readme_disagreement_fails(self):
        path = self.root / "README.md"
        path.write_text(path.read_text().replace("009826：100.0000", "009826：99.0000"))
        self.assertTrue(build_summary(self.root, date(2026, 10, 10))["errors"])

    def snapshot(self):
        source = self.root / "data/source"
        return {path.name: path.read_bytes() for path in source.iterdir() if path.is_file()}

    def changed_updater(self, page):
        path = update_sources.SOURCE / "009826_twse.csv"
        path.write_text(path.read_text().replace("10.08", "10.07"))
        return 47

    def failed_updater(self, page):
        raise RuntimeError("test source outage")

    @patch("scripts.update_sources.time.sleep")
    def test_source_failure_preserves_all_bytes(self, sleep):
        before = self.snapshot()
        with self.assertRaisesRegex(RuntimeError, "ALL existing"):
            update_sources.update_all(None, [("first", self.changed_updater), ("second", self.failed_updater)], self.root / "data/source")
        self.assertEqual(before, self.snapshot())

    @patch("scripts.update_sources.time.sleep")
    def test_validation_failure_preserves_all_bytes(self, sleep):
        before = self.snapshot()
        with patch("scripts.update_sources.inspect_sources", return_value={"errors": ["invalid candidate"]}):
            with self.assertRaisesRegex(RuntimeError, "Candidate validation failed"):
                update_sources.update_all(None, [("first", self.changed_updater)], self.root / "data/source")
        self.assertEqual(before, self.snapshot())

    @patch("scripts.update_sources.time.sleep")
    def test_success_publishes_candidate(self, sleep):
        before = self.snapshot()
        with patch("scripts.update_sources.inspect_sources", return_value={"errors": [], "status": "PASS_WITH_CALENDAR_LIMITATION"}):
            update_sources.update_all(None, [("first", self.changed_updater)], self.root / "data/source")
        self.assertNotEqual(before["009826_twse.csv"], self.snapshot()["009826_twse.csv"])
        self.assertIn("source_updates.json", self.snapshot())

    @patch("scripts.update_sources.time.sleep")
    def test_publish_failure_rolls_back(self, sleep):
        before = self.snapshot()
        original_replace = update_sources.os.replace
        count = 0
        def fail_second(src, dst):
            nonlocal count
            count += 1
            if count == 2:
                raise OSError("test publish failure")
            return original_replace(src, dst)
        with patch("scripts.update_sources.inspect_sources", return_value={"errors": [], "status": "PASS_WITH_CALENDAR_LIMITATION"}), patch("scripts.update_sources.os.replace", side_effect=fail_second):
            with self.assertRaisesRegex(OSError, "test publish failure"):
                update_sources.update_all(None, [("first", self.changed_updater)], self.root / "data/source")
        self.assertEqual(before, self.snapshot())


if __name__ == "__main__":
    unittest.main()
