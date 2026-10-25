#!/usr/bin/env python3
"""
統計口語語料（PTT 文章與推文、八卦版問答、Dcard）裡每個詞出現幾次，給主詞庫的字頻混合用（見 apply_colloquial.py）。

分詞跟 build_bigram_packs.py 一樣：主詞庫＋附加詞庫的詞表做 Viterbi 最大機率分詞，只數詞表裡有的詞。
結果寫成 sources/colloquial_counts.tsv（詞<TAB>次數，第一行是「#total<TAB>總詞數」），
之後重建主詞庫只要這個檔，不必再下載語料。

用法：count_colloquial.py <scorpio_dict.db（解壓後）> <語料目錄> <輸出 tsv> [PTT 字數上限，預設 60M]
  語料目錄需有 pttpre.parquet、pttqa.parquet、dcard.parquet（tools/fetch_corpus.sh <目錄> bg_ptt bg_dcard）
"""
import multiprocessing as mp
import os
import re
import sqlite3
import sys
import time
from collections import Counter

import pyarrow.parquet as pq

dict_db, corpus, out_path = sys.argv[1:4]
PTT_BUDGET = int(float(sys.argv[4])) if len(sys.argv) > 4 else 60_000_000
t0 = time.time()


def log(msg):
    print(f"[{time.time() - t0:6.0f}s] {msg}", flush=True)


# ---------- 詞表（同 build_bigram_packs.py；用原始的書面分數分詞，避免上一次混合的結果影響切法） ----------
con = sqlite3.connect(dict_db)
uni = {}
for table in ("dict", "addon_dict"):
    cols = [r[1] for r in con.execute(f"PRAGMA table_info({table})")]
    col = "base_score" if "base_score" in cols else "score"
    for w, s in con.execute(f"SELECT word, MAX({col}) FROM {table} GROUP BY word"):
        if w and not w.startswith("MACRO@") and all('一' <= ch <= '鿿' for ch in w):
            uni[w] = max(s, uni.get(w, -99))
con.close()
MAXLEN = min(max(len(w) for w in uni), 7)
log(f"詞表 {len(uni)} 詞，最長 {MAXLEN} 字")

UNKNOWN_COST = 14.0
LEN_BONUS = 1.6


def segment(run):
    n = len(run)
    best = [1e18] * (n + 1)
    back = [0] * (n + 1)
    best[0] = 0.0
    for i in range(n):
        bi = best[i]
        c = bi + UNKNOWN_COST
        if c < best[i + 1]:
            best[i + 1] = c
            back[i + 1] = i
        for l in range(1, min(MAXLEN, n - i) + 1):
            s = uni.get(run[i:i + l])
            if s is None:
                continue
            c = bi - s - LEN_BONUS * (l - 1)
            if c < best[i + l]:
                best[i + l] = c
                back[i + l] = i
    out = []
    j = n
    while j > 0:
        i = back[j]
        out.append(run[i:j])
        j = i
    out.reverse()
    return out


RE_URL = re.compile(r"https?://\S+")
RE_PTT_HEAD = re.compile(r"^(作者|看板|標題|時間|發信站|文章網址|轉錄至).*$", re.M)
RE_PTT_BODY = re.compile(r"^內文[:：]\s*", re.M)
RE_PUSH_PREFIX = re.compile(r"^(推|→|噓)\s+[a-zA-Z0-9_-]+:\s*", re.M)
RE_RUN = re.compile(r"[一-鿿]+")


def count_texts(args):
    texts, ptt = args
    c = Counter()
    chars = 0
    for text in texts:
        if not text:
            continue
        t = RE_URL.sub("", text)
        if ptt:
            t = RE_PTT_HEAD.sub("", t)
            t = RE_PTT_BODY.sub("", t)
            t = RE_PUSH_PREFIX.sub("", t)
        for run in RE_RUN.findall(t):
            chars += len(run)
            for w in segment(run):
                if w in uni:
                    c[w] += 1
    return c, chars


def batches():
    qa = f"{corpus}/pttqa.parquet"
    if os.path.exists(qa):
        t = pq.read_table(qa, columns=["question", "answer"])
        for col in ("question", "answer"):
            texts = t[col].to_pylist()
            for i in range(0, len(texts), 2000):
                yield texts[i:i + 2000], False
    dc = f"{corpus}/dcard.parquet"
    if os.path.exists(dc):
        t = pq.read_table(dc)
        for col in ("instruction", "input", "output"):
            if col in t.column_names:
                texts = t[col].to_pylist()
                for i in range(0, len(texts), 2000):
                    yield texts[i:i + 2000], False
    pre = f"{corpus}/pttpre.parquet"
    if os.path.exists(pre):
        for batch in pq.ParquetFile(pre).iter_batches(batch_size=500, columns=["text"]):
            yield batch["text"].to_pylist(), True


total = Counter()
chars = 0
with mp.Pool(os.cpu_count()) as pool:
    for c, n in pool.imap(count_texts, batches()):
        total.update(c)
        chars += n
        if chars // 5_000_000 != (chars - n) // 5_000_000:
            log(f"{chars / 1e6:.0f}M 字，{len(total)} 詞")
        if chars >= PTT_BUDGET:
            pool.terminate()
            break

n_tokens = sum(total.values())
with open(out_path, "w", encoding="utf-8") as f:
    f.write(f"#total\t{n_tokens}\n")
    for w, c in sorted(total.items(), key=lambda x: (-x[1], x[0])):
        if c >= 2:
            f.write(f"{w}\t{c}\n")
log(f"完成：{chars / 1e6:.1f}M 字，{n_tokens} 詞次，{sum(1 for c in total.values() if c >= 2)} 個詞出現兩次以上")
