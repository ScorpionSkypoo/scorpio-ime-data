#!/usr/bin/env python3
"""
逐鍵比對 SCD 檔與 SQLite：每個索引鍵底下的資料（含順序）都要跟 App 舊版的 SQL 查詢結果一模一樣。

用法：verify_scd.py <scorpio_dict.db> <scorpio_bigram.db> <SCD 目錄> [id...]
詞的表照 App 手機上 dict 表的樣子建索引（idx_reading、idx_toneless…），再用 App 實際下的 SQL 查，
所以驗的是「同一個查詢，舊版從 SQLite 拿到的列」與「新版從 SCD 拿到的列」相同。有任何不同就以非 0 結束。
"""
import os
import random
import sqlite3
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import scd  # noqa: E402

dict_db, bigram_db, scd_dir = sys.argv[1:4]
only = sys.argv[4:]
src = sqlite3.connect(dict_db)
bsrc = sqlite3.connect(bigram_db)
errors = 0


def fail(msg):
    global errors
    errors += 1
    if errors <= 20:
        print("  ✗", msg)


def words_db(rows):
    """依原順序建一張跟手機上 dict 表一樣的表與索引"""
    m = sqlite3.connect(":memory:")
    m.execute("CREATE TABLE dict (reading TEXT NOT NULL, toneless TEXT NOT NULL, word TEXT NOT NULL, score REAL NOT NULL, initials TEXT, finals TEXT)")
    m.executemany("INSERT INTO dict VALUES (?,?,?,?,?,?)", rows)
    for c in ("reading", "toneless", "initials", "finals", "word"):
        m.execute(f"CREATE INDEX idx_{c} ON dict({c})")
    return m


def verify_words(r, rows):
    m = words_db(rows)
    word = r.arr("w.word", "I")
    read = r.arr("w.read", "I")
    score = r.arr("w.score", "d")
    row = lambda i: (r.s(word[i]), score[i], r.s(read[i]))  # noqa: E731
    for name, col in (("w.tl", "toneless"), ("w.rd", "reading"), ("w.fn", "finals"), ("w.wd", "word"), ("w.in", "initials")):
        ix = r.index(name)
        sql_keys = {k for (k,) in m.execute(f"SELECT DISTINCT {col} FROM dict")}
        if set(ix) != sql_keys:
            fail(f"{name} 鍵不同：多 {len(set(ix) - sql_keys)}、少 {len(sql_keys - set(ix))}")
        for k, ids in ix.items():
            exp = m.execute(f"SELECT word, score, reading FROM dict WHERE {col} = ? ORDER BY score DESC", (k,)).fetchall()
            if [row(i) for i in ids] != exp:
                fail(f"{name} 「{k}」順序不同")
    # 全部依分數（設定頁瀏覽）
    exp = m.execute("SELECT word, score, reading FROM dict ORDER BY score DESC").fetchall()
    if [row(i) for i in r.arr("w.sc", "I")] != exp:
        fail("w.sc 順序不同")
    # 熱門前綴的前幾名，以及隨機前綴（含不熱門的）整段掃描的結果
    tl = r.index("w.tl")
    keys = sorted(tl, key=scd.u16key)
    heavy = r.index("w.tp")
    for p, ids in heavy.items():
        exp = m.execute("SELECT word, score, reading FROM dict WHERE toneless >= ? AND toneless < ? ORDER BY score DESC LIMIT ?",
                        (p, p + "￿", scd.TOPK)).fetchall()
        if [row(i) for i in ids] != exp:
            fail(f"w.tp 「{p}」不同")
    rnd = random.Random(1)
    for k in rnd.sample(keys, min(3000, len(keys))):
        p = k[:rnd.randint(1, len(k))]
        if p in heavy:
            continue
        ids = [i for kk in keys if kk.startswith(p) for i in tl[kk]]
        got = sorted(ids, key=lambda i: (-score[i], i))[:15]
        exp = m.execute("SELECT word, score, reading FROM dict WHERE toneless >= ? AND toneless < ? ORDER BY score DESC LIMIT 15",
                        (p, p + "￿")).fetchall()
        if [row(i) for i in got] != exp:
            fail(f"前綴「{p}」不同")
    print(f"  詞 {len(rows)} 筆、熱門前綴 {len(heavy)} 個")


