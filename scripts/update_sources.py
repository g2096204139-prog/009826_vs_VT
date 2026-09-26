from __future__ import annotations

import re
import time
from datetime import date, datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd
from playwright.sync_api import Page, sync_playwright

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "data" / "source"
START = date(2026, 8, 3)
TAIPEI = ZoneInfo("Asia/Taipei")


def rows_from_table(table) -> list[list[str]]:
    return table.locator("tr").evaluate_all(
        "rows => rows.map(row => Array.from(row.querySelectorAll('th,td')).map(cell => (cell.textContent || '').trim()))"
    )


def merge_csv(filename: str, new_data: pd.DataFrame) -> int:
    path = SOURCE / filename
    SOURCE.mkdir(parents=True, exist_ok=True)
    existing = pd.read_csv(path) if path.exists() else pd.DataFrame()
    merged = pd.concat([existing, new_data], ignore_index=True)
    merged["date"] = pd.to_datetime(merged["date"]).dt.strftime("%Y-%m-%d")
    merged = merged.drop_duplicates(subset=["date"], keep="last").sort_values("date")
    merged.to_csv(path, index=False)
    return len(merged)


def roc_date(value: str) -> str:
    year, month, day = (int(part) for part in value.split("/"))
    return f"{year + 1911:04d}-{month:02d}-{day:02d}"


def update_twse(page: Page) -> int:
    page.goto("https://www.twse.com.tw/zh/trading/historical/stock-day.html", wait_until="domcontentloaded")
    today = datetime.now(TAIPEI).date()
    months = {(today.year, today.month)}
    months.add((today.year - 1, 12) if today.month == 1 else (today.year, today.month - 1))
    records: list[dict[str, object]] = []
    for year, month in sorted(months):
        selects = page.locator("select")
        selects.nth(0).select_option(label=f"民國 {year - 1911} 年")
        selects.nth(1).select_option(label=f"{month:02d}月")
        page.get_by_label("股票代碼：").fill("009826")
        page.get_by_role("button", name=re.compile("查詢")).click()
        page.locator("main table").wait_for(state="visible", timeout=30_000)
        page.wait_for_timeout(1_500)
        for row in rows_from_table(page.locator("main table"))[1:]:
            if len(row) < 9 or not re.fullmatch(r"\d{3}/\d{2}/\d{2}", row[0]):
                continue
            records.append({
                "date": roc_date(row[0]), "open": float(row[3].replace(",", "")),
                "high": float(row[4].replace(",", "")), "low": float(row[5].replace(",", "")),
                "close": float(row[6].replace(",", "")), "volume": int(row[1].replace(",", "")),
                "source": "TWSE",
            })
        time.sleep(2)
    return merge_csv("009826_twse.csv", pd.DataFrame(records))


def money(value: str) -> float:
    return float(value.replace("$", "").replace(",", "").strip())


def update_vanguard(page: Page) -> int:
    page.goto("https://advisors.vanguard.com/investments/products/vt/vanguard-total-world-stock-etf", wait_until="domcontentloaded")
    page.get_by_role("link", name="Price & distributions", exact=True).click()
    page.get_by_text("Historical prices", exact=True).wait_for(state="visible", timeout=30_000)
    page.wait_for_timeout(2_500)
    target = None
    for index in range(page.locator("table").count()):
        table = page.locator("table").nth(index)
        text = table.inner_text()
        if "18 months" in text and "HIGH" in text and "OPEN" in text:
            target = table
            break
    if target is None:
        raise RuntimeError("Vanguard 18-month historical price table not found")
    records: list[dict[str, object]] = []
    for row in rows_from_table(target):
        if len(row) < 6 or "2026" not in row[0]:
            continue
        parsed = pd.to_datetime(row[0], errors="coerce")
        if pd.isna(parsed) or parsed.date() < START:
            continue
        records.append({
            "date": parsed.strftime("%Y-%m-%d"), "open": money(row[5]),
            "high": money(row[3]), "low": money(row[4]), "close": money(row[1]),
            "volume": float(row[2].replace(",", "")), "source": "Vanguard",
        })
    return merge_csv("vt_vanguard.csv", pd.DataFrame(records))


def update_cbc(page: Page) -> int:
    records: list[dict[str, object]] = []
    for url in ("https://www.cbc.gov.tw/en/lp-700-2.html", "https://www.cbc.gov.tw/en/lp-700-2-2-20.html"):
        page.goto(url, wait_until="domcontentloaded")
        page.wait_for_timeout(1_500)
        body = page.locator("body").inner_text()
        for value, rate in re.findall(r"(20\d{2}/\d{2}/\d{2})\s+([0-9]+\.[0-9]+)", body):
            parsed = datetime.strptime(value, "%Y/%m/%d").date()
            if parsed >= START:
                records.append({"date": parsed.isoformat(), "usd_twd": float(rate), "source": "CBC"})
        time.sleep(2)
    return merge_csv("usdtwd_cbc.csv", pd.DataFrame(records))



