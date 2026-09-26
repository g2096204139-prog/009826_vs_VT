from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import pandas as pd
import plotly.graph_objects as go
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "data" / "source"


def read_source(filename: str, allow_empty: bool = False) -> pd.DataFrame:
    path = SOURCE / filename
    data = pd.read_csv(path, parse_dates=["date"]).set_index("date").sort_index()
    if data.empty and not allow_empty:
        raise RuntimeError(f"Empty source file: {path}")
    if data.index.has_duplicates:
        raise RuntimeError(f"Duplicate dates in source file: {path}")
    return data



def read_distributions() -> pd.DataFrame:
    path = SOURCE / "vt_distributions.csv"
    if not path.exists():
        raise RuntimeError(f"Missing required VT distribution source file: {path}")
    data = pd.read_csv(path, parse_dates=["ex_date"])
    required = {"ex_date", "distribution_per_share_usd", "payable_date", "record_date", "type", "source", "source_url"}
    missing = required.difference(data.columns)
    if missing:
        raise RuntimeError(f"VT distribution source is missing columns: {sorted(missing)}")
    return data


def compute_vt_total_return(px_vt: pd.DataFrame, distributions: pd.DataFrame) -> pd.DataFrame:
    prices = px_vt[["close"]].copy()
    prices.index = pd.to_datetime(prices.index)
    prices = prices.sort_index()
    if prices.empty or prices.index.has_duplicates or not prices.index.is_monotonic_increasing:
        raise RuntimeError("VT price observations must be non-empty, unique, and ascending.")
    if prices["close"].isna().any() or (prices["close"] <= 0).any():
        raise RuntimeError("VT closing prices must be present and positive.")

    cash = pd.Series(0.0, index=prices.index, name="VT_distribution_usd")
    if not distributions.empty:
        required = {"ex_date", "distribution_per_share_usd"}
        missing = required.difference(distributions.columns)
        if missing:
            raise RuntimeError(f"VT distribution data is missing columns: {sorted(missing)}")
        records = distributions[["ex_date", "distribution_per_share_usd"]].copy()
        records["ex_date"] = pd.to_datetime(records["ex_date"], errors="coerce")
        records["distribution_per_share_usd"] = pd.to_numeric(records["distribution_per_share_usd"], errors="coerce")
        if records.isna().any().any() or (records["distribution_per_share_usd"] < 0).any():
            raise RuntimeError("VT distributions must have valid ex-dates and non-negative amounts.")
        by_date = records.groupby("ex_date")["distribution_per_share_usd"].sum()
        missing_price_dates = by_date.index.difference(prices.index)
        if len(missing_price_dates):
            raise RuntimeError(
                "VT distributions have no matching Vanguard close on ex-dates: "
                + ", ".join(d.date().isoformat() for d in missing_price_dates)
            )
        cash.loc[by_date.index] = by_date

    daily_factor = (prices["close"] + cash) / prices["close"].shift(1)
    daily_factor.iloc[0] = 1.0
    if daily_factor.isna().any() or (daily_factor <= 0).any():
        raise RuntimeError("VT total-return daily factors must be present and positive.")
    result = pd.DataFrame(index=prices.index)
    result["VT_close_usd"] = prices["close"]
    result["VT_distribution_usd"] = cash
    result["VT_total_return_usd_index"] = daily_factor.cumprod() * 100
    return result


