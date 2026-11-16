"""
用字級語言模型（/home/ubuntu/ime-lm/lm_v2.pt，29.3M 參數、PTT／Dcard／維基 4.75 億字）幫詞與接續詞打分，在 Colab GPU 上跑
（model_def.py、lm_v2.pt、words.tsv、bigram.tsv 傳到 /content；lm_v2.pt 太大要切塊上傳再接回去）。
結果給 tools/lm_word_penalty.py 算附加詞庫的扣分：
  words.tsv（pack, word, score）→ words_lm.tsv：pack, word, score, 中性上下文的 log10 機率（幾個常見上下文取平均機率）, 不在字表的字數
  bigram.tsv（src, prev, next, score）→ bigram_lm.tsv：src, prev, next, score, log10 P(next | prev), next 的中性 log10 機率
"""
import math, torch, torch.nn.functional as F
exec(open("/content/model_def.py").read())
ck = torch.load("/content/lm_v2.pt", map_location="cuda")
itos = ck["itos"]; stoi = {c: i for i, c in enumerate(itos)}
model = LM(len(itos), ck["d"], ck["L"], ck["h"], ck["ctx"]).cuda().eval()
model.load_state_dict(ck["state"])
LOG10 = 1 / math.log(10)
CTXS = ["", "，", "的", "是", "在", "我", "。", "這個", "很", "有"]

def enc(s):
    return [stoi.get(c, 2) for c in s]

@torch.no_grad()
def score(pairs, bs=4096):
    """pairs: (上下文, 詞) → log10 P(詞 | <bos> 上下文)"""
    out = [0.0] * len(pairs)
    order = sorted(range(len(pairs)), key=lambda i: len(pairs[i][0]) + len(pairs[i][1]))
    for s in range(0, len(order), bs):
        idx = order[s:s + bs]
        seqs, starts = [], []
        for i in idx:
            c = [1] + enc(pairs[i][0][-40:])
            seqs.append(c + enc(pairs[i][1])[:20]); starts.append(len(c))
        L = max(map(len, seqs))
        x = torch.zeros(len(seqs), L, dtype=torch.long)
        for k, q in enumerate(seqs): x[k, :len(q)] = torch.tensor(q)
        x = x.cuda()
        with torch.autocast("cuda", dtype=torch.bfloat16):
            lp = F.log_softmax(model(x[:, :-1]).float(), -1)
        tgt = lp.gather(2, x[:, 1:].unsqueeze(-1)).squeeze(-1)
        for k, i in enumerate(idx):
            out[i] = tgt[k, starts[k] - 1:len(seqs[k]) - 1].sum().item() * LOG10
    return out

def neutral(words):
    words = list(words)
    pairs = [(c, w) for w in words for c in CTXS]
    sc = score(pairs)
    res = {}
    for j, w in enumerate(words):
        v = sc[j * len(CTXS):(j + 1) * len(CTXS)]
        m = max(v)
        res[w] = m + math.log10(sum(10 ** (a - m) for a in v) / len(v))
    return res

rows = [l.rstrip("\n").split("\t") for l in open("/content/words.tsv", encoding="utf-8")]
nw = neutral({r[1] for r in rows})
with open("/content/words_lm.tsv", "w", encoding="utf-8") as f:
    for p, w, s in rows:
        f.write(f"{p}\t{w}\t{s}\t{nw[w]:.4f}\t{sum(1 for c in w if c not in stoi)}\n")
print("words done", len(rows), flush=True)

brows = [l.rstrip("\n").split("\t") for l in open("/content/bigram.tsv", encoding="utf-8")]
need = {r[2] for r in brows} - set(nw)
nw.update(neutral(need))
cond = score([(r[1], r[2]) for r in brows])
with open("/content/bigram_lm.tsv", "w", encoding="utf-8") as f:
    for r, c in zip(brows, cond):
        f.write(f"{r[0]}\t{r[1]}\t{r[2]}\t{r[3]}\t{c:.4f}\t{nw[r[2]]:.4f}\n")
print("bigram done", len(brows), flush=True)
