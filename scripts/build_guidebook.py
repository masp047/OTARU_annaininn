#!/usr/bin/env python3
"""公式ガイドブックの索引サイト guidebook.html を生成する。

4つの切り口で索引をつくり、選ぶと詳細（該当ページの本文と、
そのページに対応する過去問）を表示する。

  1. 目次        … 誌面の目次そのまま（部 → 節 → 項）
  2. 分野        … 検定の出題分野に沿ってこちらで分類したもの
  3. 町名        … 誌面p177の58町名が、どのページで語られているか
  4. 年代        … 元号年の記述を拾い、時代ごとにページを並べたもの

入力:
  data/guidebook_pages.json  … extract_guidebook.py の出力
  data/guidebook_toc.json    … 誌面の目次（手入力）
  data/guidebook_tags.json   … 町名と分野の定義（手入力）
  data/exam_*.json           … 過去問（分野ごとの出題数と紐付けに使う）

出力: guidebook.html

使い方:
    python3 scripts/build_guidebook.py
"""

from __future__ import annotations

import argparse
import json
import re
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DATA = ROOT / "data"
DEFAULT_OUT = ROOT / "guidebook.html"

# 「明治32(1899)年」「大正11年」「昭和61（1986）年」などを拾う
ERA = re.compile(r"(慶応|明治|大正|昭和|平成|令和)\s*([0-9０-９元]{1,2})")
ERA_START = {"慶応": 1864, "明治": 1867, "大正": 1911, "昭和": 1925,
             "平成": 1988, "令和": 2018}
ZEN = str.maketrans("０１２３４５６７８９", "0123456789")

# 年代の区切り。検定で問われる時代の切れ目に合わせた。
PERIODS = [
    ("江戸・幕末", 0, 1867, "場所請負制の時代から開拓使設置まで"),
    ("明治前期", 1868, 1889, "開拓使・幌内鉄道・鰊漁の隆盛"),
    ("明治後期", 1890, 1912, "築港・銀行街・小樽区の成立"),
    ("大正", 1912, 1926, "運河の完成・市制施行・商都の絶頂"),
    ("昭和戦前", 1926, 1945, "鰊の衰退・統制経済"),
    ("昭和戦後", 1946, 1988, "斜陽化と運河保存運動"),
    ("平成以降", 1989, 2100, "観光都市としての小樽"),
]


def to_year(era: str, num: str) -> int | None:
    """元号と年から西暦を出す。「元」は1年として扱う。"""
    num = num.translate(ZEN)
    n = 1 if num == "元" else (int(num) if num.isdigit() else None)
    if n is None or era not in ERA_START:
        return None
    return ERA_START[era] + n


def period_of(year: int) -> str | None:
    for name, lo, hi, _ in PERIODS:
        if lo <= year <= hi:
            return name
    return None


def section_of_page(toc: list[dict], page: int | None) -> dict | None:
    """誌面ページ番号から、それが属する節を返す。"""
    if page is None:
        return None
    best = None
    for s in toc:
        if s["page"] is not None and s["page"] <= page:
            if best is None or s["page"] > best["page"]:
                best = s
    return best


