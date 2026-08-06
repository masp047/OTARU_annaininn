#!/usr/bin/env python3
"""設問ごとに、公式ガイドブックの該当ページを探す。

過去問を解いたあとに「これはどこに書いてあるのか」を引けるようにする。
検定はガイドブックから出題されるので、設問の言葉はたいてい誌面のどこかに
そのまま載っている。

やり方は素朴な検索と同じで、設問に出てくる語のうち**珍しい語ほど重く**
数える（IDF）。「小樽」は全ページに出るので手がかりにならないが、
「オタルナイ」や「北前船」は数ページにしか出ないので効く。

    第7回 問1「鰊漁の需要は肥料」→ p16（鰊・歴史）
    第7回 問2「山田兵蔵が名主となった年」→ p10（オタルナイ場所）

誌面のテキストはOCRなので取りこぼしがある。点が低いものは無理に結び
つけず、リンクを作らない。当てにならないものを出すより、出さない方が
勉強の邪魔にならない。

出力: data/guidebook_links.json
    {"R07-Q001": {"page": 16, "score": 8.4, "terms": ["鰊漁", "肥料"]}, ...}

使い方:
    python3 scripts/link_guidebook.py
    python3 scripts/link_guidebook.py --only 7 --show 20
"""

from __future__ import annotations

import argparse
import json
import math
import re
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DATA = ROOT / "data"

HIRAGANA = re.compile(r"[ぁ-ゖ]")
# 手がかりにする語。漢字の連なりとカタカナの連なり、それと「明治28年」のような年
TERM = re.compile(r"[一-龥々]{2,}|[ァ-ヶー]{2,}|[一-龥]{1,2}[0-9]{1,2}年")

# どのページにも出てきて区別に使えない語。数えても点差がつかないだけだが、
# 短い設問だとこれだけで結びついてしまうので落とす。
STOP = {"小樽", "北海道", "現在", "明治", "大正", "昭和", "平成", "当時",
        "日本", "以下", "次の", "何で", "上記", "写真", "場合", "こと",
        "もの", "ため", "など", "また", "その", "この"}

# これ未満は結びつけない。設問の語が2つ3つしか当たらないときは
# たまたま同じ言葉が出ただけのことが多い。
MIN_SCORE = 8.0

# 結びつきには「その語が載っているページが数えるほどしかない」語が要る。
# 「需要」は8ページ、「輸送」は11ページに出るので、これだけで結びつけると
# 話題が近いだけの別のページに当たる。「山田兵蔵」は2ページ、「ペリー」は
# 1ページで、こういう語が当たったときだけ誌面を指せる。
MAX_PAGES_FOR_KEY = 6

# 正解に出てくる語を何倍に数えるか。3倍にすると「松前神楽はどれか」が
# 問題文の「無形文化財」に引かれず、松前神楽の載っているページを指す。
ANS_WEIGHT = 3.0


def kana_ratio(text: str) -> float:
    t = re.sub(r"\s", "", text)
    return len(HIRAGANA.findall(t)) / len(t) if t else 0.0


def terms_of(text: str) -> set[str]:
    return {t for t in TERM.findall(text) if t not in STOP and len(t) >= 2}


def load_pages(data_dir: Path) -> list[dict]:
    """検索に使えるページだけを、誌面ページ番号つきで返す。"""
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from build_guidebook import fix_page_numbers

    raw = json.loads((data_dir / "guidebook_pages.json").read_text(encoding="utf-8"))
    rows = [{"seq": r["seq"], "page": r["page"], "text": r.get("text", "")}
            for r in raw]
    nombres = json.loads((data_dir / "guidebook_nombres.json").read_text(encoding="utf-8"))
    fix_page_numbers(rows, {r["seq"]: r["page"] for r in nombres["番号"]})

    out = []
    for r in rows:
        # 図版が主のページやOCRが崩れたページは当てにならない
        if r["page"] is None or kana_ratio(r["text"]) < 0.15:
            continue
        flat = re.sub(r"\s+", "", r["text"])
        out.append({"page": r["page"], "flat": flat, "terms": terms_of(flat)})
    return out


