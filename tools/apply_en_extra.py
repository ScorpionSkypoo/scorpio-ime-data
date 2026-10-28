#!/usr/bin/env python3
"""
把 sources/en_extra.txt 併進基底詞庫的英文字典：
- [words] 的字（寫法<TAB>分數）加進 english_dict（存小寫）
- [display] 與 [words] 的寫法（跟小寫不同的才記）寫進 english_display(word, display)，
  build_scd.py 寫成 en.scd 的 e.disp，App 顯示候選時用（iPhone、Paris、DVD）

每次從頭算：上次加進 english_dict 的字記在 english_extra_added，先刪掉再照目前的檔案加，
所以重跑不會重複，從檔案刪掉的字也會從字典拿掉。english_display 每次整個重建。

用法：apply_en_extra.py <scorpio_dict.db（解壓後）> <en_extra.txt>
"""
import re
import sqlite3
import sys

dict_db, path = sys.argv[1:3]
RE_WORD = re.compile(r"^[A-Za-z]+(?:'[A-Za-z]+)?$")

display, words = [], []
section = None
for n, line in enumerate(open(path, encoding="utf-8"), 1):
    line = line.strip()
    if not line or line.startswith("#"):
        continue
    if line.startswith("[") and line.endswith("]"):
        section = line[1:-1]
        continue
    f = line.split("\t")
    if not RE_WORD.match(f[0]):
        sys.exit(f"{path}:{n} 只能是英文字母（可以有 '）：{f[0]!r}")
    if section == "display" and len(f) == 1:
        display.append(f[0])
    elif section == "words" and len(f) == 2 and f[1].lstrip("-").isdigit():
        words.append((f[0], int(f[1])))
    else:
        sys.exit(f"{path}:{n} 格式不對（[display] 一行一個字；[words] 寫法<TAB>分數）：{line!r}")

keys = [w.lower() for w in display] + [w.lower() for w, _ in words]
dup = {k for k in keys if keys.count(k) > 1}
if dup:
    sys.exit(f"重複的字：{' '.join(sorted(dup))}")

db = sqlite3.connect(dict_db)
db.execute("CREATE TABLE IF NOT EXISTS english_extra_added (word TEXT PRIMARY KEY)")
db.execute("DELETE FROM english_dict WHERE word IN (SELECT word FROM english_extra_added)")
db.execute("DELETE FROM english_extra_added")
have = {w for (w,) in db.execute("SELECT word FROM english_dict")}

added, already = [], []
for w, score in words:
    k = w.lower()
    if k in have:
        already.append(w)
        continue
    added.append((k, score))
db.executemany("INSERT INTO english_dict (word, score) VALUES (?, ?)", added)
db.executemany("INSERT INTO english_extra_added (word) VALUES (?)", [(k,) for k, _ in added])

missing = [w for w in display if w.lower() not in have]
disp = [(w.lower(), w) for w in display + [w for w, _ in words] if w.lower() != w and w.lower() not in {m.lower() for m in missing}]
db.execute("DROP TABLE IF EXISTS english_display")
db.execute("CREATE TABLE english_display (word TEXT PRIMARY KEY, display TEXT NOT NULL)")
db.executemany("INSERT INTO english_display (word, display) VALUES (?, ?)", disp)
db.commit()

print(f"英文補充詞：加進字典 {len(added)} 個，顯示寫法 {len(disp)} 個")
if already:
    print(f"  [words] 裡字典本來就有的（只用寫法，分數照字典）：{' '.join(already)}")
if missing:
    print(f"  [display] 裡字典沒有的（略過）：{' '.join(missing)}")