def verify_bigram(r, pid):
    nxt = r.arr("b.next", "I")
    sc = r.arr("b.score", "d")
    for k, ids in r.index("b.pv").items():
        exp = bsrc.execute("SELECT next, score FROM bigram WHERE prev = ? AND source = ? ORDER BY score DESC", (k, pid)).fetchall()
        if [(r.s(nxt[i]), sc[i]) for i in ids] != exp:
            fail(f"b.pv 「{k}」不同")
    n = bsrc.execute("SELECT count(*) FROM bigram WHERE source = ?", (pid,)).fetchone()[0]
    if n != len(nxt):
        fail(f"接續詞筆數不同 {len(nxt)} / {n}")
    print(f"  接續詞 {n} 筆")


def verify_simple(r, pid):
    if pid == "en":
        words = [r.s(i) for i in r.arr("e.word", "I")]
        if list(zip(words, r.arr("e.score", "i"))) != src.execute("SELECT word, score FROM english_dict ORDER BY word").fetchall():
            fail("英文單字不同")
        nxt = r.arr("eb.next", "I")
        for k, ids in r.index("eb.pv").items():
            exp = [x for (x,) in src.execute("SELECT next FROM english_bigram WHERE prev = ? ORDER BY score DESC", (k,))]
            if [r.s(nxt[i]) for i in ids] != exp:
                fail(f"eb.pv 「{k}」不同")
    elif pid == "cangjie":
        got = list(zip(*(map(r.s, r.arr(f"cj.{c}", "I")) for c in ("code", "quick", "char")), r.arr("cj.freq", "d")))
        if got != src.execute("SELECT code, quick, char, freq FROM cangjie ORDER BY code, freq DESC").fetchall():
            fail("倉頡碼表不同")
    elif pid == "emoji":
        emo = r.arr("em.emoji", "I")
        for k, ids in r.index("em.ix").items():
            exp = [x for (x,) in src.execute("SELECT emoji FROM emoji_dict WHERE keyword = ? ORDER BY priority ASC", (k,))]
            if [r.s(emo[i]) for i in ids] != exp:
                fail(f"em.ix 「{k}」不同")
        cemo = r.arr("ec.emoji", "I")
        for k, ids in r.index("ec.ix").items():
            exp = [x for (x,) in src.execute("SELECT emoji FROM emoji_category_dict WHERE category = ? ORDER BY priority ASC", (k,))]
            if [r.s(cemo[i]) for i in ids] != exp:
                fail(f"ec.ix 「{k}」不同")
    elif pid == "kaomoji":
        kao = r.arr("k.kao", "I")
        for name, col in (("k.rd", "reading"), ("k.ct", "category")):
            for k, ids in r.index(name).items():
                exp = [x for (x,) in src.execute(f"SELECT kaomoji FROM kaomoji_dict WHERE {col} = ? ORDER BY priority ASC", (k,))]
                if [r.s(kao[i]) for i in ids] != exp:
                    fail(f"{name} 「{k}」不同")


for f in sorted(os.listdir(scd_dir)):
    if not f.endswith(".scd"):
        continue
    pid = f[:-4]
    if only and pid not in only:
        continue
    print(pid)
    r = scd.Reader(open(f"{scd_dir}/{f}", "rb").read())
    if "w.word" in r.sec:
        if pid == "core":
            rows = src.execute("SELECT reading, toneless, word, score, initials, finals FROM dict WHERE source IS NULL ORDER BY rowid").fetchall()
        else:
            rows = src.execute("SELECT reading, toneless, word, score, initials, finals FROM addon_dict WHERE source = ? ORDER BY rowid", (pid,)).fetchall()
        verify_words(r, rows)
    if "b.prev" in r.sec:
        verify_bigram(r, pid)
    verify_simple(r, pid)

print("全部一致" if errors == 0 else f"有 {errors} 處不同")
sys.exit(1 if errors else 0)