def build_performance(
    px_009826: pd.DataFrame,
    px_vt: pd.DataFrame,
    fx: pd.DataFrame,
    distributions: pd.DataFrame,
    retrieved_at_utc: str | None = None,
) -> pd.DataFrame:
    vt_total_return = compute_vt_total_return(px_vt, distributions)
    out = pd.concat(
        [px_009826["close"].rename("009826_close"), fx["usd_twd"]],
        axis=1,
        join="inner",
    ).join(vt_total_return, how="inner").sort_index().dropna()
    if out.empty:
        raise RuntimeError("No overlapping TWSE/Vanguard/CBC observations.")
    if out.index.has_duplicates or not out.index.is_monotonic_increasing:
        raise RuntimeError("Common observations must have unique, ascending dates.")
    source_columns = ["009826_close", "VT_close_usd", "usd_twd", "VT_total_return_usd_index"]
    if out[source_columns].isna().any().any() or (out[source_columns] <= 0).any().any():
        raise RuntimeError("Common prices, exchange rates, and indexes must be present and positive.")

    out["VT_close_twd"] = out["VT_close_usd"] * out["usd_twd"]
    out["009826_index"] = out["009826_close"] / out["009826_close"].iloc[0] * 100
    vt_base = out["VT_total_return_usd_index"].iloc[0] * out["usd_twd"].iloc[0]
    out["VT_index"] = out["VT_total_return_usd_index"] * out["usd_twd"] / vt_base * 100
    out["VT_price_index"] = out["VT_close_twd"] / out["VT_close_twd"].iloc[0] * 100
    out["difference_pp"] = out["009826_index"] - out["VT_index"]
    out.index = pd.to_datetime(out.index).date
    out.index.name = "date"
    out["retrieved_at_utc"] = retrieved_at_utc or datetime.now(timezone.utc).isoformat()
    validate_performance(out)
    return out


def validate_performance(out: pd.DataFrame) -> None:
    required = {
        "009826_close", "VT_close_usd", "usd_twd", "VT_close_twd", "VT_distribution_usd",
        "VT_total_return_usd_index", "VT_price_index", "009826_index", "VT_index",
        "difference_pp", "retrieved_at_utc",
    }
    missing = required.difference(out.columns)
    if missing:
        raise RuntimeError(f"Performance data is missing columns: {sorted(missing)}")
    if out.empty or out.index.has_duplicates or not out.index.is_monotonic_increasing:
        raise RuntimeError("Performance data must be non-empty with unique ascending dates.")
    if out.isna().any().any():
        raise RuntimeError("Performance data contains missing values.")
    if not (out["difference_pp"] - (out["009826_index"] - out["VT_index"])).abs().lt(1e-10).all():
        raise RuntimeError("Performance gap does not match the two index series.")
    expected_vt = (
        out["VT_total_return_usd_index"] * out["usd_twd"]
        / (out["VT_total_return_usd_index"].iloc[0] * out["usd_twd"].iloc[0]) * 100
    )
    if not (out["VT_index"] - expected_vt).abs().lt(1e-10).all():
        raise RuntimeError("TWD VT total-return index does not match USD return and CBC FX.")
    if abs(out["009826_index"].iloc[0] - 100) > 1e-10 or abs(out["VT_index"].iloc[0] - 100) > 1e-10 or abs(out["VT_price_index"].iloc[0] - 100) > 1e-10:
        raise RuntimeError("All index series must start at 100.")


def update_readme(readme_path: Path, out: pd.DataFrame) -> str:
    readme = readme_path.read_text(encoding="utf-8")
    section_start = "## 最新結果\n"
    next_section = "\n## 資料來源"
    if readme.count(section_start) != 1 or readme.count(next_section) != 1:
        raise RuntimeError("README latest-results section markers are missing or duplicated.")

    start_date = out.index[0].isoformat()
    end_date = out.index[-1].isoformat()
    count = len(out)
    gap = float(out["difference_pp"].iloc[-1])
    if gap > 0:
        gap_text = f"009826 領先 VT {gap:.4f} 個百分點"
    elif gap < 0:
        gap_text = f"009826 落後 VT {abs(gap):.4f} 個百分點"
    else:
        gap_text = "兩者指數相同"

    section = (
        f"## 最新結果\n\n"
        f"- 共同完整資料：{start_date} 至 {end_date}，共 {count} 個交易日\n"
        f"- 009826：{out['009826_index'].iloc[-1]:.4f}\n"
        f"- VT（含息總報酬；配息按除息日收盤再投入後換算新臺幣）：{out['VT_index'].iloc[-1]:.4f}\n"
        f"- 差距：{gap_text}\n"
        f"- 基準：兩者於 {start_date} 均標準化為 100\n"
    )
    readme = readme.replace(section_start + readme.split(section_start, 1)[1].split(next_section, 1)[0], section)
    readme_path.write_text(readme, encoding="utf-8")
    return readme


