#!/usr/bin/env python3
"""ガイドブックの全ページを画像に書き出す。

読むためのビューアをPDFのまま作ると、ページを送るたびに70MBのPDFを
読み直すことになり、めくる操作にならない。ページを1枚ずつ画像にして
おけば、次のページを先読みして即座に切り替えられる。

WebPを使う。同じ見た目でJPEGの6割ほどの大きさになる。
1200px幅は本文の漢字が潰れない下限で、248ページで約35MB。

    1000px webp 119KB/ページ  計28MB   … ルビが読みにくい
    1200px webp 148KB/ページ  計35MB   … これを採用
    1400px webp 179KB/ページ  計43MB

出力: guidebook_pages/p001.webp 〜 p248.webp（通しページ番号）

使い方:
    python3 scripts/render_guidebook.py
    python3 scripts/render_guidebook.py --width 1400 --only 24
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pypdfium2 as pdfium

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_PAGES = ROOT / "data" / "guidebook_pages.json"
DEFAULT_PDF_DIR = ROOT / "guidebook"
DEFAULT_OUT = ROOT / "guidebook_pages"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pages", type=Path, default=DEFAULT_PAGES)
    parser.add_argument("--pdf-dir", type=Path, default=DEFAULT_PDF_DIR)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--width", type=int, default=1200)
    parser.add_argument("--quality", type=int, default=72)
    parser.add_argument("--only", type=int, help="この通しページだけ書き出す")
    parser.add_argument("--force", action="store_true",
                        help="すでにある画像も作り直す")
    args = parser.parse_args()

    pages = json.loads(args.pages.read_text(encoding="utf-8"))
    args.out.mkdir(parents=True, exist_ok=True)

    docs = {}
    for f in (1, 2):
        p = args.pdf_dir / f"guidebook_{f:02d}.pdf"
        if p.exists():
            docs[f] = pdfium.PdfDocument(str(p))
    if not docs:
        print(f"ガイドブックのPDFが無い: {args.pdf_dir}")
        return 1

    written = skipped = 0
    try:
        for r in pages:
            seq = r["seq"]
            if args.only and seq != args.only:
                continue
            dest = args.out / f"p{seq:03d}.webp"
            if dest.exists() and not args.force:
                skipped += 1
                continue
            doc = docs.get(r["file"])
            if doc is None:
                continue
            page = doc[r["pdf_page"] - 1]
            # 一度等倍で描いて幅を測り、目標の幅になる倍率で描き直す
            w0 = page.render(scale=1).to_pil().width
            img = page.render(scale=args.width / w0).to_pil().convert("RGB")
            img.save(dest, quality=args.quality, method=6)
            written += 1
            if written % 25 == 0:
                print(f"  {written}枚")
    finally:
        for d in docs.values():
            d.close()

    total = sum(f.stat().st_size for f in args.out.glob("*.webp"))
    print(f"\n書き出し: {args.out}")
    print(f"  新規 {written}枚 / 既存のまま {skipped}枚 / "
          f"合計 {len(list(args.out.glob('*.webp')))}枚 {total // 1048576}MB")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
