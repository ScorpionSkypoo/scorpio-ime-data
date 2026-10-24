#!/usr/bin/env python3
"""
鍵盤版面：layouts/<id>.json → 輸出目錄的 <id>-<版本>.json，並更新 manifest.json 的 layouts。

版面是宣告式的 JSON，只能選 App 內建的打字方式（engine），不含可執行的程式碼（格式見 README〈鍵盤版面〉）。
大千注音內建在 App，不在這裡。

用法：make_layouts.py <輸出目錄> <版本> <下載網址前綴> [版面 id...]（沒給就全部）
"""
import hashlib
import json
import os
import sys
import time

root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
out_dir, version, base_url = sys.argv[1:4]
only = sys.argv[4:]

SCHEMA = 1
ENGINES = {"zhuyin26", "pinyin", "cangjie", "quick"}
# 41 個注音符號的順序（keymap 的第 i 個字母對應第 i 個符號）
SYMBOLS = "ㄅㄆㄇㄈㄉㄊㄋㄌㄍㄎㄏㄐㄑㄒㄓㄔㄕㄖㄗㄘㄙㄧㄨㄩㄚㄛㄜㄝㄞㄟㄠㄡㄢㄣㄤㄥㄦ˙ˊˇˋ"
# 第一個認得線上版面的 App versionCode（之前的版本內建版面，讀不懂 layouts）
MIN_APP_VERSION_CODE = 134


def validate(p, path, pack_ids):
    assert p.get("schema", 1) <= SCHEMA, f"{path}：schema 太新"
    for key in ("id", "name", "engine", "language", "languageName"):
        assert key in p, f"{path}：缺少 {key}"
    assert p["id"] == os.path.basename(path)[:-5], f"{path}：id 要跟檔名一樣"
    assert p["id"] != "dachen", f"{path}：大千注音內建在 App"
    assert p["engine"] in ENGINES, f"{path}：engine 要是 {sorted(ENGINES)} 其中之一"
    if p["engine"] == "zhuyin26":
        km = p.get("keymap", "")
        assert len(km) == len(SYMBOLS) and all("a" <= c <= "z" for c in km), f"{path}：keymap 要是 {len(SYMBOLS)} 個小寫字母"
    for r in p.get("requires", []):
        assert r in pack_ids, f"{path}：requires 的 {r} 不在 packs.json"


os.makedirs(out_dir, exist_ok=True)
manifest_path = f"{root}/manifest.json"
manifest = json.load(open(manifest_path, encoding="utf-8"))
entries = {e["id"]: e for e in manifest.get("layouts", [])}
pack_ids = {p["id"] for p in json.load(open(f"{root}/packs.json", encoding="utf-8"))["packs"]}
order = {}

for name in sorted(os.listdir(f"{root}/layouts")):
    if not name.endswith(".json"):
        continue
    path = f"{root}/layouts/{name}"
    p = json.load(open(path, encoding="utf-8"))
    validate(p, path, pack_ids)
    order[p["id"]] = p.get("sort", 99)
    if only and p["id"] not in only:
        continue
    p["version"] = version
    blob = json.dumps(p, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    fname = f"{p['id']}-{version}.json"
    open(f"{out_dir}/{fname}", "wb").write(blob)
    entries[p["id"]] = {
        "id": p["id"],
        "name": p["name"],
        "description": p.get("description", ""),
        "version": version,
        "size": len(blob),
        "sha256": hashlib.sha256(blob).hexdigest(),
        "url": f"{base_url}/{fname}",
        "minAppVersion": MIN_APP_VERSION_CODE,
        "requires": p.get("requires", []),
        # 設定頁先選語言再選版面
        "language": p["language"],
        "languageName": p["languageName"],
    }
    print(f"版面 {p['id']} {version}：{len(blob)} bytes")

manifest["layouts"] = sorted(entries.values(), key=lambda e: (order.get(e["id"], 99), e["id"]))
manifest["updated"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
with open(manifest_path, "w", encoding="utf-8") as f:
    json.dump(manifest, f, ensure_ascii=False, indent=2)
    f.write("\n")