def answer_text(q: dict) -> str:
    """正解の本文。選択式なら正解の選択肢、記述式なら模範解答そのもの。"""
    choices = q.get("c") or []
    a = str(q.get("a", ""))
    if a.isdigit() and 1 <= int(a) <= len(choices):
        return choices[int(a) - 1]
    return a


def question_terms(q: dict) -> tuple[set[str], set[str]]:
    """設問の語と、そのうち正解に出てくる語を返す。

    正解の語こそ誌面に書いてある。「松前神楽はどれか」という設問では、
    問題文の「無形文化財」より正解の「松前神楽」の方が誌面を強く指す。
    誤りの選択肢も手がかりにはなるので落とさないが、正解の語は重く数える。
    """
    body = q.get("q", "") + "".join(q.get("c") or [])
    ans = answer_text(q)
    return terms_of(body + ans), terms_of(ans)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, default=DEFAULT_DATA)
    parser.add_argument("--min-score", type=float, default=MIN_SCORE)
    parser.add_argument("--max-pages", type=int, default=MAX_PAGES_FOR_KEY,
                        help="手がかりの語が載っていてよいページ数の上限")
    parser.add_argument("--only", type=int, help="この回だけ調べる")
    parser.add_argument("--show", type=int, default=0, help="結びつけた結果を並べて見る")
    args = parser.parse_args()

    pages = load_pages(args.data_dir)
    if not pages:
        print("ガイドブックのページが読めない")
        return 1

    # 珍しい語ほど重く数える
    df = Counter()
    for p in pages:
        df.update(p["terms"])
    n = len(pages)
    idf = {t: math.log(n / c) for t, c in df.items()}

    links, checked, hit = {}, 0, 0
    for path in sorted(args.data_dir.glob("exam_*.json")):
        doc = json.loads(path.read_text(encoding="utf-8"))
        exam = doc["回数"]
        if args.only and exam != args.only:
            continue
        for q in doc["設問"]:
            qid = f"R{exam:02d}-Q{q['no']:03d}" + (f"-{q['sub']}" if q.get("sub") else "")
            checked += 1
            want, ans = question_terms(q)
            if not want:
                continue

            # 正解の言葉そのものが載っているページがあれば、そこが答えの
            # 書いてある場所。候補をそこだけに絞る。無ければ話題の近い
            # ページを探すしかない。
            solid = {t for t in ans if len(t) >= 3}
            here = [p for p in pages if any(t in p["flat"] for t in solid)] if solid else []
            found = bool(here)
            hunt = here or pages

            best, best_score, best_shared = None, 0.0, set()
            for p in hunt:
                shared = want & p["terms"]
                if not shared:
                    continue
                # 語の長さも効かせる。「北前船」は「漁業」より強い手がかり。
                # 正解に出てくる語は、そこが答えの書いてあるページなので重く。
                score = sum(idf[t] * min(len(t), 5) / 2 * (ANS_WEIGHT if t in ans else 1)
                            for t in shared)
                if score > best_score:
                    best, best_score, best_shared = p["page"], score, shared
            if best is None and found:
                # 語は載っているが設問と共通の語が拾えなかった。載っている方を採る
                best, best_shared = here[0]["page"], solid & here[0]["terms"]
            if best is None:
                continue
            if not found:
                # 話題を頼りにするときだけ、当てにならないものを落とす
                if best_score < args.min_score:
                    continue
                if df[min(best_shared, key=lambda t: df[t])] > args.max_pages:
                    continue               # 珍しい語が当たっていない
            links[qid] = {
                "page": best, "score": round(best_score, 1),
                "how": "答え" if found else "話題",
                "terms": sorted(best_shared or solid, key=lambda t: df.get(t, 0))[:4]}
            hit += 1

    out = args.data_dir / "guidebook_links.json"
    out.write_text(json.dumps(links, ensure_ascii=False, indent=1) + "\n",
                   encoding="utf-8")
    print(f"書き出し: {out}")
    print(f"  設問 {checked}問 / 誌面と結びついた {hit}問 ({hit / max(checked,1):.0%})")
    print(f"  探した誌面 {len(pages)}ページ / 手がかりにした語 {len(idf):,}語")

    if args.show:
        print()
        for qid, v in list(links.items())[:args.show]:
            print(f"  {qid} → p{v['page']:<4} {v['score']:5.1f}  {'・'.join(v['terms'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
