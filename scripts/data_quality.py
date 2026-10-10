"""Bounded CSV validation; no downloads, return calculation, or market-calendar inference."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
from datetime import date, datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
START = date(2026, 8, 3)
FILES = {
    "009826_twse.csv": ("date", ["date", "open", "high", "low", "close", "volume", "source"], ["open", "high", "low", "close"], "TWSE"),
    "vt_vanguard.csv": ("date", ["date", "open", "high", "low", "close", "volume", "source"], ["open", "high", "low", "close"], "Vanguard"),
    "usdtwd_cbc.csv": ("date", ["date", "usd_twd", "source"], ["usd_twd"], "CBC"),
    "vt_distributions.csv": ("ex_date", ["ex_date", "distribution_per_share_usd", "payable_date", "record_date", "type", "source", "source_url", "retrieved_at_utc"], [], "Vanguard"),
}


def read_csv(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    with path.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        return reader.fieldnames or [], list(reader)


def inspect_sources(source: Path, as_of: date, max_age_days: int = 7) -> dict:
    if max_age_days < 0:
        raise ValueError("max_age_days must be non-negative")
    errors, warnings, summaries, dates_by_file = [], [], {}, {}
    for filename, (key, required, positive, label) in FILES.items():
        path = source / filename
        if not path.exists():
            errors.append(f"{filename}: missing file")
            continue
        fields, rows = read_csv(path)
        missing = sorted(set(required) - set(fields))
        if missing:
            errors.append(f"{filename}: missing columns {missing}")
            continue
        is_distribution = key == "ex_date"
        if not rows and not is_distribution:
            errors.append(f"{filename}: empty observations")
        missing_cells = sum(row.get(column) in (None, "") for row in rows for column in required)
        if missing_cells:
            errors.append(f"{filename}: {missing_cells} missing required cells")
        keys = [(row.get(key), row.get("type")) if is_distribution else row.get(key) for row in rows]
        duplicates = len(keys) - len(set(keys))
        if duplicates:
            errors.append(f"{filename}: {duplicates} duplicate keys")
        dates = []
        fetch_times = []
        for number, row in enumerate(rows, 2):
            try:
                observed = date.fromisoformat(row[key])
                if row[key] != observed.isoformat() or observed < START or observed > as_of:
                    raise ValueError("date outside study range")
                dates.append(observed.isoformat())
                if row["source"] != label:
                    raise ValueError("unexpected source label")
                for column in positive:
                    value = float(row[column])
                    if not math.isfinite(value) or value <= 0:
                        raise ValueError(f"invalid {column}")
                if not is_distribution and "volume" in row:
                    volume = float(row["volume"])
                    if not math.isfinite(volume) or volume < 0:
                        raise ValueError("invalid volume")
                    if not float(row["low"]) <= min(float(row["open"]), float(row["close"])) <= max(float(row["open"]), float(row["close"])) <= float(row["high"]):
                        raise ValueError("inconsistent OHLC")
                if is_distribution:
                    amount = float(row["distribution_per_share_usd"])
                    if not math.isfinite(amount) or amount < 0:
                        raise ValueError("invalid distribution amount")
                    payable = date.fromisoformat(row["payable_date"])
                    date.fromisoformat(row["record_date"])
                    if payable < observed:
                        raise ValueError("payment precedes ex-date")
                    if row["source_url"] != "https://advisors.vanguard.com/investments/products/vt/vanguard-total-world-stock-etf":
                        raise ValueError("unexpected distribution URL")
                    fetched = datetime.fromisoformat(row["retrieved_at_utc"])
                    if fetched.tzinfo is None or fetched.astimezone(timezone.utc).date() > as_of:
                        raise ValueError("invalid retrieval timestamp")
                    fetch_times.append(fetched)
            except (ValueError, TypeError, KeyError) as exc:
                errors.append(f"{filename}: row {number}: {exc}")
        latest = max(dates) if dates else None
        latest_fetch = max(fetch_times).isoformat() if fetch_times else None
        freshness_date = max(fetch_times).astimezone(timezone.utc).date() if fetch_times else None
        if not is_distribution and latest:
            freshness_date = date.fromisoformat(latest)
        age = (as_of - freshness_date).days if freshness_date else None
        if age is not None and age > max_age_days:
            errors.append(f"{filename}: age {age} calendar days exceeds {max_age_days}")
        if is_distribution and not rows:
            warnings.append(f"{filename}: header-only; current retrieval freshness unverified")
        summaries[filename] = {
            "rows": len(rows), "first_date": min(dates) if dates else None,
            "latest_observation_date": latest, "latest_retrieved_at_utc": latest_fetch,
            "age_calendar_days": age, "freshness_basis": "retrieved_at_utc" if is_distribution else "observation_date",
            "duplicate_keys": duplicates, "missing_required_cells": missing_cells,
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        }
        dates_by_file[filename] = set(dates)
    price_files = [name for name in FILES if name != "vt_distributions.csv"]
    sets = [dates_by_file.get(name, set()) for name in price_files]
    common = sorted(set.intersection(*sets))
    union = set.union(*sets)
    for name in price_files:
        if name in summaries:
            summaries[name]["absent_relative_to_other_sources"] = sorted(union - dates_by_file.get(name, set()))
    vt_dates = dates_by_file.get("vt_vanguard.csv", set())
    unmatched = sorted(dates_by_file.get("vt_distributions.csv", set()) - vt_dates)
    if unmatched:
        errors.append(f"VT ex-dates without prices: {unmatched}")
    if not common:
        errors.append("No common price/FX observations")
    return {
        "schema_version": "1.0", "as_of_date": as_of.isoformat(),
        "max_age_calendar_days": max_age_days, "status": "FAIL" if errors else "PASS_WITH_CALENDAR_LIMITATION",
        "sources": summaries, "common": {"rows": len(common), "first_date": common[0] if common else None, "latest_date": common[-1] if common else None, "dates": common},
        "calendar_validation": "NOT_VERIFIED; relative absences may be holidays or missing data; no filling",
        "errors": errors, "warnings": warnings,
    }


def build_summary(root: Path, as_of: date, max_age_days: int = 7) -> dict:
    summary = inspect_sources(root / "data/source", as_of, max_age_days)
    try:
        _, rows = read_csv(root / "data/processed/performance.csv")
        actual = [row["date"] for row in rows]
        if actual != summary["common"]["dates"]:
            summary["errors"].append("Processed dates do not equal the full source intersection")
        if any(value in (None, "") for row in rows for value in row.values()):
            summary["errors"].append("Processed CSV has missing cells")
        numeric = ["009826_close", "usd_twd", "VT_close_usd", "VT_distribution_usd", "VT_total_return_usd_index", "VT_close_twd", "009826_index", "VT_index", "VT_price_index", "difference_pp"]
        if any(not math.isfinite(float(row[column])) for row in rows for column in numeric):
            summary["errors"].append("Processed CSV contains non-finite numbers")
        readme = (root / "README.md").read_text(encoding="utf-8")
        latest = readme.split("## 最新結果\n", 1)[1].split("\n## 資料來源", 1)[0]
        if rows:
            expected = [f"{actual[0]} 至 {actual[-1]}，共 {len(rows)} 個交易日", f"009826：{float(rows[-1]['009826_index']):.4f}", f"：{float(rows[-1]['VT_index']):.4f}"]
            if not all(item in latest for item in expected):
                summary["errors"].append("README date/count/latest indexes disagree with processed CSV")
    except (OSError, ValueError, KeyError, IndexError) as exc:
        summary["errors"].append(f"Processed/README validation failed: {exc}")
    summary["status"] = "FAIL" if summary["errors"] else "PASS_WITH_CALENDAR_LIMITATION"
    updates = root / "data/source/source_updates.json"
    summary["last_source_update"] = json.loads(updates.read_text(encoding="utf-8")) if updates.exists() else None
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--as-of", type=date.fromisoformat, default=datetime.now(timezone.utc).date())
    parser.add_argument("--max-age-days", type=int, default=7)
    args = parser.parse_args()
    summary = build_summary(args.root, args.as_of, args.max_age_days)
    target = args.root / "data/processed/data_quality.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"{summary['status']}: {summary['common']['rows']} common observations through {summary['common']['latest_date']}")
    if summary["errors"]:
        raise RuntimeError("; ".join(summary["errors"]))


if __name__ == "__main__":
    main()
