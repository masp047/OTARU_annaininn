#!/usr/bin/env python3
"""抽出パイプライン検証用の疑似PDFを生成する（ネットワーク不要）。

配布元PDFのレイアウトは回によって揺れるため、代表的な3系統を作って
extract_exams.py の記法自動判定が効いているかを確かめる。

  第1回: 「問1.」見出し + 丸数字選択肢  / 解答は本文形式
  第2回: 「【問1】」見出し + （1）選択肢 / 解答は表形式
  第3回: 「第1問」見出し + カナ選択肢    / 解答は本文形式

使い方:
    python3 tests/make_fixtures.py tests/fixtures
"""

from __future__ import annotations

import sys
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.pdfgen import canvas
from reportlab.platypus import Table, TableStyle

pdfmetrics.registerFont(UnicodeCIDFont("HeiseiKakuGo-W5"))
FONT = "HeiseiKakuGo-W5"
CIRCLED = "①②③④⑤"
KATAKANA = "アイウエオ"

# (問題文, 選択肢, 正解の1始まり番号)
QUESTIONS: list[tuple[str, list[str], int]] = [
    ("小樽運河が完成したのは西暦何年か。", ["1913年", "1923年", "1933年", "1943年"], 3),
    ("「小樽オルゴール堂」がある地区はどこか。", ["色内", "堺町", "花園", "銭函"], 2),
    ("「鰊御殿」の説明として正しいものはどれか。",
     ["漁場主の住居兼漁夫の宿泊施設", "ニシンの加工工場", "漁業組合の事務所", "灯台の管理施設"], 1),
    ("小樽市の市の木に指定されているのはどれか。", ["ナナカマド", "シラカバ", "イチョウ", "ポプラ"], 1),
    ("旧日本郵船株式会社小樽支店の説明として正しいものはどれか。",
     ["国指定重要文化財", "国宝", "登録有形文化財", "史跡"], 1),
]

# 期待値: extract_exams.py がこの通りに復元できれば合格
EXPECTED = {n: [(i, q[2], q[1][q[2] - 1]) for i, q in enumerate(QUESTIONS, 1)] for n in (1, 2, 3)}


def _marker(style: str, j: int) -> str:
    return {"circled": CIRCLED[j], "paren": f"({j + 1})", "kana": f"{KATAKANA[j]}."}[style]


def _header(style: str, i: int) -> str:
    return {"maru": f"問{i}.", "bracket": f"【問{i}】", "dai": f"第{i}問"}[style]


def make_mondai(path: Path, n: int, header: str, choice: str) -> None:
    c = canvas.Canvas(str(path), pagesize=A4)
    c.setFont(FONT, 11)
    y = 800
    c.drawString(55, y, f"第{n}回 おたる案内人検定 問題")
    y -= 36
    for i, (body, choices, _) in enumerate(QUESTIONS, start=1):
        c.drawString(55, y, f"{_header(header, i)} {body}")
        y -= 20
        for j, ch in enumerate(choices):
            c.drawString(85, y, f"{_marker(choice, j)} {ch}")
            y -= 18
        y -= 10
        if y < 90:
            c.showPage()
            c.setFont(FONT, 11)
            y = 800
    c.save()


def make_kaitou_text(path: Path, n: int) -> None:
    """本文形式の解答（問1 ③ …）。"""
    c = canvas.Canvas(str(path), pagesize=A4)
    c.setFont(FONT, 11)
    y = 800
    c.drawString(55, y, f"第{n}回 おたる案内人検定 解答")
    y -= 36
    for i, (_, _, ans) in enumerate(QUESTIONS, start=1):
        c.drawString(55, y, f"問{i} {CIRCLED[ans - 1]}")
        y -= 22
    c.save()


def make_kaitou_table(path: Path, n: int) -> None:
    """表形式の解答（1行目に問番号、2行目に正解）。"""
    c = canvas.Canvas(str(path), pagesize=A4)
    c.setFont(FONT, 11)
    c.drawString(55, 800, f"第{n}回 おたる案内人検定 解答")

    data = [
        [f"問{i}" for i in range(1, len(QUESTIONS) + 1)],
        [CIRCLED[q[2] - 1] for q in QUESTIONS],
    ]
    table = Table(data, colWidths=[70] * len(QUESTIONS), rowHeights=[26, 26])
    table.setStyle(TableStyle([
        ("GRID", (0, 0), (-1, -1), 0.8, colors.black),
        ("FONTNAME", (0, 0), (-1, -1), FONT),
        ("FONTSIZE", (0, 0), (-1, -1), 11),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ]))
    table.wrapOn(c, 400, 200)
    table.drawOn(c, 55, 700)
    c.save()


def main() -> int:
    out = Path(sys.argv[1] if len(sys.argv) > 1 else Path(__file__).parent / "fixtures")
    out.mkdir(parents=True, exist_ok=True)

    make_mondai(out / "1_mondai.pdf", 1, "maru", "circled")
    make_kaitou_text(out / "1_kaitou.pdf", 1)

    make_mondai(out / "2_mondai.pdf", 2, "bracket", "paren")
    make_kaitou_table(out / "2_kaitou.pdf", 2)

    make_mondai(out / "3_mondai.pdf", 3, "dai", "kana")
    make_kaitou_text(out / "3_kaitou.pdf", 3)

    print(f"疑似PDFを生成: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
