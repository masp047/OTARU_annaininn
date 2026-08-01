#!/usr/bin/env python3
"""公式ガイドブックを読むためのビューア guidebook.html を生成する。

目次から誌面へ飛び、あとはページをめくって読む。紙の本と同じ読み方を
そのままブラウザに持ってくることを狙っている。

  - 目次（部 → 節 → 項）から誌面へジャンプ
  - ← → キー、画面の左右クリック、スワイプでページ送り
  - 開いていたページを憶えていて、次に開くとそこから続けられる
  - 本文の全文検索（OCRしたテキストを使う。誌面へ飛ぶための道しるべ）
  - 広い画面では見開き表示

ページはPDFではなく画像で持つ。PDFのままだとページを送るたびに70MBを
読み直すことになり、めくる操作にならないため（render_guidebook.py 参照）。

入力:
  data/guidebook_pages.json  … ページ本文と誌面ページ番号
  data/guidebook_toc.json    … 誌面の目次（手入力）
  guidebook_pages/p###.webp  … ページ画像

出力: guidebook.html

使い方:
    python3 scripts/build_guidebook.py
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DATA = ROOT / "data"
DEFAULT_IMG = ROOT / "guidebook_pages"
DEFAULT_OUT = ROOT / "guidebook.html"

HIRAGANA = re.compile(r"[ぁ-ゖ]")


def kana_ratio(text: str) -> float:
    """ひらがなの割合。日本語の本文なら3〜5割になる。"""
    t = re.sub(r"\s", "", text)
    return len(HIRAGANA.findall(t)) / len(t) if t else 0.0


def fix_page_numbers(rows: list[dict], read_by_eye: dict[int, int] | None = None) -> dict:
    """拾ったノンブルの誤りを落とし、刷られていないページの番号を補う。

    通しページ番号と誌面のページ番号の差（ずれ）は、番号の無い扉や図版が
    挟まるたびに増える。減ることはない。だから「ずれが減った」ところは
    ノンブルの拾い間違いで、たとえば

        seq 79→p70(ずれ9)  seq 84→p73(ずれ11)  seq 86→p77(ずれ9)

    の真ん中は、誌面を見ると実際はp75だった。ずれが増えも減りもしない
    並びのうち一番長いものを残し、そこから外れた番号は捨てる。

    残した番号を足場に、番号の無いページを埋める。前後の足場のずれが
    同じならその間に扉は無いので数えれば分かる。ずれが違えばその間の
    どこかに扉があり、どのページが扉かは分からないので埋めない。

    read_by_eye は誌面を見て確かめた番号（data/guidebook_nombres.json）。
    写真の上に白抜きで刷られた番号などは機械では拾えないが、扉の位置を
    決めるにはここが要る。拾った番号より優先する。
    """
    for i, r in enumerate(rows):
        if read_by_eye and r["seq"] in read_by_eye:
            r["page"] = read_by_eye[r["seq"]]

    n = len(rows)
    known = [(i, r["page"]) for i, r in enumerate(rows) if r["page"] is not None]

    # ずれが増えるだけの並びで一番長いものを選ぶ
    best = [1] * len(known)
    prev = [-1] * len(known)
    for a in range(len(known)):
        for b in range(a):
            off_a = known[a][0] - known[a][1]
            off_b = known[b][0] - known[b][1]
            if off_b <= off_a and best[b] + 1 > best[a]:
                best[a], prev[a] = best[b] + 1, b
    keep, k = [], best.index(max(best)) if known else -1
    while k >= 0:
        keep.append(known[k])
        k = prev[k]
    keep.reverse()

    dropped = [rows[i]["seq"] for i, _ in known if (i, rows[i]["page"]) not in keep]
    for i, _ in known:
        if (i, rows[i]["page"]) not in keep:
            rows[i]["page"] = None

    anchors = {i: p for i, p in keep}
    guessed = []
    for i, r in enumerate(rows):
        if r["page"] is not None:
            continue
        before = max((j for j in anchors if j < i), default=None)
        after = min((j for j in anchors if j > i), default=None)
        if before is not None and after is not None:
            off_b = before - anchors[before]
            if off_b != after - anchors[after]:
                continue                       # 間に扉がある。どこかは分からない
            page = i - off_b
        elif after is not None:                # 誌面の1ページ目より前
            page = i - (after - anchors[after])
        else:
            continue
        if page > 0:
            r["page"], r["page_guess"] = page, True
            guessed.append(r["seq"])
    return {"dropped": dropped, "guessed": guessed}


def build(data_dir: Path, img_dir: Path) -> dict:
    pages = json.loads((data_dir / "guidebook_pages.json").read_text(encoding="utf-8"))
    toc_doc = json.loads((data_dir / "guidebook_toc.json").read_text(encoding="utf-8"))

    # 目次の節に、その節が終わるページ（次の節の直前）を持たせる
    toc = toc_doc["章"]
    numbered = [s for s in toc if s["page"]]
    for i, s in enumerate(toc):
        nxt = next((x for x in toc[i + 1:] if x["page"]), None)
        s["end"] = (nxt["page"] - 1) if nxt else None

    out = []
    for p in pages:
        text = p.get("text", "")
        # 検索には空白と改行を落とした本文を使う。誌面は段組みで折り返すため、
        # OCRの結果では「鰊御殿」が「鰊御\n殿」のように割れていることがあり、
        # そのまま探すと見つからない。
        flat = re.sub(r"\s+", "", text)
        out.append({
            "seq": p["seq"],
            "page": p["page"],                       # 誌面のノンブル。無いページはnull
            "img": f"guidebook_pages/p{p['seq']:03d}.webp",
            # 図版が主のページやOCRが崩れたページは検索の当てにしない
            "t": "" if kana_ratio(text) < 0.15 else flat,
        })

    nombres = json.loads((data_dir / "guidebook_nombres.json").read_text(encoding="utf-8"))
    fixed = fix_page_numbers(out, {r["seq"]: r["page"] for r in nombres["番号"]})

    missing = [r["seq"] for r in out
               if not (img_dir / f"p{r['seq']:03d}.webp").exists()]
    return {"pages": out, "toc": toc, "toc_doc": toc_doc, "missing": missing,
            "fixed": fixed,
            "first_numbered": numbered[0]["page"] if numbered else None}


CSS = """
:root { color-scheme: light dark; --bg:#f6f5f2; --fg:#1d1d1a; --panel:#fff;
  --line:#e2e1da; --muted:#6d6d64; --accent:#8a6d3b; --chip:#f1ece0; --hi:#ffe9a8; }
@media (prefers-color-scheme: dark) {
  :root { --bg:#131316; --fg:#e9e9e4; --panel:#1c1c20; --line:#31313a;
    --muted:#98988f; --accent:#d8c79a; --chip:#33301f; --hi:#5b4d1f; }
}
* { box-sizing:border-box; -webkit-tap-highlight-color:transparent; }
html,body { height:100%; }
body { margin:0; background:var(--bg); color:var(--fg); overflow:hidden;
  font:15px/1.7 -apple-system,BlinkMacSystemFont,"Hiragino Sans","Noto Sans JP",sans-serif; }
button { font:inherit; cursor:pointer; border:1px solid var(--line);
  background:var(--panel); color:var(--fg); border-radius:.45rem; padding:.3rem .7rem; }
button:hover { border-color:var(--accent); }
button:disabled { opacity:.35; cursor:default; }
button.on { background:var(--accent); border-color:var(--accent); color:var(--panel); }

/* 上のバー */
#top { height:3.1rem; display:flex; align-items:center; gap:.5rem; padding:0 .8rem;
  background:var(--panel); border-bottom:1px solid var(--line); position:relative; z-index:30; }
#top .title { font-weight:600; font-size:.92rem; margin-right:auto;
  white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
#top .title small { color:var(--muted); font-weight:400; font-size:.78rem; }
#where { font-size:.82rem; color:var(--muted); font-variant-numeric:tabular-nums;
  white-space:nowrap; }
