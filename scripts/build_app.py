#!/usr/bin/env python3
"""過去問演習用の学習アプリ（単一HTMLファイル）を生成する。

data/exam_*.json を埋め込んだ study_app.html を出力する。
ブラウザで開くだけで動き、サーバもネット接続も要らない。

- 写真つき設問は images/ の画像を相対パスで表示する
  （file:// でも <img src> は読めるので、画像はファイル参照のまま持つ）
- 成績は localStorage に保存し、間違えた問題を優先的に再出題する
- 記述式は自己採点（正解を表示して○×を自分で押す）

使い方:
    python3 scripts/build_app.py
    python3 scripts/build_app.py --out study_app.html
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DATA = ROOT / "data"
DEFAULT_OUT = ROOT / "study_app.html"

CSS = """
:root { color-scheme: light dark; --bg:#fbfbfa; --fg:#1a1a18; --card:#fff;
  --line:#e4e4de; --muted:#6b6b64; --ok:#2f7d5c; --ng:#b4483c; --accent:#7a6a45;
  --chip:#f3eee1; }
@media (prefers-color-scheme: dark) {
  :root { --bg:#16161a; --fg:#e8e8e3; --card:#1e1e23; --line:#32323a;
    --muted:#9a9a92; --ok:#5fbf95; --ng:#e08a7e; --accent:#d8c79a; --chip:#33301f; }
}
* { box-sizing: border-box; }
body { margin:0; padding:1.5rem 1rem 5rem; background:var(--bg); color:var(--fg);
  font-family:"Hiragino Sans","Noto Sans JP",system-ui,sans-serif; line-height:1.7; }
main { max-width:46rem; margin:0 auto; }
h1 { font-size:1.15rem; margin:0 0 1rem; display:flex; align-items:baseline;
  gap:.6rem; flex-wrap:wrap; }
h1 small { font-weight:400; font-size:.8rem; color:var(--muted); }
.bar { display:flex; gap:.4rem; flex-wrap:wrap; margin-bottom:1.25rem; }
button { font:inherit; cursor:pointer; border-radius:7px; border:1px solid var(--line);
  background:var(--card); color:var(--fg); padding:.4rem .8rem; }
button:hover { border-color:var(--accent); }
button.on { background:var(--accent); color:var(--bg); border-color:var(--accent); }
.card { background:var(--card); border:1px solid var(--line); border-radius:11px;
  padding:1.25rem 1.4rem 1.4rem; }
.chip { display:inline-block; font-size:.72rem; font-weight:600; letter-spacing:.04em;
  color:var(--accent); background:var(--chip); border-radius:4px;
  padding:.15rem .5rem; margin-bottom:.7rem; }
.qtext { font-weight:500; margin:0 0 1.1rem; }
.photos { display:grid; grid-template-columns:repeat(2,1fr); gap:.7rem;
  margin-bottom:1rem; }
@media (max-width:30rem) { .photos { grid-template-columns:1fr; } }
.photos .pick { margin:0; padding:.35rem; border:1px solid var(--line);
  border-radius:8px; background:var(--card); cursor:pointer; text-align:left;
  display:block; width:100%; }
.photos .pick:hover { border-color:var(--accent); }
.photos img { width:100%; height:auto; display:block; border-radius:5px; }
.photos figcaption { font-size:.78rem; color:var(--muted); margin-top:.3rem; }
.photos .pick.ok { border-color:var(--ok); border-width:2px;
  background:color-mix(in srgb,var(--ok) 12%,transparent); }
.photos .pick.ng { border-color:var(--ng); border-width:2px;
  background:color-mix(in srgb,var(--ng) 12%,transparent); }
.photos .pick.ok figcaption { color:var(--ok); font-weight:700; }
.choices { display:flex; flex-direction:column; gap:.5rem; }
.choice { text-align:left; padding:.6rem .9rem; display:flex; gap:.6rem; }
.choice .n { font-weight:700; color:var(--muted); flex:0 0 1.2rem; }
.choice.ok { border-color:var(--ok); background:color-mix(in srgb,var(--ok) 12%,transparent); }
.choice.ng { border-color:var(--ng); background:color-mix(in srgb,var(--ng) 12%,transparent); }
.reveal { margin-top:1.1rem; padding-top:1rem; border-top:1px solid var(--line);
  font-size:.92rem; }
.reveal b { color:var(--ok); }
.note { font-size:.8rem; color:var(--muted); margin-top:.5rem; }
.selfmark { display:flex; gap:.5rem; margin-top:.9rem; }
.stats { display:grid; grid-template-columns:repeat(auto-fit,minmax(8rem,1fr));
  gap:.7rem; margin-bottom:1.25rem; }
.stat { background:var(--card); border:1px solid var(--line); border-radius:9px;
  padding:.7rem .9rem; }
.stat .v { font-size:1.35rem; font-weight:700; font-variant-numeric:tabular-nums; }
.stat .k { font-size:.75rem; color:var(--muted); }
table { width:100%; border-collapse:collapse; font-size:.85rem; }
th,td { text-align:left; padding:.4rem .5rem; border-bottom:1px solid var(--line); }
th { color:var(--muted); font-weight:600; }
td.num { text-align:right; font-variant-numeric:tabular-nums; }
.hint { font-size:.78rem; color:var(--muted); margin-top:1rem; }
.empty { color:var(--muted); }
"""

JS = r"""
const $ = (s, r=document) => r.querySelector(s);
const KEY = 'otaru-study-v1';
const CIRC = '①②③④⑤⑥⑦⑧⑨⑩';

let store = JSON.parse(localStorage.getItem(KEY) || '{}');
const save = () => localStorage.setItem(KEY, JSON.stringify(store));
const rec = id => store[id] || (store[id] = {seen:0, ok:0, ng:0, box:0});

let mode = 'weak';       // weak | all | unseen | exam
let examFilter = null;
let current = null, answered = false;

/* 出題の重み付け。間違えた問題と未挑戦を優先し、
   正解を重ねた問題は間隔を空ける（簡易的な間隔反復）。 */
function weight(q) {
  const r = store[q.id];
  if (!r || r.seen === 0) return 6;
  if (r.box <= 0) return 10;
  return Math.max(1, 8 - r.box * 2);
}

function pool() {
  let qs = QUESTIONS;
  if (mode === 'exam' && examFilter) qs = qs.filter(q => q.exam === examFilter);
  if (mode === 'unseen') qs = qs.filter(q => !store[q.id] || store[q.id].seen === 0);
  if (mode === 'weak') qs = qs.filter(q => { const r = store[q.id];
    return !r || r.seen === 0 || r.box <= 0; });
  return qs.length ? qs : (mode === 'exam' && examFilter
    ? QUESTIONS.filter(q => q.exam === examFilter) : QUESTIONS);
}

function pick() {
  const qs = pool();
  const total = qs.reduce((s, q) => s + weight(q), 0);
  let t = Math.random() * total;
  for (const q of qs) { t -= weight(q); if (t <= 0) return q; }
  return qs[qs.length - 1];
}

function mark(ok) {
  const r = rec(current.id);
  r.seen++;
  if (ok) { r.ok++; r.box = Math.min(5, r.box + 1); }
  else { r.ng++; r.box = 0; }
  save();
  renderStats();
}

function render() {
  answered = false;
  current = pick();
  const q = current;
  const sub = q.sub ? q.sub : '';
  /* 写真そのものが選択肢の設問は、写真をクリックして選ぶ。
     テキストの「［写真1］」は重複するので出さない。 */
  const pickPhotos = q.type === '写真選択' && q.photos.length;
  const photos = q.photos.length
    ? `<div class="photos">${q.photos.map((p, i) => pickPhotos
        ? `<button class="pick choice" data-i="${i+1}">
             <img src="${p}" alt="選択肢${i+1}" loading="lazy">
             <figcaption>${CIRC[i]} 選択肢${i+1}</figcaption></button>`
        : `<figure class="pick"><img src="${p}" alt="" loading="lazy"></figure>`
      ).join('')}</div>`
    : '';

  const body = pickPhotos ? ''
    : q.choices.length
    ? `<div class="choices">${q.choices.map((c, i) =>
        `<button class="choice" data-i="${i+1}">
           <span class="n">${CIRC[i]}</span><span>${c}</span></button>`).join('')}</div>`
    : `<div class="selfmark"><button id="show">答えを見る</button></div>`;

  $('#quiz').innerHTML = `
    <div class="card">
      <span class="chip">第${q.exam}回 問${q.no}${sub}・${q.type}</span>
      <p class="qtext">${q.q}</p>
      ${photos}${body}
      <div id="reveal"></div>
    </div>`;

  $('#quiz').querySelectorAll('.choice').forEach(b =>
    b.onclick = () => choose(Number(b.dataset.i)));
  const s = $('#show'); if (s) s.onclick = showFree;
}

function choose(i) {
  if (answered) return;
  answered = true;
  const q = current, ok = String(i) === String(q.a);
  $('#quiz').querySelectorAll('.choice').forEach(b => {
    const n = Number(b.dataset.i);
    if (String(n) === String(q.a)) b.classList.add('ok');
    else if (n === i) b.classList.add('ng');
  });
  mark(ok);
  $('#reveal').innerHTML = `<div class="reveal">
    ${ok ? '<b>正解</b>' : '<span style="color:var(--ng);font-weight:700">不正解</span>'}
    　正解は <b>${CIRC[Number(q.a)-1] || q.a}</b>
    ${q.abody ? ' ' + q.abody : ''}
    ${q.note ? `<div class="note">${q.note}</div>` : ''}
    <div class="selfmark"><button id="next">次の問題 →</button></div></div>`;
  $('#next').onclick = render;
}

function showFree() {
  if (answered) return;
  answered = true;
  const q = current;
  $('#reveal').innerHTML = `<div class="reveal">
    正解: <b>${q.a}</b>
    ${q.note ? `<div class="note">${q.note}</div>` : ''}
    <div class="selfmark">
      <button id="y">正答できた</button><button id="n">できなかった</button></div></div>`;
  $('#y').onclick = () => { mark(true); render(); };
  $('#n').onclick = () => { mark(false); render(); };
}

function renderStats() {
  const ids = Object.keys(store);
  const seen = ids.filter(k => store[k].seen > 0).length;
  const ok = ids.reduce((s, k) => s + store[k].ok, 0);
  const ng = ids.reduce((s, k) => s + store[k].ng, 0);
  const rate = ok + ng ? Math.round(ok / (ok + ng) * 100) : 0;
  const weak = ids.filter(k => store[k].seen > 0 && store[k].box <= 0).length;
  $('#stats').innerHTML = `
    <div class="stat"><div class="v">${seen}<small style="font-size:.8rem;color:var(--muted)">/${QUESTIONS.length}</small></div><div class="k">着手した問題</div></div>
    <div class="stat"><div class="v">${rate}%</div><div class="k">正答率（延べ${ok+ng}回）</div></div>
    <div class="stat"><div class="v">${weak}</div><div class="k">要復習</div></div>`;
}

function renderExamButtons() {
  const exams = [...new Set(QUESTIONS.map(q => q.exam))].sort((a,b) => a-b);
  $('#exams').innerHTML = exams.map(n =>
    `<button data-exam="${n}">第${n}回</button>`).join('');
  $('#exams').querySelectorAll('button').forEach(b => b.onclick = () => {
    mode = 'exam'; examFilter = Number(b.dataset.exam);
    setMode(); render();
  });
}

function setMode() {
  document.querySelectorAll('[data-mode]').forEach(b =>
    b.classList.toggle('on', b.dataset.mode === mode));
  document.querySelectorAll('[data-exam]').forEach(b =>
    b.classList.toggle('on', mode === 'exam' && Number(b.dataset.exam) === examFilter));
}

document.querySelectorAll('[data-mode]').forEach(b => b.onclick = () => {
  mode = b.dataset.mode; examFilter = null; setMode(); render();
});

$('#reset').onclick = () => {
  if (!confirm('学習記録をすべて消します。よろしいですか。')) return;
  store = {}; save(); renderStats(); render();
};

document.addEventListener('keydown', e => {
  if (e.key >= '1' && e.key <= '4') {
    const b = $(`.choice[data-i="${e.key}"]`); if (b) b.click();
  } else if (e.key === 'Enter' || e.key === ' ') {
    const n = $('#next') || $('#show'); if (n) { e.preventDefault(); n.click(); }
  }
});

renderExamButtons(); setMode(); renderStats(); render();
"""


def build_questions(data_dir: Path) -> list[dict]:
    out = []
    files = sorted(data_dir.glob("exam_*.json"),
                   key=lambda p: int(p.stem.split("_")[1]))
    for path in files:
        exam = json.loads(path.read_text(encoding="utf-8"))
        n = exam["回数"]
        for it in exam["設問"]:
            sub = it.get("sub", "")
            qid = f"R{n:02d}-Q{it['no']:03d}" + (f"-{sub}" if sub else "")
            choices = it.get("c", [])
            answer = str(it.get("a", ""))
            abody = ""
            if choices and answer.isdigit() and 1 <= int(answer) <= len(choices):
                abody = choices[int(answer) - 1]

            photos = []
            spec = it.get("photo")
            if spec and spec.get("role", "choices") == "choices":
                photos = [f"images/R{n:02d}-Q{it['no']:03d}-{i + 1}.png"
                          for i in range(spec["n"])]
            elif spec:
                photos = [f"images/R{n:02d}-Q{it['no']:03d}-stem.png"]

            out.append({
                "id": qid, "exam": n, "no": it["no"], "sub": sub,
                "type": it.get("type", ""), "q": it["q"], "choices": choices,
                "a": answer, "abody": abody, "photos": photos,
                "note": it.get("note", ""),
            })
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, default=DEFAULT_DATA)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args()

    questions = build_questions(args.data_dir)
    if not questions:
        print(f"データがありません: {args.data_dir}/exam_*.json")
        return 1

    exams = sorted({q["exam"] for q in questions})
    doc = f"""<!doctype html>
<html lang="ja"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>おたる案内人検定 学習アプリ</title>
<style>{CSS}</style></head><body><main>
<h1>おたる案内人検定 学習アプリ
  <small>{len(questions)}問 / 第{exams[0]}回〜第{exams[-1]}回（{len(exams)}回分）</small></h1>
<div id="stats" class="stats"></div>
<div class="bar">
  <button data-mode="weak">要復習・未挑戦</button>
  <button data-mode="all">全問ランダム</button>
  <button data-mode="unseen">未挑戦のみ</button>
  <button id="reset" style="margin-left:auto">記録を消す</button>
</div>
<div class="bar" id="exams"></div>
<div id="quiz"></div>
<p class="hint">キーボード: 1〜4 で選択 / Enter で次へ。
  記録はこのブラウザに保存されます。</p>
</main>
<script>const QUESTIONS = {json.dumps(questions, ensure_ascii=False)};</script>
<script>{JS}</script>
</body></html>
"""
    args.out.write_text(doc, encoding="utf-8")
    kb = args.out.stat().st_size / 1024
    print(f"書き出し: {args.out} ({len(questions)}問 / {kb:.0f} KB)")
    print(f"  収録: 第{exams[0]}回〜第{exams[-1]}回 ({len(exams)}回分)")
    print(f"  未収録: {[i for i in range(1, 24) if i not in exams]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
