#!/usr/bin/env python3
"""
新詞雷達：蒐集近期的網路用語語料，存成 JSON Lines（一行一段文字，只留在工作目錄，不進版控）

來源：
  1. Google Trends 台灣每日熱搜（RSS）：熱搜關鍵字本身，以及拿它們去 PTT 搜尋到的文章
  2. PTT 熱門看板最近幾天的文章與推文
  3. Threads 熱門話題統計（tools.ccea.tw/threadscount，過去 7 天的熱門話題標題與摘要；
     該站 robots.txt 允許存取、只禁止拿去訓練 AI，這裡只拿來找新詞，一週抓一次）
  4. Threads 關鍵字搜尋（設定環境變數 THREADS_ACCESS_TOKEN 才會啟用；
     Meta App Review 通過 threads_keyword_search 前只搜得到自己的貼文）
  5. 公視新聞網 RSS（news.pts.org.tw/xml/newsfeed.xml）：最近的新聞標題與摘要，補時事人名、地名
  6. 中文維基百科：最近幾天的新條目與每日瀏覽最多的條目（只取標題）。維基中文多半是大陸寫的，
     discover.py 只留台灣語料（PTT、公視…）裡也出現的標題

用法：collect.py <輸出 texts.jsonl> [--days 7] [--pages 10]
"""
import argparse
import html
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

UA = "scorpio-ime-radar/1.0 (+https://github.com/ScorpionSkypoo/scorpio-ime-data)"
PTT = "https://www.ptt.cc"
BOARDS = ["Gossiping", "C_Chat", "WomenTalk", "Boy-Girl", "Lifeismoney", "joke", "Stock", "Baseball", "Tech_Job", "movie",
          "KoreaStar", "Japan_Travel", "home-sale", "MobileComm", "e-shopping"]
SEARCH_BOARDS = ["Gossiping", "C_Chat", "WomenTalk"]
DELAY = 0.4


def get(url, headers=None, timeout=30):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Cookie": "over18=1", **(headers or {})})
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.read().decode("utf-8", errors="replace")
        except Exception as e:
            if attempt == 2:
                print(f"  失敗 {url}：{e}", file=sys.stderr)
                return None
            time.sleep(2 * (attempt + 1))
    return None


def trends():
    text = get("https://trends.google.com/trending/rss?geo=TW")
    if not text:
        return [], []
    ns = {"ht": "https://trends.google.com/trending/rss"}
    root = ET.fromstring(text)
    topics, titles = [], []
    for item in root.iter("item"):
        t = (item.findtext("title") or "").strip()
        if t:
            topics.append(t)
        for n in item.findall("ht:news_item", ns):
            titles.append((n.findtext("ht:news_item_title", default="", namespaces=ns) or "").strip())
    return topics, [t for t in titles if t]


RE_LINK = re.compile(r'<div class="title">\s*<a href="(/bbs/[^"]+\.html)">')
RE_PREV = re.compile(r'<a class="btn wide" href="(/bbs/[^"]+/index\d+\.html)">&lsaquo; 上頁</a>')
RE_MAIN = re.compile(r'<div id="main-content"[^>]*>(.*?)<span class="f2">※ 發信站', re.S)
RE_META = re.compile(r'<div class="article-metaline.*?</div>\s*</div>|<div class="article-metaline-right.*?</div>\s*</div>', re.S)
RE_PUSH = re.compile(r'<span class="[^"]*push-content">:?\s*(.*?)</span>', re.S)
RE_TAG = re.compile(r"<[^>]+>")
RE_STAMP = re.compile(r"/M\.(\d{10})\.")


def pts():
    """公視新聞網 RSS（Atom）：標題、摘要"""
    text = get("https://news.pts.org.tw/xml/newsfeed.xml")
    if not text:
        return []
    ns = {"a": "http://www.w3.org/2005/Atom"}
    out = []
    for e in ET.fromstring(text).iter("{http://www.w3.org/2005/Atom}entry"):
        for tag in ("a:title", "a:summary"):
            t = (e.findtext(tag, default="", namespaces=ns) or "").strip()
            if t:
                out.append(html.unescape(t))
    return out


WIKI = "https://zh.wikipedia.org/w/api.php"
RE_PAREN = re.compile(r"\s*[（(].*?[)）]$")


def wiki_titles(days):
    """中文維基最近 days 天的新條目、每天瀏覽最多的 1000 個條目（只取標題，去掉「（歌手）」這種消歧義括號）"""
    new, top = [], []
    since = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time() - days * 86400))
    params = {"action": "query", "list": "recentchanges", "rctype": "new", "rcnamespace": "0", "rclimit": "500",
              "rcprop": "title", "rcend": since, "format": "json"}
    for _ in range(40):
        text = get(WIKI + "?" + urllib.parse.urlencode(params))
        if not text:
            break
        d = json.loads(text)
        new += [x["title"] for x in d.get("query", {}).get("recentchanges", [])]
        if "continue" not in d:
            break
        params.update(d["continue"])
        time.sleep(DELAY)
    for k in range(1, days + 1):
        day = time.strftime("%Y/%m/%d", time.gmtime(time.time() - k * 86400))
        text = get(f"https://wikimedia.org/api/rest_v1/metrics/pageviews/top/zh.wikipedia/all-access/{day}")
        if text:
            for it in json.loads(text).get("items", []):
                top += [a["article"].replace("_", " ") for a in it.get("articles", []) if ":" not in a["article"]]
        time.sleep(DELAY)
    strip = lambda ts: list(dict.fromkeys(RE_PAREN.sub("", t) for t in ts))
    return strip(new), strip(top)


