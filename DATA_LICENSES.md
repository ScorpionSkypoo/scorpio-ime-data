# 授權

本 repo 的程式（`tools/`、`radar/`）以 MIT License 釋出，Copyright (c) 2026 ScorpionSkypoo。

資料包與 `base/` 詞庫是從下列來源整理、統計而來，各自依原來源的授權條款使用；再散布這些資料時，請一併保留本檔與 `licenses/` 目錄。

每個資料包的名稱、來源與授權也記在 [`packs.json`](packs.json)。

## 詞庫

| 內容 | 來源 | 授權 |
|---|---|---|
| 主詞庫：字詞、讀音、詞頻 | [小麥注音輸入法](https://github.com/openvanilla/McBopomofo)詞庫 | MIT License，著作權聲明見 [`licenses/McBopomofo-MIT.txt`](licenses/McBopomofo-MIT.txt) |
| 流行與口語用語 | 本專案人工整理（[`sources/trendy.txt`](sources/trendy.txt)） | MIT License（同本專案） |
| 台灣地名與路名 | 內政部戶政司〈[全國路名資料](https://data.gov.tw/dataset/35321)〉 | [政府資料開放授權條款－第 1 版](https://data.gov.tw/license) |
| 台灣景點與地標 | 交通部觀光署〈[景點－觀光資訊資料庫](https://data.gov.tw/dataset/7777)〉 | 政府資料開放授權條款－第 1 版 |
| 世界國家與城市 | [Unicode CLDR](https://cldr.unicode.org/) 地區與城市名稱、[Wikidata](https://www.wikidata.org/) | Unicode License v3、CC0 1.0 |
| 世界地標與地理 | [Wikidata](https://www.wikidata.org/) | CC0 1.0 |
| 資訊工程術語（`cs_terms`） | 國家教育研究院〈[電子計算機學術名詞](https://data.gov.tw/dataset/15416)〉 | 政府資料開放授權條款－第 1 版 |
| 教育部國語辭典（`moe_dict`） | 教育部《重編國語辭典修訂本》，經 [g0v 萌典 moedict-data](https://github.com/g0v/moedict-data) 整理 | CC BY-ND 3.0 台灣，著作權屬教育部。依教育部解釋，禁止改作的對象是文字本身，不限制格式轉換與後續應用；這裡只取詞條與注音，未更動內容 |
| 大陸計算機譯名（新詞雷達排除用） | 國家教育研究院〈[兩岸對照名詞－計算機學術名詞](https://data.gov.tw/dataset/15275)〉 | 政府資料開放授權條款－第 1 版 |
| Emoji 關鍵字與分類 | [Unicode CLDR](https://github.com/unicode-org/cldr) zh_Hant 註解（release 48）、[Unicode emoji-test.txt](https://unicode.org/Public/17.0.0/emoji/emoji-test.txt)（Emoji 17.0），原始檔在 [`emoji/`](emoji/) | Unicode License v3，見 [`licenses/Unicode-License-v3.txt`](licenses/Unicode-License-v3.txt) |
| 顏文字 | [w33ble/emoticon-data](https://github.com/w33ble/emoticon-data)（英文標籤對應成中文分類，略過含簡體字的） | MIT License，著作權聲明見 [`licenses/emoticon-data-MIT.txt`](licenses/emoticon-data-MIT.txt) |
| 倉頡、速成碼表 | [Unicode Unihan](https://www.unicode.org/Public/UCD/latest/ucd/) `kCangjie` | Unicode License v3 |
| 英文單字與字頻 | [hermitdave/FrequencyWords](https://github.com/hermitdave/FrequencyWords)（OpenSubtitles 2018） | CC BY-SA 4.0 |
| 英文接續詞 | [OPUS OpenSubtitles v2018](https://opus.nlpl.eu/OpenSubtitles/corpus/version/OpenSubtitles) 英文對白統計 | 依 OPUS 規定引用：P. Lison and J. Tiedemann (2016), *OpenSubtitles2016: Extracting Large Parallel Corpora from Movie and TV Subtitles*, LREC 2016 |

## 接續詞語料

只存「前一個詞 → 下一個詞」的條件機率（ln P(next | prev)），不含原文。

| 來源 | 原始資料 | 授權 |
|---|---|---|
| 維基百科 | [中文維基百科](https://dumps.wikimedia.org/zhwiki/)條目，以 OpenCC `s2twp` 轉台灣正體用語 | CC BY-SA 4.0 |
| PTT | Hugging Face [yuhuanstudio/PTT-pretrain-zhtw](https://huggingface.co/datasets/yuhuanstudio/PTT-pretrain-zhtw)、[Riyuechang/PTT-Corpus-100K_Gossiping-1400-39400_v2](https://huggingface.co/datasets/Riyuechang/PTT-Corpus-100K_Gossiping-1400-39400_v2) | Apache License 2.0 |
| Dcard | Hugging Face [iddle/dcard_conversations](https://huggingface.co/datasets/iddle/dcard_conversations) | MIT License |
| 流行與口語用語 | 本專案人工整理（`sources/trendy.txt` 的 `[pairs]`） | MIT License（同本專案） |

## 台灣生活用語

[`sources/tw_life.txt`](sources/tw_life.txt) 是人工整理的詞表（每個詞都看過），來源：

| 來源 | 原始資料 | 授權 |
|---|---|---|
| taiwan-md 兩岸用語對照（台灣說法） | [frank890417/taiwan-md](https://github.com/frank890417/taiwan-md) `data/terminology` | CC BY-SA 4.0 |
| OpenCC 台灣詞語 | [BYVoid/OpenCC](https://github.com/BYVoid/OpenCC) `data/dictionary/TWPhrases.txt` | Apache License 2.0 |
| 語料裡常出現的新詞 | 上表的 PTT、Dcard 語料與 taiwan-md 文章（CC BY-SA 4.0），`tools/mine_new_words.py` 挑候選後人工選 | 同各語料 |

## 台灣百科專有名詞

[`sources/tw_md.txt`](sources/tw_md.txt) 是人工整理的詞表（每個詞都看過），只取詞條，不含文章內容：

| 來源 | 原始資料 | 授權 |
|---|---|---|
| taiwan-md 文章的標題、tags、連結與粗體詞 | [frank890417/taiwan-md](https://github.com/frank890417/taiwan-md) `knowledge/`，`tools/mine_taiwan_md.py` 挑候選後人工選 | CC BY-SA 4.0 |

## 口語詞頻

[`sources/colloquial_counts.tsv`](sources/colloquial_counts.tsv) 只存「詞 → 在語料裡出現幾次」，不含原文；來源是上表的 PTT 與 Dcard 語料（授權同上表）。
用來把書面詞頻很冷門、口語卻常用的詞在主詞庫與附加詞庫裡的分數拉上來（`tools/apply_colloquial.py`）。

## 相同方式分享（ShareAlike）

維基百科與 FrequencyWords 是 CC BY-SA 4.0，所以從它們衍生的部分（`bg_wiki` 資料包、基底詞庫的 `english_dict` 表）再散布時也要以 CC BY-SA 4.0 授權並註明出處。其他程式碼與資料不受影響。
