#!/usr/bin/env python3
"""past_exams/ のPDFから設問を抽出し、NotebookLM用のCSVデータベースを作る。

problem PDF (`{n}_mondai.pdf`) から「問題番号・問題文・選択肢」を、
answer PDF (`{n}_kaitou.pdf`) から「正解」を取り出し、回数をキーに突き合わせる。

使い方:
    python3 scripts/extract_exams.py
    python3 scripts/extract_exams.py --pdf-dir past_exams --out otaru_kanko_past_exams.csv
    python3 scripts/extract_exams.py --only 3          # 第3回だけ試す（ルール調整用）

配布元PDFのレイアウトは回によって揺れるため、見出し・選択肢の記法は
複数の候補パターンを当てて「最も設問らしく並ぶもの」を自動採用する。
うまく取れない回は extraction_report.md に警告として残るので、
scripts/inspect_pdf.py で実レイアウトを確認して PATTERNS を調整すること。
"""

from __future__ import annotations

import argparse
import csv
import re
import sys
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path

try:
    import pdfplumber
except ImportError:  # pragma: no cover
    print("pdfplumber が必要です: pip install pdfplumber pypdf", file=sys.stderr)
    raise

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_PDF_DIR = ROOT / "past_exams"
DEFAULT_OUT = ROOT / "otaru_kanko_past_exams.csv"
DEFAULT_REPORT = ROOT / "extraction_report.md"

# ── 文字の正規化 ───────────────────────────────────────────────
# NFKC を素通しすると ①→1 のように選択肢記号が壊れるため、丸数字は先に退避する。
CIRCLED = "①②③④⑤⑥⑦⑧⑨⑩⑪⑫⑬⑭⑮⑯⑰⑱⑲⑳"
CIRCLED_TO_INDEX = {ch: i + 1 for i, ch in enumerate(CIRCLED)}
KATAKANA_CHOICES = "アイウエオカキク"
KATAKANA_TO_INDEX = {ch: i + 1 for i, ch in enumerate(KATAKANA_CHOICES)}


def normalize(text: str) -> str:
    """全角英数を半角に寄せつつ、丸数字と日本語の体裁は保持する。"""
    placeholders = {ch: f"{i:02d}" for i, ch in enumerate(CIRCLED)}
    for ch, ph in placeholders.items():
        text = text.replace(ch, ph)

    text = unicodedata.normalize("NFKC", text)

    for ch, ph in placeholders.items():
        text = text.replace(ph, ch)

    text = text.replace("　", " ")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text


def clean(text: str) -> str:
    """セル内に入れる最終形。改行と余分な空白を潰す。

    句点「。」は問題文の一部なので残す。先頭に残った区切り記号だけ落とす。
    """
    text = re.sub(r"\s+", " ", text).strip()
    return text.lstrip(".．、:：)）】 ").strip()


# ── パターン候補 ──────────────────────────────────────────────
# 設問見出しは2段階で探す。「問」を含む記法は設問以外に現れないので優先し、
# 裸の番号（n. や (n)）は選択肢記号と紛れるため、前者が空振りしたときだけ使う。
QUESTION_PATTERNS_PRIMARY: list[tuple[str, re.Pattern[str]]] = [
    ("【問n】", re.compile(r"【\s*問\s*(\d{1,3})\s*】")),
    ("問n", re.compile(r"問\s*(\d{1,3})\s*[\.．、:：]?\s*")),
    ("第n問", re.compile(r"第\s*(\d{1,3})\s*問")),
]

QUESTION_PATTERNS_FALLBACK: list[tuple[str, re.Pattern[str]]] = [
    ("n.", re.compile(r"(?m)^\s*(\d{1,3})\s*[\.．]\s+")),
    ("(n)", re.compile(r"(?m)^\s*[（(]\s*(\d{1,3})\s*[）)]\s*")),
]