def parse_distribution_rows(rows: list[list[str]]) -> list[dict[str, object]]:
    if not rows:
        raise RuntimeError("Vanguard distribution table is missing its header")
    headers = [cell.strip().upper() for cell in rows[0]]
    required = ["TYPE", "$/SHARE", "PAYABLE DATE", "RECORD DATE", "EX-DIVIDEND DATE"]
    if not all(name in headers for name in required):
        raise RuntimeError(f"Unexpected Vanguard distribution columns: {headers}")
    positions = {name: headers.index(name) for name in required}
    records: list[dict[str, object]] = []
    for row in rows[1:]:
        if len(row) < len(headers):
            continue
        ex_date = datetime.strptime(row[positions["EX-DIVIDEND DATE"]], "%m/%d/%Y").date()
        if ex_date < START:
            continue
        records.append({
            "ex_date": ex_date.isoformat(),
            "distribution_per_share_usd": money(row[positions["$/SHARE"]]),
            "payable_date": datetime.strptime(row[positions["PAYABLE DATE"]], "%m/%d/%Y").date().isoformat(),
            "record_date": datetime.strptime(row[positions["RECORD DATE"]], "%m/%d/%Y").date().isoformat(),
            "type": row[positions["TYPE"]].strip(),
            "source": "Vanguard",
            "source_url": "https://advisors.vanguard.com/investments/products/vt/vanguard-total-world-stock-etf",
            "retrieved_at_utc": datetime.now(timezone.utc).isoformat(),
        })
    return records


def merge_distributions(new_data: pd.DataFrame) -> int:
    path = SOURCE / "vt_distributions.csv"
    SOURCE.mkdir(parents=True, exist_ok=True)
    existing = pd.read_csv(path) if path.exists() else pd.DataFrame()
    merged = pd.concat([existing, new_data], ignore_index=True)
    columns = ["ex_date", "distribution_per_share_usd", "payable_date", "record_date", "type", "source", "source_url", "retrieved_at_utc"]
    if merged.empty:
        merged = pd.DataFrame(columns=columns)
    else:
        for column in ("ex_date", "payable_date", "record_date"):
            merged[column] = pd.to_datetime(merged[column]).dt.strftime("%Y-%m-%d")
        merged = merged.drop_duplicates(subset=["ex_date", "type", "payable_date"], keep="last")
        merged = merged.sort_values(["ex_date", "type"])
    merged[columns].to_csv(path, index=False)
    return len(merged)


def update_vt_distributions(page: Page) -> int:
    page.goto("https://advisors.vanguard.com/investments/products/vt/vanguard-total-world-stock-etf", wait_until="domcontentloaded")
    page.get_by_role("link", name="Price & distributions", exact=True).click()
    start_input = page.locator("#distributionStartDateInput")
    start_input.wait_for(state="visible", timeout=30_000)
    start_input.fill(START.isoformat())
    page.wait_for_timeout(2_000)
    distribution_table = None
    for index in range(page.locator("table").count()):
        table = page.locator("table").nth(index)
        text = table.inner_text()
        if "EX-DIVIDEND DATE" in text and "$/SHARE" in text and "PAYABLE DATE" in text:
            distribution_table = table
            break
    if distribution_table is None:
        raise RuntimeError("Vanguard distribution table not found")
    records: list[dict[str, object]] = []
    page_count = 0
    while True:
        records.extend(parse_distribution_rows(rows_from_table(distribution_table)))
        page_count += 1
        if page_count > 100:
            raise RuntimeError("Vanguard distribution pagination exceeded safety limit")
        next_page = page.locator("#priceanddistributions").get_by_role("button", name="Next page")
        next_page_count = next_page.count()
        if next_page_count != 1:
            raise RuntimeError(f"Expected one Vanguard distribution pagination button, found {next_page_count}")
        next_page_class = next_page.get_attribute("class") or ""
        if "axs-pagination__link--disabled" in next_page_class or not next_page.is_enabled():
            break
        next_page.click()
        page.wait_for_timeout(500)
    columns = ["ex_date", "distribution_per_share_usd", "payable_date", "record_date", "type", "source", "source_url", "retrieved_at_utc"]
    return merge_distributions(pd.DataFrame(records, columns=columns))


def main() -> None:
    results: dict[str, str] = {}
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page(locale="zh-TW")
        for name, updater in (("TWSE", update_twse), ("Vanguard prices", update_vanguard), ("Vanguard distributions", update_vt_distributions), ("CBC", update_cbc)):
            try:
                count = updater(page)
                results[name] = f"ok ({count} rows retained)"
            except Exception as exc:
                results[name] = f"failed; existing cache retained ({exc})"
            time.sleep(3)
        browser.close()
    for name, result in results.items():
        print(f"{name}: {result}")
    if not all(result.startswith("ok") for result in results.values()):
        raise RuntimeError("One or more sources failed; existing source files were preserved")


if __name__ == "__main__":
    main()
