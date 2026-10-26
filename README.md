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
| `cs_terms` | 資訊工程術語（國家教育研究院電子計算機學術名詞，約 4 萬詞） | 詞，**只能線上安裝、預設不開** |
| `moe_dict` | 教育部國語辭典（重編國語辭典修訂本，約 8.3 萬詞，含成語、書面語，附官方注音） | 詞，**只能線上安裝、預設不開** |
| `bg_wiki` | 維基百科的詞與詞搭配 | 接續詞 |
| `bg_ptt` | PTT 文章、推文的詞與詞搭配 | 接續詞 |
| `bg_dcard` | Dcard 討論串的詞與詞搭配 | 接續詞 |

App 內建、一律使用的資料也能線上更新（manifest 標 `"system": true`，App 不列開關、有新版就自動更新；App v1.2.7（versionCode 172）起才認得）：

| 建置時指名 | 內容 | 來源檔 |
|---|---|---|
| `core` | 主詞庫（小麥注音），約 6 MB，有改才發佈 | base |
| `emoji` | Emoji 關鍵字與面板分類 | `emoji/zh_Hant.xml`（CLDR 繁中註解）、`emoji/emoji-test.txt`（Unicode） |
| `en` | 英文詞頻與接續 | base |
| `cangjie_table` | 倉頡／速成碼表（SCD 的 id 是 `cangjie`，跟倉頡版面同名，建置時用這個名字區分） | base |

例：Unicode 出新版 Emoji 時，換掉 `emoji/` 的兩個檔，手動執行「建置並發佈資料包」填 `emoji`。

## 鍵盤設定

[`config/ime.json`](config/ime.json) 是跟著資料更新的鍵盤設定（App v1.2.7 起），改了推上 main 就會自動建置發佈，手機每天檢查時套用：

- `lazySyllables`：只打聲母或介音時展開成哪些音節（`"ㄨ": ["ㄨㄛ", …]`，越前面越常用）
- `kaomojiKeywords`：候選詞是這些詞時穿插哪一類顏文字（分類名稱要是顏文字資料包裡有的）
- `fuzzyPriors`：讀音混用的預設比例（鍵是「打的注音＋想打的注音」，ㄣ／ㄥ 前面是 ㄧ 時加 `i`；每個人會照自己的選字調整）
- `symbols`：符號鍵盤，`zh` 是從中文切過來、`en` 是從英文，每頁兩排各 10 個、第三排 7 個

`tools/make_configs.py` 照 App 的規則檢查，不合就中止、不發佈。

`packs.json` 的 `bundled: false` 表示 App 不內建、只能在「字典與學習 → 可下載的詞庫」打開開關下載；`default: false` 表示預設不開。

每個資料包是 gzip 壓縮的 SCD 二進位詞庫（`<id>-<版本>.scd.gz`），放在 Release `packs-<版本>`；App 解壓後直接 mmap 查詢，不經 SQLite。版本號是建置時間（`2026.10.23.1530`），App 逐段比數字大小。格式見 [`docs/scd-format.md`](docs/scd-format.md)、[`tools/scd.py`](tools/scd.py)；建置用的 SQLite 基底詞庫（Release `base` 的 `scorpio_*.db.gz`）轉成 SCD 的流程在 [`tools/build_scd.py`](tools/build_scd.py)、[`tools/make_packs.py`](tools/make_packs.py)，`tools/verify_scd.py` 會逐鍵比對 SCD 與 SQLite 的查詢結果。

`manifest.json` 範例：

```json
{
  "schema": 1,
  "packs": [
    {
      "id": "trendy", "group": "words", "name": "流行與口語用語",
      "version": "2026.10.23", "rows": 154, "size": 4358,
      "sha256": "…", "url": "https://github.com/…/releases/download/packs-2026.10.23/trendy-2026.10.23.scd.gz",
      "minAppVersion": 103
    }
  ],
  "layouts": []
}
```

`minAppVersion` 是能套用這個資料包的最低 App versionCode。`plugins` 是工具列擴充功能、`layouts` 是鍵盤版面（都見下面）。

## 擴充功能（工具列外掛）

`plugins/<id>.json`，在 App「設定 → 擴充功能」線上安裝，裝好後直接出現在鍵盤工具列上（順序可以在設定裡調）。

外掛是**宣告式**的：只能組合 App 內建的三種動作，不含任何程式碼，也讀不到使用者打的字；只有使用者點了項目時，才會用到目前選取的文字。

