#!/usr/bin/env python3
"""写真つき設問の画像を切り抜き、設問と紐付けて保存する。

data/exam_NN.json の設問に photo 指定があるものを対象にする。
指定の書き方とファイル名の決まりは photo_spec.py を参照。

ページ内の画像は「上の行から、行内は左から」の読み順に並べ替えて
選択肢番号を割り当てる。設問との対応はJSON側に人手で記録する方式にした。
ページ画像を読んで問題文を書き起こす作業と同時に対応が分かるので、
座標からの自動推定より確実。

出力: images/R01-Q012-1.png … / images/R23-Q023-stem.png

使い方:
    python3 scripts/crop_photos.py
    python3 scripts/crop_photos.py --dpi 300 --only 1
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pdfplumber
import pypdfium2 as pdfium

from photo_spec import page_slice, photo_names

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DATA = ROOT / "data"
DEFAULT_PDF_DIR = ROOT / "past_exams_ocr"
DEFAULT_OUT = ROOT / "images"

# 余白を取ると隣に置かれた選択肢番号を拾ってしまうため、bboxぴったりで切る
MARGIN_PT = 0.0
# 同じ行と見なす縦方向のずれ
ROW_TOLERANCE = 20.0
# 埋め込み画像がこれ未満の解像度なら警告する。
# 元PDFに情報が無いので、高DPIで描画しても判別できるようにはならない。
MIN_SRC_PIXELS = 200


def reading_order(boxes: list[dict]) -> list[dict]:
    """画像を「上の行から、行内は左から」の順に並べる。"""
    rows: list[list[dict]] = []
    for b in sorted(boxes, key=lambda b: b["top"]):
        if rows and abs(b["top"] - rows[-1][0]["top"]) <= ROW_TOLERANCE:
            rows[-1].append(b)
        else:
            rows.append([b])
    ordered = []
    for row in rows:
        ordered.extend(sorted(row, key=lambda b: b["x0"]))
    return ordered


def crop_page(pdf_path: Path, page_no: int, boxes: list[dict],
              names: list[str], out_dir: Path, dpi: int) -> list[Path]:
    """指定ページを高解像度で描画し、各bboxを切り出して保存する。"""
    scale = dpi / 72.0
    doc = pdfium.PdfDocument(str(pdf_path))
    try:
        img = doc[page_no - 1].render(scale=scale).to_pil().convert("RGB")
    finally:
        doc.close()

    written = []
    for box, name in zip(boxes, names):
        left = max(0, (box["x0"] - MARGIN_PT) * scale)
        top = max(0, (box["top"] - MARGIN_PT) * scale)
        right = min(img.width, (box["x1"] + MARGIN_PT) * scale)
        bottom = min(img.height, (box["bottom"] + MARGIN_PT) * scale)
        dest = out_dir / f"{name}.png"
        img.crop((int(left), int(top), int(right), int(bottom))).save(dest)
        written.append(dest)
    return written


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, default=DEFAULT_DATA)
    parser.add_argument("--pdf-dir", type=Path, default=DEFAULT_PDF_DIR)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--dpi", type=int, default=220)
    parser.add_argument("--only", type=int, help="この回だけ処理する")
    args = parser.parse_args()

    args.out.mkdir(parents=True, exist_ok=True)
    files = sorted(args.data_dir.glob("exam_*.json"),
                   key=lambda p: int(p.stem.split("_")[1]))
    total, warnings = 0, []

    for path in files:
        exam = json.loads(path.read_text(encoding="utf-8"))
        n = exam["回数"]
        if args.only and n != args.only:
            continue

        targets = [it for it in exam["設問"] if it.get("photo")]
        if not targets:
            continue

        pdf_path = args.pdf_dir / f"{n}-問題.pdf"
        if not pdf_path.exists():
            warnings.append(f"第{n}回: PDFが無い ({pdf_path.name})")
            continue

        # ページごとに画像bboxを一度だけ取る
        with pdfplumber.open(pdf_path) as pdf:
            page_boxes = {}
            for it in targets:
                if it["photo"].get("bbox"):
                    continue
                p = it["photo"]["page"]
                if p not in page_boxes:
                    if p > len(pdf.pages):
                        warnings.append(f"第{n}回 問{it['no']}: {p}ページは存在しない")
                        continue
                    # 隣のページの画像が座標だけページ外（x<0 や幅を超える）で
                    # 混ざって出てくることがある（第22回）。誌面に写らないので外す。
                    page = pdf.pages[p - 1]
                    page_boxes[p] = reading_order([
                        {k: im[k] for k in ("x0", "top", "x1", "bottom")}
                        for im in page.images
                        if im["x1"] > 0 and im["x0"] < page.width
                    ])
                    for im in pdf.pages[p - 1].images:
                        w, h = im.get("srcsize", (0, 0))
                        if min(w, h) and min(w, h) < MIN_SRC_PIXELS:
                            warnings.append(
                                f"第{n}回 {p}ページ: 埋め込み画像が{w}x{h}pxしかなく "
                                f"判別が困難。元PDFの品質による")

        for it in targets:
            spec = it["photo"]
            p, want = spec["page"], spec["n"]
            if spec.get("bbox"):
                # ページ全体が1枚のスキャン画像のPDFは、埋め込み画像の
                # 位置から写真を割り出せないので座標をそのまま使う。
                boxes = [{"x0": b[0], "top": b[1], "x1": b[2], "bottom": b[3]}
                         for b in spec["bbox"]]
                if len(boxes) != want:
                    warnings.append(
                        f"第{n}回 問{it['no']}: bbox が{len(boxes)}個で n={want} と合わない")
            else:
                all_boxes = page_boxes.get(p, [])
                lo, hi = page_slice(spec)
                boxes = all_boxes[lo:hi]

            if not spec.get("bbox") and len(boxes) != want:
                warnings.append(
                    f"第{n}回 問{it['no']}: {p}ページの画像{len(all_boxes)}枚から"
                    f"{lo + 1}枚目以降を{want}枚使う指定だが{len(boxes)}枚しか無い "
                    f"— 対応がずれる可能性があります")
            if not boxes:
                continue

            names = photo_names(n, it["no"], spec)
            written = crop_page(pdf_path, p, boxes, names, args.out, args.dpi)
            total += len(written)
            print(f"第{n}回 問{it['no']}: {len(written)}枚 → "
                  f"{', '.join(w.name for w in written)}")

    print(f"\n書き出し: {total}枚 → {args.out}")
    if warnings:
        print("\n注意:")
        for w in warnings:
            print(f"  - {w}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
