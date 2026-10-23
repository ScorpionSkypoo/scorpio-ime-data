#!/usr/bin/env bash
# 下載接續詞語料到 <目錄>（約 750 MB）：中文維基百科第一個分割檔、PTT 兩份、Dcard 一份
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
ls -la "$C"