CHOICE_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("丸数字", re.compile(rf"([{CIRCLED}])")),
    ("(n)", re.compile(r"[（(]\s*(\d)\s*[）)]")),
    ("n)", re.compile(r"(?m)(?:^|\s)(\d)\s*[）)]\s*")),
    ("n.", re.compile(r"(?m)(?:^|\s)(\d)\s*[\.．]\s+")),
    ("カナ", re.compile(rf"(?m)(?:^|\s)([{KATAKANA_CHOICES}])\s*[\.．、）)]\s*")),
]


def marker_to_index(token: str) -> int | None:
    if token in CIRCLED_TO_INDEX:
        return CIRCLED_TO_INDEX[token]
    if token in KATAKANA_TO_INDEX:
        return KATAKANA_TO_INDEX[token]
    if token.isdigit():
        return int(token)
    return None


def choice_score(numbers: list[int]) -> float:
    """選択肢記号らしさ。1,2,3,4 が問ごとに繰り返されるので番号の戻りは許容する。"""
    if len(numbers) < 2:
        return 0.0
    ascending = sum(1 for a, b in zip(numbers, numbers[1:]) if b == a + 1)
    starts_at_one = 1.0 if numbers[0] == 1 else 0.0
    return len(numbers) * (ascending / max(1, len(numbers) - 1)) + starts_at_one


def question_score(numbers: list[int]) -> float:
    """設問見出しらしさ。番号は文書全体で単調増加するはずなので、戻る候補は捨てる。

    これが無いと (1)(2)(3)(4) の選択肢記号が「設問が20問ある」と誤検出される。
    """
    if len(numbers) < 3:
        return 0.0
    increasing = sum(1 for a, b in zip(numbers, numbers[1:]) if b > a)
    if increasing / (len(numbers) - 1) < 0.9:
        return 0.0
    return len(numbers) + (1.0 if numbers[0] == 1 else 0.0)


# ── PDF → テキスト ────────────────────────────────────────────
def extract_text(pdf_path: Path) -> str:
    """pdfplumber で抽出し、空振りしたら pypdf に切り替える。"""
    pages: list[str] = []
    try:
        with pdfplumber.open(pdf_path) as pdf:
            for page in pdf.pages:
                pages.append(page.extract_text() or "")
    except Exception as exc:  # 壊れたPDFでも他の回の処理は続ける
        print(f"  ! pdfplumber 失敗 ({exc}) — pypdf で再試行", file=sys.stderr)
        pages = []

    text = "\n".join(pages).strip()
    if text:
        return normalize(text)

    try:
        from pypdf import PdfReader

        reader = PdfReader(str(pdf_path))
        text = "\n".join((p.extract_text() or "") for p in reader.pages)
    except Exception as exc:
        print(f"  ! pypdf も失敗: {exc}", file=sys.stderr)
        return ""
    return normalize(text.strip())


# ── 設問の解析 ────────────────────────────────────────────────
@dataclass
class Question:
    number: int
    body: str
    choices: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def pick_question_pattern(text: str) -> tuple[str, list[tuple[int, int, int]]]:
    """最も設問らしい見出しパターンを選び、(番号, 開始, 終了) の列を返す。"""
    for tier in (QUESTION_PATTERNS_PRIMARY, QUESTION_PATTERNS_FALLBACK):
        best_name, best_hits, best_score = "", [], 0.0
        for name, pattern in tier:
            hits = [(int(m.group(1)), m.start(), m.end()) for m in pattern.finditer(text)]
            score = question_score([h[0] for h in hits])
            if score > best_score:
                best_name, best_hits, best_score = name, hits, score
        if best_hits:
            return best_name, best_hits
    return "", []


def split_choices(block: str) -> tuple[str, list[str], str]:
    """設問ブロックを (問題文, 選択肢リスト, 使用した記法) に割る。"""
    best_name, best_marks, best_score = "", [], 0.0
    for name, pattern in CHOICE_PATTERNS:
        marks = []
        for m in pattern.finditer(block):
            idx = marker_to_index(m.group(1))
            if idx is not None:
                marks.append((idx, m.start(), m.end()))
        score = choice_score([m[0] for m in marks])
        if score > best_score:
            best_name, best_marks, best_score = name, marks, score

    if len(best_marks) < 2:
        return clean(block), [], ""

    body = clean(block[: best_marks[0][1]])
    choices = []
    for i, (_, _, end) in enumerate(best_marks):
        stop = best_marks[i + 1][1] if i + 1 < len(best_marks) else len(block)
        choices.append(clean(block[end:stop]))
    return body, choices, best_name


