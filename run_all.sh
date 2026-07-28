#!/usr/bin/env bash
# おたる案内人検定 過去問DB構築を一括実行する。
#   ./run_all.sh
set -euo pipefail

cd "$(dirname "$0")"

echo "== 1/3 依存パッケージ =="
python3 -m pip install --quiet --requirement requirements.txt

echo "== 2/3 PDFダウンロード (第1回〜第23回) =="
python3 scripts/download_exams.py

echo "== 3/3 抽出とCSV生成 =="
python3 scripts/extract_exams.py

echo
echo "完了: otaru_kanko_past_exams.csv"
echo "抽出の警告は extraction_report.md を確認してください。"
