#!/usr/bin/env python3
"""疑似PDFを使った抽出パイプラインのスモークテスト（ネットワーク不要）。

    python3 tests/test_extract.py

3系統のレイアウトそれぞれで、設問・選択肢・正解が復元できることを確認する。
"""

from __future__ import annotations

import csv
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tests"))

from make_fixtures import EXPECTED, QUESTIONS, main as build_fixtures  # noqa: E402

failures: list[str] = []


def check(condition: bool, message: str) -> None:
    if condition:
        print(f"  ok   {message}")
    else:
        print(f"  FAIL {message}")
        failures.append(message)


def run() -> int:
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        sys.argv = ["make_fixtures", str(tmp_path / "pdfs")]
        build_fixtures()

        csv_path = tmp_path / "out.csv"
        proc = subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "extract_exams.py"),
             "--pdf-dir", str(tmp_path / "pdfs"),
             "--out", str(csv_path),
             "--report", str(tmp_path / "report.md"),
             "--start", "1", "--end", "3"],
            capture_output=True, text=True,
        )
        print(proc.stdout)
        if proc.returncode != 0:
            print(proc.stderr, file=sys.stderr)
            return 1

        rows = list(csv.DictReader(csv_path.open(encoding="utf-8-sig")))

        print("\n検証:")
        check(len(rows) == 3 * len(QUESTIONS),
              f"設問数が {3 * len(QUESTIONS)} 件 (実際 {len(rows)})")

        by_exam: dict[int, dict[int, dict[str, str]]] = {}
        for r in rows:
            by_exam.setdefault(int(r["回数"]), {})[int(r["問題番号"])] = r

        for exam, expected in EXPECTED.items():
            check(exam in by_exam, f"第{exam}回が出力に含まれる")
            if exam not in by_exam:
                continue
            for qno, ans_idx, ans_body in expected:
                row = by_exam[exam].get(qno)
                if row is None:
                    check(False, f"第{exam}回 問{qno} が存在する")
                    continue
                check(row["正解番号"] == str(ans_idx),
                      f"第{exam}回 問{qno} の正解番号が {ans_idx} (実際 {row['正解番号']!r})")
                check(row["正解本文"] == ans_body,
                      f"第{exam}回 問{qno} の正解本文が {ans_body!r} (実際 {row['正解本文']!r})")
                check(row["選択肢数"] == "4",
                      f"第{exam}回 問{qno} の選択肢が4つ (実際 {row['選択肢数']})")

        # 句点が問題文から欠落していないこと
        first = by_exam.get(1, {}).get(1, {})
        check(first.get("問題文", "").endswith("。"),
              f"問題文の句点が保持される (実際 {first.get('問題文')!r})")

    print()
    if failures:
        print(f"NG: {len(failures)}件失敗")
        return 1
    print("すべて成功")
    return 0


if __name__ == "__main__":
    raise SystemExit(run())
