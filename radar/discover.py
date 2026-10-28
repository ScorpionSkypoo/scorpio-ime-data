#!/usr/bin/env python3
"""
新詞雷達：從 collect.py 蒐集的語料找出詞庫還沒有的新詞

判斷方式（常見的無監督新詞發現）：
  - 頻率：2～5 字的字串出現夠多次
  - 凝固度：整串一起出現的機率，遠高於任何一種拆法各自出現的機率相乘（PMI 取最小的那個切點）
  - 自由度：左右兩邊接的字夠多樣（鄰字熵），代表它能獨立使用，不是更長的詞的一部分
  - 不在詞庫裡（主詞庫、附加詞庫、流行用語），也不能整個拆成詞庫裡的兩字以上的詞
  - 含簡體字或大陸用語的不收（OpenCC：s2t 會變的是簡體字；s2tw 與 s2twp 結果不同的是大陸用語，例如視頻、軟件；
    OpenCC 沒收的大陸用語列在 sources/mainland_terms*.txt）
另外把 Google Trends 熱搜裡詞庫沒有的詞另外列出（多半是人名、事件，收不收由人決定）。
維基百科的新條目、熱門條目（轉成台灣正體）：詞庫沒有、在台灣語料（PTT、公視、Threads…）也出現至少 WIKI_MIN 次的才收，
加進 trendy.txt；維基中文多半是大陸寫的，只在維基出現的不收。
--twmd：tools/mine_taiwan_md.py 挑出的 taiwan-md 新詞候選（還沒看過的），前 TWMD_TOP 個加進 sources/tw_md.txt。
--en-apply：中文句子裡夾的英文字（品牌、產品、縮寫），英文字典（english_dict）與 sources/en_extra.txt 都沒有、
至少 EN_MIN_DOCS 段文字、EN_MIN_GROUPS 個來源（PTT 不同看板算不同來源）用過的，前 EN_TOP 個加進 en_extra.txt 的 [words]，
分數先給 EN_SCORE（PTT／Dcard 約 10 個人用過的程度），審核時可以改。

用法：discover.py <texts.jsonl> <scorpio_dict.db（解壓後）> <報告 report.md> [--apply sources/trendy.txt] [--top 60]
                   [--twmd work/twmd.tsv --twmd-apply sources/tw_md.txt] [--en-apply sources/en_extra.txt]
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
    _s2tw = opencc.OpenCC("s2tw")
    _s2twp = opencc.OpenCC("s2twp")

    def is_simplified(w):
        """含簡體字，或是大陸用語（例如視頻、軟件、質量）：
        s2t 轉換會變的是簡體字；s2tw（只轉字形）跟 s2twp（連台灣慣用詞一起轉，用 OpenCC 的 TWPhrases 詞典）結果不同的是大陸用語"""
        return _s2t.convert(w) != w or _s2tw.convert(w) != _s2twp.convert(w)
except ImportError:  # 沒裝 opencc 就不過濾
    def is_simplified(w):
        return False

RE_RUN = re.compile(r"[一-鿿]{2,}")
# 開頭或結尾是這些字的多半是片語碎片（「的人」「是不」），直接排除
EDGE_STOP = set("的了是在和與及或而就也都又還才把被讓給對向從到於之其這那個些啊吧呢嗎啦喔哦耶欸囉咧嘛")
# 只排除結尾：副詞、代名詞、量詞收尾的多半是「真的很」「幫你」「一堆人」「第二部」這種碎片
END_STOP = EDGE_STOP | set("很太超更最沒不你我他她它們人部種次樣下上中裡著過嗎")
MIN_LEN, MAX_LEN = 2, 5
WIKI_MIN = 3
TWMD_TOP = 40
# 英文字：中文句子裡夾的（純字母，可以有 '；網址、帳號、檔名的一部分不算）
RE_EN = re.compile(r"(?<![A-Za-z0-9@./_#'-])([A-Za-z]+(?:'[A-Za-z]+)?)(?![A-Za-z0-9@_/'-])")
RE_URL = re.compile(r"https?://\S+|www\.\S+|\S+@\S+")
RE_HAN = re.compile(r"[一-鿿]")
# 笑聲、重複字母（XDDD、wwww、QQQ）
RE_EN_REP = re.compile(r"(.)\1\1|^(x+d+|xd(xd)+|w+|z+|q+|o+x+)$", re.I)
EN_MIN_DOCS, EN_MIN_GROUPS, EN_TOP = 4, 2, 30
# 三個字母以下的全大寫縮寫多半意思不明（ABC、LH），要更多段文字用過
EN_SHORT_CAPS_DOCS = 10
EN_SCORE = 3347
RE_TITLE = re.compile(r"[一-鿿]{2,8}")
SOURCE_NAMES = {"trends": "Google Trends 熱搜", "trends-news": "Google Trends 新聞標題", "pts": "公視新聞",
                "threadscount": "Threads 熱門話題統計", "threads": "Threads", "wiki-new": "維基新條目", "wiki-top": "維基熱門條目"}


def load_vocab(db_path):
    db = sqlite3.connect(db_path)
    vocab = set()
    for table in ("dict", "addon_dict"):
        try:
            vocab.update(w for (w,) in db.execute(f"SELECT DISTINCT word FROM {table}"))
        except sqlite3.OperationalError:
            pass
    return vocab


def load_english(db_path, extra_path):
    """英文字典（小寫）加上 en_extra.txt 已經收的字（[display]、[words]）與「# 不收：」那幾行列的字（審核時刪掉、不想再看到的）"""
    words = set()
    try:
        words.update(w for (w,) in sqlite3.connect(db_path).execute("SELECT word FROM english_dict"))
    except sqlite3.OperationalError:
        pass
    if extra_path:
        for line in open(extra_path, encoding="utf-8"):
            line = line.strip()
            if line.startswith("# 不收："):
                words.update(w.lower() for w in line[len("# 不收："):].split())
            elif line and not line.startswith(("#", "[")):
                words.add(line.split("\t")[0].lower())
    return words


