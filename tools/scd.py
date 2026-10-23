#!/usr/bin/env python3
"""
SCD（Scorpio Compiled Dictionary）：App 用 mmap 直接讀的唯讀二進位詞庫，格式見 docs/scd-format.md。

- 數字一律 little-endian；字串存 UTF-16（App 的 Kotlin 字串就是 UTF-16，比對時不必解碼）
- 字串表依 UTF-16 code unit 排序後編號；索引的鍵依同樣順序排，App 用二分搜尋找鍵
- 同一個鍵底下的資料先依分數（或優先序）排、同分時依原本 SQLite 的掃描順序，
  所以跟舊版 `ORDER BY score DESC LIMIT n` 的結果逐筆一致（tools/verify_scd.py 逐鍵比對）

App 端（ScorpionBopomofo 的 engine/scd/ScdWriter.kt）有同一套寫法，把使用者匯入的詞庫轉成 SCD；
兩邊對同一份資料寫出的檔案每個 byte 都一樣（App 的單元測試用 tools/scd_fixture.py 產生的檔案比對）。
"""
import bisect
import json
import struct

MAGIC = b"SCD1"
VERSION = 1
HEADER = 32
DIR_ENTRY = 32
NAME_LEN = 24

# 前綴查詢（toneless >= p AND toneless < p || U+FFFF）範圍超過這麼多筆的前綴，預先算好前 TOPK 名
PREFIX_HEAVY = 256
TOPK = 16


def u16key(s):
    """UTF-16 code unit 順序（App 端 String.compareTo）"""
    return s.encode("utf-16-be")


def align(n):
    return (n + 7) & ~7


