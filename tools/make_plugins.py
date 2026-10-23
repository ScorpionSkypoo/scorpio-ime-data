#!/usr/bin/env python3
"""
工具列擴充功能（外掛）：plugins/<id>.json → 輸出目錄的 <id>-<版本>.json，並更新 manifest.json 的 plugins。

外掛是宣告式的 JSON，只能組合 App 內建的動作，不含可執行的程式碼（格式見 README〈擴充功能〉）。

用法：make_plugins.py <輸出目錄> <版本> <下載網址前綴> [外掛 id...]（沒給就全部）
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
ACTIONS = {"insert", "transform", "open_url"}
OPS = {"fullwidth", "halfwidth", "upper", "lower", "title", "trim_spaces"}
MIN_APP_VERSION_CODE = 105


def validate(p, path):
    assert p.get("schema", 1) <= SCHEMA, f"{path}：schema 太新"
    for key in ("id", "name", "tabs"):
        assert key in p, f"{path}：缺少 {key}"
    assert p["id"] == os.path.basename(path)[:-5], f"{path}：id 要跟檔名一樣"
    for tab in p["tabs"]:
        assert tab.get("name") and tab.get("items"), f"{path}：每個分頁要有 name 和 items"
        for item in tab["items"]:
            if isinstance(item, str):
                continue
            action = item.get("action", "insert")
            assert action in ACTIONS, f"{path}：不支援的動作 {action}"
            assert item.get("label"), f"{path}：項目要有 label"
            if action == "insert":
                assert "insert" in item, f"{path}：{item['label']} 缺少 insert"
            if action == "transform":
                assert item.get("op") in OPS, f"{path}：不支援的轉換 {item.get('op')}"
            if action == "open_url":
                assert item.get("url", "").startswith("https://"), f"{path}：網址要用 https"


os.makedirs(out_dir, exist_ok=True)
manifest_path = f"{root}/manifest.json"
manifest = json.load(open(manifest_path, encoding="utf-8"))
entries = {e["id"]: e for e in manifest.get("plugins", [])}

for name in sorted(os.listdir(f"{root}/plugins")):
    if not name.endswith(".json"):
        continue
    path = f"{root}/plugins/{name}"
    p = json.load(open(path, encoding="utf-8"))
    validate(p, path)
    if only and p["id"] not in only:
        continue
    p["version"] = version
    blob = json.dumps(p, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    fname = f"{p['id']}-{version}.json"
    open(f"{out_dir}/{fname}", "wb").write(blob)
    entries[p["id"]] = {
        "id": p["id"],
        "name": p["name"],
        "icon": p.get("icon", ""),
        "description": p.get("description", ""),
        "version": version,
        "size": len(blob),
        "sha256": hashlib.sha256(blob).hexdigest(),
        "url": f"{base_url}/{fname}",
        "minAppVersion": MIN_APP_VERSION_CODE,
    }
    print(f"外掛 {p['id']} {version}：{len(blob)} bytes")

manifest["plugins"] = sorted(entries.values(), key=lambda e: e["id"])
manifest["updated"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
with open(manifest_path, "w", encoding="utf-8") as f:
    json.dump(manifest, f, ensure_ascii=False, indent=2)
    f.write("\n")