def build_index(data_dir: Path) -> dict:
    pages = json.loads((data_dir / "guidebook_pages.json").read_text(encoding="utf-8"))
    toc_doc = json.loads((data_dir / "guidebook_toc.json").read_text(encoding="utf-8"))
    tags = json.loads((data_dir / "guidebook_tags.json").read_text(encoding="utf-8"))
    toc = toc_doc["章"]

    # --- ページに節を割り当てる ---
    for p in pages:
        s = section_of_page(toc, p["page"])
        p["節"] = s["節"] if s else None
        p["部"] = s["部"] if s else None

    # --- 分野（自前の分類）---
    by_section = {c: cat["名"] for cat in tags["カテゴリ"] for c in cat["章"]}
    cat_pages: dict[str, set[int]] = defaultdict(set)
    for p in pages:
        if not p["page"]:
            continue
        # まず節から。目次に載っている節はそのまま分野に対応させる
        name = by_section.get(p["節"] or "")
        if name:
            cat_pages[name].add(p["page"])
        # 加えて、他の分野の語が濃く出るページも拾う（章をまたぐ話題のため）
        for cat in tags["カテゴリ"]:
            if cat["名"] == name:
                continue
            hits = sum(1 for w in cat["語"] if w in p["text"])
            if hits >= 3:
                cat_pages[cat["名"]].add(p["page"])

    # --- 町名 ---
    # 「幸」「桜」のような単漢字の町名は、そのまま探すと「枝幸」「幸三」などに
    # 当たってしまう。検索語が指定されている町名は、その語だけで探す。
    terms = tags.get("町名の検索語", {})
    town_words = {t: terms.get(t, [t]) for t in tags["町名"]}
    town_pages: dict[str, set[int]] = defaultdict(set)
    for p in pages:
        if not p["page"]:
            continue
        for town, words in town_words.items():
            if any(w in p["text"] for w in words):
                town_pages[town].add(p["page"])

    # --- 年代 ---
    period_pages: dict[str, set[int]] = defaultdict(set)
    page_years: dict[int, list[int]] = defaultdict(list)
    for p in pages:
        if not p["page"]:
            continue
        for era, num in ERA.findall(p["text"]):
            y = to_year(era, num)
            if y is None:
                continue
            page_years[p["page"]].append(y)
            per = period_of(y)
            if per:
                period_pages[per].add(p["page"])

    # --- 過去問を分野に紐付ける ---
    exam_by_cat: dict[str, list[dict]] = defaultdict(list)
    for path in sorted(data_dir.glob("exam_*.json"),
                       key=lambda p: int(p.stem.split("_")[1])):
        exam = json.loads(path.read_text(encoding="utf-8"))
        n = exam["回数"]
        for it in exam["設問"]:
            blob = it["q"] + " " + " ".join(it.get("c", []))
            best, best_hits = None, 0
            for cat in tags["カテゴリ"]:
                hits = sum(1 for w in cat["語"] if w in blob)
                if hits > best_hits:
                    best, best_hits = cat["名"], hits
            if best:
                exam_by_cat[best].append({
                    "exam": n, "no": it["no"], "sub": it.get("sub", ""),
                    "q": it["q"], "a": it["a"],
                })

    return {"pages": pages, "toc": toc, "toc_doc": toc_doc, "tags": tags,
            "cat_pages": {k: sorted(v) for k, v in cat_pages.items()},
            "town_pages": {k: sorted(v) for k, v in town_pages.items()},
            "town_words": town_words,
            "period_pages": {k: sorted(v) for k, v in period_pages.items()},
            "page_years": {str(k): sorted(set(v)) for k, v in page_years.items()},
            "exam_by_cat": dict(exam_by_cat)}


CSS = """
:root { color-scheme: light dark; --bg:#fbfbfa; --fg:#1a1a18; --card:#fff;
  --line:#e3e3dd; --muted:#6b6b63; --accent:#8a6d3b; --chip:#f2ede0;
  --hi:#fff6d8; }
@media (prefers-color-scheme: dark) {
  :root { --bg:#16161a; --fg:#e8e8e3; --card:#1e1e23; --line:#32323a;
    --muted:#9a9a92; --accent:#d8c79a; --chip:#33301f; --hi:#3a3320; }
}
* { box-sizing:border-box; }
body { margin:0; background:var(--bg); color:var(--fg);
  font:16px/1.75 -apple-system,BlinkMacSystemFont,"Hiragino Sans","Noto Sans JP",sans-serif; }
header { padding:1.4rem 1rem .9rem; border-bottom:1px solid var(--line);
  background:var(--card); position:sticky; top:0; z-index:5; }
.wrap { max-width:56rem; margin:0 auto; padding:0 1rem; }
h1 { margin:0; font-size:1.15rem; letter-spacing:.02em; }
h1 small { display:block; font-size:.78rem; font-weight:400; color:var(--muted);
  margin-top:.25rem; letter-spacing:0; }
nav { display:flex; gap:.4rem; flex-wrap:wrap; margin-top:.9rem; }
button { font:inherit; cursor:pointer; border:1px solid var(--line);
  background:var(--card); color:var(--fg); border-radius:.5rem;
  padding:.4rem .85rem; }
button:hover { border-color:var(--accent); }
nav button.on { background:var(--accent); border-color:var(--accent); color:var(--bg);
  font-weight:600; }
main { padding:1.4rem 0 4rem; }
.hint { color:var(--muted); font-size:.85rem; margin:0 0 1rem; }
.grid { display:grid; gap:.6rem; grid-template-columns:repeat(auto-fill,minmax(13rem,1fr)); }
.item { text-align:left; padding:.7rem .9rem; border-radius:.6rem;
  display:flex; flex-direction:column; gap:.15rem; width:100%; }
.item b { font-weight:600; }
.item span { font-size:.78rem; color:var(--muted); }
.part { margin:1.6rem 0 .6rem; font-size:.8rem; font-weight:700; color:var(--accent);
  letter-spacing:.08em; }
.part:first-child { margin-top:0; }
.rowlist { display:flex; flex-direction:column; gap:.35rem; }
.row { display:flex; align-items:baseline; gap:.6rem; padding:.55rem .9rem;
  border-radius:.5rem; text-align:left; width:100%; }
.row .pg { font-variant-numeric:tabular-nums; color:var(--muted); font-size:.8rem;
  flex:0 0 3.4rem; }
.row .sub { font-size:.78rem; color:var(--muted); }
.bar { height:.35rem; border-radius:.2rem; background:var(--accent); opacity:.55;
  margin-top:.35rem; }
.back { margin-bottom:1rem; }
.detail h2 { font-size:1.05rem; margin:.2rem 0 .1rem; }
.meta { color:var(--muted); font-size:.83rem; margin-bottom:1.1rem; }
.page { background:var(--card); border:1px solid var(--line); border-radius:.7rem;
  padding:.9rem 1.1rem; margin-bottom:.8rem; }
.page h3 { margin:0 0 .5rem; font-size:.85rem; color:var(--accent);
  display:flex; align-items:center; gap:.7rem; flex-wrap:wrap; }
.page h3 a { color:var(--accent); font-size:.8rem; }
.page pre { margin:0; white-space:pre-wrap; word-break:break-word;
  font:inherit; font-size:.9rem; line-height:1.85; }
mark { background:var(--hi); color:inherit; padding:0 .1em; border-radius:.15em; }
.exam { background:var(--card); border:1px solid var(--line); border-radius:.7rem;
  padding:.75rem 1rem; margin-bottom:.5rem; font-size:.9rem; }
.exam .k { font-size:.75rem; color:var(--muted); display:block; }
.exam .ans { color:var(--accent); font-weight:600; }
.note { font-size:.82rem; color:var(--muted); border-left:3px solid var(--line);
  padding-left:.8rem; margin:1.2rem 0; }
.empty { color:var(--muted); padding:2rem 0; }
@media (max-width:32rem) { .grid { grid-template-columns:1fr; } }
"""

