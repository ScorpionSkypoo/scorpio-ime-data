#!/usr/bin/env python3
"""
taiwan-md（github.com/frank890417/taiwan-md）的專有名詞候選，給 sources/tw_md.txt 人工挑選用。

從 knowledge/ 各分類文章取：標題、tags、[[連結]]、**粗體**；只留主詞庫與附加詞庫都沒有、
也不能由已知詞（中間可夾「的、與、後、年」這類單字）拼出來的詞，粗體只在一篇出現的多半是章節小標，略過。
taiwan-md 的文章大多是 AI 寫的，會有「它把因果搞反了」這種句子被加粗：給了語料目錄就另外數
PTT、Dcard、維基各出現幾次（真人寫的語料），篩選時參考。

用法：mine_taiwan_md.py <taiwan-md 目錄> <scorpio_dict.db（解壓後）> <輸出 tsv> [語料目錄]
  語料目錄：pttpre.parquet、pttqa.parquet、dcard.parquet、wiki1.bz2（tools/fetch_corpus.sh）
  已經在 sources/tw_md.txt 的詞（收錄或註記不收的）不再列出
輸出欄位：詞、推得的讀音、全文次數、篇數、出處、要確認讀音的破音字[、PTT、Dcard、維基]
"""
import bz2
import collections
import os
import re
import sqlite3
import sys

root, db_path, out_path = sys.argv[1:4]
corpus = sys.argv[4] if len(sys.argv) > 4 else None
repo = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
db = sqlite3.connect(db_path)
word_reading = {}
for w, r, s in db.execute("SELECT word, reading, score FROM dict"):
    if w not in word_reading or s > word_reading[w][1]:
        word_reading[w] = (r, s)
known = set(word_reading) | {w for (w,) in db.execute("SELECT word FROM addon_dict")}
# 看過的詞：收錄的、註記不收的（# 不收：詞 詞 …）
for line in open(f"{repo}/sources/tw_md.txt", encoding="utf-8"):
    line = line.strip()
    if line.startswith("# 不收："):
        known.update(line[len("# 不收："):].split())
    elif line and not line.startswith(("#", "[")):
        known.add(line.split()[0])
# 破音字：單字有兩個以上讀音、次要讀音不算太冷門
readings = collections.defaultdict(list)
for w, r, s in db.execute("SELECT word, reading, score FROM dict WHERE length(word) = 1"):
    readings[w].append((s, r))
poly = {c for c, rs in readings.items() if len(rs) > 1 and sorted(rs)[-2][0] > -9}


def guess(word):
    """跟 build_addon_dicts.py 一樣：最少切段、同段數取詞頻總和高的；另外回傳落單的破音字"""
    n = len(word)
    best = [None] * (n + 1)
    best[0] = (0, 0.0, [], [])
    for i in range(n):
        if best[i] is None:
            continue
        for j in range(min(n, i + 6), i, -1):
            hit = word_reading.get(word[i:j])
            if hit:
                cand = (best[i][0] + 1, best[i][1] + hit[1], best[i][2] + [hit[0]], best[i][3] + ([word[i]] if j == i + 1 else []))
                cur = best[j]
                if cur is None or cand[0] < cur[0] or (cand[0] == cur[0] and cand[1] > cur[1]):
                    best[j] = cand
    if not best[n]:
        return None, []
    return "-".join(best[n][2]), [c for c in best[n][3] if c in poly]


# 拼詞時可以夾的單字（「在那裡」「同一年」「解嚴後」不算新詞）
FUNC = set("在的是與和及了這那它他她把不有一後前中年時上下裡內外再也都就又很更最被讓給從對向為於以而或")
PHRASE = re.compile(r"與|是什麼|為什麼|怎麼|的是|不是|^(這|那|它|有|在)|(的|了|嗎|呢|是)$")


def composable(w):
    ok = [True] + [False] * len(w)
    for i in range(len(w)):
        if ok[i]:
            if w[i] in FUNC:
                ok[i + 1] = True
            for j in range(i + 2, len(w) + 1):
                if w[i:j] in known:
                    ok[j] = True
    return ok[-1] and not all(ch in FUNC for ch in w)


