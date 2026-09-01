from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd
import plotly.graph_objects as go

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "data" / "source"


def read_source(filename: str) -> pd.DataFrame:
    path = SOURCE / filename
    data = pd.read_csv(path, parse_dates=["date"]).set_index("date").sort_index()
    if data.empty:
        raise RuntimeError(f"Empty source file: {path}")
    if data.index.has_duplicates:
        raise RuntimeError(f"Duplicate dates in source file: {path}")
    return data


def main() -> None:
    px_009826 = read_source("009826_twse.csv")
    px_vt = read_source("vt_vanguard.csv")
    fx = read_source("usdtwd_cbc.csv")

    out = pd.concat(
        [
            px_009826["close"].rename("009826_close"),
            px_vt["close"].rename("VT_close_usd"),
            fx["usd_twd"],
        ],
        axis=1,
        join="inner",
    ).sort_index().dropna()

    out["VT_close_twd"] = out["VT_close_usd"] * out["usd_twd"]
    if out.empty:
        raise RuntimeError("No overlapping TWSE/Vanguard/CBC observations.")

    out["009826_index"] = out["009826_close"] / out["009826_close"].iloc[0] * 100
    out["VT_index"] = out["VT_close_twd"] / out["VT_close_twd"].iloc[0] * 100
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
    fig.add_annotation(
        text="來源：TWSE、Vanguard、中央銀行；共同完整資料截至 2026-08-31",
        xref="paper",
        yref="paper",
        x=0,
        y=-0.18,
        showarrow=False,
        font={"size": 11, "color": "#555"},
    )
    fig.write_html(reports / "performance.html", include_plotlyjs="cdn")

    plt.figure(figsize=(11, 6))
    plt.plot(out.index, out["009826_index"], label="009826")
    plt.plot(out.index, out["VT_index"], label="VT")
    plt.title("009826 vs VT cumulative performance (TWD, start = 100)")
    plt.xlabel("Date")
    plt.ylabel("Performance index")
    plt.grid(alpha=0.25)
    plt.legend()
    plt.tight_layout()
    plt.savefig(reports / "performance.png", dpi=160)
    plt.close()

    print(
        f"Saved {len(out)} observations from {out.index[0]} through {out.index[-1]}; "
        f"009826={out['009826_index'].iloc[-1]:.4f}, VT={out['VT_index'].iloc[-1]:.4f}"
    )


if __name__ == "__main__":
    main()
