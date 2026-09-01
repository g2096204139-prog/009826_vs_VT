from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import time

import matplotlib.pyplot as plt
import pandas as pd
import plotly.graph_objects as go
import yfinance as yf

ROOT = Path(__file__).resolve().parents[1]
START = "2026-08-03"
END = (pd.Timestamp.now(tz="Asia/Taipei").normalize() + pd.Timedelta(days=1)).strftime("%Y-%m-%d")
TICKERS = {"009826": "009826.TW", "VT": "VT", "USDTWD": "TWD=X"}
MAX_RETRIES = 4
RETRY_DELAYS = (20, 45, 90, 180)


def download(symbol: str, start: str, end: str, *, auto_adjust: bool = False) -> pd.DataFrame:
    raw_dir = ROOT / "data" / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)
    mode = "adjusted" if auto_adjust else "raw"
    cache_path = raw_dir / f"{symbol.replace('=', '_').replace('.', '_')}_{mode}.csv"
    if cache_path.exists():
        cached = pd.read_csv(cache_path, index_col=0, parse_dates=True)
        if not cached.empty:
            return cached

    last_error: Exception | None = None
    for attempt in range(MAX_RETRIES):
        try:
            data = yf.download(
                symbol,
                start=start,
                end=end,
                auto_adjust=auto_adjust,
                progress=False,
                threads=False,
            )
            if isinstance(data.columns, pd.MultiIndex):
                data.columns = data.columns.get_level_values(0)
            if not data.empty:
                data.to_csv(cache_path)
                return data
            last_error = RuntimeError(f"No data returned for {symbol}")
        except Exception as exc:
            last_error = exc
        if attempt < MAX_RETRIES - 1:
            delay = RETRY_DELAYS[attempt]
            print(f"{symbol}: attempt {attempt + 1} failed; retrying in {delay}s")
            time.sleep(delay)
    raise RuntimeError(f"Unable to download {symbol} after {MAX_RETRIES} attempts: {last_error}")


def adjusted_close(symbol: str, start: str, end: str) -> pd.Series:
    data = download(symbol, start, end, auto_adjust=True)
    return data["Close"].rename(symbol)


def main() -> None:
    px_009826 = download(TICKERS["009826"], START, END)
    px_vt = download(TICKERS["VT"], START, END)
    fx = download(TICKERS["USDTWD"], START, END)

    out = pd.concat(
        [
            px_009826["Close"].rename("009826_close"),
            px_009826["Adj Close"].rename("009826_adj_close"),
            px_vt["Close"].rename("VT_close_usd"),
            adjusted_close(TICKERS["VT"], START, END).rename("VT_adj_close_usd"),
            fx["Close"].rename("usd_twd"),
        ],
        axis=1,
    ).sort_index()

    out["VT_adj_close_twd"] = out["VT_adj_close_usd"] * out["usd_twd"]
    out = out.loc[out.index >= START].dropna(subset=["009826_adj_close", "VT_adj_close_twd"])
    if out.empty:
        raise RuntimeError("No overlapping 009826/VT/USD-TWD observations.")

    out["009826_index"] = out["009826_adj_close"] / out["009826_adj_close"].iloc[0] * 100
    out["VT_index"] = out["VT_adj_close_twd"] / out["VT_adj_close_twd"].iloc[0] * 100
    out["difference_pp"] = out["009826_index"] - out["VT_index"]
    out.index = pd.to_datetime(out.index).date
    out.index.name = "date"
    out["retrieved_at_utc"] = datetime.now(timezone.utc).isoformat()

    processed = ROOT / "data" / "processed"
    reports = ROOT / "reports"
    processed.mkdir(parents=True, exist_ok=True)
    reports.mkdir(parents=True, exist_ok=True)

    out.to_csv(processed / "performance.csv")

    fig = go.Figure()
    fig.add_trace(go.Scatter(x=out.index, y=out["009826_index"], mode="lines", name="009826 貝萊德世界股票"))
    fig.add_trace(go.Scatter(x=out.index, y=out["VT_index"], mode="lines", name="VT"))
    fig.update_layout(
        title="009826 vs VT 累積績效（新臺幣，起始值 100）",
        xaxis_title="交易日",
        yaxis_title="累積績效指數",
        hovermode="x unified",
        template="plotly_white",
    )
    fig.write_html(reports / "performance.html", include_plotlyjs="cdn")

    plt.figure(figsize=(11, 6))
    plt.plot(out.index, out["009826_index"], label="009826 貝萊德世界股票")
    plt.plot(out.index, out["VT_index"], label="VT")
    plt.title("009826 vs VT 累積績效（新臺幣，起始值 100）")
    plt.xlabel("交易日")
    plt.ylabel("累積績效指數")
    plt.grid(alpha=0.25)
    plt.legend()
    plt.tight_layout()
    plt.savefig(reports / "performance.png", dpi=160)
    plt.close()

    print(f"Saved {len(out)} observations through {out.index[-1]}")


if __name__ == "__main__":
    main()