#jump { width:4.4rem; font:inherit; font-size:.85rem; padding:.25rem .4rem;
  border:1px solid var(--line); border-radius:.4rem; background:var(--bg); color:var(--fg);
  text-align:center; }

/* 読む場所 */
#reader { position:absolute; inset:3.1rem 0 0 0; }
#stage { position:absolute; inset:0; overflow:hidden; display:flex;
  align-items:center; justify-content:center; gap:.6rem; padding:.8rem .8rem 3.2rem; }
#stage img { max-width:100%; max-height:100%; object-fit:contain; display:block;
  border-radius:3px; box-shadow:0 2px 14px rgba(0,0,0,.14); background:#fff; }
#stage.two img { max-width:calc(50% - .3rem); }
/* 左右をクリック（タップ）でめくる */
.tap { position:absolute; top:0; bottom:3rem; width:22%; border:0; background:transparent;
  padding:0; border-radius:0; z-index:5; }
.tap:hover { background:linear-gradient(var(--dir), rgba(128,128,128,.10), transparent); }
.tap.prev { left:0; --dir:to right; }
.tap.next { right:0; --dir:to left; }
.tap span { position:absolute; top:50%; transform:translateY(-50%);
  font-size:1.7rem; color:var(--muted); opacity:0; transition:opacity .15s; }
