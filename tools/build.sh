#!/usr/bin/env bash
# 重建指定的資料包並更新 manifest.json
#
# 用法：tools/build.sh <工作目錄> <版本> <資料包、外掛或版面 id...>
#   例：tools/build.sh work 2026.10.23 trendy
#       tools/build.sh work 2026.10.23 emoji trendy   （emoji 是 App 內建的 Emoji 資料，只更新 base；要跟一個資料包一起建，Release 才不會是空的）
#       tools/build.sh work 2026.10.23 bg_wiki bg_ptt bg_dcard   （先跑 tools/fetch_corpus.sh work/corpus）
#   工作目錄/raw     附加詞庫原始資料（缺的來源保留 base 裡原本的詞）
#   工作目錄/corpus  接續詞語料
#   base/            基底詞庫（主詞庫＋目前的附加詞庫、接續詞），沒有就從 base Release 下載
# 產出：工作目錄/out（資料包 <id>-<版本>.scd.gz，網址指向 Release「packs-<版本>」）、
#       工作目錄/base（更新後的基底詞庫：scorpio_*.db.gz 是建置用的 SQLite，*.scd.gz 是 App 內建的 SCD 詞庫）
# 上傳由 GitHub Actions 處理
set -euo pipefail
W=$(realpath -m "$1"); V=$2; shift 2
PACKS="$*"
R=$(dirname "$(dirname "$(realpath "$0")")")
PY=${PYTHON:-python3}
REPO=${GITHUB_REPOSITORY:-ScorpionSkypoo/scorpio-ime-data}
mkdir -p "$W/raw" "$W/corpus" "$W/bg" "$W/out" "$R/base"

for f in scorpio_dict.db.gz scorpio_bigram.db.gz; do
  [ -s "$R/base/$f" ] || curl -fsSL --retry 3 -o "$R/base/$f" "https://github.com/$REPO/releases/download/base/$f"
done
gunzip -c "$R/base/scorpio_dict.db.gz" > "$W/dict.db"
gunzip -c "$R/base/scorpio_bigram.db.gz" > "$W/bigram.db"

"$PY" -I "$R/tools/build_addon_dicts.py" "$W/raw" "$W/dict.db"
# Emoji 關鍵字（CLDR 繁中註解）與面板分類（Unicode emoji-test.txt），來源檔在 emoji/
if [[ " $PACKS " == *" emoji "* ]]; then
  "$PY" -I "$R/tools/build_emoji_dict.py" "$W/dict.db" "$R/emoji/zh_Hant.xml"
  "$PY" -I "$R/tools/build_emoji_categories.py" "$W/dict.db" "$R/emoji/emoji-test.txt"
fi
if [[ " $PACKS " == *" kaomoji "* ]]; then
  "$PY" -I "$R/tools/build_kaomoji.py" "$W/dict.db" $( [ -f "$W/raw/emoticons.json" ] && echo "$W/raw/emoticons.json" )
fi

BG=""
for s in $PACKS; do case $s in bg_*|trendy) BG="$BG $s";; esac; done
for s in $BG; do
  rm -f "$W/bg/$s.db"
  "$PY" -I "$R/tools/build_bigram_packs.py" "$W/dict.db" "$W/corpus" "$R/sources/trendy.txt" "$W/bg/$s.db" "$s" > "$W/bg/$s.log" 2>&1 &
done
wait
for s in $BG; do tail -n 1 "$W/bg/$s.log"; done
"$PY" -I - "$W/bigram.db" "$W/bg" $BG <<'PYEOF'
import sqlite3, sys
out, bg, sources = sys.argv[1], sys.argv[2], sys.argv[3:]
db = sqlite3.connect(out)
for s in sources:
    db.execute("ATTACH ? AS src", (f"{bg}/{s}.db",))
    if db.execute("SELECT count(*) FROM src.bigram WHERE source = ?", (s,)).fetchone()[0]:
        db.execute("DELETE FROM bigram WHERE source = ?", (s,))
        db.execute("INSERT INTO bigram SELECT prev, next, score, source FROM src.bigram WHERE source = ?", (s,))
    db.commit()
    db.execute("DETACH src")
PYEOF

# 外掛（plugins/<id>.json）、鍵盤版面（layouts/<id>.json）與資料包分開處理
DATA="" PLUGINS="" LAYOUTS=""
for s in $PACKS; do
  if [ "$s" = emoji ]; then continue
  elif [ -f "$R/plugins/$s.json" ]; then PLUGINS="$PLUGINS $s"
  elif [ -f "$R/layouts/$s.json" ]; then LAYOUTS="$LAYOUTS $s"
  else DATA="$DATA $s"; fi
done
if [ -n "$DATA" ]; then
  "$PY" -I "$R/tools/make_packs.py" "$W/dict.db" "$W/bigram.db" "$W/out" "$V" \
    "https://github.com/$REPO/releases/download/packs-$V" $DATA
fi
if [ -n "$PLUGINS" ]; then
  "$PY" -I "$R/tools/make_plugins.py" "$W/out" "$V" "https://github.com/$REPO/releases/download/packs-$V" $PLUGINS
fi
if [ -n "$LAYOUTS" ]; then
  "$PY" -I "$R/tools/make_layouts.py" "$W/out" "$V" "https://github.com/$REPO/releases/download/packs-$V" $LAYOUTS
fi
# 新的 base（給下一次建置與 App 打包用）
mkdir -p "$W/base" "$W/scd"
gzip -9 -n -c "$W/dict.db" > "$W/base/scorpio_dict.db.gz"
gzip -9 -n -c "$W/bigram.db" > "$W/base/scorpio_bigram.db.gz"
# App 內建的 SCD 詞庫（只放內建的資料包；版本是各資料包最後發佈的那版）
rm -f "$W/scd"/*.scd "$W/base"/*.scd.gz
"$PY" -I "$R/tools/build_scd.py" --base "$W/dict.db" "$W/bigram.db" "$W/scd" "$V"
# 逐鍵比對 SCD 與 SQLite（結果、同分順序都要跟 App 舊版的 SQL 一樣），不一致就中止，不發佈
"$PY" -I "$R/tools/verify_scd.py" "$W/dict.db" "$W/bigram.db" "$W/scd" | tail -n 1
for f in "$W/scd"/*.scd; do gzip -9 -n -c "$f" > "$W/base/$(basename "$f").gz"; done
ls -la "$W/out" "$W/base"