| 動作 | 說明 | 欄位 |
|---|---|---|
| `insert`（預設） | 插入文字 | `insert`：可用 `{date:格式}`、`{time:格式}`（Java SimpleDateFormat）、`{weekday}`、`{weekday:short}`、`{roc}`（民國年）、`{selection}`；`date`、`weekday`、`roc` 可加天數，例如 `{date+1:M/d}` 是明天、`{weekday-1}` 是昨天星期幾（App versionCode 136 起） |
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
- 項目可加 `title`：面板上顯示在內容上方的小標題（例如「今天」「明天」），一樣會展開標記（App versionCode 136 起）。
- 用到新功能的外掛要寫 `minAppVersion`（App 的 versionCode），舊版 App 就不會裝到看不懂的版本。
- `id` 要跟檔名一樣。`icon` 是工具列上的圖示，從 App 內建的向量圖示選一個：`calendar`、`symbols`、`text`、`search`、`star`、`note`、`link`、`clipboard`。
- App 不認得的動作會略過，所以之後新增動作不會讓舊版 App 出錯。
- 推上 main 後，[`packs.yml`](.github/workflows/packs.yml) 會驗證格式並發佈有改到的外掛；已安裝的使用者隔天自動更新。

## 鍵盤版面

`layouts/<id>.json`，在 App「設定 → 輸入法」線上安裝，裝好後就能用地球鍵切換。大千注音內建在 App，不在這裡；其他版面都用 QWERTY 鍵盤，鍵上標該版面的符號。

版面也是**宣告式**的：只能選 App 內建的打字方式（`engine`），不含程式碼。

| engine | 說明 | 欄位 |
|---|---|---|
| `zhuyin26` | 26 鍵注音（一個鍵代表一到兩個注音，自動判斷） | `keymap`：41 個小寫字母，依序對應 ㄅ…ㄙ、ㄧㄨㄩ、ㄚ…ㄦ、˙ˊˇˋ（跟 libchewing `key2pho.c` 同格式） |
| `pinyin` | 漢語拼音 | — |
| `cangjie` | 倉頡（碼表內建在 App） | — |
| `quick` | 速成 | — |

```json
{
  "schema": 1,
  "id": "hsu",
  "name": "注音（許氏）",
  "language": "zh-TW",
  "languageName": "中文（台灣）",
  "spaceLabel": "注音·許氏",
  "description": "許氏 26 鍵：一個鍵代表一到兩個注音，自動判斷。",
  "engine": "zhuyin26",
  "keymap": "bpmfdtnlgkhjvcjvcrzasexuyhgeiawomnkllsdfj",
  "sort": 10
}
```

- `id` 要跟檔名一樣；`language`（BCP 47 語言標籤）與 `languageName` 決定設定頁「新增輸入法」裡分在哪個語言底下；`spaceLabel` 是空白鍵上的字；`sort` 決定設定頁與切換的順序（小的在前）。
- `requires`（選填）列出這個版面要用的資料包 id（要在 `packs.json` 裡），App 會先下載好資料包再裝上版面。

### 字鍵排（schema 2，選填）

沒寫 `keys` 的版面用內建的 QWERTY。要換字鍵的排法（例如 Dvorak），寫 `"schema": 2`、`keys`，另外要寫 `minAppVersion`（第一個看得懂 `keys` 的 App versionCode，舊版 App 會整個不收這個版面）。最下排（符號、逗號、地球、空白、句號、Enter）固定由 App 畫，不能改。

```json
"keys": {
  "columns": 10,
  "numberRow": "1234567890",
  "rows": [
    "pyfgcrl",
    "aoeuidhtns",
    ["qjkxbmwvz", {"special": "backspace"}]
  ]
}
```

- `columns`：10～12 欄（預設 10），一欄＝鍵盤寬 ÷ 欄數。`numberRow`（選填）只能是數字。
- `rows`：1～4 排。每排可以是字串（一個字一鍵），或陣列：字串是一串字鍵、`{"key":"x","width":1.5}` 是一個字鍵（寬 1～2 欄）、`{"special":"shift"}`／`{"special":"backspace"}` 是 Shift／刪除鍵（至少 1 欄；沒寫 `width` 就平分這排剩下的寬度）。
- 每排加起來不能超過 `columns`，不足的部分左右平分留空；刪除鍵剛好一個、Shift 最多一個；同一個字只能出現一次，`* : ;` 與空白不能當字鍵。
- 目前的打字方式都用英文字母，所以字鍵要剛好是 a–z 各一次。
- 按鍵落點學習依鍵位分組：鍵位跟內建 QWERTY 一樣的版面共用原本的學習資料；鍵位不同的另外學，版面改版時 App 會依位置把舊的習慣搬過去。
- 不合規則的版面 `make_layouts.py` 會直接失敗，App 端也會拒收。
- App 不認得的 `engine` 會略過，所以之後新增打字方式不會讓舊版 App 出錯。
- 推上 main 後，[`packs.yml`](.github/workflows/packs.yml) 會驗證格式並發佈有改到的版面；已安裝的使用者隔天自動更新。

## 新詞雷達

[`radar.yml`](.github/workflows/radar.yml) 每週一自動執行：

