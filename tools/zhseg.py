"""
語料分詞共用：主詞庫＋附加詞庫的詞表做 Viterbi 最大機率分詞（跟 build_bigram_packs.py 同一套），
以及 PTT／Dcard 語料的讀取與清理。count_colloquial.py、build_trigram_pack.py 共用
"""
import os
import re
import sqlite3

import pyarrow.parquet as pq

UNKNOWN_COST = 14.0
LEN_BONUS = 1.6

RE_URL = re.compile(r"https?://\S+")
RE_PTT_HEAD = re.compile(r"^(作者|看板|標題|時間|發信站|文章網址|轉錄至).*$", re.M)
RE_PTT_BODY = re.compile(r"^內文[:：]\s*", re.M)
RE_PUSH_PREFIX = re.compile(r"^(推|→|噓)\s+[a-zA-Z0-9_-]+:\s*", re.M)
RE_RUN = re.compile(r"[一-鿿]+")


def load_vocab(dict_db):
    """詞 → 分數（用原始的書面分數 base_score，沒有的話用 score），只收全是漢字的詞"""
    con = sqlite3.connect(dict_db)
    uni = {}
    for table in ("dict", "addon_dict"):
        cols = [r[1] for r in con.execute(f"PRAGMA table_info({table})")]
        col = "base_score" if "base_score" in cols else "score"
        for w, s in con.execute(f"SELECT word, MAX({col}) FROM {table} GROUP BY word"):
            if w and not w.startswith("MACRO@") and all('一' <= ch <= '鿿' for ch in w):
                uni[w] = max(s, uni.get(w, -99))
    con.close()
    return uni


def segmenter(uni):
    maxlen = min(max(len(w) for w in uni), 7)

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
            for l in range(1, min(maxlen, n - i) + 1):
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

    return segment


def runs(text, ptt=False):
    """一段文字裡連續的漢字（標點、英數、網址斷開）"""
    t = RE_URL.sub("", text)
    if ptt:
        t = RE_PTT_HEAD.sub("", t)
        t = RE_PTT_BODY.sub("", t)
        t = RE_PUSH_PREFIX.sub("", t)
    return RE_RUN.findall(t)


def corpus_batches(corpus):
    """(文字清單, 是不是 PTT 文章) 一批一批：PTT 八卦版問答、Dcard、PTT 文章與推文"""
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
