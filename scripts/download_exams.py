#!/usr/bin/env python3
"""おたる案内人検定の過去問PDF（第1回〜第23回）を past_exams/ に一括ダウンロードする。

取得元:
    https://www.otaru-kd.com/assets/pdf/past-coolection/{n}_mondai.pdf   問題
    https://www.otaru-kd.com/assets/pdf/past-coolection/{n}_kaitou.pdf   解答

使い方:
    python3 scripts/download_exams.py                 # 1〜23回を取得
    python3 scripts/download_exams.py --start 5 --end 9
    python3 scripts/download_exams.py --force         # 既存ファイルも再取得
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import requests

BASE_URL = "https://www.otaru-kd.com/assets/pdf/past-coolection"
KINDS = ("mondai", "kaitou")  # 問題 / 解答
DEFAULT_OUT = Path(__file__).resolve().parent.parent / "past_exams"

# サイトによっては素の User-Agent を弾くため、ブラウザ相当を名乗る。
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/126.0 Safari/537.36"
    ),
    "Accept": "application/pdf,*/*",
}

MAX_RETRIES = 4
BACKOFF_SECONDS = (2, 4, 8, 16)


def looks_like_pdf(body: bytes) -> bool:
    """PDFではなくHTMLのエラーページを掴んでいないか検査する。"""
    return body[:5] == b"%PDF-"


def fetch(url: str, session: requests.Session) -> bytes | None:
    """1URLを取得する。404は None、ネットワーク障害はバックオフして再試行。"""
    for attempt in range(MAX_RETRIES):
        try:
            resp = session.get(url, headers=HEADERS, timeout=60)
        except requests.RequestException as exc:
            if attempt == MAX_RETRIES - 1:
                print(f"  ! 通信エラーで断念: {exc}", file=sys.stderr)
                return None
            wait = BACKOFF_SECONDS[attempt]
            print(f"  . 通信エラー ({exc.__class__.__name__})、{wait}秒後に再試行")
            time.sleep(wait)
            continue

        if resp.status_code == 404:
            return None
        if resp.status_code >= 500 and attempt < MAX_RETRIES - 1:
            wait = BACKOFF_SECONDS[attempt]
            print(f"  . HTTP {resp.status_code}、{wait}秒後に再試行")
            time.sleep(wait)
            continue
        if resp.status_code != 200:
            print(f"  ! HTTP {resp.status_code}: {url}", file=sys.stderr)
            return None

        if not looks_like_pdf(resp.content):
            print(f"  ! PDFではない応答（HTMLエラーページ？）: {url}", file=sys.stderr)
            return None
        return resp.content
    return None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--start", type=int, default=1, help="開始回 (既定: 1)")
    parser.add_argument("--end", type=int, default=23, help="終了回 (既定: 23)")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT, help="保存先ディレクトリ")
    parser.add_argument("--force", action="store_true", help="既存ファイルも上書き取得")
    args = parser.parse_args()

    args.out.mkdir(parents=True, exist_ok=True)

    saved, skipped, missing = 0, 0, []
    with requests.Session() as session:
        for n in range(args.start, args.end + 1):
            for kind in KINDS:
                name = f"{n}_{kind}.pdf"
                dest = args.out / name

                if dest.exists() and dest.stat().st_size > 0 and not args.force:
                    skipped += 1
                    continue

                url = f"{BASE_URL}/{name}"
                print(f"取得中: {name}")
                body = fetch(url, session)
                if body is None:
                    missing.append(name)
                    print(f"  - 取得できず: {name}")
                    continue

                dest.write_bytes(body)
                saved += 1
                print(f"  + 保存 {dest} ({len(body):,} bytes)")

    print(f"\n完了: 保存 {saved} / スキップ(既存) {skipped} / 未取得 {len(missing)}")
    if missing:
        print("未取得のファイル:")
        for name in missing:
            print(f"  - {name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
