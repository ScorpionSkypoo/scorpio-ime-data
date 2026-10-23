# Scorpio 智慧注音：詞庫資料

[Scorpio 智慧注音](https://github.com/ScorpionSkypoo/ScorpionBopomofo)的線上詞庫。App 每天在 Wi-Fi 下讀一次 [`manifest.json`](manifest.json)，有比手機上新的資料包就下載、驗證 sha256 後套用；也可以在「設定 → 字典與學習 → 線上更新」手動檢查。

## 資料包

| id | 內容 | 類型 |
|---|---|---|
| `trendy` | 流行與口語用語（人工整理＋新詞雷達） | 詞＋接續詞 |
| `tw_places` | 台灣縣市、鄉鎮市區、全國路名 | 詞 |
| `tw_landmarks` | 台灣觀光景點、步道、古蹟、夜市 | 詞 |
| `world_places` | 國家地區名稱、世界主要城市 | 詞 |
| `world_landmarks` | 知名建築、博物館、山岳、湖泊、島嶼 | 詞 |
| `kaomoji` | 顏文字（28 個分類） | 顏文字 |
| `bg_wiki` | 維基百科的詞與詞搭配 | 接續詞 |
| `bg_ptt` | PTT 文章、推文的詞與詞搭配 | 接續詞 |
| `bg_dcard` | Dcard 討論串的詞與詞搭配 | 接續詞 |

主詞庫（小麥注音）、英文、倉頡、Emoji 跟著 App 一起發佈，不做線上更新。

每個資料包是 gzip 壓縮的 SQLite 檔，放在 Release `packs-<版本>`；版本號是建置時間（`2026.10.23.1530`），App 逐段比數字大小。格式見 [`tools/make_packs.py`](tools/make_packs.py)。

`manifest.json` 範例：

```json
{
  "schema": 1,
  "packs": [
    {
      "id": "trendy", "group": "words", "name": "流行與口語用語",
      "version": "2026.10.23", "rows": 154, "size": 4358,
      "sha256": "…", "url": "https://github.com/…/releases/download/packs-2026.10.23/trendy-2026.10.23.db.gz",
      "minAppVersion": 103
    }
  ],
  "layouts": []
}
```

`minAppVersion` 是能套用這個資料包的最低 App versionCode。`plugins` 是工具列擴充功能（見下面），`layouts` 預留給之後的鍵盤版面、符號版面。

## 擴充功能（工具列外掛）

`plugins/<id>.json`，在 App「設定 → 擴充功能」線上安裝，裝好後直接出現在鍵盤工具列上（順序可以在設定裡調）。

外掛是**宣告式**的：只能組合 App 內建的三種動作，不含任何程式碼，也讀不到使用者打的字；只有使用者點了項目時，才會用到目前選取的文字。

| 動作 | 說明 | 欄位 |
|---|---|---|
| `insert`（預設） | 插入文字 | `insert`：可用 `{date:格式}`、`{time:格式}`（Java SimpleDateFormat）、`{weekday}`、`{weekday:short}`、`{roc}`（民國年）、`{selection}` |
| `transform` | 轉換選取的文字 | `op`：`fullwidth`、`halfwidth`、`upper`、`lower`、`title`、`trim_spaces` |
| `open_url` | 用選取的文字開網址 | `url`：只接受 `https://`，`{selection}` 會先做 URL 編碼 |

```json
{
  "schema": 1,
  "id": "datetime",
  "name": "日期時間",
  "icon": "calendar",
  "description": "插入今天的日期、現在時間、星期",
  "tabs": [
    {"name": "日期", "items": [
      {"label": "{date:yyyy/MM/dd}", "insert": "{date:yyyy/MM/dd}"},
      "、"
    ]}
  ]
}
```

- 項目直接寫字串，等於「顯示這段、插入這段」。`label` 也會展開日期標記，面板上看得到實際會插入什麼。
- `id` 要跟檔名一樣。`icon` 是工具列上的圖示，從 App 內建的向量圖示選一個：`calendar`、`symbols`、`text`、`search`、`star`、`note`、`link`、`clipboard`。
- App 不認得的動作會略過，所以之後新增動作不會讓舊版 App 出錯。
- 推上 main 後，[`packs.yml`](.github/workflows/packs.yml) 會驗證格式並發佈有改到的外掛；已安裝的使用者隔天自動更新。

## 新詞雷達

[`radar.yml`](.github/workflows/radar.yml) 每週一自動執行：

1. 蒐集 Google Trends 台灣熱搜、[Threads 熱門話題統計](https://tools.ccea.tw/threadscount/)過去 7 天的話題標題與摘要，以及 PTT 熱門看板最近 7 天的文章與推文；也會拿熱搜字去 PTT 搜尋相關文章（[`radar/collect.py`](radar/collect.py)）。
2. 找出詞庫還沒有的新詞（[`radar/discover.py`](radar/discover.py)）：出現次數、凝固度（整串一起出現的機率遠高於拆開）、左右鄰字的多樣性，並排除能拆成兩個已知詞的組合。
3. 開 PR，把候選詞加進 [`sources/trendy.txt`](sources/trendy.txt)，PR 說明列出每個詞的次數與例句。

**審核**：在 PR 的 Files changed 刪掉不要的詞再合併。合併後 [`packs.yml`](.github/workflows/packs.yml) 會重建 `trendy` 並發佈新版，手機隔天就會更新。

Threads：設定 repo secret `THREADS_ACCESS_TOKEN` 後，雷達會用熱搜字搜尋 Threads。Meta 要通過 `threads_keyword_search` 權限審核才搜得到公開貼文，沒通過只會搜到自己的貼文。

## 手動更新流行用語

直接編輯 [`sources/trendy.txt`](sources/trendy.txt) 推上 main，或在網頁上改，就會自動發佈。格式寫在檔案開頭。

## 重建其他資料包

到 Actions →「建置並發佈資料包」→ Run workflow，填入要重建的 id（例如 `bg_wiki bg_ptt bg_dcard`）。接續詞語料會先下載約 750 MB 的原始語料。

本機建置：

```bash
pip install opencc pyarrow
tools/fetch_corpus.sh work/corpus bg_ptt      # 只在重建接續詞時需要
tools/build.sh work 2026.10.23 trendy bg_ptt  # 產出 work/out（資料包）、work/base（新的基底詞庫），並更新 manifest.json
```

基底詞庫（`base/`，主詞庫＋目前所有資料）放在 Release `base`，App repo 打包時也從這裡取用。

## 授權

程式（`tools/`、`radar/`）是 [MIT License](LICENSE)；詞庫資料依各來源授權，見 [DATA_LICENSES.md](DATA_LICENSES.md)。
