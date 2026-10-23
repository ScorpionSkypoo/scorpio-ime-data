#!/usr/bin/env python3
"""
把基底詞庫（SQLite）轉成 App 用的 SCD 檔（格式見 tools/scd.py、docs/scd-format.md）。

用法：build_scd.py [--base] <scorpio_dict.db> <scorpio_bigram.db> <輸出目錄> <版本> [id...]
  沒給 id 就輸出全部：主詞庫 core、各附加詞庫、接續詞、顏文字，以及 App 內建的 emoji、en（英文）、cangjie（倉頡）
  輸出 <輸出目錄>/<id>.scd
  --base：資料包的版本用 dict_packs／pack_versions 記的那一版（App 內建的就是各資料包最後發佈的版本，
          不必一裝好就重新下載）；沒記的才用 <版本>
"""
import json
import os
import sqlite3
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import scd  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# 不是資料包、跟著 App 走的資料（設定頁不列為詞庫）
BUILTIN = {
    "emoji": {"name": "Emoji", "source": "Unicode CLDR 繁中註解", "license": "Unicode License v3"},
    "en": {"name": "英文", "source": "英文詞頻與 OpenSubtitles 口語接續", "license": "見 DATA_LICENSES.md"},
    "cangjie": {"name": "倉頡／速成", "source": "倉頡碼表", "license": "見 DATA_LICENSES.md"},
}


def packs_json():
    return {p["id"]: p for p in json.load(open(f"{ROOT}/packs.json", encoding="utf-8"))["packs"]}


BASE_MODE = False


def recorded_version(db, bdb, pid):
    """base 詞庫記的資料包版本（詞與顏文字在 dict_packs，接續詞在 pack_versions；流行用語兩邊都有，取舊的）"""
    def key(v):
        return [int(x) for x in v.split(".")]
    vs = []
    row = db.execute("SELECT version FROM dict_packs WHERE id = ?", (pid,)).fetchone()
    if row and row[0]:
        vs.append(row[0])
    try:
        row = bdb.execute("SELECT version FROM pack_versions WHERE id = ?", (pid,)).fetchone()
        if row and row[0]:
            vs.append(row[0])
    except sqlite3.OperationalError:
        pass
    return min(vs, key=key) if vs else None


def pack_meta(db, pid, version):
    """資料包的名稱、說明、授權等：packs.json 為主，dict_packs 補排序"""
    p = packs_json().get(pid, {})
    row = db.execute("SELECT grp, name, description, source, license, url, sort FROM dict_packs WHERE id = ?", (pid,)).fetchone()
    meta = {
        "id": pid,
        "group": p.get("group") or (row[0] if row else "words"),
        "name": p.get("name") or (row[1] if row else pid),
        "description": p.get("description") or (row[2] if row else ""),
        "source": p.get("source") or (row[3] if row else ""),
        "license": p.get("license") or (row[4] if row else ""),
        "url": p.get("url") or (row[5] if row else ""),
        "sort": row[6] if row else 99,
        "bundled": p.get("bundled", True),
        "default": p.get("default", True),
        "category": p.get("category", ""),
        "version": version,
    }
    return meta


def word_rows(db, where, args=()):
    return db.execute(f"SELECT reading, toneless, word, score, initials, finals FROM {where} ORDER BY rowid", args).fetchall()


def build(pid, db, bdb, version):
    """回傳 SCD 檔內容；這個 id 沒有任何資料時回傳 None"""
    if pid in BUILTIN:
        meta = {"id": pid, "group": pid, "version": version, **BUILTIN[pid]}
        w = scd.Writer(meta)
        if pid == "emoji":
            w.add(scd.Emoji(
                db.execute("SELECT keyword, emoji, priority FROM emoji_dict ORDER BY rowid").fetchall(),
                db.execute("SELECT category, emoji, priority FROM emoji_category_dict ORDER BY rowid").fetchall(),
                [r[0] for r in db.execute("SELECT DISTINCT emoji FROM emoji_dict ORDER BY priority ASC")],
                [r[0] for r in db.execute("SELECT DISTINCT category FROM emoji_category_dict ORDER BY rowid ASC")],
            ))
        elif pid == "en":
            w.add(scd.English(
                db.execute("SELECT word, score FROM english_dict ORDER BY word").fetchall(),
                db.execute("SELECT prev, next, score FROM english_bigram ORDER BY rowid").fetchall(),
            ))
        else:
            w.add(scd.Cangjie(db.execute("SELECT code, quick, char, freq FROM cangjie ORDER BY code, freq DESC").fetchall()))
        return w.build()

    if BASE_MODE:
        version = recorded_version(db, bdb, pid) or version
    meta = pack_meta(db, pid, version)
    w = scd.Writer(meta)
    if pid == "core":
        w.add(scd.Words(word_rows(db, "dict WHERE source IS NULL")))
    elif meta["group"] == "words":
        rows = word_rows(db, "addon_dict WHERE source = ?", (pid,))
        if rows:
            w.add(scd.Words(rows))
    if meta["group"] == "bigram" or pid == "trendy":
        rows = bdb.execute("SELECT prev, next, score FROM bigram WHERE source = ? ORDER BY prev, next", (pid,)).fetchall()
        if rows:
            w.add(scd.Bigram(rows))
    if meta["group"] == "kaomoji":
        w.add(scd.Kaomoji(
            db.execute("SELECT reading, kaomoji, category, priority FROM kaomoji_dict ORDER BY rowid").fetchall(),
            [r[0] for r in db.execute("SELECT category FROM kaomoji_dict GROUP BY category ORDER BY MIN(priority)")],
        ))
    if not w.tables:
        return None
    return w.build()


def all_ids(db):
    ids = ["core"]
    ids += [r[0] for r in db.execute("SELECT id FROM dict_packs WHERE id <> 'core' ORDER BY sort, id")]
    return ids + list(BUILTIN)


def main():
    global BASE_MODE
    args = sys.argv[1:]
    if args and args[0] == "--base":
        BASE_MODE = True
        args = args[1:]
    dict_db, bigram_db, out_dir, version = args[:4]
    db = sqlite3.connect(dict_db)
    bdb = sqlite3.connect(bigram_db)
    ids = args[4:] or all_ids(db)
    os.makedirs(out_dir, exist_ok=True)
    for pid in ids:
        data = build(pid, db, bdb, version)
        if data is None:
            print(f"{pid}：沒有資料，略過")
            continue
        with open(f"{out_dir}/{pid}.scd", "wb") as f:
            f.write(data)
        print(f"{pid}.scd {len(data) / 1048576:.1f} MB")


if __name__ == "__main__":
    main()
