#!/usr/bin/env python3
"""
「前兩個詞」的搭配（三詞，trigram）資料包：P(下一個詞 | 前兩個詞)，從 PTT、Dcard 語料統計。
接續詞資料包只看前一個詞（「打」後面接什麼），這裡多看一個詞（「現在打」後面接「字」），整句選字的前文比較長。

存法跟接續詞一樣（bigram 表：prev、next、score＝ln P），prev 是「前兩個詞」用 \\u0001 串起來，
App 查「前兩個詞」時跟查一般接續詞是同一張表、同一種格式。

分詞同 zhseg.py；計數不放記憶體：每個 worker 把三詞組寫到暫存檔，再用 sort | uniq -c 數（語料約 2 億字）。
留下來的：三詞組至少 MIN_COUNT 次、前兩個詞一起出現至少 MIN_CONTEXT 次、條件機率至少 MIN_PROB
（太小的 App 也不會加分），每組前兩個詞最多留 MAX_PER_CONTEXT 個，總數最多 LIMIT 筆（照次數）。

2026-10-25 試過（沒有放進 tools/build.sh）：PTT＋Dcard 1.9 億字 → 102 萬組、資料包 34 MB（gzip 13 MB），
用真實打字記錄 840 次選字重播，第一候選 77.7% → 77.7%、沒列出 2.0% → 1.7%，不值得那個大小。
之後要加別的語料（例如 FineWeb-2 的台灣繁中）再試，App 端已經會用（ScorpioDictManager.TRIGRAM_SEP）。

用法：build_trigram_pack.py <scorpio_dict.db（解壓後）> <語料目錄> <輸出 scorpio_bigram.db> <來源 id> [字數上限]
"""
import math
import multiprocessing as mp
import os
import sqlite3
import subprocess
import sys
import tempfile
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import zhseg  # noqa: E402

MIN_COUNT = 4
MIN_CONTEXT = 8
MIN_PROB = 0.02
MAX_PER_CONTEXT = 30
LIMIT = 1_200_000
SEP = "\u0001"

dict_db, corpus, out_db, source = sys.argv[1:5]
BUDGET = int(float(sys.argv[5])) if len(sys.argv) > 5 else 1_000_000_000
t0 = time.time()


def log(msg):
    print(f"[{time.time() - t0:6.0f}s] {msg}", flush=True)


uni = zhseg.load_vocab(dict_db)
segment = zhseg.segmenter(uni)
log(f"詞表 {len(uni)} 詞")
tmp = tempfile.mkdtemp(prefix="trigram-", dir=os.path.dirname(os.path.abspath(out_db)))


def work(args):
    """一批文字 → 三詞組寫進這個 worker 的暫存檔；回傳字數"""
    texts, ptt = args
    chars = 0
    with open(os.path.join(tmp, f"{os.getpid()}.tsv"), "a", encoding="utf-8") as out:
        for text in texts:
            if not text:
                continue
            for run in zhseg.runs(text, ptt):
                chars += len(run)
                a = b = None
                for w in segment(run):
                    if w not in uni:
                        a = b = None
                        continue
                    if a is not None:
                        out.write(f"{a}\t{b}\t{w}\n")
                    a, b = b, w
    return chars


chars = 0
with mp.Pool(os.cpu_count()) as pool:
    for n in pool.imap(work, zhseg.corpus_batches(corpus)):
        chars += n
        if chars // 10_000_000 != (chars - n) // 10_000_000:
            log(f"{chars / 1e6:.0f}M 字")
        if chars >= BUDGET:
            pool.terminate()
            break
log(f"分詞完成 {chars / 1e6:.1f}M 字，開始計數")

# 依「前兩個詞、下一個詞」排序後數次數：同一組前兩個詞會連在一起
files = [os.path.join(tmp, f) for f in os.listdir(tmp)]
env = dict(os.environ, LC_ALL="C")
sorter = subprocess.Popen(
    f"cat {' '.join(files)} | sort -S 4G --parallel={os.cpu_count()} -T {tmp} | uniq -c",
    shell=True, stdout=subprocess.PIPE, env=env, text=True, encoding="utf-8")

rows = []
kept_contexts = 0


def flush(ctx, nexts):
    global kept_contexts
    total = sum(c for _, c in nexts)
    if total < MIN_CONTEXT:
        return
    picked = 0
    for w, c in sorted(nexts, key=lambda x: -x[1]):
        if c < MIN_COUNT or picked >= MAX_PER_CONTEXT:
            break
        p = c / total
        if p < MIN_PROB:
            break
        rows.append((ctx, w, round(math.log(p), 3), c))
        picked += 1
    if picked:
        kept_contexts += 1


ctx = None
nexts = []
for line in sorter.stdout:
    cnt, rest = line.lstrip().split(" ", 1)
    a, b, w = rest.rstrip("\n").split("\t")
    key = a + SEP + b
    if key != ctx:
        if ctx is not None:
            flush(ctx, nexts)
        ctx, nexts = key, []
    nexts.append((w, int(cnt)))
if ctx is not None:
    flush(ctx, nexts)
sorter.wait()
subprocess.run(["rm", "-rf", tmp])

rows.sort(key=lambda r: -r[3])
rows = rows[:LIMIT]
log(f"三詞組 {len(rows)} 筆（{kept_contexts} 組前兩個詞）")

out = sqlite3.connect(out_db)
out.execute("CREATE TABLE IF NOT EXISTS bigram (prev TEXT NOT NULL, next TEXT NOT NULL, score REAL NOT NULL, source TEXT NOT NULL)")
out.execute("DELETE FROM bigram WHERE source = ?", (source,))
out.executemany("INSERT INTO bigram (prev, next, score, source) VALUES (?,?,?,?)", [(r[0], r[1], r[2], source) for r in rows])
out.commit()
log(f"寫入 {out_db}（source = {source}）")
