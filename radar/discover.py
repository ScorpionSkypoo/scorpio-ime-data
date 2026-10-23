#!/usr/bin/env python3
"""
新詞雷達：從 collect.py 蒐集的語料找出詞庫還沒有的新詞

判斷方式（常見的無監督新詞發現）：
  - 頻率：2～5 字的字串出現夠多次
  - 凝固度：整串一起出現的機率，遠高於任何一種拆法各自出現的機率相乘（PMI 取最小的那個切點）
  - 自由度：左右兩邊接的字夠多樣（鄰字熵），代表它能獨立使用，不是更長的詞的一部分
  - 不在詞庫裡（主詞庫、附加詞庫、流行用語），也不能整個拆成詞庫裡的兩字以上的詞
  - 含簡體字的（OpenCC s2t 轉換後會變）不收
另外把 Google Trends 熱搜裡詞庫沒有的詞另外列出（多半是人名、事件，收不收由人決定）。

用法：discover.py <texts.jsonl> <scorpio_dict.db（解壓後）> <報告 report.md> [--apply sources/trendy.txt] [--top 60]
  --apply：把候選詞加進 trendy.txt 的 [words]（附上日期註解），給 PR 審核時刪掉不要的
"""
import argparse
import json
import math
import re
import sqlite3
import time
from collections import Counter, defaultdict

try:
    import opencc
    _s2t = opencc.OpenCC("s2t")

    def is_simplified(w):
        return _s2t.convert(w) != w
except ImportError:  # 沒裝 opencc 就不過濾
    def is_simplified(w):
        return False

RE_RUN = re.compile(r"[一-鿿]{2,}")
# 開頭或結尾是這些字的多半是片語碎片（「的人」「是不」），直接排除
EDGE_STOP = set("的了是在和與及或而就也都又還才把被讓給對向從到於之其這那個些啊吧呢嗎啦喔哦耶欸囉咧嘛")
# 只排除結尾：副詞、代名詞、量詞收尾的多半是「真的很」「幫你」「一堆人」「第二部」這種碎片
END_STOP = EDGE_STOP | set("很太超更最沒不你我他她它們人部種次樣下上中裡著過嗎")
MIN_LEN, MAX_LEN = 2, 5


def load_vocab(db_path):
    db = sqlite3.connect(db_path)
    vocab = set()
    for table in ("dict", "addon_dict"):
        try:
            vocab.update(w for (w,) in db.execute(f"SELECT DISTINCT word FROM {table}"))
        except sqlite3.OperationalError:
            pass
    return vocab


def splits_into_known(w, vocab):
    """能不能整個拆成詞庫裡的詞，而且每段至少兩個字（兩個已知詞的組合不算新詞）"""
    n = len(w)
    ok = [False] * (n + 1)
    ok[0] = True
    for i in range(n):
        if not ok[i]:
            continue
        for j in range(i + 2, n + 1):
            if w[i:j] in vocab:
                ok[j] = True
    return ok[n] and w not in vocab


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("texts")
    ap.add_argument("dict_db")
    ap.add_argument("report")
    ap.add_argument("--apply")
    ap.add_argument("--top", type=int, default=60)
    ap.add_argument("--min-freq", type=int, default=6)
    args = ap.parse_args()

    vocab = load_vocab(args.dict_db)
    if args.apply:
        for line in open(args.apply, encoding="utf-8"):
            line = line.strip()
            if line and not line.startswith(("#", "[")):
                vocab.add(line.split()[0])

    runs, trend_topics = [], []
    for line in open(args.texts, encoding="utf-8"):
        d = json.loads(line)
        if d["source"] == "trends":
            trend_topics.append(d["text"].replace(" ", ""))
        runs.extend(RE_RUN.findall(d["text"]))

    ngram = Counter()
    left = defaultdict(Counter)
    right = defaultdict(Counter)
    total = 0
    for r in runs:
        total += len(r)
        for n in range(1, MAX_LEN + 1):
            for i in range(len(r) - n + 1):
                g = r[i:i + n]
                ngram[g] += 1
                if n >= MIN_LEN:
                    left[g][r[i - 1] if i > 0 else "^"] += 1
                    right[g][r[i + n] if i + n < len(r) else "$"] += 1

    def p(g):
        return ngram[g] / total

    def entropy(c):
        s = sum(c.values())
        return -sum(v / s * math.log(v / s) for v in c.values())

    cands = []
    for g, f in ngram.items():
        if not (MIN_LEN <= len(g) <= MAX_LEN) or f < args.min_freq:
            continue
        if g in vocab or is_simplified(g) or g[0] in EDGE_STOP or g[-1] in END_STOP or splits_into_known(g, vocab):
            continue
        pmi = min(math.log(p(g) / (p(g[:k]) * p(g[k:]))) for k in range(1, len(g)))
        le, re_ = entropy(left[g]), entropy(right[g])
        if pmi < 3.0 or min(le, re_) < 1.2:
            continue
        cands.append((f * pmi * min(le, re_), g, f, pmi, le, re_))
    cands.sort(reverse=True)

    # 長串跟它包含的短串頻率差不多時，只留一個（「暈爛了」和「暈爛」只留分數高的）
    picked = []
    for c in cands:
        g = c[1]
        if any(g in q[1] or q[1] in g for q in picked):
            continue
        picked.append(c)
        if len(picked) >= args.top:
            break

    def example(w):
        for r in runs:
            i = r.find(w)
            if i >= 0 and len(r) >= len(w) + 4:
                return r[max(0, i - 10): i + len(w) + 10]
        return ""

    trend_new = [t for t in dict.fromkeys(trend_topics) if RE_RUN.fullmatch(t) and t not in vocab and not is_simplified(t)]

    today = time.strftime("%Y-%m-%d")
    with open(args.report, "w", encoding="utf-8") as f:
        f.write(f"## 新詞雷達 {today}\n\n")
        f.write(f"語料：{len(runs):,} 段、{total:,} 字（Google Trends 熱搜＋PTT 近期文章與推文）。\n\n")
        f.write("下面的候選詞已經加進 `sources/trendy.txt`。**合併前請在 Files changed 刪掉不要的行**，合併後會自動發佈新版流行用語詞庫。\n\n")
        f.write("| 候選詞 | 次數 | 凝固度 | 左／右自由度 | 例句 |\n|---|---:|---:|---:|---|\n")
        for _, g, fr, pmi, le, re_ in picked:
            f.write(f"| {g} | {fr} | {pmi:.1f} | {le:.1f}／{re_:.1f} | {example(g)} |\n")
        if trend_new:
            f.write("\n### Google Trends 熱搜中詞庫沒有的詞\n\n多半是人名或事件，**沒有自動加入**；要收的話手動加到 `sources/trendy.txt`。\n\n")
            f.write("、".join(trend_new) + "\n")
    print(f"候選 {len(picked)} 個 → {args.report}")

    if args.apply and picked:
        lines = open(args.apply, encoding="utf-8").read().split("\n")
        at = lines.index("[pairs]")
        while at > 0 and not lines[at - 1].strip():
            at -= 1
        block = [f"# 新詞雷達 {today}"] + [c[1] for c in picked]
        lines[at:at] = block
        open(args.apply, "w", encoding="utf-8").write("\n".join(lines))
        print(f"已加入 {args.apply}")


if __name__ == "__main__":
    main()
