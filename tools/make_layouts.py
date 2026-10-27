#!/usr/bin/env python3
"""
鍵盤版面：layouts/<id>.json → 輸出目錄的 <id>-<版本>.json，並更新 manifest.json 的 layouts。

版面是宣告式的 JSON，只能選 App 內建的打字方式（engine），不含可執行的程式碼（格式見 README〈鍵盤版面〉）。
內建的大千注音（10×4）在 App 裡；大千的其他鍵位（例如三星）用 engine "dachen" 加上 keys 宣告。

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

SCHEMA = 2
ENGINES = {"zhuyin26", "pinyin", "cangjie", "quick", "dachen"}
# 41 個注音符號的順序（keymap 的第 i 個字母對應第 i 個符號）
SYMBOLS = "ㄅㄆㄇㄈㄉㄊㄋㄌㄍㄎㄏㄐㄑㄒㄓㄔㄕㄖㄗㄘㄙㄧㄨㄩㄚㄛㄜㄝㄞㄟㄠㄡㄢㄣㄤㄥㄦ˙ˊˇˋ"
# 第一個認得線上版面的 App versionCode（之前的版本內建版面，讀不懂 layouts）
MIN_APP_VERSION_CODE = 134
# 第一個認得 engine "dachen"（宣告的大千鍵位）的 App versionCode：v1.2.8（173）之後的版本
MIN_APP_VERSION_DACHEN = 174


def validate_keys(k, path, engine):
    """schema 2 的 keys（QWERTY 面板或大千鍵盤的字鍵排），規則跟 App 的 KeyboardLayout.parse、ChineseMethod.parse 一樣，見 README〈字鍵排〉"""
    cols = k.get("columns", 10)
    assert isinstance(cols, int) and 10 <= cols <= 12, f"{path}：columns 要是 10～12"
    rows = k.get("rows")
    assert isinstance(rows, list) and 1 <= len(rows) <= 4, f"{path}：rows 要有 1～4 排"
    nums = k.get("numberRow", "")
    assert all("0" <= c <= "9" for c in nums) and len(nums) <= cols, f"{path}：numberRow 只能是數字、最多 {cols} 個"
    chars, shifts, backspaces = list(nums), 0, 0
    for i, row in enumerate(rows):
        items = [row] if isinstance(row, str) else row
        assert isinstance(items, list) and items, f"{path}：第 {i + 1} 排是空的"
        fixed, flexible = 0.0, 0
        for e in items:
            if isinstance(e, str):
                chars += list(e)
                fixed += len(e)
                continue
            assert isinstance(e, dict), f"{path}：第 {i + 1} 排的鍵要是字串或物件"
            w = e.get("width")
            if "special" in e:
                assert e["special"] in ("shift", "backspace"), f"{path}：special 只能是 shift 或 backspace"
                shifts += e["special"] == "shift"
                backspaces += e["special"] == "backspace"
                assert w is None or w >= 1, f"{path}：功能鍵至少 1 欄"
                if w is None:
                    flexible += 1
                else:
                    fixed += w
            else:
                assert isinstance(e.get("key"), str) and len(e["key"]) == 1, f"{path}：key 要是一個字"
                assert w is None or 1 <= w <= 2, f"{path}：字鍵寬 1～2 欄"
                chars.append(e["key"])
                fixed += 1 if w is None else w
        assert fixed <= cols + 1e-6, f"{path}：第 {i + 1} 排超過 {cols} 欄"
        assert flexible == 0 or (cols - fixed) / flexible >= 1, f"{path}：第 {i + 1} 排的功能鍵分不到 1 欄"
    assert backspaces == 1 and shifts <= 1, f"{path}：刪除鍵要剛好一個、Shift 最多一個"
    assert len(chars) == len(set(chars)), f"{path}：有重複的鍵"
    assert not any(c in "*:;" or c.isspace() for c in chars), f"{path}：* : ; 與空白不能當字鍵"
    letters = [c for c in chars if c not in nums]
    if engine == "dachen":
        # 大千：字鍵剛好是 41 個注音符號與聲調（含 ㄦ），沒有 Shift
        assert sorted(letters) == sorted(SYMBOLS), f"{path}：大千的字鍵要剛好是 41 個注音符號與聲調各一次"
        assert shifts == 0, f"{path}：大千不能有 Shift"
        return
    # 其他打字方式都用 26 個英文字母
    assert sorted(letters) == [chr(c) for c in range(ord("a"), ord("z") + 1)], f"{path}：字鍵要剛好是 a–z 各一次"


def validate(p, path, pack_ids):
    assert p.get("schema", 1) <= SCHEMA, f"{path}：schema 太新"
    for key in ("id", "name", "engine", "language", "languageName"):
        assert key in p, f"{path}：缺少 {key}"
    assert p["id"] == os.path.basename(path)[:-5], f"{path}：id 要跟檔名一樣"
    assert p["id"] != "dachen", f"{path}：內建的大千注音在 App 裡，id 不能是 dachen"
    assert p["engine"] in ENGINES, f"{path}：engine 要是 {sorted(ENGINES)} 其中之一"
    if p["engine"] == "zhuyin26":
        km = p.get("keymap", "")
        assert len(km) == len(SYMBOLS) and all("a" <= c <= "z" for c in km), f"{path}：keymap 要是 {len(SYMBOLS)} 個小寫字母"
    if p["engine"] == "dachen":
        assert "keys" in p, f"{path}：大千的版面要寫 keys（內建的 10×4 在 App 裡）"
        assert p.get("minAppVersion", 0) >= MIN_APP_VERSION_DACHEN, f"{path}：大千的版面 minAppVersion 至少 {MIN_APP_VERSION_DACHEN}"
    for r in p.get("requires", []):
        assert r in pack_ids, f"{path}：requires 的 {r} 不在 packs.json"
    if "keys" in p:
        assert p.get("schema", 1) >= 2, f"{path}：有 keys 的版面 schema 要是 2"
        # 舊版 App 看不懂 keys（會整個不收），要寫第一個看得懂的 App versionCode
        assert isinstance(p.get("minAppVersion"), int), f"{path}：有 keys 的版面要寫 minAppVersion"
        validate_keys(p["keys"], path, p["engine"])


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
        "minAppVersion": max(MIN_APP_VERSION_CODE, p.get("minAppVersion", 0)),
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
