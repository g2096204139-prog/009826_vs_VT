# 009826 vs VT

比較 009826 貝萊德世界股票與 Vanguard Total World Stock ETF（VT）的每日累積績效。

目前圖檔 reports/performance.png 仍是未含配息版本；新程式合併後的下一次資料流程會重新產圖。

## 最新結果

- 共同完整資料：2026-08-03 至 2026-09-24，共 38 個交易日
- 009826：99.8016
- VT（含息總報酬，配息以除息日收盤再投入並換算新臺幣）：99.1213
- 差距：009826 領先 VT 0.6803 個百分點
- VT 配息納入 2026-09-18 每股 0.4084 美元；以現有來源 CSV 計算，38 個共同日期
- 基準：兩者於 2026-08-03 均標準化為 100

## 資料來源

- 009826：臺灣證券交易所（TWSE）個股日成交資訊
- VT 收盤價與每股實際配息、除息日：Vanguard 官方價格／配息頁
- USD/TWD：中華民國中央銀行 NT$/US$ Closing Rate

每次更新以官方來源取得資料；成功後才合併既有 CSV，來源失敗時保留快取並使工作流程失敗。VT 原始配息資料獨立保存於 data/source/vt_distributions.csv，含除息日、每股美元配息、記錄日、發放日、配息類型、來源網址與擷取時間。

## 比較規格

- 起算日：009826 上市日 2026-08-03
- 顯示幣別：新臺幣
- 009826：市場收盤價
- VT：以 Vanguard 官方每股配息金額，於除息日收盤價視為再投入，形成美元總報酬指數，再按同日央行 USD/TWD 收盤匯率換算
- 比較日期：TWSE、Vanguard 與央行均有資料的共同日期；VT 配息總報酬先按完整 Vanguard 交易日計算，再對齊共同日期
- 起始值：兩者均為 100
- 配息模型不扣美國預扣稅、交易成本或匯款費，也不模擬個別券商實際入帳時間或零股處理

## 目錄

- scripts/update_sources.py：更新 TWSE、Vanguard 價格／配息、中央銀行來源資料
- scripts/fetch_and_calculate.py：合併資料、計算累積績效並產圖
- data/source/：來源原始資料
- data/processed/performance.csv：共同日期的整理資料
- reports/performance.html：互動式線圖
- reports/performance.png：靜態線圖
- .github/workflows/daily-update.yml：平日自動更新

## 驗證

GitHub Actions 每次產生報告時，會核對 CSV 的日期範圍與筆數、HTML 註記、PNG 中繼資料及本 README 最新結果區塊。任何一項與本次共同資料不一致，工作流程就會失敗。

## 執行

    python -m pip install -r requirements.txt
    python -m playwright install chromium
    python scripts/update_sources.py
    python scripts/fetch_and_calculate.py

## 重要限制

009826 上市時間很短，不能由目前結果推論長期績效。未納入個人交易手續費、證券交易稅、匯款費、複委託費用或個人稅務結果；圖表不是投資建議。