def parse_questions(text: str) -> tuple[list[Question], str]:
    pattern_name, hits = pick_question_pattern(text)
    if not hits:
        return [], ""

    questions: list[Question] = []
    seen: set[int] = set()
    for i, (number, _, header_end) in enumerate(hits):
        stop = hits[i + 1][1] if i + 1 < len(hits) else len(text)
        body, choices, _ = split_choices(text[header_end:stop])

        q = Question(number=number, body=body, choices=choices)
        if not body:
            q.warnings.append("問題文が空")
        if not choices:
            q.warnings.append("選択肢を検出できず")
        if number in seen:
            q.warnings.append("問題番号が重複")
        seen.add(number)
        questions.append(q)

    return questions, pattern_name


# ── 解答の解析 ────────────────────────────────────────────────
ANSWER_TOKEN = rf"[{CIRCLED}]|[1-9]|[{KATAKANA_CHOICES}]"
ANSWER_INLINE = re.compile(rf"問?\s*(\d{{1,3}})\s*[\.．:：、\s]\s*({ANSWER_TOKEN})(?![0-9])")


def parse_answers_from_tables(pdf_path: Path) -> dict[int, str]:
    """解答PDFが表組みの場合。縦横どちらの並びにも対応する。"""
    answers: dict[int, str] = {}
    try:
        with pdfplumber.open(pdf_path) as pdf:
            for page in pdf.pages:
                for table in page.extract_tables():
                    rows = [[normalize(c or "").strip() for c in row] for row in table]

                    # 横並び: 「問1 問2 …」の次行に解答が並ぶ
                    for r_i, row in enumerate(rows[:-1]):
                        nums = [re.fullmatch(r"問?\s*(\d{1,3})", c) for c in row]
                        if sum(1 for n in nums if n) >= 3:
                            for c_i, n in enumerate(nums):
                                if not n or c_i >= len(rows[r_i + 1]):
                                    continue
                                val = rows[r_i + 1][c_i]
                                if val and marker_to_index(val[0]) is not None:
                                    answers[int(n.group(1))] = val[0]

                    # 縦並び: 各行が (問番号, 解答) の対
                    for row in rows:
                        cells = [c for c in row if c]
                        if len(cells) < 2:
                            continue
                        m = re.fullmatch(r"問?\s*(\d{1,3})", cells[0])
                        if m and marker_to_index(cells[1][0]) is not None:
                            answers.setdefault(int(m.group(1)), cells[1][0])
    except Exception as exc:
        print(f"  ! 解答表の読み取り失敗: {exc}", file=sys.stderr)
    return answers


def parse_answers(pdf_path: Path) -> tuple[dict[int, str], str]:
    answers = parse_answers_from_tables(pdf_path)
    if answers:
        return answers, "表"

    text = extract_text(pdf_path)
    inline = {
        int(m.group(1)): m.group(2)
        for m in ANSWER_INLINE.finditer(text)
    }
    return inline, "本文" if inline else ""