def write_outputs(out: pd.DataFrame, root: Path = ROOT) -> None:
    validate_performance(out)
    processed = root / "data" / "processed"
    reports = root / "reports"
    processed.mkdir(parents=True, exist_ok=True)
    reports.mkdir(parents=True, exist_ok=True)

    csv_path = processed / "performance.csv"
    html_path = reports / "performance.html"
    png_path = reports / "performance.png"
    readme_path = root / "README.md"
    start_date = out.index[0].isoformat()
    end_date = out.index[-1].isoformat()
    count = len(out)
    report_note = f"來源：TWSE、Vanguard、中央銀行；共同完整資料截至 {end_date}，共 {count} 個交易日"
    png_note = f"Common data through {end_date}; {count} trading days"
    html_validation_marker = f"009826-vs-VT-report: through={end_date}; observations={count}"

    out.to_csv(csv_path)

    fig = go.Figure()
    fig.add_trace(go.Scatter(x=out.index, y=out["009826_index"], mode="lines", name="009826 貝萊德世界股票"))
    fig.add_trace(go.Scatter(x=out.index, y=out["VT_index"], mode="lines", name="VT（含息總報酬）"))
    fig.update_layout(
        title="009826 vs VT 累積績效（新臺幣，起始值 100）",
        xaxis_title="交易日",
        yaxis_title="累積績效指數",
        hovermode="x unified",
        template="plotly_white",
    )
    fig.add_annotation(
        text=report_note,
        xref="paper",
        yref="paper",
        x=0,
        y=-0.18,
        showarrow=False,
        font={"size": 11, "color": "#555"},
    )
    fig.write_html(html_path, include_plotlyjs="cdn")
    with html_path.open("a", encoding="utf-8") as html_file:
        html_file.write(f"\n<!-- {html_validation_marker} -->\n")

    plt.figure(figsize=(11, 6))
    plt.plot(out.index, out["009826_index"], label="009826")
    plt.plot(out.index, out["VT_index"], label="VT total return")
    plt.title("009826 vs VT cumulative performance (TWD, start = 100)")
    plt.xlabel("Date")
    plt.ylabel("Performance index")
    plt.grid(alpha=0.25)
    plt.legend()
    plt.figtext(0.01, 0.01, png_note, ha="left", fontsize=9)
    plt.tight_layout(rect=(0, 0.04, 1, 1))
    plt.savefig(png_path, dpi=160, metadata={"Description": png_note})
    plt.close()

    update_readme(readme_path, out)
    validate_artifacts(
        csv_path, html_path, png_path, readme_path,
        start_date, end_date, count, html_validation_marker, png_note,
    )


def validate_artifacts(
    csv_path: Path,
    html_path: Path,
    png_path: Path,
    readme_path: Path,
    start_date: str,
    end_date: str,
    count: int,
    html_validation_marker: str,
    png_note: str,
) -> None:
    saved = pd.read_csv(csv_path, parse_dates=["date"])
    if (
        len(saved) != count
        or saved["date"].isna().any()
        or saved["date"].duplicated().any()
        or saved["date"].iloc[0].date().isoformat() != start_date
        or saved["date"].iloc[-1].date().isoformat() != end_date
    ):
        raise RuntimeError("CSV date range or observation count does not match the calculated data.")

    if html_validation_marker not in html_path.read_text(encoding="utf-8"):
        raise RuntimeError("HTML annotation metadata does not match the calculated date range and count.")
    with Image.open(png_path) as image:
        if image.info.get("Description") != png_note:
            raise RuntimeError("PNG metadata does not match the calculated date range and count.")

    readme = readme_path.read_text(encoding="utf-8")
    expected_readme_facts = [end_date, f"共 {count} 個交易日"]
    latest_results = readme.split("## 最新結果\n", 1)[1].split("\n## 資料來源", 1)[0]
    if any(value not in latest_results for value in expected_readme_facts):
        raise RuntimeError("README latest results do not match the calculated date range and count.")


def main() -> None:
    px_009826 = read_source("009826_twse.csv")
    px_vt = read_source("vt_vanguard.csv")
    fx = read_source("usdtwd_cbc.csv")
    distributions = read_distributions()
    out = build_performance(px_009826, px_vt, fx, distributions)
    write_outputs(out)
    print(
        f"Saved {len(out)} observations from {out.index[0]} through {out.index[-1]}; "
        f"009826={out['009826_index'].iloc[-1]:.4f}, VT={out['VT_index'].iloc[-1]:.4f}"
    )


if __name__ == "__main__":
    main()
