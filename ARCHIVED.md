# 009826_vs_VT 已封存

封存日期：2026-10-19（Asia/Taipei）
狀態：ARCHIVED_BY_USER_REQUEST / RESEARCH_INCOMPLETE
依據：使用者於本對話明確要求「請封存這個專案」。

## 封存範圍

保留程式、原始資料、整理資料、PNG/HTML 報告、方法 v0.2、GitHub 歷史及 Drive 原始檔案 ID；停止主動研究推進與每日資料更新。封存不代表研究完成，也不代表所有驗證通過。

本次採專案作業封存：README 與正式 Drive 入口標記已封存，每日 workflow 移除 schedule/push 觸發，且 job 設為永遠略過。這不是將 GitHub repository 的平台 archived flag 設為 true；目前 connector 沒有該設定能力。

## 固定資料版本

最後資料 commit：`cb047ec8140646496ca61bfa83cdb248b57c1aba`。
最後成功工作流程：[2026-10-16 Daily performance update](https://github.com/g2096204139-prog/009826_vs_VT/actions/runs/38913062091)。
共同資料：2026-08-03～2026-10-15，共 50 個交易日。
末值：009826 100.0000；VT 理論含息 TWD 100.1658；差值 -0.1658 個百分點。
品質結果：`PASS_WITH_CALENDAR_LIMITATION`，沒有列出錯誤，但官方日曆尚未全面驗證。

| 來源 | 列數 | 最新觀察／事件日 | SHA-256（固定品質摘要記錄） |
|---|---:|---|---|
| 009826_twse.csv | 52 | 2026-10-16 | `76293da242e3294cf8af903c9f6d72aa59bc7d39a2f7b436865b980b4787c2fc` |
| vt_vanguard.csv | 53 | 2026-10-15 | `16e3e1b71adceb9ab3c801141351b5291bd750a658cd88156983a9faa45e8b2b` |
| usdtwd_cbc.csv | 52 | 2026-10-16 | `3cb2b6c6b38596f10d4a79562832f234f7d1ce97157451db4a8b2799f60606ba` |
| vt_distributions.csv | 1 | 2026-09-18 | `9fcd3e04533c3b1f36c626a342aaf16ef4f86e227b1076957791977f6e70f5b5` |

最新 VT 除息日 2026-09-18；配息擷取時間 2026-10-16T14:07:34.205279+00:00。兩者不同，不以除息日判定來源過期。封存不追加新行情、不手動補值。

## 已完成與保留限制

已完成：每日市價／VT 理論含息 TWD 比較、v0.2 方法定義、基本品質摘要、四來源暫存驗證及正常例外還原；先前 15 項測試通過。
未完成並停止推進：完整交易／發布日曆驗證；10/16 VT 價格後續補入確認；10/8～10/15 差距拆解；兩檔官方 NAV 與各自含息基準資料取得性；個人稅費與實際持有淨報酬。
既有短樣本不能推出長期優劣；兩檔追蹤不同指數，差值不是同一指數追蹤誤差。未執行正式回測、模擬交易或交易。

## 研究與資料入口

- [原固定入口](https://drive.google.com/file/d/1BiGUK0G6LqPwN8LiO5O8uCsLXrEn8ZzZ/view)
- [資料清單](https://drive.google.com/file/d/1FgV2gQKKbiguM4pisKgHRJOQBuKkX5yb/view)
- [上次完整狀態](https://drive.google.com/file/d/1H1QpzapDoNJ9m3B4RNrQr635-iBuUCcr/view)
- [比較規格 v0.2](https://drive.google.com/file/d/13fJ6ZZUyStalARRTQC76ibgH4V8qpO07/view)
- [固定資料與報告版本](https://github.com/g2096204139-prog/009826_vs_VT/tree/cb047ec8140646496ca61bfa83cdb248b57c1aba)

## 日後恢復

使用者明確要求恢復後，先讀本封存紀錄及固定資料 commit，檢查官方來源與方法變更、實際缺日及權限，再決定是否恢復更新。原每日 workflow 完整保存在 `docs/archive/daily-update.before-archive.yml`，不自動重新啟用。任何正式回測或交易仍需另行授權。

## ChatGPT 每週任務檢查

本次透過可用的 automations.peek 查閱 20 個任務，沒有找到「推進 009826_vs_VT 研究」或同專案的週六 10:00 任務。故未宣稱週報任務已停用；其 ID／管理範圍尚未定位，需在該任務所屬介面的 Tasks／Scheduled 清單停用。其他專案任務未變更。