def meta_json(meta):
    return json.dumps(meta, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()


class Writer:
    """先把各表加進來（add_*），build() 時統一建字串表、寫出各區段"""

    def __init__(self, meta):
        self.meta = dict(meta)
        self.tables = []

    def add(self, table):
        self.tables.append(table)
        return self

    def build(self):
        strings = set()
        for t in self.tables:
            strings.update(t.strings())
        str_list = sorted(strings, key=u16key)
        sid = {s: i for i, s in enumerate(str_list)}
        offs = [0]
        chars = bytearray()
        for s in str_list:
            b = s.encode("utf-16-le")
            chars += b
            offs.append(offs[-1] + len(b) // 2)
        sections = [("str.off", pack("I", offs)), ("str.chr", bytes(chars))]
        for t in self.tables:
            sections.extend(t.sections(sid))
            self.meta.setdefault("rows", {})[t.NAME] = t.row_count()
        names = [n for n, _ in sections]
        assert len(names) == len(set(names)) and all(len(n.encode()) <= NAME_LEN for n in names), names

        meta = meta_json(self.meta)
        pos = HEADER
        meta_off = pos
        pos = align(pos + len(meta))
        dir_off = pos
        pos = align(pos + len(sections) * DIR_ENTRY)
        layout = []
        for name, data in sections:
            layout.append((name, pos, len(data)))
            pos = align(pos + len(data))
        out = bytearray(pos)
        struct.pack_into("<4sIIIIIII", out, 0, MAGIC, VERSION, meta_off, len(meta), dir_off, len(sections), pos, 0)
        out[meta_off:meta_off + len(meta)] = meta
        for i, (name, off, ln) in enumerate(layout):
            struct.pack_into(f"<{NAME_LEN}sII", out, dir_off + i * DIR_ENTRY, name.encode(), off, ln)
        for (_, data), (_, off, ln) in zip(sections, layout):
            out[off:off + ln] = data
        return bytes(out)


def pack(fmt, values):
    return struct.pack(f"<{len(values)}{fmt}", *values)


def index_sections(name, sid, keys, groups, clustered=False):
    """keys：依 UTF-16 排序的鍵；groups：每個鍵的資料列編號（已排好）。clustered：資料列本身就依這個鍵排，不存 posting"""
    starts = [0]
    post = []
    for g in groups:
        if clustered:
            assert g == list(range(starts[-1], starts[-1] + len(g)))
            starts.append(starts[-1] + len(g))
        else:
            post.extend(g)
            starts.append(len(post))
    out = [(name + ".k", pack("I", [sid[k] for k in keys])), (name + ".s", pack("I", starts))]
    if not clustered:
        out.append((name + ".p", pack("I", post)))
    return out


def group(n, key, order):
    """把資料列 0..n-1 依 key 分組：回傳（依 UTF-16 排序的鍵, 每組依 order 排好的資料列）"""
    d = {}
    for i in range(n):
        d.setdefault(key(i), []).append(i)
    keys = sorted(d, key=u16key)
    return keys, [sorted(d[k], key=order) for k in keys]


class Words:
    """
    詞（主詞庫、附加詞庫、匯入詞庫）。rows：(reading, toneless, word, score, initials, finals)，依原本 rowid 順序。
    資料列依 (toneless, 分數高到低, 原順序) 排，toneless 查詢、前綴查詢都是一段連續的資料列；
    同分時：單一鍵依原順序，多個鍵（前綴、IN、聲母 OR）依鍵的順序再依原順序——都跟 SQLite 的掃描順序相同
    """
    NAME = "w"

    def __init__(self, rows):
        self.orig = sorted(range(len(rows)), key=lambda i: (u16key(rows[i][1]), -rows[i][3], i))
        self.rs = [rows[i] for i in self.orig]
        rs = self.rs
        tl16 = [u16key(r[1]) for r in rs]
        prefixes = set()
        last = None
        for r in rs:
            if r[1] != last:
                last = r[1]
                for j in range(1, len(last) + 1):
                    prefixes.add(last[:j])
        self.heavy = []
        for p in sorted(prefixes, key=u16key):
            lo = bisect.bisect_left(tl16, u16key(p))
            hi = bisect.bisect_left(tl16, u16key(p + "￿"))
            if hi - lo > PREFIX_HEAVY:
                self.heavy.append((p, sorted(range(lo, hi), key=lambda i: (-rs[i][3], i))[:TOPK]))

    def row_count(self):
        return len(self.rs)

    def strings(self):
        out = {s for r in self.rs for s in (r[0], r[1], r[2], r[4], r[5])}
        out.update(p for p, _ in self.heavy)
        return out

    def sections(self, sid):
        rs, orig, n = self.rs, self.orig, len(self.rs)
        out = [
            ("w.word", pack("I", [sid[r[2]] for r in rs])),
            ("w.read", pack("I", [sid[r[0]] for r in rs])),
            ("w.tl", pack("I", [sid[r[1]] for r in rs])),
            ("w.score", pack("d", [r[3] for r in rs])),
        ]
        keys, groups = group(n, lambda i: rs[i][1], lambda i: i)
        out += index_sections("w.tl", sid, keys, groups, clustered=True)
        for name, col in (("w.rd", 0), ("w.in", 4), ("w.fn", 5), ("w.wd", 2)):
            keys, groups = group(n, lambda i, c=col: rs[i][c], lambda i: (-rs[i][3], orig[i]))
            out += index_sections(name, sid, keys, groups)
        out.append(("w.sc", pack("I", sorted(range(n), key=lambda i: (-rs[i][3], orig[i])))))
        out += index_sections("w.tp", sid, [p for p, _ in self.heavy], [t for _, t in self.heavy])
        return out


class Bigram:
    """詞與詞的接續（ln P(next|prev)）。rows：(prev, next, score)，依原本主鍵 (prev, next) 的順序"""
    NAME = "b"

    def __init__(self, rows):
        self.rs = rows

    def row_count(self):
        return len(self.rs)

    def strings(self):
        return {s for r in self.rs for s in (r[0], r[1])}

    def sections(self, sid):
        rs, n = self.rs, len(self.rs)
        out = [
            ("b.prev", pack("I", [sid[r[0]] for r in rs])),
            ("b.next", pack("I", [sid[r[1]] for r in rs])),
            ("b.score", pack("d", [r[2] for r in rs])),
        ]
        keys, groups = group(n, lambda i: rs[i][0], lambda i: (-rs[i][2], i))
        out += index_sections("b.pv", sid, keys, groups)
        out.append(("b.sc", pack("I", sorted(range(n), key=lambda i: (-rs[i][2], i)))))
        return out


class English:
    """英文單字（rows：(word, score) 依 ORDER BY word）與英文接續（brows：(prev, next, score) 依 rowid）"""
    NAME = "e"

    def __init__(self, rows, brows):
        self.rs, self.bs = rows, brows

    def row_count(self):
        return len(self.rs)

    def strings(self):
        return {r[0] for r in self.rs} | {s for r in self.bs for s in (r[0], r[1])}

    def sections(self, sid):
        n = len(self.bs)
        keys, groups = group(n, lambda i: self.bs[i][0], lambda i: (-self.bs[i][2], i))
        return [
            ("e.word", pack("I", [sid[r[0]] for r in self.rs])),
            ("e.score", pack("i", [r[1] for r in self.rs])),
            ("eb.next", pack("I", [sid[r[1]] for r in self.bs])),
        ] + index_sections("eb.pv", sid, keys, groups)


class Cangjie:
    """倉頡碼表，rows：(code, quick, char, freq) 依 ORDER BY code, freq DESC"""
    NAME = "cj"

    def __init__(self, rows):
        self.rs = rows

    def row_count(self):
        return len(self.rs)

    def strings(self):
        return {s for r in self.rs for s in (r[0], r[1], r[2])}

    def sections(self, sid):
        return [
            ("cj.code", pack("I", [sid[r[0]] for r in self.rs])),
            ("cj.quick", pack("I", [sid[r[1]] for r in self.rs])),
            ("cj.char", pack("I", [sid[r[2]] for r in self.rs])),
            ("cj.freq", pack("d", [r[3] for r in self.rs])),
        ]


class Emoji:
    """
    rows：emoji_dict (keyword, emoji, priority)；crows：emoji_category_dict (category, emoji, priority)，都依 rowid
    all_emoji：SELECT DISTINCT emoji … ORDER BY priority 的結果；cats：分類依 rowid 首次出現的順序
    """
    NAME = "em"

    def __init__(self, rows, crows, all_emoji, cats):
        self.rs, self.cs, self.all, self.cats = rows, crows, all_emoji, cats

    def row_count(self):
        return len(self.rs)

    def strings(self):
        return {s for r in self.rs for s in (r[0], r[1])} | {s for r in self.cs for s in (r[0], r[1])} | set(self.all) | set(self.cats)

    def sections(self, sid):
        k1, g1 = group(len(self.rs), lambda i: self.rs[i][0], lambda i: (self.rs[i][2], i))
        k2, g2 = group(len(self.cs), lambda i: self.cs[i][0], lambda i: (self.cs[i][2], i))
        return [
            ("em.kw", pack("I", [sid[r[0]] for r in self.rs])),
            ("em.emoji", pack("I", [sid[r[1]] for r in self.rs])),
            ("em.pri", pack("i", [r[2] for r in self.rs])),
            ("em.all", pack("I", [sid[s] for s in self.all])),
            ("ec.emoji", pack("I", [sid[r[1]] for r in self.cs])),
            ("ec.cats", pack("I", [sid[s] for s in self.cats])),
        ] + index_sections("em.ix", sid, k1, g1) + index_sections("ec.ix", sid, k2, g2)


class Kaomoji:
    """rows：kaomoji_dict (reading, kaomoji, category, priority) 依 rowid；cats：分類依 MIN(priority)"""
    NAME = "k"

    def __init__(self, rows, cats):
        self.rs, self.cats = rows, cats

    def row_count(self):
        return len(self.rs)

    def strings(self):
        return {s for r in self.rs for s in (r[0], r[1], r[2])} | set(self.cats)

    def sections(self, sid):
        n = len(self.rs)
        k1, g1 = group(n, lambda i: self.rs[i][0], lambda i: (self.rs[i][3], i))
        k2, g2 = group(n, lambda i: self.rs[i][2], lambda i: (self.rs[i][3], i))
        return [
            ("k.read", pack("I", [sid[r[0]] for r in self.rs])),
            ("k.kao", pack("I", [sid[r[1]] for r in self.rs])),
            ("k.cat", pack("I", [sid[r[2]] for r in self.rs])),
            ("k.pri", pack("i", [r[3] for r in self.rs])),
            ("k.cats", pack("I", [sid[s] for s in self.cats])),
        ] + index_sections("k.rd", sid, k1, g1) + index_sections("k.ct", sid, k2, g2)


# ---------- 讀檔（驗證用；App 端是 Kotlin 的 ScdFile） ----------

class Reader:
    def __init__(self, data):
        self.d = memoryview(data)
        magic, ver, mo, ml, do, dn, flen, _ = struct.unpack_from("<4sIIIIIII", data, 0)
        assert magic == MAGIC and ver == VERSION and flen == len(data)
        self.meta = json.loads(bytes(self.d[mo:mo + ml]))
        self.sec = {}
        for i in range(dn):
            name, off, ln = struct.unpack_from(f"<{NAME_LEN}sII", data, do + i * DIR_ENTRY)
            self.sec[name.rstrip(b"\0").decode()] = (off, ln)
        self.offs = self.arr("str.off", "I")
        o, ln = self.sec["str.chr"]
        self.chars = bytes(self.d[o:o + ln])

    def arr(self, name, fmt):
        if name not in self.sec:
            return None
        o, ln = self.sec[name]
        return list(struct.unpack_from(f"<{ln // struct.calcsize(fmt)}{fmt}", self.d, o))

    def s(self, sid):
        return self.chars[self.offs[sid] * 2:self.offs[sid + 1] * 2].decode("utf-16-le")

    def index(self, name):
        keys = [self.s(k) for k in self.arr(name + ".k", "I")]
        starts = self.arr(name + ".s", "I")
        post = self.arr(name + ".p", "I")
        out = {}
        for j, k in enumerate(keys):
            rng = range(starts[j], starts[j + 1])
            out[k] = list(rng) if post is None else [post[p] for p in rng]
        return out
