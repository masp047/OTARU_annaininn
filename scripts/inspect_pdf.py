#!/usr/bin/env python3
"""PDFの生テキストと表構造をそのまま出力して、抽出ルールの調整に使う診断ツール。

extract_exams.py の解析結果が合わない場合、まずこれで実際のレイアウトを確認する。

使い方:
    python3 scripts/inspect_pdf.py past_exams/1_mondai.pdf
    python3 scripts/inspect_pdf.py past_exams/1_kaitou.pdf --tables
    python3 scripts/inspect_pdf.py past_exams/1_mondai.pdf --pages 1-2 --repr
"""

from __future__ import annotations

import argparse
from pathlib import Path

import pdfplumber


def parse_pages(spec: str | None, total: int) -> list[int]:
    if not spec:
        return list(range(total))
    pages: list[int] = []
    for part in spec.split(","):
        part = part.strip()
        if "-" in part:
            lo, hi = part.split("-", 1)
            pages.extend(range(int(lo) - 1, int(hi)))
        else:
            pages.append(int(part) - 1)
    return [p for p in pages if 0 <= p < total]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pdf", type=Path)
    parser.add_argument("--pages", help="対象ページ 例: 1-3 または 1,4")
    parser.add_argument("--tables", action="store_true", help="表構造も出力する")
    parser.add_argument("--repr", action="store_true", help="不可視文字を可視化して出力")
    args = parser.parse_args()

    with pdfplumber.open(args.pdf) as pdf:
        targets = parse_pages(args.pages, len(pdf.pages))
        print(f"# {args.pdf.name} — 全{len(pdf.pages)}ページ中 {len(targets)}ページを表示\n")

        for idx in targets:
            page = pdf.pages[idx]
            print(f"{'=' * 70}\n=== ページ {idx + 1} ===\n{'=' * 70}")

            text = page.extract_text() or ""
            for line in text.splitlines():
                print(repr(line) if args.repr else line)

            if args.tables:
                for t_i, table in enumerate(page.extract_tables(), start=1):
                    print(f"\n--- 表 {t_i} ({len(table)}行) ---")
                    for row in table:
                        print([c.replace("\n", "⏎") if c else c for c in row])
            print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
