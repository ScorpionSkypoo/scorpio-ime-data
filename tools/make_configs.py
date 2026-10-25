#!/usr/bin/env python3
"""
鍵盤設定：config/<id>.json → 輸出目錄的 <id>-<版本>.json，並更新 manifest.json 的 configs；
同時寫一份 <base 目錄>/<id>.json.gz（App 打包時內建的就是最新版）。

設定是資料，不含可執行的程式碼；檢查規則跟 App 的 ImeConfig.parse 一樣（格式見 README〈鍵盤設定〉），不合就中止、不發佈。

用法：make_configs.py <dict.db> <輸出目錄> <base 目錄> <版本> <下載網址前綴> [設定 id...]（沒給就全部）
"""
import gzip
import hashlib
import json
import os
import sqlite3
import sys
import time

root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
dict_db, out_dir, base_dir, version, base_url = sys.argv[1:6]
only = sys.argv[6:]

SCHEMA = 1
# 第一個認得線上鍵盤設定的 App versionCode
MIN_APP_VERSION_CODE = 170
ZHUYIN = set("ㄅㄆㄇㄈㄉㄊㄋㄌㄍㄎㄏㄐㄑㄒㄓㄔㄕㄖㄗㄘㄙㄧㄨㄩㄚㄛㄜㄝㄞㄟㄠㄡㄢㄣㄤㄥㄦ")


def validate(c, path, kaomoji_categories):
    assert c.get("schema") == SCHEMA, f"{path}：schema 要是 {SCHEMA}"
    for k, v in c["lazySyllables"].items():
        assert len(k) == 1 and k in ZHUYIN, f"{path}：lazySyllables 的鍵 {k} 要是一個注音符號"
        assert isinstance(v, list) and v and all(isinstance(s, str) and s and set(s) <= ZHUYIN and s[0] == k for s in v), \
            f"{path}：lazySyllables[{k}] 要是以 {k} 開頭的注音音節（不含聲調）"
    for cat, words in c["kaomojiKeywords"].items():
        assert not kaomoji_categories or cat in kaomoji_categories, f"{path}：顏文字沒有「{cat}」這個分類"
        assert isinstance(words, list) and all(isinstance(w, str) and w for w in words), f"{path}：kaomojiKeywords[{cat}] 要是詞的清單"
    seen = {}
    for cat, words in c["kaomojiKeywords"].items():
        for w in words:
            assert w not in seen, f"{path}：「{w}」同時在 {seen[w]} 和 {cat}"
            seen[w] = cat
    for k, p in c["fuzzyPriors"].items():
        ok = len(k) in (2, 3) and k[0] in ZHUYIN and k[1] in ZHUYIN and (len(k) == 2 or (k[2] == "i" and k[0] in "ㄣㄥ"))
        assert ok, f"{path}：fuzzyPriors 的鍵 {k} 要是「打的注音＋想打的注音」（ㄣ／ㄥ 前面是 ㄧ 時加 i）"
        assert isinstance(p, (int, float)) and 0 < p < 1, f"{path}：fuzzyPriors[{k}] 要在 0～1 之間"
    for lang in ("zh", "en"):
        pages = c["symbols"][lang]
        assert isinstance(pages, list) and pages, f"{path}：symbols.{lang} 至少一頁"
        for i, pg in enumerate(pages):
            rows, row3 = pg["rows"], pg["row3"]
            assert len(rows) == 2 and all(len(r) == 10 for r in rows) and len(row3) == 7, \
                f"{path}：symbols.{lang} 第 {i + 1} 頁要兩排各 10 個、第三排 7 個"
            assert all(isinstance(s, str) and 0 < len(s) <= 4 for s in rows[0] + rows[1] + row3), f"{path}：symbols.{lang} 第 {i + 1} 頁有空的鍵或太長的字"


db = sqlite3.connect(dict_db)
try:
    kaomoji_categories = {r[0] for r in db.execute("SELECT DISTINCT category FROM kaomoji_dict")}
except sqlite3.OperationalError:
    kaomoji_categories = set()

manifest_path = f"{root}/manifest.json"
manifest = json.load(open(manifest_path, encoding="utf-8"))
entries = {e["id"]: e for e in manifest.get("configs", [])}
os.makedirs(out_dir, exist_ok=True)
os.makedirs(base_dir, exist_ok=True)

ids = only or sorted(f[:-5] for f in os.listdir(f"{root}/config") if f.endswith(".json"))
for cid in ids:
    path = f"config/{cid}.json"
    c = json.load(open(f"{root}/{path}", encoding="utf-8"))
    validate(c, path, kaomoji_categories)
    c = {k: v for k, v in c.items() if not k.startswith("_")}
    c["id"] = cid
    c["version"] = version
    blob = json.dumps(c, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    name = f"{cid}-{version}.json"
    open(f"{out_dir}/{name}", "wb").write(blob)
    with gzip.GzipFile(f"{base_dir}/{cid}.json.gz", "wb", 9, mtime=0) as fo:
        fo.write(blob)
    entries[cid] = {
        "id": cid,
        "version": version,
        "size": len(blob),
        "sha256": hashlib.sha256(blob).hexdigest(),
        "url": f"{base_url}/{name}",
        "minAppVersion": MIN_APP_VERSION_CODE,
    }
    print(f"設定 {cid} {version}：{len(blob) / 1024:.1f} KB")

manifest["configs"] = sorted(entries.values(), key=lambda e: e["id"])
manifest["updated"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
with open(manifest_path, "w", encoding="utf-8") as f:
    json.dump(manifest, f, ensure_ascii=False, indent=2)
    f.write("\n")
