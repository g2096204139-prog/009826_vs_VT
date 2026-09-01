# 009826 vs VT

比較 009826 貝萊德世界股票與 Vanguard Total World Stock ETF（VT）的每日累積績效。

## 比較規格

- 起算日：009826 上市日 2026-08-03
- 起始值：兩者均標準化為 100
- 顯示幣別：新臺幣
- 009826：使用台股調整後收盤價；目前為不配息 ETF
- VT：使用調整後收盤價，代表股息再投入後的價格系列
- 匯率：USD/TWD，用於將 VT 換算為新臺幣
- 主圖：價格／調整後價格累積績效
- 輔助欄位：009826 市價、VT 美元價格、匯率、資料來源與擷取時間

## 目錄

- `scripts/fetch_and_calculate.py`：抓取資料並計算累積績效
- `data/processed/performance.csv`：整理後的每日資料
- `reports/performance.html`：互動式績效圖
- `reports/performance.png`：靜態圖
- `.github/workflows/daily-update.yml`：每日更新工作流程

## 執行

```bash
python -m pip install -r requirements.txt
python scripts/fetch_and_calculate.py
```

## 重要限制

009826 於 2026-08-03 才上市，歷史資料很短，不能據此推論長期績效。Yahoo Finance 資料僅作為可重現的初始資料來源；正式報告應以貝萊德官方淨值、追蹤差距及 TWSE 資料交叉核對。

本專案不納入個人交易手續費、證券交易稅、匯款費、複委託費用或個人稅務結果。圖表不是投資建議。
