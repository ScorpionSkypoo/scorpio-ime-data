# SCD（Scorpio Compiled Dictionary）格式

App 內建與線上下載的詞庫都是 SCD：唯讀的二進位檔，App 用 `mmap` 直接查，不經 SQLite。
檔案頁是乾淨的唯讀頁，系統缺記憶體時可以直接丟掉，不算行程自己的記憶體。

實作：Python 寫入端 [`tools/scd.py`](../tools/scd.py)；App 端讀 `ScdFile.kt`、寫 `ScdWriter.kt`
（手機上把使用者匯入的詞庫編成 SCD，兩邊對同一份資料寫出的檔案每個 byte 都一樣，
由 `tools/scd_fixture.py` 產生的固定檔做單元測試）。

## 檔案結構（全部 little-endian）

| 位置 | 內容 |
|---|---|
| 0–31 | 檔頭：magic `SCD1`、版本（1）、meta 位置、meta 長度、區段目錄位置、區段數、檔案長度、保留 |
| meta | JSON（UTF-8，鍵排序、無空白）：`id`、`group`、`version`、`name`、`source`、`license`、`bundled`、`default`、`category`、`sort`、`rows`（各表筆數） |
| 區段目錄 | 每筆 32 bytes：名稱 24 bytes（NUL 補齊）＋位置＋長度 |
| 區段 | 8 bytes 對齊；字串表 `str.off`／`str.chr`（UTF-16），其餘是 u32／f64 陣列或索引（`.k` 鍵、`.s` 起點、`.p` 資料列） |

字串依 UTF-16 code unit 排序後編號，索引的鍵依同樣順序排，查詢用二分搜尋。
同一個鍵底下的資料先依分數（或優先序）排、同分時依原本 SQLite 的掃描順序，所以結果跟舊版 `ORDER BY score DESC LIMIT n` 逐筆一致。

## 表

| 表 | 內容 |
|---|---|
| `w` | 詞（主詞庫、附加詞庫、匯入詞庫）：reading、toneless、word、score，索引 `w.tl`（clustered）、`w.rd`、`w.in`、`w.fn`、`w.wd`、`w.tp`（熱門前綴預先算好前 16 名） |
| `b` | 詞與詞的接續（ln P(next｜prev)） |
| `e` | 英文單字與英文接續：`e.word`（小寫，依字串順序）、`e.score`、`e.disp`（顯示的寫法，iPhone、Paris；可以沒有，舊版 App 不讀）、`eb.next`，索引 `eb.pv` |
| `cj` | 倉頡碼表 |
| `em` | Emoji（關鍵字、分類） |
| `k` | 顏文字（讀音、分類） |

## 版本

meta 的 `version` 是資料包版本（`2026.10.23.1530`）。手機上同一個 `id` 有內建與下載兩份時用版本新的；
App 改版內建了更新的版本，下載的舊檔會被刪掉。
