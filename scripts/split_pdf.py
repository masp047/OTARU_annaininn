#!/usr/bin/env python3
"""大きなPDFを、指定サイズ未満の複数ファイルに分割する。

GitHubは1ファイル100MBを超えるpushを拒否するため、
公式ガイドブック（135MB）をそのまま置けない。ページ単位で分割する。

再圧縮はしない。画質を落とすと文字が読めなくなり、
ページ画像から読む用途に耐えなくなるため。

使い方:
    python3 scripts/split_pdf.py "元のPDF" --out guidebook
    python3 scripts/split_pdf.py "元のPDF" --out guidebook --limit-mb 80
"""

from __future__ import annotations

import argparse
from pathlib import Path

from pypdf import PdfReader, PdfWriter


def write_part(reader: PdfReader, pages: list[int], dest: Path) -> int:
    w = PdfWriter()
    for i in pages:
        w.add_page(reader.pages[i])
    with dest.open("wb") as fh:
        w.write(fh)
    return dest.stat().st_size


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pdf", type=Path)
    parser.add_argument("--out", type=Path, required=True, help="出力先ディレクトリ")
    parser.add_argument("--limit-mb", type=float, default=80.0,
                        help="1ファイルの上限MB (既定80 / GitHubの制限は100)")
    parser.add_argument("--prefix", default="guidebook", help="出力ファイル名の接頭辞")
    args = parser.parse_args()

    if not args.pdf.exists():
        print(f"ファイルがありません: {args.pdf}")
        return 1

    args.out.mkdir(parents=True, exist_ok=True)
    reader = PdfReader(str(args.pdf))
    total = len(reader.pages)
    limit = args.limit_mb * 1024 * 1024
    src_mb = args.pdf.stat().st_size / 1024 / 1024
    print(f"入力: {args.pdf.name} / {total}ページ / {src_mb:.0f} MB")

    # まず均等割りの目安を出し、超過したら分割数を増やして作り直す
    parts = max(1, int(src_mb / args.limit_mb) + 1)
    while True:
        per = -(-total // parts)  # 切り上げ
        ranges = [list(range(s, min(s + per, total))) for s in range(0, total, per)]
        made, over = [], False
        for i, pages in enumerate(ranges, start=1):
            dest = args.out / f"{args.prefix}_{i:02d}.pdf"
            size = write_part(reader, pages, dest)
            made.append((dest, pages, size))
            if size > limit:
                over = True
        if not over:
            break
        for dest, _, _ in made:
            dest.unlink(missing_ok=True)
        parts += 1
        print(f"  上限を超えたため {parts} 分割で再試行します")

    print()
    for dest, pages, size in made:
        print(f"  {dest.name}: p.{pages[0] + 1}〜p.{pages[-1] + 1} "
              f"({len(pages)}ページ / {size / 1024 / 1024:.0f} MB)")
    print(f"\n{len(made)}ファイルに分割しました → {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
