#!/usr/bin/env python3
"""
Rebuild emoji_dict (keyword -> emoji) in the base dict (SQLite) from Unicode CLDR Traditional Chinese annotations.

Source: unicode-org/cldr release-48 common/annotations/zh_Hant.xml (Unicode License v3)
  https://raw.githubusercontent.com/unicode-org/cldr/release-48/common/annotations/zh_Hant.xml

Priority (lower = shown first):
  1. hand-curated rows already in the table (kept as-is, e.g. 狗 -> 🐶 🐕 🐩)
  2. the keyword is the emoji's spoken name (tts), e.g. 老鼠 -> 🐀
  3. other keywords, more specific first (a keyword shared by fewer emoji ranks higher)
Keywords shared by more than MAX_SHARED emoji (動物, 臉, 符號…) are dropped as too generic.

Emoji the phone's font can't draw (too new) are filtered by the App at display time, so nothing is excluded here.

Usage: python3 tools/build_emoji_dict.py <dict.db> <zh_Hant.xml>
"""

import re
import sqlite3
import sys
import xml.etree.ElementTree as ET

MAX_SHARED = 25
HAN_RE = re.compile(r'[㐀-鿿]')

# Hand-picked additions (shown first)
EXTRA = {
    '台灣': ['🇹🇼', '🧋'],
    '開心': ['😄', '😊', '🥰'],
    '高興': ['😄', '😊'],
    '難過': ['😢', '😭'],
}


def main():
    if len(sys.argv) != 3:
        print(__doc__)
        sys.exit(1)

    names, keywords = {}, {}
    for a in ET.parse(sys.argv[2]).getroot().iter('annotation'):
        cp, text = a.get('cp'), (a.text or '').strip()
        if not cp or not text:
            continue
        # BMP symbols (☂ ☕ ✂) default to text style; FE0F asks for the colour emoji glyph
        if len(cp) == 1 and ord(cp) < 0x1F000:
            cp += '\ufe0f'

        if a.get('type') == 'tts':
            names[cp] = text
        else:
            keywords[cp] = [k.strip() for k in text.split('|') if k.strip()]

    shared = {}
    for cp, kws in keywords.items():
        for k in set(kws):
            shared[k] = shared.get(k, 0) + 1

    rows = {}  # (keyword, emoji) -> priority

    def put(k, e, p):
        if not HAN_RE.search(k):
            return
        if (k, e) not in rows or p < rows[(k, e)]:
            rows[(k, e)] = p

    for cp, name in names.items():
        put(name, cp, 10)
    for cp, kws in keywords.items():
        for k in kws:
            n = shared.get(k, 1)
            if n > MAX_SHARED:
                continue
            put(k, cp, 20 + n)

    conn = sqlite3.connect(sys.argv[1])
    curated = conn.execute("SELECT keyword, emoji, priority FROM emoji_dict WHERE priority < 10").fetchall()
    before = conn.execute("SELECT count(*) FROM emoji_dict").fetchone()[0]
    # Curated rows win; drop CLDR duplicates that differ only by the FE0F selector (☕ vs ☕️)
    curated_bare = {(k, e.replace('\ufe0f', '')) for k, e, _ in curated}
    rows = {(k, e): p for (k, e), p in rows.items() if (k, e.replace('\ufe0f', '')) not in curated_bare}
    for k, e, p in curated:
        rows[(k, e)] = p
    for k, ems in EXTRA.items():
        for i, e in enumerate(ems):
            rows[(k, e)] = min(rows.get((k, e), 99), i)
    conn.execute("DELETE FROM emoji_dict")
    conn.executemany("INSERT INTO emoji_dict (keyword, emoji, priority) VALUES (?, ?, ?)",
                     sorted(((k, e, p) for (k, e), p in rows.items()), key=lambda r: (r[0], r[2])))
    conn.commit()
    n_kw = conn.execute("SELECT count(DISTINCT keyword) FROM emoji_dict").fetchone()[0]
    n_em = conn.execute("SELECT count(DISTINCT emoji) FROM emoji_dict").fetchone()[0]
    conn.close()
    print(f"emoji_dict rebuilt: {len(rows)} rows, {n_kw} keywords, {n_em} emoji (was {before} rows; kept {len(curated)} curated)")


if __name__ == '__main__':
    main()
