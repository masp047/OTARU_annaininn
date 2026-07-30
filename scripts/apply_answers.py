#!/usr/bin/env python3
"""data/answers/answers_N.json を正として data/exam_NN.json の a を上書きする。

問題文の書き起こしは誌面画像を目で読んで行うため、正解を読み違える余地が
ある。解答PDFはテキスト層が生きていて座標抽出できる（extract_answers.py）
ので、そちらを常に真とし、こちらで機械的に上書きする。

枝番（sub）つきの設問は、解答が「A ２ B １」「Ａ ３ Ｂ ４ Ｃ ２」のように
1行にまとまっているので、該当する記号の部分だけを取り出す。

書き起こし時に入れた a と食い違ったものは「相違」として表示する。
これが自分の読み違いの検出になる。

使い方:
    python3 scripts/apply_answers.py            # 全回
    python3 scripts/apply_answers.py --only 4
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DATA = ROOT / "data"

# 「A ２ B １」「Ａ ３ Ｂ ４ Ｃ ２ Ｄ １ Ｅ ２」を分解する
SUB_TOKEN = re.compile(r"([A-EＡ-Ｅ])\s*[：:.．]?\s*([^A-EＡ-Ｅ]*)")
# 「＊Ａ、Ｂ逆も正解」のような注記。ここにも記号が出るので、切り離してから分解する
NOTE_TAIL = re.compile(r"[＊*※].*$", re.S)


ZEN_DIGITS = str.maketrans("０１２３４５６７８９", "0123456789")
# 解答用紙の折り返しで入った空白。両側とも非ASCIIなら改行由来とみなして詰める
# （「小樽グランベル ホテル」→「小樽グランベルホテル」）。
# 「OMO5小樽by 星野リゾート」のようにASCIIに接する空白は語の区切りなので残す。
WRAP_SPACE = re.compile(r"(?<=[^\x00-\x7f])[ 　]+(?=[^\x00-\x7f])")


def normalize_answer(raw: str) -> str:
    """全角数字を半角にし、折り返しの空白を詰める。

    選択肢番号は「４」のまま持つとアプリ側の比較（1〜4の半角）と一致せず、
    すべて不正解になる。数字は常に半角に寄せる。
    """
    # 空白を詰めるのが先。「１８６９年」を半角にしてから判定すると
    # 「明治２年または １８６９年」の空白がASCII隣接と見なされて残ってしまう。
    return WRAP_SPACE.sub("", raw).translate(ZEN_DIGITS).strip()


def normalize_sub(label: str) -> str:
    """Ａ（全角）と A（半角）を同じものとして扱う。"""
    return label.translate(str.maketrans("ＡＢＣＤＥ", "ABCDE")).strip().upper()


def split_sub_answers(raw: str) -> dict[str, str]:
    """「A ２ B １」→ {"A": "２", "B": "１"}"""
    out: dict[str, str] = {}
    for label, value in SUB_TOKEN.findall(NOTE_TAIL.sub("", raw)):
        value = value.strip(" 　・、,")
        # 同じ記号が二度出たら先に出たほうを採る
        if value and normalize_sub(label) not in out:
            out[normalize_sub(label)] = value
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, default=DEFAULT_DATA)
    parser.add_argument("--only", type=int, help="この回だけ処理する")
    args = parser.parse_args()

    files = sorted(args.data_dir.glob("exam_*.json"),
                   key=lambda p: int(p.stem.split("_")[1]))
    for path in files:
        exam = json.loads(path.read_text(encoding="utf-8"))
        n = exam["回数"]
        if args.only and n != args.only:
            continue

        key_path = args.data_dir / "answers" / f"answers_{n}.json"
        if not key_path.exists():
            print(f"第{n}回: 解答ファイルが無い ({key_path.name})")
            continue
        key = json.loads(key_path.read_text(encoding="utf-8"))

        diffs, missing = [], []
        for it in exam["設問"]:
            raw = key.get(str(it["no"]))
            if raw is None:
                missing.append(it["no"])
                continue
            want = raw
            if it.get("sub"):
                parts = split_sub_answers(raw)
                got = parts.get(normalize_sub(it["sub"]))
                if got is None:
                    missing.append(f"{it['no']}{it['sub']}")
                    continue
                want = got
            want = normalize_answer(want)
            before = it.get("a", "")
            if before and before != want:
                diffs.append((it["no"], it.get("sub", ""), before, want))
            it["a"] = want

        path.write_text(
            json.dumps(exam, ensure_ascii=False, indent=1) + "\n",
            encoding="utf-8")
        print(f"第{n}回: {len(exam['設問'])}件に正解を反映")
        for no, sub, before, want in diffs:
            print(f"  相違 問{no}{sub}: 「{before}」→ 「{want}」（解答PDF優先）")
        if missing:
            print(f"  解答なし: {missing}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