.tap:hover span { opacity:.75; }
.tap.prev span { left:.7rem; } .tap.next span { right:.7rem; }

/* 下のバー */
#bottom { position:absolute; left:0; right:0; bottom:0; height:2.8rem;
  display:flex; align-items:center; gap:.6rem; padding:0 .8rem;
  background:color-mix(in srgb,var(--panel) 92%,transparent);
  border-top:1px solid var(--line); backdrop-filter:blur(6px); z-index:10; }
#slider { flex:1; accent-color:var(--accent); }

/* 目次・検索の引き出し */
#panel { width:21rem; max-width:84vw; background:var(--panel);
  border-right:1px solid var(--line); overflow-y:auto; padding:.8rem;
  position:absolute; inset:0 auto 0 0; transform:translateX(-101%);
  transition:transform .18s ease; z-index:25; }
#panel.open { transform:none; box-shadow:0 0 26px rgba(0,0,0,.16); }
#scrim { position:absolute; inset:0; background:rgba(0,0,0,.28); z-index:24;
  opacity:0; pointer-events:none; transition:opacity .18s; }
#scrim.on { opacity:1; pointer-events:auto; }
#panel .tabs { display:flex; gap:.3rem; margin-bottom:.7rem; }
.part { margin:1rem 0 .35rem; font-size:.72rem; font-weight:700; color:var(--accent);
  letter-spacing:.09em; }
.part:first-of-type { margin-top:0; }
.sec { display:flex; gap:.55rem; align-items:baseline; width:100%; text-align:left;
  border:0; background:transparent; padding:.42rem .5rem; border-radius:.4rem; }
.sec:hover { background:var(--chip); }
.sec.here { background:var(--chip); box-shadow:inset 2px 0 0 var(--accent); }
.sec .pg { color:var(--muted); font-size:.76rem; flex:0 0 3.1rem;
  font-variant-numeric:tabular-nums; }
.sec b { font-weight:600; }
.sec .kou { display:block; font-size:.74rem; color:var(--muted); line-height:1.55; }
#q { width:100%; font:inherit; font-size:.9rem; padding:.45rem .6rem; margin-bottom:.6rem;
  border:1px solid var(--line); border-radius:.4rem; background:var(--bg); color:var(--fg); }
.hit { display:block; width:100%; text-align:left; border:0; background:transparent;
  padding:.45rem .5rem; border-radius:.4rem; font-size:.82rem; line-height:1.6; }
.hit:hover { background:var(--chip); }
.hit .pg { color:var(--accent); font-weight:700; font-size:.76rem; }
.hit mark { background:var(--hi); color:inherit; }
.hit .near { font-size:.7rem; color:var(--muted); border:1px solid var(--line);
  border-radius:.25rem; padding:0 .25rem; }