def english_candidates(texts, english):
    """texts：(來源, 文字)。回傳 [(段數, 來源數, 寫法, 例句)]，依段數排"""
    docs, groups, forms, example = Counter(), defaultdict(set), defaultdict(Counter), {}
    for src, text in texts:
        seen = set()
        for line in RE_URL.sub(" ", text).splitlines():
            if not RE_HAN.search(line):
                continue
            for m in RE_EN.finditer(line):
                w = m.group(1)
                k = w.lower()
                if len(w) < 2 or k in english or RE_EN_REP.search(k):
                    continue
                forms[k][w] += 1
                if k not in seen:
                    seen.add(k)
                    docs[k] += 1
                    groups[k].add(src)
                    example.setdefault(k, line[max(0, m.start() - 12): m.end() + 12].strip())
    out = []
    for k, n in docs.items():
        w = forms[k].most_common(1)[0][0]
        if n < EN_MIN_DOCS or len(groups[k]) < EN_MIN_GROUPS:
            continue
        if w.isupper() and len(w) <= 3 and n < EN_SHORT_CAPS_DOCS:
            continue
        out.append((n, len(groups[k]), w, example[k]))
    out.sort(key=lambda x: (-x[0], -x[1], x[2]))
    return out[:EN_TOP]


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
    ap.add_argument("--opencc-twphrases", help="OpenCC GitHub master 最新的 TWPhrases.txt（左欄是大陸用語）")
    ap.add_argument("--twmd", help="tools/mine_taiwan_md.py 的輸出 tsv")
    ap.add_argument("--twmd-apply", help="sources/tw_md.txt")
    ap.add_argument("--en-apply", help="sources/en_extra.txt：英文新詞加進 [words]")
    args = ap.parse_args()

    vocab = load_vocab(args.dict_db)
    # 人工維護的大陸用語清單（OpenCC 沒收的），一律排除
    root = __import__("os").path.dirname(__import__("os").path.dirname(__import__("os").path.abspath(__file__)))
    mainland = set()
    for name in sorted(__import__("os").listdir(f"{root}/sources")):
        if name.startswith("mainland_terms") and name.endswith(".txt"):
            mainland |= {l.strip() for l in open(f"{root}/sources/{name}", encoding="utf-8") if l.strip() and not l.startswith("#")}
    # pip 版 OpenCC 的詞典只到它發佈的那版；這裡再加上 GitHub master 最新的 TWPhrases（大陸用語 → 台灣用語）
    if args.opencc_twphrases and __import__("os").path.exists(args.opencc_twphrases):
        for line in open(args.opencc_twphrases, encoding="utf-8"):
            if line.startswith("#") or "\t" not in line:
                continue
            key, values = line.rstrip("\n").split("\t", 1)
            if key not in values.split():
                mainland.add(key)
    if args.apply:
        for line in open(args.apply, encoding="utf-8"):
            line = line.strip()
            if line and not line.startswith(("#", "[")):
                vocab.add(line.split()[0])

    runs, trend_topics, wiki, en_texts = [], [], [], []
    sources = Counter()
    to_tw = _s2twp.convert if "_s2twp" in globals() else (lambda t: t)
    for line in open(args.texts, encoding="utf-8"):
        d = json.loads(line)
        src = d["source"]
        sources[SOURCE_NAMES.get(src, "PTT" if src.startswith("ptt") else src)] += 1
        if src.startswith("wiki"):
            # 維基只取標題當候選，不算進語料（大陸寫的條目會讓詞頻偏掉）
            wiki.append(to_tw(d["text"]).replace(" ", ""))
            continue
        if src == "trends":
            trend_topics.append(d["text"].replace(" ", ""))
        # 英文字的來源：PTT 每個看板各算一個（ptt:Gossiping 與 ptt-search:Gossiping 同一個）
        en_texts.append((src.split(":")[-1] if src.startswith("ptt") else src, d["text"]))
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
        if g in vocab or g in mainland or is_simplified(g) or g[0] in EDGE_STOP or g[-1] in END_STOP or splits_into_known(g, vocab):
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

    trend_new = [t for t in dict.fromkeys(trend_topics) if RE_RUN.fullmatch(t) and t not in vocab and t not in mainland and not is_simplified(t)]

    # 維基標題：台灣語料裡也出現的才收
    corpus = "\n".join(runs)
    picked_words = {c[1] for c in picked}
    wiki_new = []
    for t in dict.fromkeys(wiki):
        if not RE_TITLE.fullmatch(t) or t in vocab or t in mainland or t in picked_words or t in trend_new or splits_into_known(t, vocab):
            continue
        c = corpus.count(t)
        if c >= WIKI_MIN:
            wiki_new.append((c, t))
    wiki_new.sort(reverse=True)

    # taiwan-md：mine_taiwan_md.py 的候選（欄位：詞、讀音、全文次數、篇數、出處、要確認讀音的破音字）
    twmd = []
    if args.twmd and __import__("os").path.exists(args.twmd):
        for line in open(args.twmd, encoding="utf-8"):
            if line.startswith("#"):
                continue
            f = line.rstrip("\n").split("\t")
            if len(f) >= 6 and f[0] not in vocab and f[0] not in mainland and not is_simplified(f[0]):
                twmd.append(f)
        twmd = twmd[:TWMD_TOP]

    en_new = english_candidates(en_texts, load_english(args.dict_db, args.en_apply)) if args.en_apply else []

    today = time.strftime("%Y-%m-%d")
    with open(args.report, "w", encoding="utf-8") as f:
        f.write(f"## 新詞雷達 {today}\n\n")
        f.write(f"語料：{len(runs):,} 段、{total:,} 字（" + "、".join(f"{k} {v:,}" for k, v in sources.most_common()) + "）。\n\n")
        f.write("下面的候選詞已經加進 `sources/trendy.txt`。**合併前請在 Files changed 刪掉不要的行**，合併後會自動發佈新版流行用語詞庫。\n\n")
        f.write("| 候選詞 | 次數 | 凝固度 | 左／右自由度 | 例句 |\n|---|---:|---:|---:|---|\n")
        for _, g, fr, pmi, le, re_ in picked:
            f.write(f"| {g} | {fr} | {pmi:.1f} | {le:.1f}／{re_:.1f} | {example(g)} |\n")
        if wiki_new:
            f.write(f"\n### 維基百科新條目、熱門條目\n\n詞庫沒有、台灣語料（PTT、公視…）也出現 {WIKI_MIN} 次以上的，**已經加進 `sources/trendy.txt`**（括號是台灣語料次數）。\n\n")
            f.write("、".join(f"{t}（{c}）" for c, t in wiki_new) + "\n")
        if twmd:
            f.write("\n### taiwan-md 新詞\n\n還沒看過的專有名詞，**已經加進 `sources/tw_md.txt`**；不要的刪掉，或移到檔尾的「# 不收：」那幾行，下次就不會再列。"
                    "破音字欄有字的要確認讀音（讀音不對就在詞後面寫正確讀音）。\n\n| 詞 | 推得的讀音 | 篇數 | 破音字 |\n|---|---|---:|---|\n")
            for x in twmd:
                f.write(f"| {x[0]} | {x[1]} | {x[3]} | {x[5]} |\n")
        if en_new:
            f.write(f"\n### 英文新詞\n\n中文句子裡夾的英文字，英文字典沒有的，**已經加進 `sources/en_extra.txt` 的 [words]**（分數先給 {EN_SCORE}）。"
                    "寫法照最常見的大小寫；不要的刪掉（或移到檔頭的「# 不收：」那行，以後就不會再列），寫法不對的直接改（App 照這裡的寫法顯示）。\n\n| 寫法 | 段數 | 來源數 | 例句 |\n|---|---:|---:|---|\n")
            for n, g, w, ex in en_new:
                f.write(f"| {w} | {n} | {g} | {ex.replace('|', '｜')} |\n")
        if trend_new:
            f.write("\n### Google Trends 熱搜中詞庫沒有的詞\n\n多半是人名或事件，**沒有自動加入**；要收的話手動加到 `sources/trendy.txt`。\n\n")
            f.write("、".join(trend_new) + "\n")
    print(f"候選 {len(picked)} 個 → {args.report}")

    if args.apply and (picked or wiki_new):
        lines = open(args.apply, encoding="utf-8").read().split("\n")
        at = lines.index("[pairs]")
        while at > 0 and not lines[at - 1].strip():
            at -= 1
        block = ([f"# 新詞雷達 {today}"] + [c[1] for c in picked] if picked else []) + \
            ([f"# 新詞雷達 {today}（維基條目）"] + [t for _, t in wiki_new] if wiki_new else [])
        lines[at:at] = block
        open(args.apply, "w", encoding="utf-8").write("\n".join(lines))
        print(f"已加入 {args.apply}")
    if args.twmd_apply and twmd:
        lines = open(args.twmd_apply, encoding="utf-8").read().rstrip("\n").split("\n")
        # 加在最後一個收錄的詞後面（檔尾是「# 不收：」）
        at = max(i for i, l in enumerate(lines) if l.strip() and not l.startswith(("#", "["))) + 1
        lines[at:at] = [f"# 新詞雷達 {today}"] + [x[0] for x in twmd]
        open(args.twmd_apply, "w", encoding="utf-8").write("\n".join(lines) + "\n")
        print(f"已加入 {args.twmd_apply}：{len(twmd)} 個")
    if args.en_apply and en_new:
        text = open(args.en_apply, encoding="utf-8").read().rstrip("\n")
        block = [f"# 新詞雷達 {today}"] + [f"{w}\t{EN_SCORE}" for _, _, w, _ in en_new]
        open(args.en_apply, "w", encoding="utf-8").write(text + "\n" + "\n".join(block) + "\n")
        print(f"已加入 {args.en_apply}：{len(en_new)} 個")


if __name__ == "__main__":
    main()