1. 蒐集 Google Trends 台灣熱搜、[Threads 熱門話題統計](https://tools.ccea.tw/threadscount/)過去 7 天的話題標題與摘要、[公視新聞網 RSS](https://news.pts.org.tw/xml/newsfeed.xml) 的標題與摘要，以及 PTT 熱門看板最近 7 天的文章與推文；也會拿熱搜字去 PTT 搜尋相關文章（[`radar/collect.py`](radar/collect.py)）。
   另外取中文維基百科最近 7 天的新條目與每天瀏覽最多的條目標題（只取標題）。
2. 找出詞庫還沒有的新詞（[`radar/discover.py`](radar/discover.py)）：出現次數、凝固度（整串一起出現的機率遠高於拆開）、左右鄰字的多樣性，並排除能拆成兩個已知詞的組合。
3. 排除簡體字與大陸用語：
   - OpenCC（`pip install opencc` 每次裝 PyPI 最新版）：`s2t` 轉換會變的是簡體字；`s2tw` 跟 `s2twp` 結果不同的是大陸用語。
   - OpenCC GitHub master 最新的 [`TWPhrases.txt`](https://github.com/BYVoid/OpenCC/blob/master/data/dictionary/TWPhrases.txt)：每次執行直接下載，左欄的大陸用語都排除（不必等 OpenCC 發新版）。
   - [`sources/mainland_terms.txt`](sources/mainland_terms.txt)：OpenCC 沒收的大陸用語（靠譜、老鐵、內卷…），人工維護。
   - [`sources/mainland_terms_naer.txt`](sources/mainland_terms_naer.txt)：國家教育研究院〈兩岸對照名詞－計算機〉裡跟台灣譯名不同的大陸譯名。
4. 維基條目標題轉成台灣正體，詞庫沒有、在台灣語料（PTT、公視…）也出現 3 次以上的才收（維基中文多半是大陸寫的，只在維基出現的不收）。
5. taiwan-md：拿最新的 taiwan-md 跑 [`tools/mine_taiwan_md.py`](tools/mine_taiwan_md.py)，還沒看過的專有名詞（前 40 個）加進 [`sources/tw_md.txt`](sources/tw_md.txt)。
6. 開 PR，把候選詞加進 [`sources/trendy.txt`](sources/trendy.txt)（新詞、維基條目）與 `sources/tw_md.txt`，PR 說明列出每個詞的次數與例句、taiwan-md 新詞要確認讀音的破音字。

**審核**：在 PR 的 Files changed 刪掉不要的詞再合併（taiwan-md 不收的詞移到 `tw_md.txt` 檔尾的「# 不收：」，下次就不會再列）。合併後 [`packs.yml`](.github/workflows/packs.yml) 會重建 `trendy`（改到 `tw_md.txt` 也重建 `tw_md`）並發佈新版，手機隔天就會更新。

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

### 台灣生活用語

[`sources/tw_life.txt`](sources/tw_life.txt)：主詞庫沒有的常用詞（免運、截圖、貼文、按讚、執行緒…），人工整理，來源寫在檔案開頭。
新詞候選用 `tools/mine_new_words.py`（PTT、Dcard 等大語料的新詞發現，同 `radar/discover.py` 的判斷方式）找，看過再加。

### 台灣百科專有名詞

[`sources/tw_md.txt`](sources/tw_md.txt)：taiwan-md 文章裡主詞庫沒有的人名、團體、作品、地名、制度用語（黃仁勳、草東沒有派對、麟洋配…）。
候選用 `tools/mine_taiwan_md.py <taiwan-md 目錄> <dict.db> <輸出 tsv> [語料目錄]` 找：已經看過的詞（收錄的、`# 不收：`）不會再列；
taiwan-md 的文章大多是 AI 寫的，給語料目錄會另外數 PTT、Dcard、維基的次數，真人語料沒出現的多半是 AI 文章才有的詞組。

### 口語詞頻

小麥注音的詞頻來自書面語料，秒殺、手環、咖哩飯這類生活詞分數很低。`tools/build.sh` 每次建置都會用
[`sources/colloquial_counts.tsv`](sources/colloquial_counts.tsv)（PTT、Dcard 約 1.9 億字裡每個詞出現幾次）
把「書面很冷門、口語常用」的詞拉上來，單字則在同讀音裡照口語次數重排（ㄇㄚ 先「嗎」），其他詞不動（規則寫在 `tools/apply_colloquial.py` 開頭）。重算次數：

```bash
tools/fetch_corpus.sh work/corpus bg_ptt bg_dcard
gunzip -c base/scorpio_dict.db.gz > work/dict.db
tools/count_colloquial.py work/dict.db work/corpus sources/colloquial_counts.tsv
```

### 主詞庫修正

[`sources/core_fixes.txt`](sources/core_fixes.txt)：口語加分之後套用（`tools/apply_core_fixes.py`）。刪掉台灣不這樣說的支語（視頻、激光、概率…，兩岸都用的點擊、查找不刪）
與錯字，壓低搶走常用詞位置的冷門同音詞（是有 → 室友、遊資 → 郵資），修正或補上讀音（菠蘿麵包 ㄅㄛ）。
台灣地名裡路名資料的異體字（双十街、山脚路）同時換回正體。刪掉的支語也列在 `sources/mainland_terms.txt`，新詞雷達不會再撿回來。

## 授權

程式（`tools/`、`radar/`）是 [MIT License](LICENSE)；詞庫資料依各來源授權，見 [DATA_LICENSES.md](DATA_LICENSES.md)。
