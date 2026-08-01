#!/usr/bin/env python3
"""ガイドブックのページをtesseractで読み直し、ページごとに良い方を採る。

配布されたPDFにはOCR済みのテキスト層が入っているが、質にばらつきがあり、
図版のまわりや段組みの境目で「鱗感溌纏 醗匡且二覇」のような読めない
文字列になっているページが少なくない。索引サイトの本文表示がこれで
埋まってしまうため、tesseract（日本語）で読み直す。

どちらが良いかは「ひらがなの割合」で判定する。日本語の本文は3〜5割が
ひらがなになるが、OCRが崩れた箇所は漢字の羅列になりひらがながほぼ無い。
これが両者を分ける一番はっきりした指標だった。

    p95   既存 かな率 1.3%  →  tesseract 26.4%
    p23   既存 かな率 8.7%  →  tesseract 17.4%
    p150  既存 かな率49.8%  →  tesseract 49.9%（差がない＝どちらでもよい）

段組みは --psm 3（自動でページを解析）に任せる。--psm 6 で1ブロック扱いに
すると、本文と側注が横に混ざって読めなくなる。

出力: data/guidebook_pages.json を上書きし、次の項目を持たせる
    text      … 採用したテキスト
    text_pdf  … 元のPDFのテキスト層
    text_ocr  … tesseractで読み直したもの
    text_src  … どちらを採ったか（"pdf" / "ocr"）

使い方:
    python3 scripts/ocr_guidebook.py
    python3 scripts/ocr_guidebook.py --dpi 400 --only 95
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import tempfile
from pathlib import Path

import pypdfium2 as pdfium

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_PAGES = ROOT / "data" / "guidebook_pages.json"
DEFAULT_PDF_DIR = ROOT / "guidebook"

HIRAGANA = re.compile(r"[ぁ-ゖ]")
KANA_KANJI = re.compile(r"[ぁ-ゖァ-ヺ一-龥]")
# 本文として扱わない記号だけの行を落とすための判定
MEANINGFUL = re.compile(r"[ぁ-ゖァ-ヺ一-龥0-9A-Za-z]")


def kana_ratio(text: str) -> float:
    """ひらがなの割合。日本語の本文なら3〜5割、崩れた箇所はほぼ0になる。"""
    t = re.sub(r"\s", "", text)
    return len(HIRAGANA.findall(t)) / len(t) if t else 0.0


def clean(text: str) -> str:
    """読めない行を落とし、余分な空白を詰める。"""
    out = []
    for line in text.splitlines():
        s = line.strip()
        if not s:
            continue
        # 意味のある文字が1つも無い行（罫線や網点を拾ったもの）
        if not MEANINGFUL.search(s):
            continue
        # 短くて、かな・漢字が2文字未満の行はまず図版まわりのノイズ
        if len(s) <= 8 and len(KANA_KANJI.findall(s)) < 2:
            continue
        out.append(re.sub(r"[ \t　]{2,}", " ", s))
    return "\n".join(out)


def ocr_page(page, dpi: int, lang: str) -> str:
    """1ページを描画してtesseractにかける。"""
    img = page.render(scale=dpi / 72).to_pil()
    with tempfile.NamedTemporaryFile(suffix=".png") as tmp:
        img.save(tmp.name)
        r = subprocess.run(
            ["tesseract", tmp.name, "-", "-l", lang, "--psm", "3"],
            capture_output=True, text=True)
    return r.stdout


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pages", type=Path, default=DEFAULT_PAGES)
    parser.add_argument("--pdf-dir", type=Path, default=DEFAULT_PDF_DIR)
    parser.add_argument("--dpi", type=int, default=300)
    parser.add_argument("--lang", default="jpn")
    parser.add_argument("--only", type=int, help="この誌面ページだけ処理する")
    args = parser.parse_args()

    pages = json.loads(args.pages.read_text(encoding="utf-8"))
    docs = {}
    for f in (1, 2):
        p = args.pdf_dir / f"guidebook_{f:02d}.pdf"
        if p.exists():
            docs[f] = pdfium.PdfDocument(str(p))
    if not docs:
        print(f"ガイドブックのPDFが無い: {args.pdf_dir}")
        return 1

    swapped = 0
    try:
        for i, r in enumerate(pages, 1):
            if args.only and r.get("page") != args.only:
                continue
            doc = docs.get(r["file"])
            if doc is None:
                continue
            raw_pdf = r.get("text_pdf", r["text"])
            raw_ocr = ocr_page(doc[r["pdf_page"] - 1], args.dpi, args.lang)

            a, b = clean(raw_pdf), clean(raw_ocr)
            # 短すぎる方は比較にならないので、まず量で足切りしてから質で選ぶ
            if len(b) < 20 and len(a) >= 20:
                use, src = a, "pdf"
            elif len(a) < 20 and len(b) >= 20:
                use, src = b, "ocr"
            else:
                use, src = ((b, "ocr") if kana_ratio(b) > kana_ratio(a)
                            else (a, "pdf"))

            r["text_pdf"], r["text_ocr"], r["text"], r["text_src"] = a, b, use, src
            if src == "ocr":
                swapped += 1
            if i % 20 == 0:
                print(f"  {i}/{len(pages)}ページ")
    finally:
        for d in docs.values():
            d.close()

    args.pages.write_text(json.dumps(pages, ensure_ascii=False, indent=1) + "\n",
                          encoding="utf-8")
    done = [r for r in pages if "text_src" in r]
    avg = sum(kana_ratio(r["text"]) for r in done) / max(len(done), 1)
    was = sum(kana_ratio(r["text_pdf"]) for r in done) / max(len(done), 1)
    print(f"\n書き出し: {args.pages}")
    print(f"  {len(done)}ページを処理 / tesseract を採用 {swapped}ページ")
    print(f"  ひらがな率の平均 {was:.1%} → {avg:.1%}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