# ── 組み立て ──────────────────────────────────────────────────
def render_full_text(exam: int, q: Question, answer_label: str, answer_body: str) -> str:
    """NotebookLM がそのまま読める、1問=1かたまりの本文。"""
    lines = [f"【第{exam}回 おたる案内人検定 問{q.number}】", q.body]
    for i, choice in enumerate(q.choices, start=1):
        marker = CIRCLED[i - 1] if i <= len(CIRCLED) else str(i)
        lines.append(f"{marker} {choice}")
    if answer_label:
        lines.append(f"正解: {answer_label}{(' ' + answer_body) if answer_body else ''}")
    return "\n".join(line for line in lines if line)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pdf-dir", type=Path, default=DEFAULT_PDF_DIR)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--only", type=int, help="この回だけ処理する（調整用）")
    parser.add_argument("--start", type=int, default=1)
    parser.add_argument("--end", type=int, default=23)
    args = parser.parse_args()

    if not args.pdf_dir.is_dir():
        print(f"PDFディレクトリがありません: {args.pdf_dir}", file=sys.stderr)
        print("先に scripts/download_exams.py を実行してください。", file=sys.stderr)
        return 1

    exams = [args.only] if args.only else range(args.start, args.end + 1)
    rows: list[dict[str, str]] = []
    report: list[str] = []
    max_choices = 0

    for n in exams:
        mondai = args.pdf_dir / f"{n}_mondai.pdf"
        kaitou = args.pdf_dir / f"{n}_kaitou.pdf"

        if not mondai.exists():
            report.append(f"- 第{n}回: 問題PDFが無いためスキップ (`{mondai.name}`)")
            continue

        print(f"解析中: 第{n}回")
        questions, q_pattern = parse_questions(extract_text(mondai))
        if not questions:
            report.append(f"- 第{n}回: **設問を1問も抽出できず** — `inspect_pdf.py {mondai}` で確認")
            continue

        if kaitou.exists():
            answers, a_source = parse_answers(kaitou)
        else:
            answers, a_source = {}, ""
            report.append(f"- 第{n}回: 解答PDFが無く正解列は空 (`{kaitou.name}`)")

        matched = 0
        for q in questions:
            label = answers.get(q.number, "")
            idx = marker_to_index(label) if label else None
            body = ""
            if idx and 1 <= idx <= len(q.choices):
                body = q.choices[idx - 1]
                matched += 1
            elif label:
                q.warnings.append("正解記号に対応する選択肢が無い")

            max_choices = max(max_choices, len(q.choices))
            row = {
                "問題ID": f"R{n:02d}-Q{q.number:03d}",
                "回数": str(n),
                "検定回": f"第{n}回",
                "問題番号": str(q.number),
                "問題文": q.body,
                "選択肢数": str(len(q.choices)),
                "正解番号": str(idx) if idx else "",
                "正解記号": label,
                "正解本文": body,
                "出典PDF": mondai.name,
                "注意": " / ".join(q.warnings),
                "_choices": q.choices,
                "全文": render_full_text(n, q, label, body),
            }
            rows.append(row)

        print(f"  {len(questions)}問 / 正解紐付け {matched}問 "
              f"(設問記法: {q_pattern or '不明'}, 解答: {a_source or 'なし'})")
        if matched < len(questions):
            report.append(
                f"- 第{n}回: {len(questions)}問中 {len(questions) - matched}問で正解を紐付けできず"
            )

    if not rows:
        print("\n抽出できた設問がありません。PDFを取得済みか確認してください。", file=sys.stderr)
        return 1

    # 選択肢を列に展開
    choice_cols = [f"選択肢{i}" for i in range(1, max_choices + 1)]
    fieldnames = [
        "問題ID", "回数", "検定回", "問題番号", "問題文",
        *choice_cols, "選択肢数", "正解番号", "正解記号", "正解本文",
        "出典PDF", "注意", "全文",
    ]

    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("w", encoding="utf-8-sig", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            choices = row.pop("_choices")
            for i, col in enumerate(choice_cols):
                row[col] = choices[i] if i < len(choices) else ""
            writer.writerow(row)

    exams_done = sorted({int(r["回数"]) for r in rows})
    flagged = sum(1 for r in rows if r["注意"])
    print(f"\n書き出し: {args.out}")
    print(f"  {len(rows)}問 / {len(exams_done)}回分 (第{exams_done[0]}回〜第{exams_done[-1]}回)")
    print(f"  要確認: {flagged}問")

    args.report.write_text(
        "# 抽出レポート\n\n"
        f"- 出力: `{args.out.name}`\n"
        f"- 設問数: {len(rows)}\n"
        f"- 対象回: {', '.join(f'第{n}回' for n in exams_done)}\n"
        f"- 注意フラグ付き: {flagged}問\n\n"
        "## 警告\n\n" + ("\n".join(report) if report else "- なし\n"),
        encoding="utf-8",
    )
    print(f"  レポート: {args.report}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
