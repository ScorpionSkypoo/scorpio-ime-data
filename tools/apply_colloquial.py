#!/usr/bin/env python3
"""
用口語詞頻（sources/colloquial_counts.tsv，count_colloquial.py 從 PTT、Dcard 算的）把主詞庫與附加詞庫裡
「書面語料幾乎沒出現、口語卻很常用」的詞拉上來：秒殺、盜刷、手環、禮包、正夯、咖哩飯…
在小麥注音的書面分數裡都只有 −6～−8，打字時幾乎排不到。

只動這種詞，其他詞維持原本的分數：
- 書面分數 ≤ RARE（很冷門）、口語語料出現至少 MIN_COUNT 次、混合後至少高 MIN_GAIN 才調
- 新分數 = log10(λ × 書面機率 + (1 − λ) × 口語機率)（換回書面分數的尺度），最高到 CAP（一般常用詞的程度）
- 口語機率先縮放成跟書面的多字詞同樣的總量；多音字詞的口語次數照各讀音原本的比例分；單字不動
整批換成口語詞頻（或同音詞照口語重排）試過：用使用者真實打字記錄 840 次選字重播，第一候選命中
77.1% → 75.7～76.7%，口語比重越高越差（技術、書面詞被往後擠）；只拉冷門詞是 76.7%，換生活詞不再墊底。

單字另外處理：同一個讀音（無聲調）裡的單字照口語次數重新分先後（各半混合），這個讀音的總量不變，
所以不影響整句要切成長詞還是單字。小麥的單字字頻偏書面，ㄇㄚ 排「馬」不是「嗎」、ㄟ 排符號不是「欸」、
ㄌㄚ 的「啦」輸「拉」。「阿」不調：PTT 常把「啊」寫成「阿」。用真實打字記錄 1,140 次選字重播：第一候選
79.9% → 81.1%、前三 91.1% → 92.3%（口語占七成是 81.4%、92.1%，選比較保守的一半）。

原本的分數存在 base_score 欄，每次都從原本的分數重算，重跑不會越疊越多（新加進來的詞 base_score 是空的，先補上）。

用法：apply_colloquial.py <scorpio_dict.db（解壓後）> <colloquial_counts.tsv>
"""
import math
import sqlite3
import sys
from collections import defaultdict

LAMBDA = 0.5
# 單字同讀音重排：書面占的比例，跟不調的字（PTT 的習慣寫法）
SINGLE_LAMBDA = 0.5
SINGLE_EXCLUDE = set("阿")
RARE = -6.0
MIN_COUNT = 100
MIN_GAIN = 1.0
CAP = -4.5

dict_db, counts_path = sys.argv[1:3]

counts = {}
total = 0
for line in open(counts_path, encoding="utf-8"):
    w, c = line.rstrip("\n").split("\t")
    if w == "#total":
        total = int(c)
    else:
        counts[w] = int(c)

db = sqlite3.connect(dict_db)
TABLES = ("dict", "addon_dict")
for t in TABLES:
    if "base_score" not in [r[1] for r in db.execute(f"PRAGMA table_info({t})")]:
        db.execute(f"ALTER TABLE {t} ADD COLUMN base_score REAL")
    db.execute(f"UPDATE {t} SET base_score = score WHERE base_score IS NULL")


def is_multi(w):
    return len(w) >= 2 and not w.startswith("MACRO@")


rows = {t: db.execute(f"SELECT rowid, word, base_score FROM {t}").fetchall() for t in TABLES}

# 書面機率的尺度：主詞庫所有詞 10^分數 的總和（分數是 log10 機率但沒有正規化）
Z = sum(10 ** s for _, w, s in rows["dict"] if not w.startswith("MACRO@"))
word_mass = defaultdict(float)
for t in TABLES:
    for _, w, s in rows[t]:
        if is_multi(w):
            word_mass[w] += 10 ** s
scale = (sum(word_mass.values()) / Z) / (sum(c for w, c in counts.items() if w in word_mass) / total)

# 單字：同讀音（無聲調）裡照口語次數重分，讀音的總量不變（多音字的次數照各讀音的書面比例分）
singles = db.execute("SELECT rowid, word, base_score, toneless FROM dict WHERE length(word) = 1").fetchall()
single_mass = defaultdict(float)
for _, w, s, _ in singles:
    single_mass[w] += 10 ** s
by_reading = defaultdict(list)
for rowid, w, s, tl in singles:
    by_reading[tl].append((rowid, w, s))
single_new = {}
for tl, items in by_reading.items():
    m = sum(10 ** s for _, _, s in items)
    cm = sum(counts.get(w, 0) * 10 ** s / single_mass[w] for _, w, s in items if w not in SINGLE_EXCLUDE)
    for rowid, w, s in items:
        pw = 10 ** s / m
        pc = pw if w in SINGLE_EXCLUDE or cm <= 0 else counts.get(w, 0) * 10 ** s / single_mass[w] / cm
        single_new[rowid] = round(math.log10((SINGLE_LAMBDA * pw + (1 - SINGLE_LAMBDA) * pc) * m), 4)

raised = 0
for t in TABLES:
    upd = []
    for rowid, w, s in rows[t]:
        new = single_new.get(rowid, s) if t == "dict" else s
        if is_multi(w) and s <= RARE and counts.get(w, 0) >= MIN_COUNT:
            p_colloq = counts[w] / total * scale * (10 ** s / word_mass[w])
            cand = math.log10((LAMBDA * 10 ** s / Z + (1 - LAMBDA) * p_colloq) * Z)
            if cand >= s + MIN_GAIN:
                new = round(min(cand, CAP), 4)
                raised += 1
        upd.append((new, rowid))
    db.executemany(f"UPDATE {t} SET score = ? WHERE rowid = ?", upd)
db.commit()
print(f"口語常用的冷門詞拉高 {raised} 筆，單字同讀音重排 {len(single_new)} 筆")
