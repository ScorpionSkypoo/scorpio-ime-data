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

`minAppVersion` 是能套用這個資料包的最低 App versionCode。`layouts` 預留給之後的鍵盤版面、符號版面、工具列擴充選單。

## 新詞雷達

[`radar.yml`](.github/workflows/radar.yml) 每週一自動執行：

1. 蒐集 Google Trends 台灣熱搜，以及 PTT 熱門看板最近 7 天的文章與推文；也會拿熱搜字去 PTT 搜尋相關文章（[`radar/collect.py`](radar/collect.py)）。
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
