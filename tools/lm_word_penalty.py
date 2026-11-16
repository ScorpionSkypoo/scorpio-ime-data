#!/usr/bin/env python3
"""
用字級語言模型的分數，幫附加詞庫裡「固定分數」的詞（教育部國語辭典、資訊工程術語）扣分：罕用詞不再跟常用詞同分。
那兩包每個詞都是同一個分數（−6.6、−6.8），「氄刺」跟「詞綴」一樣高，比主詞庫的「冗詞」（−7.47）還前面。

輸入 words_lm.tsv（tools/lm_score_colab.py 在 Colab 用 ime-lm 的 lm_v2.pt 算的）：資料包、詞、分數、中性上下文的 log10 機率、不在模型字表的字數
輸出 sources/lm_word_penalty.tsv：詞、扣分（build_addon_dicts.py 建詞時扣掉）

只扣不加：字級模型看的是「這串字常不常出現」，不是「這是不是一個詞」，「可能的」「多資料」這種片段分數很高，
拿來加分會把它們拉上來。扣分＝(主詞庫同字數的詞，模型分數的中位數 − 這個詞的模型分數) × SLOPE，
加上不在模型字表（訓練語料前 8,000 字以外）的罕用字每字 UNK，最多扣 CAP。
SLOPE 是主詞庫兩字詞「詞庫分數 對 模型分數」的迴歸斜率（相關係數 0.74；三字 0.61、四字以上 0.48，詞庫本身比較平）。

用法：lm_word_penalty.py <words_lm.tsv> <輸出 tsv>
"""
import statistics
import sys
from collections import defaultdict

SLOPE = 0.5
UNK = 1.5
CAP = 3.0
MIN = 0.05
PACKS = ("moe_dict", "cs_terms")

src, out = sys.argv[1:3]
rows = [line.rstrip("\n").split("\t") for line in open(src, encoding="utf-8")]


def bucket(w):
    return min(len(w), 4)


core = defaultdict(list)
for pack, w, _, lm, unk in rows:
    if pack == "core" and unk == "0":
        core[bucket(w)].append(float(lm))
median = {k: statistics.median(v) for k, v in core.items()}

pen = {}
for pack, w, _, lm, unk in rows:
    if pack in PACKS:
        p = min(CAP, max(0.0, median[bucket(w)] - float(lm)) * SLOPE + UNK * int(unk))
        if p >= MIN:
            pen[w] = max(pen.get(w, 0.0), round(p, 2))

with open(out, "w", encoding="utf-8") as f:
    f.write("# 附加詞庫的語言模型扣分（tools/lm_word_penalty.py 產生，不要手改）\n")
    f.write("# 主詞庫字數中位數 " + " ".join(f"{k}字{v:.2f}" for k, v in sorted(median.items())) + "\n")
    for w in sorted(pen):
        f.write(f"{w}\t{pen[w]}\n")
print(f"扣分 {len(pen)} 詞")
