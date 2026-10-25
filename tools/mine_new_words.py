#!/usr/bin/env python3
"""
從大量語料找主詞庫沒有的常用詞（radar/discover.py 的大語料版）：

新詞在主詞庫的分詞裡會被切成一串單字（截圖 → 截／圖、免運 → 免／運），所以只數「連續單字」裡的 2～4 字組合，
不必像 discover.py 把語料所有字串都放進記憶體。判斷方式同 discover.py：
  - 頻率夠高（MIN_FREQ）
  - 凝固度：整串一起出現的機率遠高於任何一種拆法（PMI 取最小的那個切點，≥ MIN_PMI）
  - 自由度：左右接的字夠多樣（鄰字熵，≥ MIN_ENTROPY；第二輪只對候選詞重掃語料算）
  - 不在詞庫、不能整個拆成詞庫裡兩字以上的詞、頭尾不是虛詞、不是簡體字或大陸用語
結果是候選清單（詞、次數、凝固度、自由度、例句），要人看過才收進 sources/tw_life.txt。

用法：mine_new_words.py <scorpio_dict.db（解壓後）> <語料目錄> <輸出 tsv> [--md 目錄...] [--top 4000]
  語料目錄：pttpre.parquet、pttqa.parquet、dcard.parquet；--md：Markdown 文章目錄（例如 taiwan-md 的 knowledge/）
"""
import argparse
import math
import multiprocessing as mp
import os
import re
import sys
import time
from collections import Counter, defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import zhseg  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from radar.discover import EDGE_STOP, END_STOP, is_simplified, splits_into_known  # noqa: E402

MIN_FREQ = 30
MIN_PMI = 3.0
MIN_ENTROPY = 1.2
MAX_N = 4

ap = argparse.ArgumentParser()
ap.add_argument("dict_db")
ap.add_argument("corpus")
ap.add_argument("out")
ap.add_argument("--md", nargs="*", default=[])
ap.add_argument("--top", type=int, default=4000)
args = ap.parse_args()
t0 = time.time()


def log(msg):
    print(f"[{time.time() - t0:6.0f}s] {msg}", flush=True)


uni = zhseg.load_vocab(args.dict_db)
segment = zhseg.segmenter(uni)
vocab = set(uni)
mainland = set()
for name in os.listdir(f"{ROOT}/sources"):
    if name.startswith("mainland_terms") and name.endswith(".txt"):
        mainland |= {l.strip() for l in open(f"{ROOT}/sources/{name}", encoding="utf-8") if l.strip() and not l.startswith("#")}


def md_batches(dirs):
    for d in dirs:
        texts = []
        for dp, _, fs in os.walk(d):
            for f in fs:
                if f.endswith(".md"):
                    texts.append(open(os.path.join(dp, f), encoding="utf-8", errors="ignore").read())
                    if len(texts) >= 200:
                        yield texts, False
                        texts = []
        if texts:
            yield texts, False


def batches():
    yield from md_batches(args.md)
    yield from zhseg.corpus_batches(args.corpus)


def pass1(job):
    """連續單字裡的 2～4 字組合次數，加上單字次數（算凝固度用）"""
    texts, ptt = job
    grams = Counter()
    chars = Counter()
    n_chars = 0
    for text in texts:
        if not text:
            continue
        for run in zhseg.runs(text, ptt):
            n_chars += len(run)
            chars.update(run)
            stretch = []
            for w in segment(run) + [""]:
                if len(w) == 1:
                    stretch.append(w)
                    continue
                if len(stretch) >= 2:
                    s = "".join(stretch)
                    for n in range(2, min(MAX_N, len(s)) + 1):
                        for i in range(len(s) - n + 1):
                            g = s[i:i + n]
                            if g[0] not in EDGE_STOP and g[-1] not in END_STOP:
                                grams[g] += 1
                stretch = []
    return grams, chars, n_chars


grams = Counter()
chars = Counter()
total = 0
with mp.Pool(os.cpu_count()) as pool:
    for k, (g, c, n) in enumerate(pool.imap_unordered(pass1, batches())):
        grams.update(g)
        chars.update(c)
        total += n
        if k % 200 == 199:
            # 記憶體：定期丟掉只出現一次的
            grams = Counter({x: v for x, v in grams.items() if v > 1})
            log(f"{total / 1e6:.0f}M 字，{len(grams)} 個組合")
log(f"第一輪完成：{total / 1e6:.1f}M 字")

# 子字串的次數（算凝固度）：組合本身沒數到的（例如被詞庫詞切走）就用單字次數相乘估不到，直接跳過那個切點
def p(s):
    if len(s) == 1:
        return chars[s] / total
    return grams.get(s, 0) / total


cands = {}
for g, f in grams.items():
    if f < MIN_FREQ or g in vocab or g in mainland or is_simplified(g) or splits_into_known(g, vocab):
        continue
    parts = [(g[:k], g[k:]) for k in range(1, len(g))]
    vals = [math.log(p(g) / (p(a) * p(b))) for a, b in parts if p(a) > 0 and p(b) > 0]
    if not vals or min(vals) < MIN_PMI:
        continue
    cands[g] = (f, min(vals))
log(f"凝固度過關 {len(cands)} 個，第二輪算左右自由度")

# 第二輪：只對候選詞掃一次語料，記左右鄰字
by_first = defaultdict(list)
for g in cands:
    by_first[g[0]].append(g)


def pass2(job):
    texts, ptt = job
    left = defaultdict(Counter)
    right = defaultdict(Counter)
    example = {}
    for text in texts:
        if not text:
            continue
        for run in zhseg.runs(text, ptt):
            for i, ch in enumerate(run):
                for g in by_first.get(ch, ()):
                    if run.startswith(g, i):
                        left[g][run[i - 1] if i > 0 else "^"] += 1
                        right[g][run[i + len(g)] if i + len(g) < len(run) else "$"] += 1
                        if g not in example and len(run) >= len(g) + 4:
                            example[g] = run[max(0, i - 8): i + len(g) + 8]
    return left, right, example


left = defaultdict(Counter)
right = defaultdict(Counter)
example = {}
with mp.Pool(os.cpu_count()) as pool:
    for l, r, e in pool.imap_unordered(pass2, batches()):
        for g, c in l.items():
            left[g].update(c)
        for g, c in r.items():
            right[g].update(c)
        for g, x in e.items():
            example.setdefault(g, x)


def entropy(c):
    s = sum(c.values())
    return -sum(v / s * math.log(v / s) for v in c.values()) if s else 0.0


scored = []
for g, (f, pmi) in cands.items():
    le, re_ = entropy(left[g]), entropy(right[g])
    if min(le, re_) < MIN_ENTROPY:
        continue
    scored.append((f * pmi * min(le, re_), g, f, pmi, le, re_))
scored.sort(reverse=True)
# 長串跟它包含的短串只留分數高的
picked = []
seen = set()
for c in scored:
    g = c[1]
    if any(g in q or q in g for q in seen):
        continue
    picked.append(c)
    seen.add(g)
    if len(picked) >= args.top:
        break
with open(args.out, "w", encoding="utf-8") as out:
    for _, g, f, pmi, le, re_ in picked:
        out.write(f"{g}\t{f}\t{pmi:.1f}\t{le:.1f}/{re_:.1f}\t{example.get(g, '')}\n")
log(f"候選 {len(picked)} 個 → {args.out}")
