#!/usr/bin/env python3
"""写真つき設問を「問題文＋切り抜いた写真＋正解」の形で1枚のHTMLにまとめる。

写真は文字で描写しても伝わらないため、画像そのものを設問と並べて見せる。
画像は data URI で埋め込むので、HTMLファイル1つで完結し、
images/ を持ち歩かなくても閲覧できる。

先に scripts/crop_photos.py を実行して images/ を作っておく。

使い方:
    python3 scripts/build_photo_sheet.py
    python3 scripts/build_photo_sheet.py --out photo_questions.html
"""

from __future__ import annotations

import argparse
import base64
import html
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DATA = ROOT / "data"
DEFAULT_IMAGES = ROOT / "images"
DEFAULT_OUT = ROOT / "photo_questions.html"

CIRCLED = "①②③④⑤⑥⑦⑧⑨⑩"

CSS = """
:root { color-scheme: light dark; }
* { box-sizing: border-box; }
body { margin: 0; padding: 2rem 1rem 4rem;
  font-family: "Hiragino Sans", "Noto Sans JP", system-ui, sans-serif;
  line-height: 1.7; background: #fbfbfa; color: #1a1a18; }
main { max-width: 56rem; margin: 0 auto; }
h1 { font-size: 1.5rem; margin: 0 0 .25rem; }
.lead { color: #6b6b64; margin: 0 0 2.5rem; font-size: .9rem; }
.q { background: #fff; border: 1px solid #e4e4de; border-radius: 10px;
  padding: 1.25rem 1.5rem 1.5rem; margin-bottom: 1.75rem; }
.tag { display: inline-block; font-size: .75rem; font-weight: 600;
  letter-spacing: .04em; color: #7a6a45; background: #f3eee1;
  border-radius: 4px; padding: .15rem .5rem; margin-bottom: .6rem; }
.text { margin: 0 0 1.1rem; font-weight: 500; }
.grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(15rem, 1fr));
  gap: 1rem; margin-bottom: 1.1rem; }
figure { margin: 0; }
figure img { width: 100%; height: auto; display: block;
  border: 1px solid #dcdcd4; border-radius: 6px; background: #fff; }
figcaption { font-size: .8rem; color: #6b6b64; margin-top: .35rem; }
figure.correct img { border: 2px solid #2f7d5c; }
figure.correct figcaption { color: #2f7d5c; font-weight: 600; }
.stem img { max-width: 26rem; }
.ans { font-size: .9rem; border-top: 1px solid #eeeee8; padding-top: .8rem; }
.ans b { color: #2f7d5c; }
.note { font-size: .8rem; color: #8a8a80; margin-top: .5rem; }
@media (prefers-color-scheme: dark) {
  body { background: #16161a; color: #e8e8e3; }
  .lead, figcaption, .note { color: #9a9a92; }
  .q { background: #1e1e23; border-color: #32323a; }
  .tag { color: #d8c79a; background: #33301f; }
  figure img { border-color: #3a3a42; }
  .ans { border-color: #2c2c34; }
  figure.correct img { border-color: #5fbf95; }
  figure.correct figcaption, .ans b { color: #5fbf95; }
}
:root[data-theme="dark"] body { background: #16161a; color: #e8e8e3; }
:root[data-theme="light"] body { background: #fbfbfa; color: #1a1a18; }
"""


def data_uri(path: Path) -> str | None:
    if not path.exists():
        return None
    return "data:image/png;base64," + base64.b64encode(path.read_bytes()).decode()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, default=DEFAULT_DATA)
    parser.add_argument("--images", type=Path, default=DEFAULT_IMAGES)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args()

    files = sorted(args.data_dir.glob("exam_*.json"),
                   key=lambda p: int(p.stem.split("_")[1]))
    blocks: list[str] = []
    count, missing = 0, []

    for path in files:
        exam = json.loads(path.read_text(encoding="utf-8"))
        n = exam["回数"]
        for it in exam["設問"]:
            spec = it.get("photo")
            if not spec:
                continue
            count += 1
            base = f"R{n:02d}-Q{it['no']:03d}"
            role = spec.get("role", "choices")
            answer = str(it.get("a", ""))

            parts = [f'<article class="q">',
                     f'<span class="tag">第{n}回 問{it["no"]}</span>',
                     f'<p class="text">{html.escape(it["q"])}</p>']

            if role == "stem":
                uri = data_uri(args.images / f"{base}-stem.png")
                if uri:
                    parts.append(f'<div class="stem"><img src="{uri}" alt=""></div>')
                else:
                    missing.append(f"{base}-stem.png")
                if it.get("c"):
                    lis = "".join(
                        f"<li>{CIRCLED[i]} {html.escape(c)}</li>"
                        for i, c in enumerate(it["c"]))
                    parts.append(f"<ol style='list-style:none;padding:0'>{lis}</ol>")
            else:
                cells = []
                for i in range(len(it.get("c", []))):
                    uri = data_uri(args.images / f"{base}-{i + 1}.png")
                    if not uri:
                        missing.append(f"{base}-{i + 1}.png")
                        continue
                    ok = answer == str(i + 1)
                    cells.append(
                        f'<figure class="{"correct" if ok else ""}">'
                        f'<img src="{uri}" alt="選択肢{i + 1}">'
                        f'<figcaption>{CIRCLED[i]} 選択肢{i + 1}'
                        f'{" ← 正解" if ok else ""}</figcaption></figure>')
                if cells:
                    parts.append(f'<div class="grid">{"".join(cells)}</div>')

            label = CIRCLED[int(answer) - 1] if answer.isdigit() and int(answer) <= 10 else answer
            parts.append(f'<p class="ans">正解: <b>{label}</b></p>')
            if it.get("note"):
                parts.append(f'<p class="note">{html.escape(it["note"])}</p>')
            parts.append("</article>")
            blocks.append("".join(parts))

    doc = (f"<title>おたる案内人検定 写真つき設問</title>"
           f"<style>{CSS}</style>"
           f"<main><h1>おたる案内人検定 写真つき設問</h1>"
           f'<p class="lead">写真は問題PDFから切り抜いたものです。'
           f'正解の選択肢を緑の枠で示しています。全{count}問。</p>'
           + "".join(blocks) + "</main>")

    args.out.write_text(doc, encoding="utf-8")
    print(f"書き出し: {args.out} ({count}問 / {args.out.stat().st_size / 1024:.0f} KB)")
    if missing:
        print(f"画像が見つからない: {len(missing)}件 — crop_photos.py を実行してください")
        for m in missing[:10]:
            print(f"  - {m}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
