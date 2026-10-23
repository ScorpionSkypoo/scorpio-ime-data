#!/usr/bin/env bash
# 下載接續詞語料到 <目錄>（約 750 MB）：中文維基百科第一個分割檔、PTT 兩份、Dcard 一份
# 以及需要原始資料的附加詞庫（放在 <目錄>/../raw）：cs_terms（國家教育研究院電子計算機學術名詞）、moe_dict（教育部國語辭典）
set -euo pipefail
C=${1:?用法：fetch_corpus.sh <目錄> [來源...]}
mkdir -p "$C"
H=https://huggingface.co/api/datasets
shift
SRC="$*"
get() { [ -s "$C/$1" ] || curl -fsSL --retry 3 -o "$C/$1" "$2"; }
if [ -z "$SRC" ] || [[ " $SRC " == *" bg_wiki "* ]]; then
  get wiki1.bz2 https://dumps.wikimedia.org/zhwiki/latest/zhwiki-latest-pages-articles1.xml-p1p187712.bz2
fi
if [ -z "$SRC" ] || [[ " $SRC " == *" bg_ptt "* ]]; then
  get pttpre.parquet $H/yuhuanstudio/PTT-pretrain-zhtw/parquet/default/train/0.parquet
  get pttqa.parquet $H/Riyuechang/PTT-Corpus-100K_Gossiping-1400-39400_v2/parquet/default/train/0.parquet
fi
if [ -z "$SRC" ] || [[ " $SRC " == *" bg_dcard "* ]]; then
  get dcard.parquet $H/iddle/dcard_conversations/parquet/default/train/0.parquet
fi
if [ -z "$SRC" ] || [[ " $SRC " == *" cs_terms "* ]]; then
  # 附加詞庫原始資料放 raw（跟 corpus 同一層）
  mkdir -p "$C/../raw"
  [ -s "$C/../raw/naer_cs_terms.csv" ] || curl -fsSL --retry 3 -o "$C/../raw/naer_cs_terms.csv" \
    "https://opendata.naer.edu.tw/%E5%AD%B8%E8%A1%93%E5%90%8D%E8%A9%9E/%E5%9C%8B%E5%AE%B6%E6%95%99%E8%82%B2%E7%A0%94%E7%A9%B6%E9%99%A2-%E9%9B%BB%E5%AD%90%E8%A8%88%E7%AE%97%E6%A9%9F%E5%AD%B8%E8%A1%93%E5%90%8D%E8%A9%9E.csv"
fi
if [ -z "$SRC" ] || [[ " $SRC " == *" moe_dict "* ]]; then
  mkdir -p "$C/../raw"
  if [ ! -s "$C/../raw/dict-revised.json" ]; then
    curl -fsSL --retry 3 -o "$C/../raw/dict-revised.json.xz" https://raw.githubusercontent.com/g0v/moedict-data/master/dict-revised.json.xz
    xz -d -f "$C/../raw/dict-revised.json.xz"
  fi
fi
ls -la "$C"
