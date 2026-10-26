#!/usr/bin/env python3
"""
套用主詞庫修正（sources/core_fixes.txt）：刪詞（支語、錯字）、改分數（同音詞搶位置）、改讀音、補讀音。
在 apply_colloquial.py 之後跑：口語加分每次從 base_score 重算，這裡再蓋上去，重跑結果一樣。

另外把台灣地名（tw_places）裡的「双、脚、强」換回「雙、腳、強」：內政部路名資料有些用異體字（双十街、山脚路），
打「雙十街」反而打不出來；換完跟原本就有的正體重複的直接刪掉。讀音不用改（同一個字），自强街的讀音另外錯成 ㄐㄧㄤˋ，正體的自強街本來就有。

用法：apply_core_fixes.py <scorpio_dict.db（解壓後）> <core_fixes.txt>
"""
import sqlite3
import sys

INITIALS = set("ㄅㄆㄇㄈㄉㄊㄋㄌㄍㄎㄏㄐㄑㄒㄓㄔㄕㄖㄗㄘㄙ")
TONES = "ˊˇˋ˙ˉ"
VARIANTS = str.maketrans("双脚强", "雙腳強")


def split_syllable(s):
    t = s.rstrip(TONES)
    ini = t[0] if t and t[0] in INITIALS else ""
    fin = t[len(ini):]
    return t, ini or "_", fin or "_"


def keys(reading):
    parts = [split_syllable(s) for s in reading.split("-")]
    return tuple("-".join(p[i] for p in parts) for i in range(3))


dict_db, fixes_path = sys.argv[1:3]
db = sqlite3.connect(dict_db)
section = None
n = {"刪除": 0, "分數": 0, "讀音": 0, "加讀音": 0}
missing = []
for line in open(fixes_path, encoding="utf-8"):
    line = line.strip()
    if not line or line.startswith("#"):
        continue
    if line.startswith("["):
        section = line.strip("[]")
        continue
    f = line.split()
    w = f[0]
    if section == "刪除":
        cur = db.execute("DELETE FROM dict WHERE word = ?" + (" AND reading = ?" if len(f) > 1 else ""), tuple(f[:2]))
    elif section == "分數":
        cur = db.execute("UPDATE dict SET score = ? WHERE word = ? AND reading = ?", (float(f[2]), w, f[1]))
    elif section == "讀音":
        if db.execute("SELECT 1 FROM dict WHERE word = ? AND reading = ?", (w, f[2])).fetchone():
            continue
        tl, ini, fin = keys(f[2])
        cur = db.execute("UPDATE dict SET reading = ?, toneless = ?, initials = ?, finals = ? WHERE word = ? AND reading = ?",
                         (f[2], tl, ini, fin, w, f[1]))
    elif section == "加讀音":
        if db.execute("SELECT 1 FROM dict WHERE word = ? AND reading = ?", (w, f[1])).fetchone():
            continue
        score = float(f[2]) if len(f) > 2 else (db.execute("SELECT max(score) FROM dict WHERE word = ?", (w,)).fetchone()[0])
        if score is None:
            missing.append(line)
            continue
        tl, ini, fin = keys(f[1])
        cur = db.execute("INSERT INTO dict (reading, toneless, word, score, initials, finals, base_score) VALUES (?,?,?,?,?,?,?)",
                         (f[1], tl, w, score, ini, fin, score))
    else:
        sys.exit(f"不認得的段落 [{section}]：{line}")
    if cur.rowcount:
        n[section] += cur.rowcount
    elif section != "刪除":
        # 刪除找不到是正常的（base 已經刪過）；其他找不到代表主詞庫改了，修正要跟著看
        missing.append(line)

# 台灣地名的異體字
places = db.execute("SELECT rowid, word, reading FROM addon_dict WHERE source = 'tw_places'").fetchall()
have = {(w, r) for _, w, r in places}
have_word = {w for _, w, _ in places}
var_del = var_upd = 0
for rowid, w, r in places:
    t = w.translate(VARIANTS)
    if t == w:
        continue
    if t in have_word:
        db.execute("DELETE FROM addon_dict WHERE rowid = ?", (rowid,))
        var_del += 1
    elif (t, r) not in have:
        db.execute("UPDATE addon_dict SET word = ? WHERE rowid = ?", (t, rowid))
        have.add((t, r))
        var_upd += 1
db.commit()
print(f"主詞庫修正：刪除 {n['刪除']} 筆、分數 {n['分數']}、讀音 {n['讀音']}、補讀音 {n['加讀音']}；"
      f"地名異體字換回正體 {var_upd}、重複刪掉 {var_del}")
for m in missing:
    print("  找不到：", m)