CATS = "About Art Culture Economy Food Geography History Lifestyle Music Nature People Politics Society Technology".split()
HAN = re.compile(r"^[一-鿿]{2,8}$")
FM = re.compile(r"^---\n(.*?)\n---\n", re.S)
TITLE = re.compile(r"^title:\s*['\"]?(.+?)['\"]?\s*$", re.M)
TAGS = re.compile(r"^tags:\s*\[(.*)\]", re.M)
LINK = re.compile(r"\[\[([^\]|#]+)(?:[#|][^\]]*)?\]\]")
BOLD = re.compile(r"\*\*([^*\n]{2,12})\*\*")
# 版型與章節標題
BOILER = set("延伸閱讀 參考資料 圖片來源 策展人筆記 你知道嗎 爭議觀點 資料來源 三十秒概覽 結尾警句 關鍵數字 "
             "代表作品 重要作品 創作理念 創作特色 歷史背景 建築特色 空間特色".split())

kinds = collections.defaultdict(set)
texts = []
for c in CATS:
    for dp, _, fs in os.walk(f"{root}/knowledge/{c}"):
        for f in fs:
            if not f.endswith(".md"):
                continue
            t = open(os.path.join(dp, f), encoding="utf-8").read()
            texts.append(t)
            fm = FM.match(t)
            head = fm.group(1) if fm else ""
            m = TITLE.search(head)
            found = [("title", m.group(1).strip())] if m else []
            m = TAGS.search(head)
            if m:
                found += [("tag", x.strip(" '\"")) for x in m.group(1).split(",")]
            found += [("link", x.strip()) for x in LINK.findall(t)]
            found += [("bold", x.strip()) for x in BOLD.findall(t)]
            for k, w in found:
                if HAN.match(w) and w not in BOILER:
                    kinds[w].add(k)

body = "\n".join(texts)
rows = []
for w, ks in kinds.items():
    if w in known or composable(w) or PHRASE.search(w):
        continue
    n = body.count(w)
    d = sum(1 for t in texts if w in t)
    if not ks & {"title", "link", "tag"} and (d < 2 or n < 3):
        continue
    reading, polys = guess(w)
    if reading:
        rows.append([w, reading, str(n), str(d), ",".join(sorted(ks)), "".join(polys)])
rows.sort(key=lambda r: (-int(r[3]), -int(r[2])))
head = "# 詞\t讀音\t全文次數\t篇數\t出處\t要確認讀音的破音字"

if corpus:
    import opencc
    import pyarrow.parquet as pq

    words = {r[0] for r in rows}
    lens = sorted({len(w) for w in words})
    RUN = re.compile(r"[一-鿿]{2,}")

    def scan(texts, budget):
        c = dict.fromkeys(words, 0)
        n = 0
        for t in texts:
            for run in RUN.findall(t):
                n += len(run)
                for l in lens:
                    for i in range(len(run) - l + 1):
                        if run[i:i + l] in c:
                            c[run[i:i + l]] += 1
            if n >= budget:
                break
        return c

    def ptt():
        t = pq.read_table(f"{corpus}/pttqa.parquet", columns=["question", "answer"])
        for col in ("question", "answer"):
            yield from (x for x in t[col].to_pylist() if x)
        for b in pq.ParquetFile(f"{corpus}/pttpre.parquet").iter_batches(batch_size=2000, columns=["text"]):
            yield from (x for x in b["text"].to_pylist() if x)

    def dcard():
        t = pq.read_table(f"{corpus}/dcard.parquet")
        for col in ("instruction", "input", "output"):
            if col in t.column_names:
                yield from (x for x in t[col].to_pylist() if x)

    def wiki():
        cc = opencc.OpenCC("s2twp")
        with bz2.open(f"{corpus}/wiki1.bz2", "rt", encoding="utf-8", errors="ignore") as f:
            while chunk := f.read(1 << 22):
                yield cc.convert(chunk)

    counts = [scan(ptt(), 80_000_000), scan(dcard(), 10 ** 12), scan(wiki(), 40_000_000)]
    for r in rows:
        r += [str(c[r[0]]) for c in counts]
    head += "\tPTT\tDcard\t維基"

with open(out_path, "w", encoding="utf-8") as f:
    f.write(head + "\n")
    for r in rows:
        f.write("\t".join(r) + "\n")
print(len(rows), "個候選；要確認讀音", sum(1 for r in rows if r[5]))
