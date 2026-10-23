#!/usr/bin/env python3
"""
產生 App 單元測試用的 SCD 固定檔：App 端 ScdWriter.kt 對同一份資料必須寫出每個 byte 都相同的檔案。

用法：scd_fixture.py <輸出目錄>
  輸出 words_fixture.tsv（reading、toneless、word、score、initials、finals，Tab 分隔，順序即原本的 rowid 順序）
  與 words_fixture.scd（scd.py 對同一份資料寫出的檔案）。把兩個檔放進 App 的 app/src/test/resources/。
資料刻意包含：同分（比同分時的先後）、補充平面的字（surrogate pair）、超過 PREFIX_HEAVY 筆的熱門前綴、
空的聲母或韻母（_）、需要 JSON 跳脫的 meta。
"""
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import scd  # noqa: E402

META = {"id": "fixture", "group": "words", "name": "測試\"詞庫\"\n\\\t\u0001", "version": "2026.1.1", "bundled": True, "sort": 7}


def rows():
    rnd = random.Random(20261023)
    initials = "ㄅㄆㄇㄈㄉㄊㄋㄌ"
    finals = ["ㄚ", "ㄞ", "ㄢ", "ㄤ", "ㄧㄚ", "ㄨㄛ", "ㄥ"]
    out = []
    # 熱門前綴：「ㄅㄚ」開頭的 300 筆以上，分數有大量同分
    for i in range(320):
        syl = ["ㄅㄚ"] + (["ㄇㄚ"] if i % 3 == 0 else []) + (["ㄉㄜ"] if i % 7 == 0 else [])
        out.append(("-".join(syl), "-".join(syl), "詞%d" % i, -3.0 - (i % 9) * 0.5, "ㄅ" + "-ㄇ" * (i % 3 == 0), "ㄚ" + "-ㄚ" * (i % 3 == 0)))
    for i in range(400):
        ini, fin = rnd.choice(initials), rnd.choice(finals)
        syl = ini + fin
        word = rnd.choice(["字", "𠀀", "好", "𥯓", "你好", "媽媽", "ABC"]) + str(rnd.randrange(30))
        out.append((syl + ("ˋ" if i % 2 else ""), syl, word, round(rnd.uniform(-9, -2), 1), ini, fin))
    out.append(("ㄚ", "ㄚ", "啊", -2.5, "_", "ㄚ"))
    out.append(("ㄅ", "ㄅ", "不", -2.5, "ㄅ", "_"))
    return out


def main():
    out_dir = sys.argv[1]
    os.makedirs(out_dir, exist_ok=True)
    rs = rows()
    with open(f"{out_dir}/words_fixture.tsv", "w", encoding="utf-8") as f:
        for r in rs:
            f.write("\t".join([r[0], r[1], r[2], repr(r[3]), r[4], r[5]]) + "\n")
    data = scd.Writer(META).add(scd.Words(rs)).build()
    with open(f"{out_dir}/words_fixture.scd", "wb") as f:
        f.write(data)
    print(f"words_fixture.scd {len(data)} bytes，{len(rs)} 筆")


if __name__ == "__main__":
    main()
