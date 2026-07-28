#!/usr/bin/env python3
"""past_exams/ の全PDFを調べ、なぜ抽出できないかを切り分けるための診断スクリプト。

各PDFについて「テキスト層があるか」「何文字取れるか」「画像だけか」を一覧化する。
抽出失敗の原因は大きく2つに分かれ、対処法がまったく違うため、まずここを確定させる。

  A. テキスト層が無い（スキャン画像PDF） → OCRが必要
  B. テキスト層はあるが記法が想定外   → 抽出パターンの調整で済む

使い方:
    python3 scripts/diagnose_pdfs.py                 # 一覧表
    python3 scripts/diagnose_pdfs.py --sample 1 20   # 指定回の本文も表示
"""

from __future__ import annotations

import argparse
from pathlib import Path

import pdfplumber

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_PDF_DIR = ROOT / "past_exams"
SAMPLE_CHARS = 600


def probe(pdf_path: Path) -> dict:
    """1つのPDFからページ数・文字数・画像数を取る。"""
    info = {"pages": 0, "chars": 0, "images": 0, "first_text": "", "error": ""}
    try:
        with pdfplumber.open(pdf_path) as pdf:
            info["pages"] = len(pdf.pages)
            texts = []
            for page in pdf.pages:
                texts.append(page.extract_text() or "")
                info["images"] += len(page.images)
            joined = "\n".join(texts)
            info["chars"] = len(joined.strip())
            info["first_text"] = joined.strip()[:SAMPLE_CHARS]
    except Exception as exc:
        info["error"] = f"{exc.__class__.__name__}: {exc}"

    # テキストが空ならpypdfでも試す（抽出器の差を切り分ける）
    if info["chars"] == 0 and not info["error"]:
        try:
            from pypdf import PdfReader

            reader = PdfReader(str(pdf_path))
            alt = "\n".join((p.extract_text() or "") for p in reader.pages).strip()
            info["chars"] = len(alt)
            info["first_text"] = alt[:SAMPLE_CHARS]
            if alt:
                info["error"] = "(pypdfでのみ取得可)"
        except Exception as exc:
            info["error"] = f"pypdf {exc.__class__.__name__}: {exc}"
    return info


def verdict(info: dict) -> str:
    if info["error"] and not info["chars"]:
        return "エラー"
    if info["chars"] == 0:
        return "画像PDF(OCR必要)" if info["images"] else "テキスト無し"
    if info["chars"] < 200:
        return "ほぼ空"
    return "テキストあり"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pdf-dir", type=Path, default=DEFAULT_PDF_DIR)
    parser.add_argument("--sample", type=int, nargs="*", default=[],
                        help="本文を表示する回番号 例: --sample 1 20")
    parser.add_argument("--start", type=int, default=1)
    parser.add_argument("--end", type=int, default=23)
    args = parser.parse_args()

    if not args.pdf_dir.is_dir():
        print(f"PDFディレクトリがありません: {args.pdf_dir}")
        return 1

    print(f"{'ファイル':<18}{'頁':>4}{'文字数':>8}{'画像':>6}  判定")
    print("-" * 62)

    summary: dict[str, int] = {}
    for n in range(args.start, args.end + 1):
        for kind in ("mondai", "kaitou"):
            path = args.pdf_dir / f"{n}_{kind}.pdf"
            if not path.exists():
                print(f"{path.name:<18}{'-':>4}{'-':>8}{'-':>6}  ファイル無し")
                summary["ファイル無し"] = summary.get("ファイル無し", 0) + 1
                continue
            info = probe(path)
            v = verdict(info)
            summary[v] = summary.get(v, 0) + 1
            note = f"  {info['error']}" if info["error"] else ""
            print(f"{path.name:<18}{info['pages']:>4}{info['chars']:>8}"
                  f"{info['images']:>6}  {v}{note}")

    print("\n=== 集計 ===")
    for k, v in sorted(summary.items(), key=lambda x: -x[1]):
        print(f"  {k}: {v}件")

    for n in args.sample:
        for kind in ("mondai", "kaitou"):
            path = args.pdf_dir / f"{n}_{kind}.pdf"
            if not path.exists():
                continue
            print(f"\n{'=' * 62}\n=== {path.name} 冒頭{SAMPLE_CHARS}文字 ===\n{'=' * 62}")
            text = probe(path)["first_text"]
            print(text if text else "(テキストを取得できず)")

    print("\nヒント: 「画像PDF(OCR必要)」が多い場合、正規表現の調整では解決しません。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
