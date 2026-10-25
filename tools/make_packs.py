#!/usr/bin/env python3
"""
把組好的詞庫切成可以單獨下載的資料包，並更新 manifest.json（App 依這份清單檢查更新）。

每個資料包是一個 gzip 壓縮的 SCD 二進位詞庫（格式見 tools/scd.py、tools/build_scd.py）：meta 帶 id、group、version、name、
description、source、license、url；內容依 group 是詞（流行用語另帶接續詞）、接續詞或顏文字。
App 解壓後直接 mmap 使用，依 meta.id 換掉同 id 的舊檔。輸出的同時把 <dict.db> 的 dict_packs、<bigram.db> 的 pack_versions 改成這一版。

用法：make_packs.py <dict.db> <bigram.db> <輸出目錄> <版本> <下載網址前綴> [資料包 id...]
  沒給 id 就輸出 packs.json 裡所有能線上更新的資料包
  App 內建、一律使用的資料（主詞庫 core、emoji、英文 en、倉頡碼表 cangjie_table）要指名才建：
  manifest 標 system，App 不列開關、有新版就自動更新（主詞庫很大，有改才發佈）
  下載網址前綴例如 https://github.com/ScorpionSkypoo/scorpio-ime-data/releases/download/packs-2026.10.23
"""
import gzip
import hashlib
import json
import os
import sqlite3
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import build_scd  # noqa: E402
import scd  # noqa: E402

root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
dict_db, bigram_db, out_dir, version, base_url = sys.argv[1:6]
only = sys.argv[6:]

MANIFEST_SCHEMA = 1
MIN_APP_SCD = 123  # 第一個讀得懂 SCD 資料包的 App versionCode（舊版 App 讀的是 SQLite 資料包，不能裝 SCD）
MIN_APP_SYSTEM = 200  # 第一個認得 system（內建資料線上更新）的 App versionCode；舊版會把它當成可開關的詞庫列出來
# 指名用的 id → SCD 的 id（倉頡碼表跟倉頡版面同名，建置時用 cangjie_table 區分）
SYSTEM = {"core": "core", "emoji": "emoji", "en": "en", "cangjie_table": "cangjie"}

all_packs = json.load(open(f"{root}/packs.json", encoding="utf-8"))["packs"]
packs = [p for p in all_packs if p["id"] != "core" and (not only or p["id"] in only)]
for alias, pid in SYSTEM.items():
    if alias in only:
        info = next((p for p in all_packs if p["id"] == pid), None) or {"id": pid, **build_scd.BUILTIN[pid]}
        packs.append({"id": pid, "group": info.get("group", pid), "name": info["name"], "description": info.get("description", ""),
                      "source": info["source"], "license": info["license"], "url": info.get("url", ""), "system": True})
os.makedirs(out_dir, exist_ok=True)

src = sqlite3.connect(dict_db)
src.execute("ATTACH ? AS bg", (bigram_db,))
bsrc = sqlite3.connect(bigram_db)

manifest_path = f"{root}/manifest.json"
manifest = json.load(open(manifest_path, encoding="utf-8")) if os.path.exists(manifest_path) else {"packs": []}
entries = {e["id"]: e for e in manifest.get("packs", [])}

for p in packs:
    pid = p["id"]
    name = f"{pid}-{version}.scd"
    path = f"{out_dir}/{name}"
    data = build_scd.build(pid, src, bsrc, version)
    system = p.get("system", False)
    if data is None:
        print(f"{pid}：沒有資料，略過")
        continue
    rows = sum(scd.Reader(data).meta.get("rows", {}).values())
    with gzip.GzipFile(f"{path}.gz", "wb", 9, mtime=0) as fo:
        fo.write(data)
    blob = open(f"{path}.gz", "rb").read()
    entries[pid] = {
        "id": pid,
        "group": scd.Reader(data).meta.get("group", p["group"]) if data else p["group"],
        "name": p["name"],
        "version": version,
        "rows": rows,
        "size": len(blob),
        "sha256": hashlib.sha256(blob).hexdigest(),
        "url": f"{base_url}/{name}.gz",
        # 不內建的資料包要 App 認得「未安裝、預設不開」才行，舊版 App 會把它當一般詞庫自動裝起來
        "minAppVersion": MIN_APP_SYSTEM if system else MIN_APP_SCD,
        "description": p["description"],
        "source": p["source"],
        "license": p["license"],
        "bundled": p.get("bundled", True),
        "default": p.get("default", True),
        "category": p.get("category", ""),
    }
    if system:
        entries[pid]["system"] = True
    print(f"{pid} {version}：{rows} 筆，{len(blob) / 1024:.0f} KB")
    if not p.get("bundled", True):
        # 只能線上安裝的資料包不放進 base（App 不內建）
        src.execute("DELETE FROM addon_dict WHERE source = ?", (pid,))
        src.execute("DELETE FROM bg.bigram WHERE source = ?", (pid,))
        src.execute("DELETE FROM dict_packs WHERE id = ?", (pid,))
        src.commit()
        print(f"{pid}：不內建，已從 base 移除")
        continue
    # 內建的 emoji、en、cangjie 每次建置 base 都用當次版本，不必記
    if system and pid != "core":
        continue
    # base 詞庫記下這版，App 打包時內建的就是最新版，不必一裝好就重新下載
    if src.execute("UPDATE dict_packs SET version = ? WHERE id = ?", (version, pid)).rowcount == 0:
        src.execute("INSERT INTO dict_packs (id, grp, name, description, source, license, url, version, sort) VALUES (?,?,?,?,?,?,?,?,?)",
                    (pid, p["group"], p["name"], p["description"], p["source"], p["license"], p["url"], version, 99))
    if p["group"] == "bigram" or pid == "trendy":
        src.execute("CREATE TABLE IF NOT EXISTS bg.pack_versions (id TEXT PRIMARY KEY, version TEXT NOT NULL)")
        src.execute("INSERT OR REPLACE INTO bg.pack_versions VALUES (?, ?)", (pid, version))
    src.commit()

order = [p["id"] for p in json.load(open(f"{root}/packs.json", encoding="utf-8"))["packs"]]
manifest = {
    "schema": MANIFEST_SCHEMA,
    "updated": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    "packs": sorted(entries.values(), key=lambda e: order.index(e["id"]) if e["id"] in order else 999),
    # 工具列擴充功能（tools/make_plugins.py 寫入）
    "plugins": manifest.get("plugins", []),
    # 鍵盤版面（tools/make_layouts.py 寫入）
    "layouts": manifest.get("layouts", []),
    # 鍵盤設定（tools/make_configs.py 寫入）
    "configs": manifest.get("configs", []),
}
with open(manifest_path, "w", encoding="utf-8") as f:
    json.dump(manifest, f, ensure_ascii=False, indent=2)
    f.write("\n")
