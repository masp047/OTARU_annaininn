#!/usr/bin/env python3
"""設問の photo 指定から、切り抜き画像のファイル名を決める。

crop_photos.py（画像を書き出す側）と build_app.py / build_csv.py
（画像を参照する側）が同じ規則を使うように、ここに一本化する。
片方だけ直すと参照が切れるため。

photo 指定の形:

    {"page": 3, "n": 4}
        3ページ目の画像4枚を、読み順に選択肢1〜4として使う。
        → R01-Q012-1.png … -4.png（クリックできる選択肢として出る）

    {"page": 4, "n": 1, "role": "stem"}
        問題文側の参考写真。クリックの対象にはしない。
        → R04-Q015-stem.png

    {"page": 9, "n": 4, "order": [1, 3, 4, 2]}
        誌面の並びが選択肢番号と一致しない場合。読み順のi番目が
        order[i] 番の選択肢であることを示す（第3回 問24 など）。

    {"page": 9, "n": 2, "start": 2, "role": "stem", "labels": ["A", "B"]}
        1ページに写真つきの設問が複数ある場合、start でそのページの
        何枚目から使うかを指定する（1始まり）。labels は連番以外の
        見出しがついている場合に使う（第6回 問76 の A・B など）。
"""

from __future__ import annotations


def photo_names(exam_no: int, q_no: int, spec: dict) -> list[str]:
    """画像ファイル名（拡張子なし）を、誌面の読み順に並べて返す。"""
    base = f"R{exam_no:02d}-Q{q_no:03d}"
    n = spec["n"]
    labels = spec.get("labels")
    if labels:
        if len(labels) != n:
            raise ValueError(f"{base}: labels の数({len(labels)})がn({n})と違う")
        return [f"{base}-{s}" for s in labels]
    if spec.get("role", "choices") == "stem":
        return [f"{base}-stem"] if n == 1 else [f"{base}-stem{i+1}" for i in range(n)]
    order = spec.get("order") or list(range(1, n + 1))
    if len(order) != n:
        raise ValueError(f"{base}: order の数({len(order)})がn({n})と違う")
    return [f"{base}-{k}" for k in order]


def is_choice_photos(spec: dict) -> bool:
    """写真そのものが選択肢か（クリックさせるか）。"""
    return spec.get("role", "choices") == "choices"


def page_slice(spec: dict) -> tuple[int, int]:
    """ページ内の画像のうち何枚目から何枚目を使うか（0始まり, 終端排他）。"""
    start = spec.get("start", 1) - 1
    return start, start + spec["n"]
