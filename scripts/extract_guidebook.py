#!/usr/bin/env python3
"""公式ガイドブックのPDFから、ページ本文と誌面ページ番号を取り出す。

ガイドブックは全248ページで、GitHubの制限に合わせて2分割してある
（guidebook/guidebook_01.pdf, _02.pdf）。中扉や口絵にはノンブルが
振られていないため、PDFの通しページ番号と誌面のページ番号は一致しない。
ずれは巻頭で+9、巻末では+16まで広がる。

そこで各ページの下端・上端にある孤立した数字をノンブルとして拾い、
それをアンカーにして全ページへ誌面ページ番号を割り当てる。
章番号などの誤検出は「ずれが妥当な範囲」「ノンブルが単調増加」の
2条件で落とす。

出力: data/guidebook_pages.json
    [{"seq":1, "file":1, "pdf_page":1, "page":null, "text":"…"}, …]
    seq  … 通しページ（1〜248）
    page … 誌面に刷られたページ番号。無いページは null

使い方:
    python3 scripts/extract_guidebook.py
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

import pdfplumber

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_PDFS = [ROOT / "guidebook" / "guidebook_01.pdf",
                ROOT / "guidebook" / "guidebook_02.pdf"]
DEFAULT_OUT = ROOT / "data" / "guidebook_pages.json"

NUMBER = re.compile(r"[0-9]{1,3}")
# ノンブルはページの上下の帯にある
EDGE_TOP = 0.08
EDGE_BOTTOM = 0.90
# 通しページ番号と誌面ページ番号のずれの許容範囲。
# 実測で+9〜+16。章番号の「1」などを拾うと桁違いの値になるので弾ける。
OFFSET_MIN, OFFSET_MAX = 8, 20


def page_nombre(page) -> int | None:
    """ページ下端・上端にある孤立した数字をノンブルとして返す。"""
    h = page.height
    found = [int(w["text"]) for w in page.extract_words()
             if NUMBER.fullmatch(w["text"])
             and (w["top"] > h * EDGE_BOTTOM or w["bottom"] < h * EDGE_TOP)]
    # 2つ以上見つかったページは判断できないので使わない（アンカーを減らすだけ）
    return found[0] if len(found) == 1 else None


def assign_pages(raw: list[dict]) -> None:
    """検出したノンブルをアンカーにして、全ページへ誌面ページ番号を入れる。"""
    anchors: list[tuple[int, int]] = []
    for r in raw:
        n = r.get("nombre")
        if n is None:
            continue
        if not (OFFSET_MIN <= r["seq"] - n <= OFFSET_MAX):
            continue          # 章番号などの誤検出
        if anchors and n <= anchors[-1][1]:
            continue          # ノンブルは単調増加するはず
        anchors.append((r["seq"], n))

    by_seq = {r["seq"]: r for r in raw}
    for r in raw:
        r["page"] = None
    for seq, n in anchors:
        by_seq[seq]["page"] = n
    # アンカー間はノンブルが1ずつ増える前提で埋める。
    # ページ数が合わないところは中扉が挟まっているので埋めない。
    for (a_seq, a_n), (b_seq, b_n) in zip(anchors, anchors[1:]):
        if b_seq - a_seq == b_n - a_n:
            for d in range(1, b_seq - a_seq):
                by_seq[a_seq + d]["page"] = a_n + d
    # 最後のアンカーより後ろは、ずれをそのまま延長する
    if anchors:
        last_seq, last_n = anchors[-1]
        for r in raw:
            if r["seq"] > last_seq and r["page"] is None:
                r["page"] = last_n + (r["seq"] - last_seq)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pdf", type=Path, nargs="*", default=DEFAULT_PDFS)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args()

    raw: list[dict] = []
    seq = 0
    for fi, path in enumerate(args.pdf, 1):
        if not path.exists():
            print(f"PDFが無い: {path}")
            return 1
        with pdfplumber.open(path) as pdf:
            for pi, page in enumerate(pdf.pages, 1):
                seq += 1
                raw.append({
                    "seq": seq, "file": fi, "pdf_page": pi,
                    "nombre": page_nombre(page),
                    "text": (page.extract_text() or "").strip(),
                })

    assign_pages(raw)
    out = [{k: r[k] for k in ("seq", "file", "pdf_page", "page", "text")}
           for r in raw]
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(out, ensure_ascii=False, indent=1) + "\n",
                        encoding="utf-8")

    numbered = sum(1 for r in out if r["page"])
    chars = sum(len(r["text"]) for r in out)
    print(f"書き出し: {args.out}")
    print(f"  {len(out)}ページ / 誌面ページ番号あり {numbered} / 本文 {chars:,}字")
    empty = [r["seq"] for r in out if not r["text"]]
    if empty:
        print(f"  本文が取れなかったページ: {empty}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