def clean(fragment):
    return html.unescape(RE_TAG.sub("", fragment)).strip()


def article(url):
    page = get(PTT + url)
    time.sleep(DELAY)
    if not page:
        return []
    out = []
    m = RE_MAIN.search(page)
    if m:
        body = RE_META.sub("", m.group(1))
        body = clean(body.split('<div class="push">')[0])
        # 去掉引用（: 開頭）與簽名檔
        lines = [l for l in body.splitlines() if l.strip() and not l.startswith((":", "※", "--"))]
        if lines:
            out.append("\n".join(lines))
    out.extend(p for p in (clean(x) for x in RE_PUSH.findall(page)) if p)
    return out


def threadscount():
    """Threads 熱門話題統計：過去 7 天的熱門話題（標題、摘要、涵蓋的事件）"""
    text = get(f"https://tools.ccea.tw/threadscount/data/live_7d.json?t={int(time.time())}")
    if not text:
        return []
    try:
        topics = json.loads(text).get("topics", [])
    except ValueError:
        return []
    out = []
    for t in topics:
        out.extend(x for x in (t.get("title"), t.get("summary")) if x)
        out.extend(x for x in t.get("items", []) if isinstance(x, str))
    return out


def board_recent(board, days, pages):
    since = time.time() - days * 86400
    url = f"/bbs/{board}/index.html"
    links = []
    for _ in range(pages):
        page = get(PTT + url)
        time.sleep(DELAY)
        if not page:
            break
        found = RE_LINK.findall(page)
        stamps = [int(s.group(1)) for s in map(RE_STAMP.search, found) if s]
        links.extend(l for l in found if (s := RE_STAMP.search(l)) and int(s.group(1)) >= since)
        prev = RE_PREV.search(page)
        # 首頁最底下有置底的舊文，所以整頁都比 since 舊才停
        if not prev or (stamps and max(stamps) < since):
            break
        url = prev.group(1)
    return links


def ptt_search(board, q, limit=6):
    page = get(f"{PTT}/bbs/{board}/search?q={urllib.parse.quote(q)}")
    time.sleep(DELAY)
    return RE_LINK.findall(page or "")[:limit]


def threads_search(token, q):
    url = "https://graph.threads.net/v1.0/keyword_search?" + urllib.parse.urlencode(
        {"q": q, "search_type": "RECENT", "fields": "text", "access_token": token})
    text = get(url)
    if not text:
        return []
    try:
        return [d["text"] for d in json.loads(text).get("data", []) if d.get("text")]
    except ValueError:
        return []


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("out")
    ap.add_argument("--days", type=int, default=7)
    ap.add_argument("--pages", type=int, default=10, help="每個看板最多往前翻幾頁")
    args = ap.parse_args()

    n = 0
    seen = set()
    with open(args.out, "w", encoding="utf-8") as f:
        def emit(source, text):
            nonlocal n
            f.write(json.dumps({"source": source, "text": text}, ensure_ascii=False) + "\n")
            n += 1

        topics, news = trends()
        print(f"Google Trends：{len(topics)} 個熱搜、{len(news)} 則新聞標題")
        for t in topics:
            emit("trends", t)
        for t in news:
            emit("trends-news", t)

        news = pts()
        print(f"公視新聞：{len(news)} 段")
        for t in news:
            emit("pts", t)

        new, top = wiki_titles(args.days)
        print(f"維基百科：{len(new)} 個新條目、{len(top)} 個熱門條目")
        for t in new:
            emit("wiki-new", t)
        for t in top:
            emit("wiki-top", t)

        tc = threadscount()
        print(f"Threads 熱門話題統計：{len(tc)} 段")
        for t in tc:
            emit("threadscount", t)

        for board in BOARDS:
            links = board_recent(board, args.days, args.pages)
            print(f"PTT {board}：{len(links)} 篇")
            for url in links:
                if url not in seen:
                    seen.add(url)
                    for text in article(url):
                        emit(f"ptt:{board}", text)

        for t in topics[:20]:
            for board in SEARCH_BOARDS:
                for url in ptt_search(board, t):
                    if url not in seen:
                        seen.add(url)
                        for text in article(url):
                            emit(f"ptt-search:{board}", text)

        token = os.environ.get("THREADS_ACCESS_TOKEN")
        if token:
            for t in topics[:20]:
                for text in threads_search(token, t):
                    emit("threads", text)
            print("Threads：已搜尋熱搜關鍵字")
    print(f"共 {n} 段文字 → {args.out}")


if __name__ == "__main__":
    main()
