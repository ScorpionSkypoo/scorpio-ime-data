#!/usr/bin/env python3
"""
一次性：把 manifest.json 裡已發佈的舊格式（SQLite，.db.gz）資料包轉成 SCD（.scd.gz），版本與內容不變。
轉好的檔放在 <輸出目錄>，manifest.json 的 url／size／sha256／rows／minAppVersion 改成 SCD 版；
上傳由呼叫端做（gh release upload packs-<版本> <檔>）。每個資料包轉完都用 verify_scd.py 跟原本的 SQLite 逐鍵比對。

用法：convert_packs_to_scd.py <base 的 scorpio_dict.db> <工作目錄>
"""
import gzip
import hashlib
import json
import os
import shutil
import sqlite3
import subprocess
import sys
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import build_scd  # noqa: E402

MIN_APP_SCD = 123  # 同 make_packs.py：第一個讀得懂 SCD 資料包的 App versionCode

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
base_db, work = sys.argv[1:3]
manifest_path = f"{ROOT}/manifest.json"
manifest = json.load(open(manifest_path, encoding="utf-8"))
out_dir = f"{work}/out"
os.makedirs(out_dir, exist_ok=True)

for e in manifest["packs"]:
    if not e["url"].endswith(".db.gz"):
        continue
    pid, version = e["id"], e["version"]
    d = f"{work}/{pid}"
    shutil.rmtree(d, ignore_errors=True)
    os.makedirs(f"{d}/scd")
    gz = f"{d}/pack.db.gz"
    urllib.request.urlretrieve(e["url"], gz)
    if hashlib.sha256(open(gz, "rb").read()).hexdigest() != e["sha256"]:
        sys.exit(f"{pid}：下載的檔案 sha256 不符")
    with gzip.open(gz) as fi, open(f"{d}/pack.db", "wb") as fo:
        shutil.copyfileobj(fi, fo)
    pack = sqlite3.connect(f"{d}/pack.db")
    tables = {r[0] for r in pack.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}

    # 照 base 詞庫的樣子組一份只有這個資料包的 dict.db／bigram.db，交給 build_scd 與 verify_scd
    db = sqlite3.connect(f"{d}/dict.db")
    db.execute("CREATE TABLE dict (reading TEXT NOT NULL, toneless TEXT NOT NULL, word TEXT NOT NULL, score REAL NOT NULL, initials TEXT, finals TEXT, source TEXT)")
    db.execute("CREATE TABLE addon_dict (reading TEXT NOT NULL, toneless TEXT NOT NULL, word TEXT NOT NULL, score REAL NOT NULL, initials TEXT NOT NULL, finals TEXT NOT NULL, source TEXT NOT NULL)")
    db.execute("CREATE TABLE kaomoji_dict (reading TEXT NOT NULL, kaomoji TEXT NOT NULL, category TEXT NOT NULL, priority INTEGER NOT NULL)")
    db.execute("ATTACH ? AS base", (base_db,))
    db.execute("CREATE TABLE dict_packs AS SELECT * FROM base.dict_packs")
    db.execute("DETACH base")
    db.execute("ATTACH ? AS pack", (f"{d}/pack.db",))
    if "addon_dict" in tables:
        db.execute("INSERT INTO addon_dict SELECT reading, toneless, word, score, initials, finals, source FROM pack.addon_dict ORDER BY rowid")
    if "kaomoji_dict" in tables:
        db.execute("INSERT INTO kaomoji_dict SELECT reading, kaomoji, category, priority FROM pack.kaomoji_dict ORDER BY rowid")
    db.commit()
    bdb = sqlite3.connect(f"{d}/bigram.db")
    bdb.execute("CREATE TABLE bigram (prev TEXT NOT NULL, next TEXT NOT NULL, score REAL NOT NULL, source TEXT NOT NULL, PRIMARY KEY(prev, next, source)) WITHOUT ROWID")
    if "bigram" in tables:
        bdb.execute("ATTACH ? AS pack", (f"{d}/pack.db",))
        bdb.execute("INSERT INTO bigram SELECT prev, next, score, source FROM pack.bigram")
    bdb.commit()

    data = build_scd.build(pid, db, bdb, version)
    if data is None:
        sys.exit(f"{pid}：沒有資料")
    open(f"{d}/scd/{pid}.scd", "wb").write(data)
    subprocess.run([sys.executable, "-I", f"{ROOT}/tools/verify_scd.py", f"{d}/dict.db", f"{d}/bigram.db", f"{d}/scd", pid], check=True)

    name = f"{pid}-{version}.scd.gz"
    with gzip.GzipFile(f"{out_dir}/{name}", "wb", 9, mtime=0) as fo:
        fo.write(data)
    blob = open(f"{out_dir}/{name}", "rb").read()
    rows = sum(build_scd.scd.Reader(data).meta.get("rows", {}).values())
    e.update({
        "url": e["url"].rsplit("/", 1)[0] + "/" + name,
        "size": len(blob),
        "sha256": hashlib.sha256(blob).hexdigest(),
        "rows": rows,
        "minAppVersion": MIN_APP_SCD,
    })
    print(f"{pid} {version}：{rows} 筆，{len(blob) / 1024:.0f} KB")

with open(manifest_path, "w", encoding="utf-8") as f:
    json.dump(manifest, f, ensure_ascii=False, indent=2)
    f.write("\n")
