#!/usr/bin/env python3
"""
補齊 Emoji 面板的分類（emoji_category_dict）：照 Unicode emoji-test.txt 把還沒收錄的 Emoji 加進對應分類。

- 已經有的保留原本的順序；缺的照 Unicode 的順序，插在它前一個（同分類、已收錄的）Emoji 後面，新的會跟相近的排在一起
- 只收 fully-qualified、不含膚色的（膚色變體不列在面板上）
- 手機字型畫不出來的（太新的 Emoji）由 App 在顯示時濾掉，這裡不必排除

Source: https://unicode.org/Public/<版本>/emoji/emoji-test.txt (Unicode License v3)

Usage: python3 tools/build_emoji_categories.py <dict.db> <emoji-test.txt>
"""

import re
import sqlite3
import sys

# Unicode 的大分類 → 面板的分類
GROUPS = {
    'Smileys & Emotion': '😀 表情人物',
    'People & Body': '😀 表情人物',
    'Animals & Nature': '🐶 動物自然',
    'Food & Drink': '🍔 美食飲品',
    'Travel & Places': '✈️ 旅遊景點',
    'Activities': '⚽ 休閒活動',
    'Objects': '💡 生活物品',
    'Symbols': '🔣 符號標記',
    'Flags': '🚩 旗幟標籤',
}
LINE = re.compile(r'^([0-9A-F ]+?)\s*;\s*fully-qualified\s*#')


def bare(e):
    return e.replace('️', '')


def read_unicode(path):
    """每個面板分類：Unicode 順序的 Emoji 清單"""
    out = {c: [] for c in set(GROUPS.values())}
    group = None
    for line in open(path, encoding='utf-8'):
        if line.startswith('# group:'):
            group = line.split(':', 1)[1].strip()
            continue
        m = LINE.match(line)
        if not m or group not in GROUPS:
            continue
        cps = [int(x, 16) for x in m.group(1).split()]
        if any(0x1F3FB <= x <= 0x1F3FF for x in cps):
            continue
        out[GROUPS[group]].append(''.join(chr(x) for x in cps))
    return out


def main():
    if len(sys.argv) != 3:
        print(__doc__)
        sys.exit(1)
    unicode_order = read_unicode(sys.argv[2])
    conn = sqlite3.connect(sys.argv[1])
    # 分類的順序是第一次出現的 rowid（App 的頁籤照這個排），重寫時保持不變
    cats = [c for (c,) in conn.execute("SELECT category FROM emoji_category_dict GROUP BY category ORDER BY min(rowid)")]
    rows = conn.execute("SELECT category, emoji FROM emoji_category_dict ORDER BY category, priority").fetchall()
    current = {c: [] for c in cats}
    for cat, e in rows:
        current.setdefault(cat, []).append(e)
    have = {bare(e) for _, e in rows}

    added = 0
    for cat, order in unicode_order.items():
        lst = current.setdefault(cat, [])
        pos = {bare(e): i for i, e in enumerate(lst)}
        # 每個缺的 Emoji 插在 Unicode 順序裡它前一個已收錄者的後面（連續缺的照順序接在一起）
        last = -1
        out_after = {}  # 插入點 → 要插的 Emoji
        for e in order:
            b = bare(e)
            if b in pos:
                last = pos[b]
            elif b not in have:
                out_after.setdefault(last, []).append(e)
                have.add(b)
                added += 1
        merged = out_after.get(-1, [])[:]
        for i, e in enumerate(lst):
            merged.append(e)
            merged.extend(out_after.get(i, []))
        current[cat] = merged

    conn.execute("DELETE FROM emoji_category_dict")
    for cat, lst in current.items():
        conn.executemany("INSERT INTO emoji_category_dict (category, emoji, priority) VALUES (?, ?, ?)",
                         [(cat, e, i) for i, e in enumerate(lst, start=1)])
    conn.commit()
    total = conn.execute("SELECT count(*) FROM emoji_category_dict").fetchone()[0]
    conn.close()
    print(f"emoji_category_dict：補上 {added} 個，共 {total} 個")


if __name__ == '__main__':
    main()