JS = r"""
const $ = s => document.querySelector(s);
const esc = s => (s||'').replace(/[&<>"]/g, c => (
  {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
const byPage = {};
DATA.pages.forEach(p => { if (p.page) (byPage[p.page] = byPage[p.page] || []).push(p); });

/* 誌面ページ番号 → PDFのどのファイルの何ページか。
   ガイドブックは2分割してあるので、開くファイルも切り替える。 */
function pdfLink(page) {
  const p = (byPage[page] || [])[0];
  if (!p) return null;
  return `guidebook/guidebook_${String(p.file).padStart(2,'0')}.pdf#page=${p.pdf_page}`;
}
function pageText(page) {
  return (byPage[page] || []).map(p => p.text).join('\n');
}

let view = 'toc';
function setView(v) {
  view = v;
  document.querySelectorAll('nav button').forEach(b =>
    b.classList.toggle('on', b.dataset.v === v));
  render();
}

function render() {
  const m = $('#main');
  if (view === 'toc') m.innerHTML = renderToc();
  else if (view === 'cat') m.innerHTML = renderCat();
  else if (view === 'town') m.innerHTML = renderTown();
  else if (view === 'era') m.innerHTML = renderEra();
  bind();
  window.scrollTo(0, 0);
}

/* ---------- 索引1: 目次 ---------- */
function renderToc() {
  let out = `<p class="hint">誌面の目次です。節を選ぶと、その範囲の本文と関連する過去問を表示します。</p>`;
  let part = null;
  DATA.toc.forEach((s, i) => {
    if (s.部 !== part) { part = s.部; out += `<div class="part">${esc(part)}</div><div class="rowlist">`; }
    const next = DATA.toc.slice(i+1).find(x => x.page);
    const range = s.page ? (next ? `p${s.page}〜${next.page-1}` : `p${s.page}〜`) : '—';
    out += `<button class="row" data-open="sec:${i}">
      <span class="pg">${s.page ? 'p'+s.page : '—'}</span>
      <span><b>${esc(s.節)}</b>${s.項.length ? `<span class="sub"> ／ ${esc(s.項.join('・'))}</span>` : ''}</span>
    </button>`;
    const after = DATA.toc[i+1];
    if (!after || after.部 !== part) out += `</div>`;
  });
  return out;
}

/* ---------- 索引2: 分野 ---------- */
function renderCat() {
  const cats = DATA.tags.カテゴリ.slice().sort((a,b) =>
    (DATA.exam_by_cat[b.名]||[]).length - (DATA.exam_by_cat[a.名]||[]).length);
  const max = Math.max(...cats.map(c => (DATA.exam_by_cat[c.名]||[]).length), 1);
  let out = `<p class="hint">検定の出題分野に沿って分けたものです。過去問での出題数が多い順に並べています。</p><div class="grid">`;
  cats.forEach(c => {
    const pages = DATA.cat_pages[c.名] || [];
    const qs = (DATA.exam_by_cat[c.名] || []).length;
    out += `<button class="item" data-open="cat:${encodeURIComponent(c.名)}">
      <b>${esc(c.名)}</b>
      <span>${esc(c.説明)}</span>
      <span>本文 ${pages.length}ページ ／ 過去問 ${qs}問</span>
      <span class="bar" style="width:${Math.max(6, qs/max*100)}%"></span>
    </button>`;
  });
  return out + `</div>`;
}

/* ---------- 索引3: 町名 ---------- */
function renderTown() {
  const towns = DATA.tags.町名.filter(t => (DATA.town_pages[t]||[]).length);
  const none = DATA.tags.町名.filter(t => !(DATA.town_pages[t]||[]).length);
  let out = `<p class="hint">誌面p177の58町名が、ガイドブックのどこで語られているかを引けます。掲載ページの多い順です。</p><div class="grid">`;
  towns.sort((a,b) => DATA.town_pages[b].length - DATA.town_pages[a].length);
  towns.forEach(t => {
    const pages = DATA.town_pages[t];
    out += `<button class="item" data-open="town:${encodeURIComponent(t)}">
      <b>${esc(t)}</b><span>${pages.length}ページ（p${pages[0]}〜）</span>
    </button>`;
  });
  out += `</div>`;
  if (none.length) out += `<p class="note">本文中に記述が見つからなかった町名：${esc(none.join('、'))}</p>`;
  return out;
}

/* ---------- 索引4: 年代 ---------- */
function renderEra() {
  let out = `<p class="hint">本文の元号年の記述を拾い、時代ごとにページを並べています。同じページが複数の時代に出ることがあります。</p><div class="rowlist">`;
  DATA.periods.forEach(p => {
    const pages = DATA.period_pages[p.名] || [];
    out += `<button class="row" data-open="era:${encodeURIComponent(p.名)}">
      <span class="pg">${pages.length}p</span>
      <span><b>${esc(p.名)}</b><span class="sub"> ／ ${esc(p.説明)}</span></span>
    </button>`;
  });
  return out + `</div>`;
}

/* ---------- 詳細 ---------- */
function open_(key) {
  const [kind, rest] = [key.slice(0, key.indexOf(':')), key.slice(key.indexOf(':')+1)];
  if (kind === 'sec') return detailSection(Number(rest));
  if (kind === 'cat') return detailCat(decodeURIComponent(rest));
  if (kind === 'town') return detailTown(decodeURIComponent(rest));
  if (kind === 'era') return detailEra(decodeURIComponent(rest));
}

function shell(title, meta, body) {
  $('#main').innerHTML = `<div class="detail">
    <button class="back" id="back">← 索引にもどる</button>
    <h2>${esc(title)}</h2><div class="meta">${meta}</div>${body}</div>`;
  $('#back').onclick = render;
  window.scrollTo(0, 0);
}

function pageBlocks(pages, words) {
  if (!pages.length) return `<p class="empty">該当するページがありません。</p>`;
  return pages.map(pg => {
    let t = esc(pageText(pg));
    (words || []).forEach(w => {
      if (!w) return;
      t = t.split(esc(w)).join(`<mark>${esc(w)}</mark>`);
    });
    const link = pdfLink(pg);
    return `<div class="page"><h3>誌面 p${pg}
      ${link ? `<a href="${link}" target="_blank" rel="noopener">PDFのこのページを開く →</a>` : ''}</h3>
      <pre>${t}</pre></div>`;
  }).join('');
}

function examBlocks(list, limit) {
  if (!list || !list.length) return '';
  /* 先頭から取ると第1回ばかりになるので、全回から等間隔で拾う。 */
  const n = Math.min(limit || 20, list.length);
  const step = list.length / n;
  const shown = Array.from({length: n}, (_, i) => list[Math.floor(i * step)]);
  let out = `<div class="part">この分野の過去問（${list.length}問中 ${n}問を全回から抜粋）</div>`;
  out += shown.map(q => `<div class="exam">
    <span class="k">第${q.exam}回 問${q.no}${esc(q.sub||'')}</span>
    ${esc(q.q)}<br><span class="ans">正解: ${esc(q.a)}</span></div>`).join('');
  return out;
}

function detailSection(i) {
  const s = DATA.toc[i];
  const next = DATA.toc.slice(i+1).find(x => x.page);
  const from = s.page, to = next ? next.page - 1 : 999;
  const pages = Object.keys(byPage).map(Number)
    .filter(p => from !== null && p >= from && p <= to).sort((a,b)=>a-b);
  const meta = `${esc(s.部)} ／ ${s.page ? `誌面 p${s.page}〜${pages.length ? pages[pages.length-1] : s.page}` : 'ページ番号なし'}
    ${s.項.length ? `<br>${esc(s.項.join(' ・ '))}` : ''}`;
  shell(s.節, meta, pageBlocks(pages, s.項));
}

function detailCat(name) {
  const cat = DATA.tags.カテゴリ.find(c => c.名 === name);
  const pages = DATA.cat_pages[name] || [];
  const qs = DATA.exam_by_cat[name] || [];
  const meta = `${esc(cat.説明)}<br>該当する章：${esc(cat.章.join('・'))}
    ／ 本文 ${pages.length}ページ ／ 過去問 ${qs.length}問`;
  shell(name, meta, examBlocks(qs) + `<div class="part">ガイドブック本文</div>`
    + pageBlocks(pages, cat.語));
}

function detailTown(name) {
  const pages = DATA.town_pages[name] || [];
  const words = DATA.town_words[name] || [name];
  const other = words.filter(w => w !== name);
  shell(name, `ガイドブック本文 ${pages.length}ページに記述があります`
    + (other.length ? `（あわせて探した語：${esc(other.join('、'))}）` : ''),
    pageBlocks(pages, words));
}

function detailEra(name) {
  const p = DATA.periods.find(x => x.名 === name);
  const pages = DATA.period_pages[name] || [];
  shell(name, `${esc(p.説明)} ／ 本文 ${pages.length}ページ`, pageBlocks(pages, []));
}

function bind() {
  document.querySelectorAll('[data-open]').forEach(b =>
    b.onclick = () => open_(b.dataset.open));
}
document.querySelectorAll('nav button').forEach(b =>
  b.onclick = () => setView(b.dataset.v));
render();
"""


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, default=DEFAULT_DATA)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args()

    d = build_index(args.data_dir)
    payload = {
        "pages": [{"page": p["page"], "file": p["file"],
                   "pdf_page": p["pdf_page"], "text": p["text"]}
                  for p in d["pages"] if p["page"]],
        "toc": d["toc"],
        "tags": d["tags"],
        "cat_pages": d["cat_pages"],
        "town_pages": d["town_pages"],
        "town_words": d["town_words"],
        "period_pages": d["period_pages"],
        "periods": [{"名": n, "説明": desc} for n, _, _, desc in PERIODS],
        "exam_by_cat": d["exam_by_cat"],
    }

    html = f"""<!doctype html>
<html lang="ja"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>おたる案内人 公式ガイドブック 索引</title>
<style>{CSS}</style></head><body>
<header><div class="wrap">
  <h1>おたる案内人 公式ガイドブック
    <small>{d['toc_doc']['書名']}　全{d['toc_doc']['総ページ']}ページ</small></h1>
  <nav>
    <button data-v="toc" class="on">目次</button>
    <button data-v="cat">分野</button>
    <button data-v="town">町名</button>
    <button data-v="era">年代</button>
  </nav>
</div></header>
<main><div class="wrap" id="main"></div></main>
<script>const DATA = {json.dumps(payload, ensure_ascii=False)};</script>
<script>{JS}</script>
</body></html>
"""
    args.out.write_text(html, encoding="utf-8")
    kb = args.out.stat().st_size // 1024

    print(f"書き出し: {args.out} ({kb:,} KB)")
    print(f"  目次: {len(d['toc'])}節")
    print(f"  分野: {len(d['cat_pages'])}分類 / "
          f"過去問の紐付け {sum(len(v) for v in d['exam_by_cat'].values())}問")
    print(f"  町名: {len(d['town_pages'])}/{len(d['tags']['町名'])}件で本文にヒット")
    print(f"  年代: {len(d['period_pages'])}区分")
    miss = [t for t in d["tags"]["町名"] if t not in d["town_pages"]]
    if miss:
        print(f"  本文に出てこない町名: {'、'.join(miss)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
