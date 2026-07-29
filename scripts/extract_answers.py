#!/usr/bin/env python3
"""解答PDFから「問番号 → 正解」を座標ベースで抽出する。

解答用紙は4列の表で、各セルに「問N」ラベルとその右に答えが置かれている。
テキストを行単位で読むと列がまざって対応付けを誤るため、
pdfplumber の単語座標を使い「同じ列・同じ行帯」で紐付ける。

A/B/C の小問がある設問はセル内に複数行が入るので、
次のラベルが現れるまでを1つのセルとして扱う。

使い方:
    python3 scripts/extract_answers.py past_exams/20_kaitou.pdf
    python3 scripts/extract_answers.py past_exams/20_kaitou.pdf --json
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import unicodedata
from pathlib import Path

import pdfplumber

# 「問39」だけの語もあるが、「問３９伊藤長右衛門」のようにラベルと答えが
# 1語に連結している場合もある。残りの文字列は答えの先頭として扱う。
LABEL = re.compile(r"^問\s*([0-9０-９]{1,3})\s*(.*)$")
# ラベルと答えが縦に数ポイントずれることがあるため許容幅を持たせる
Y_TOLERANCE = 6.0
# 列クラスタリングの許容幅（列間隔は約133pt）
X_CLUSTER = 40.0


def to_int(s: str) -> int:
    return int(unicodedata.normalize("NFKC", s))


def cluster_columns(xs: list[float]) -> list[float]:
    """ラベルのx座標を列にまとめ、各列の代表x（最小値）を返す。"""
    cols: list[list[float]] = []
    for x in sorted(xs):
        if cols and x - cols[-1][-1] <= X_CLUSTER:
            cols[-1].append(x)
        else:
            cols.append([x])
    return [min(c) for c in cols]


def extract(pdf_path: Path) -> dict[int, str]:
    answers: dict[int, str] = {}

    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            words = page.extract_words()
            labels = [(to_int(m.group(1)), w, m.group(2).strip()) for w in words
                      if (m := LABEL.match(w["text"]))]
            if not labels:
                continue

            col_xs = cluster_columns([w["x0"] for _, w, _ in labels])
            # 各列の右端＝次の列の左端。最終列はページ右端。
            col_right = {x: (col_xs[i + 1] if i + 1 < len(col_xs) else page.width)
                         for i, x in enumerate(col_xs)}

            def col_of(x: float) -> float:
                return min(col_xs, key=lambda c: abs(c - x))

            # 列ごとにラベルをy順に並べ、次のラベルまでをセル範囲とする
            by_col: dict[float, list] = {}
            for no, w, inline in labels:
                by_col.setdefault(col_of(w["x0"]), []).append((no, w, inline))

            for cx, items in by_col.items():
                items.sort(key=lambda t: t[1]["top"])
                right = col_right[cx]
                for i, (no, w, inline) in enumerate(items):
                    y_top = w["top"] - Y_TOLERANCE
                    y_end = (items[i + 1][1]["top"] - Y_TOLERANCE
                             if i + 1 < len(items) else page.height)

                    cell = [
                        v for v in words
                        if v["x0"] >= w["x1"] - 2 and v["x0"] < right
                        and y_top <= v["top"] < y_end
                        and not LABEL.match(v["text"])
                    ]
                    cell.sort(key=lambda v: (round(v["top"] / 8), v["x0"]))
                    parts = ([inline] if inline else []) + [v["text"] for v in cell]
                    text = " ".join(parts).strip()
                    if text:
                        answers[no] = text

    return answers


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pdf", type=Path)
    parser.add_argument("--json", action="store_true", help="JSONで出力")
    args = parser.parse_args()

    answers = extract(args.pdf)
    if not answers:
        print(f"解答を抽出できませんでした: {args.pdf}", file=sys.stderr)
        return 1

    if args.json:
        print(json.dumps(answers, ensure_ascii=False, indent=1))
    else:
        nums = sorted(answers)
        print(f"{args.pdf.name}: {len(answers)}問 (問{nums[0]}〜問{nums[-1]})")
        missing = [i for i in range(nums[0], nums[-1] + 1) if i not in answers]
        if missing:
            print(f"  欠番: {missing}")
        for n in nums:
            print(f"  問{n:>3}: {answers[n]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
