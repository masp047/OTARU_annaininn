#!/usr/bin/env python3
"""data/exam_*.json を結合して NotebookLM 用のCSVを生成する。

回ごとに1つのJSONを作り、このスクリプトで束ねる構成にしている。
23回分を一度に処理する必要がなく、1回分ずつ追加・修正できる。

使い方:
    python3 scripts/build_csv.py
    python3 scripts/build_csv.py --out otaru_kanko_past_exams.csv
"""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

from photo_spec import is_choice_photos, photo_names

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DATA = ROOT / "data"
DEFAULT_OUT = ROOT / "otaru_kanko_past_exams.csv"

CIRCLED = "①②③④⑤⑥⑦⑧⑨⑩"

FIELDS = [
    "問題ID", "回数", "検定回", "実施日", "級", "問題番号", "枝番",
    "形式", "問題文", "選択肢1", "選択肢2", "選択肢3", "選択肢4",
    "正解", "正解本文", "画像", "注意", "出典", "全文",
]


def marker(i: int) -> str:
    return CIRCLED[i] if i < len(CIRCLED) else str(i + 1)


def build_rows(exam: dict) -> list[dict]:
    n = exam["回数"]
    rows = []
    for item in exam["設問"]:
        no = item["no"]
        sub = item.get("sub", "")
        choices = item.get("c", [])
        answer = str(item.get("a", ""))

        # 選択式なら正解番号→選択肢本文を引く
        answer_body = ""
        if choices and answer.isdigit():
            idx = int(answer)
            if 1 <= idx <= len(choices):
                answer_body = choices[idx - 1]

        # 表示用の正解表記（選択式は丸数字、記述式はそのまま）
        if choices and answer.isdigit():
            answer_label = marker(int(answer) - 1)
        else:
            answer_label = answer

        qid = f"R{n:02d}-Q{no:03d}" + (f"-{sub}" if sub else "")

        # 写真つき設問は切り抜き画像のファイル名を記録する。
        # 写真は文字で描写しても伝わらないため、画像そのものを参照させる。
        photo = item.get("photo")
        images = ""
        if photo:
            images = " ".join(
                f"images/{name}.png" for name in photo_names(n, no, photo))

        lines = [f"【第{n}回 おたる案内人検定 問{no}{sub}】", item["q"]]
        for i, ch in enumerate(choices):
            lines.append(f"{marker(i)} {ch}")
        if photo:
            lines.append(
                "（選択肢は写真です。images/ の画像を参照）"
                if is_choice_photos(photo)
                else "（設問に写真がつきます。images/ の画像を参照）")
        if answer_label:
            lines.append(
                f"正解: {answer_label}" + (f" {answer_body}" if answer_body else "")
            )
        else:
            lines.append("正解: （未確定）")

        row = {
            "問題ID": qid,
            "回数": n,
            "検定回": f"第{n}回",
            "実施日": exam.get("実施日", ""),
            "級": exam.get("級", ""),
            "問題番号": no,
            "枝番": sub,
            "形式": item.get("type", ""),
            "問題文": item["q"],
            "正解": answer_label,
            "正解本文": answer_body,
            "画像": images,
            "注意": item.get("note", ""),
            "出典": exam.get("出典", ""),
            "全文": "\n".join(lines),
        }
        for i in range(4):
            row[f"選択肢{i + 1}"] = choices[i] if i < len(choices) else ""
        rows.append(row)
    return rows


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, default=DEFAULT_DATA)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args()

    files = sorted(
        args.data_dir.glob("exam_*.json"),
        key=lambda p: int(p.stem.split("_")[1]),
    )
    if not files:
        print(f"データがありません: {args.data_dir}/exam_*.json")
        return 1

    rows: list[dict] = []
    for path in files:
        exam = json.loads(path.read_text(encoding="utf-8"))
        built = build_rows(exam)
        rows.extend(built)
        print(f"第{exam['回数']:>2}回: {len(built)}行")

    with args.out.open("w", encoding="utf-8-sig", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)

    flagged = sum(1 for r in rows if r["注意"])
    unresolved = sum(1 for r in rows if not r["正解"])
    exams = sorted({r["回数"] for r in rows})

    print(f"\n書き出し: {args.out}")
    print(f"  {len(rows)}行 / {len(exams)}回分")
    kinds: dict[str, int] = {}
    for r in rows:
        kinds[r["形式"] or "(不明)"] = kinds.get(r["形式"] or "(不明)", 0) + 1
    print("  形式内訳: " + " / ".join(f"{k} {v}" for k, v in sorted(kinds.items())))
    print(f"  注意フラグ: {flagged}行 / 正解未確定: {unresolved}行")
    print(f"  未収録の回: {[i for i in range(1, 24) if i not in exams]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