.msg { color:var(--muted); font-size:.83rem; padding:.6rem .2rem; }
@media (max-width:44rem) { #top .title small { display:none; } #jump { display:none; } }
@media (max-width:30rem) { #top .title { font-size:.82rem; } }
"""

JS = r"""
const $ = s => document.querySelector(s);
const PAGES = DATA.pages;
const LAST = 'otaru-gb-last';

let i = 0;                 // いま開いている通しページの添字（0始まり）
let two = false;           // 見開きかどうか
let tab = 'toc';

const esc = s => (s || '').replace(/[&<>"]/g, c =>
  ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
const label = p => p.page ? `p${p.page}` : `${p.seq}枚目`;

/* ---------- 表示 ---------- */
function show() {
  i = Math.max(0, Math.min(PAGES.length - 1, i));
  const stage = $('#stage');
  stage.classList.toggle('two', two);
  const list = two ? [PAGES[i], PAGES[i + 1]].filter(Boolean) : [PAGES[i]];
  stage.querySelectorAll('img').forEach(e => e.remove());
  const anchor = $('#tapNext');
  list.forEach(p => {
    const img = document.createElement('img');
    img.src = p.img; img.alt = `${label(p)} の誌面`;
    stage.insertBefore(img, anchor);
  });
  $('#where').textContent = list.map(label).join('・');
  $('#slider').value = i;
  $('#jump').value = PAGES[i].page || '';
  $('#prev').disabled = i <= 0;
  $('#next').disabled = i >= PAGES.length - 1;
  localStorage.setItem(LAST, String(i));
  markToc();
  prefetch();
}

/* 次に見るページを先に読み込んでおく。めくった瞬間に出るように。 */
function prefetch() {
  [i + 1, i + 2, i + 3, i - 1, i - 2].forEach(k => {
    if (k >= 0 && k < PAGES.length) { const im = new Image(); im.src = PAGES[k].img; }
  });
}

function go(delta) { i += delta * (two ? 2 : 1); show(); }
function goSeq(seq) { i = PAGES.findIndex(p => p.seq === seq); show(); closePanel(); }
function goPage(page) { const k = indexOfPage(page); if (k >= 0) { i = k; show(); closePanel(); } }

/* ---------- 目次 ---------- */
function renderToc() {
  let out = '', part = null;
  DATA.toc.forEach((s, k) => {
    if (s.部 !== part) { part = s.部; out += `<div class="part">${esc(part)}</div>`; }
    const range = s.page ? (s.end ? `${s.page}–${s.end}` : `${s.page}–`) : '—';
    out += `<button class="sec" data-page="${s.page ?? ''}" data-k="${k}">
      <span class="pg">${esc(range)}</span>
      <span><b>${esc(s.節)}</b>
        ${s.項.length ? `<span class="kou">${esc(s.項.join('・'))}</span>` : ''}</span>
    </button>`;
  });
  return out;
}

/* いま読んでいる節に印をつける */
function markToc() {
  const page = PAGES[i].page;
  let best = -1;
  if (page != null) DATA.toc.forEach((s, k) => {
    if (s.page != null && s.page <= page && (s.end == null || page <= s.end)) best = k;
  });
  document.querySelectorAll('.sec').forEach(b =>
    b.classList.toggle('here', Number(b.dataset.k) === best));
}

/* ---------- 検索 ---------- */
function search(q) {
  q = (q || '').trim();
  if (!q) return `<p class="msg">語を入れると、その語が出てくる誌面を探します。<br>
    目次の見出しからも探します。</p>`;
  const flat = q.replace(/\s+/g, '');

  /* まず目次から。見出しは手で起こしてあるので、OCRの読み違いの影響を受けない。 */
  const tocHits = [];
  DATA.toc.forEach(s => {
    const hay = s.節 + ' ' + s.項.join(' ');
    if (s.page != null && hay.includes(flat)) tocHits.push(s);
  });

  /* 本文はOCRなので読み違いがある（「鰊」を「鯨」と読むなど）。
     完全一致で拾えなかったときのために、1文字だけ違う箇所も探す。 */
  const exact = [], near = [];
  for (const p of PAGES) {
    if (!p.t) continue;                  // 読み取れていないページは当てにしない
    const at = p.t.indexOf(flat);
    if (at >= 0) { exact.push({p, at, len: flat.length, near: false}); continue; }
    if (flat.length >= 3 && exact.length + near.length < 40) {
      const at2 = findNear(p.t, flat);
      if (at2 >= 0) near.push({p, at: at2, len: flat.length, near: true});
    }
  }
  const body = exact.concat(near).slice(0, 60);

  if (!tocHits.length && !body.length) return `<p class="msg">
    「${esc(q)}」は見つかりませんでした。<br>
    本文の検索は誌面を機械で読み取った文字を使っているため、
    読み違いや、図版が主のページで見つからないことがあります。</p>`;

  let out = '';
  if (tocHits.length) {
    out += `<div class="part">目次から</div>` + tocHits.map(s =>
      `<button class="hit" data-page="${s.page}">
        <span class="pg">p${s.page}</span> ${esc(s.部)} ／ <b>${esc(s.節)}</b></button>`).join('');
  }
  if (body.length) {
    out += `<div class="part">本文から ${body.length}件</div>` + body.map(h => {
      const from = Math.max(0, h.at - 22);
      const snip = h.p.t.slice(from, h.at + h.len + 38);
      const hit = h.p.t.slice(h.at, h.at + h.len);
      return `<button class="hit" data-seq="${h.p.seq}">
        <span class="pg">${esc(label(h.p))}</span>
        ${h.near ? '<span class="near">1文字違い</span> ' : ''}
        ${esc(snip).split(esc(hit)).join(`<mark>${esc(hit)}</mark>`)}</button>`;
    }).join('');
  }
  return out;
}

/* 1文字だけ違う箇所を探す。OCRの読み違いを拾うため。 */
function findNear(hay, needle) {
  const n = needle.length;
  for (let i = 0; i + n <= hay.length; i++) {
    let bad = 0;
    for (let k = 0; k < n; k++) {
      if (hay[i + k] !== needle[k] && ++bad > 1) break;
    }
    if (bad <= 1) return i;
  }
  return -1;
}

function setTab(t) {
  tab = t;
  document.querySelectorAll('#panel .tabs button').forEach(b =>
    b.classList.toggle('on', b.dataset.t === t));
  $('#qwrap').style.display = t === 'find' ? '' : 'none';
  $('#list').innerHTML = t === 'toc' ? renderToc() : search($('#q').value);
  if (t === 'toc') markToc();
  if (t === 'find') $('#q').focus();
  bindList();
}

function bindList() {
  document.querySelectorAll('.sec').forEach(b => b.onclick = () => {
    if (b.dataset.page) goPage(Number(b.dataset.page));
  });
  document.querySelectorAll('.hit').forEach(b => b.onclick = () => {
    if (b.dataset.seq) goSeq(Number(b.dataset.seq));
    else if (b.dataset.page) goPage(Number(b.dataset.page));
  });
}

/* ---------- 引き出し ---------- */
function openPanel(t) {
  $('#panel').classList.add('open'); $('#scrim').classList.add('on'); setTab(t);
}
function closePanel() {
  $('#panel').classList.remove('open'); $('#scrim').classList.remove('on');
}

/* ---------- 操作 ---------- */
$('#prev').onclick = () => go(-1);
$('#next').onclick = () => go(1);
$('#tapPrev').onclick = () => go(-1);
$('#tapNext').onclick = () => go(1);
$('#toc').onclick = () =>
  $('#panel').classList.contains('open') && tab === 'toc' ? closePanel() : openPanel('toc');
$('#find').onclick = () =>
  $('#panel').classList.contains('open') && tab === 'find' ? closePanel() : openPanel('find');
$('#scrim').onclick = closePanel;
$('#spread').onclick = () => { two = !two; $('#spread').classList.toggle('on', two); show(); };
$('#slider').oninput = e => { i = Number(e.target.value); show(); };
$('#jump').onchange = e => {
  const n = Number(e.target.value);
  if (indexOfPage(n) >= 0) goPage(n); else show();   // 無い番号なら今の表示に戻す
};
$('#q').oninput = () => { $('#list').innerHTML = search($('#q').value); bindList(); };
document.querySelectorAll('#panel .tabs button').forEach(b =>
  b.onclick = () => setTab(b.dataset.t));

document.addEventListener('keydown', e => {
  if (e.target.tagName === 'INPUT') { if (e.key === 'Escape') e.target.blur(); return; }
  if (e.key === 'ArrowLeft')  { go(-1); e.preventDefault(); }
  if (e.key === 'ArrowRight') { go(1);  e.preventDefault(); }
  if (e.key === 'Home') { i = 0; show(); }
  if (e.key === 'End')  { i = PAGES.length - 1; show(); }
  if (e.key === 'Escape') closePanel();
  if (e.key === 't') openPanel('toc');
  if (e.key === '/') { openPanel('find'); e.preventDefault(); }
});

/* スワイプ */
let x0 = null;
$('#stage').addEventListener('touchstart', e => { x0 = e.touches[0].clientX; }, {passive:true});
$('#stage').addEventListener('touchend', e => {
  if (x0 == null) return;
  const dx = e.changedTouches[0].clientX - x0;
  if (Math.abs(dx) > 45) go(dx < 0 ? 1 : -1);
  x0 = null;
}, {passive:true});

/* 広い画面では見開きを既定にする */
if (window.matchMedia('(min-width:64rem)').matches) { two = true; $('#spread').classList.add('on'); }

/* 誌面のこのページが何枚目かを返す。番号が拾えていないページは、
   番号のある一番近い後ろのページから枚数を戻して割り出す。
   （誌面のp1はノンブルが入っていないので、これが無いとp2から始まってしまう） */
function indexOfPage(n) {
  const hit = PAGES.findIndex(p => p.page === n);
  if (hit >= 0) return hit;
  const after = PAGES.findIndex(p => p.page != null && p.page > n);
  if (after < 0) return -1;
  const back = after - (PAGES[after].page - n);
  return back >= 0 ? back : -1;
}

/* 前に読んでいたページから続ける。無ければ本文の1ページ目から。 */
const savedRaw = localStorage.getItem(LAST);
const saved = savedRaw === null ? NaN : Number(savedRaw);
i = Number.isInteger(saved) && saved >= 0 && saved < PAGES.length
  ? saved
  : Math.max(0, indexOfPage(1));   // 既定は本文の1ページ目
$('#slider').max = PAGES.length - 1;
$('#list').innerHTML = renderToc();
bindList();
show();
"""


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, default=DEFAULT_DATA)
    parser.add_argument("--img-dir", type=Path, default=DEFAULT_IMG)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args()

    d = build(args.data_dir, args.img_dir)
    payload = {"pages": d["pages"], "toc": d["toc"],
               "first_numbered": d["first_numbered"]}

    html = f"""<!doctype html>
<html lang="ja"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<title>おたる案内人 公式ガイドブック</title>
<style>{CSS}</style></head><body>

<div id="top">
  <button id="toc" title="目次（t）">目次</button>
  <button id="find" title="本文を探す（/）">探す</button>
  <div class="title">おたる案内人 公式ガイドブック
    <small>{d['toc_doc']['書名']}</small></div>
  <input id="jump" type="number" min="1" title="誌面のページ番号へ飛ぶ" placeholder="ページ">
  <span id="where"></span>
  <button id="spread" title="見開きにする">見開き</button>
</div>

<div id="reader">
  <div id="stage">
    <button class="tap prev" id="tapPrev" aria-label="前のページ"><span>‹</span></button>
    <button class="tap next" id="tapNext" aria-label="次のページ"><span>›</span></button>
    <div id="bottom">
      <button id="prev">← 前</button>
      <input id="slider" type="range" min="0" value="0" aria-label="ページ位置">
      <button id="next">次 →</button>
    </div>
  </div>
  <div id="scrim"></div>
  <div id="panel">
    <div class="tabs">
      <button data-t="toc" class="on">目次</button>
      <button data-t="find">探す</button>
    </div>
    <div id="qwrap" style="display:none">
      <input id="q" placeholder="本文を探す（例：北前船）"></div>
    <div id="list"></div>
  </div>
</div>

<script>const DATA = {json.dumps(payload, ensure_ascii=False)};</script>
<script>{JS}</script>
</body></html>
"""
    args.out.write_text(html, encoding="utf-8")

    print(f"書き出し: {args.out} ({args.out.stat().st_size // 1024:,} KB)")
    print(f"  {len(d['pages'])}ページ / 目次 {len(d['toc'])}節")
    poor = sum(1 for p in d["pages"] if not p["t"])
    print(f"  検索の対象にしないページ（図版が主・OCRが崩れている）: {poor}")
    fx = d["fixed"]
    if fx["dropped"]:
        print(f"  ノンブルの拾い間違いとして捨てた: {fx['dropped']}枚目")
    print(f"  番号が刷られていないページのうち補えた: {len(fx['guessed'])}ページ / "
          f"補えず: {sum(1 for p in d['pages'] if p['page'] is None)}ページ")
    if d["missing"]:
        print(f"  画像がまだ無いページ: {len(d['missing'])}枚 "
              f"（python3 scripts/render_guidebook.py で作る）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
