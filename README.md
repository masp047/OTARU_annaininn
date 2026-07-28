# おたる案内人検定 過去問データベース

第1回〜第23回の過去問PDFを取得し、NotebookLMに読み込ませられるCSV
（`otaru_kanko_past_exams.csv`）を生成するパイプライン。

## ⚠️ 現状：PDF未取得

このリポジトリにはまだCSVの実データが入っていません。**配布元
`www.otaru-kd.com` が実行環境の外部通信ポリシーで遮断されている**ためです
（CONNECT に対してプロキシが 403 を返す）。ネットワークが通る環境で
`./run_all.sh` を実行すれば、そのままCSVまで生成されます。

解消するには次のいずれかを:

1. 手元のPCなど、当該サイトにアクセスできる環境で `./run_all.sh` を実行する
2. Claude Code の環境設定で `www.otaru-kd.com` を許可ドメインに追加し、再実行する
3. PDFを手動で `past_exams/` に置き、`python3 scripts/extract_exams.py` だけ実行する

抽出処理そのものは疑似PDFによるテストで検証済みです（後述）。

## 使い方

```bash
./run_all.sh
```

個別に実行する場合:

```bash
pip install -r requirements.txt

# 1. PDF取得 → past_exams/{1..23}_mondai.pdf, {1..23}_kaitou.pdf
python3 scripts/download_exams.py

# 2-3. 抽出 → otaru_kanko_past_exams.csv
python3 scripts/extract_exams.py
```

## 出力CSVの構成

`otaru_kanko_past_exams.csv`（UTF-8 BOM付き / Excel・NotebookLM双方で文字化けしない）

| 列 | 内容 |
| --- | --- |
| `問題ID` | `R03-Q012` 形式の一意キー |
| `回数` / `検定回` | `3` / `第3回` |
| `問題番号` | 回の中での設問番号 |
| `問題文` | 設問本文 |
| `選択肢1`〜`選択肢N` | 選択肢を1つずつ列に展開 |
| `選択肢数` | 検出した選択肢の数 |
| `正解番号` | 正解の選択肢番号（1始まり） |
| `正解記号` | 解答PDF上の表記（`③` など） |
| `正解本文` | 正解選択肢のテキスト |
| `出典PDF` | 抽出元ファイル名 |
| `注意` | 抽出時の警告（空なら問題なし） |
| `全文` | 1問を1かたまりに整形したテキスト |

`全文` 列は NotebookLM 向けです。設問・選択肢・正解が1セルに収まっているため、
検索や引用の際に文脈が途切れません。

## PDFレイアウトの揺れへの対応

配布元PDFは回によって記法が異なります。`extract_exams.py` は候補パターンを
すべて当てて、最も設問らしく並ぶものを自動採用します。

- 設問見出し: `【問1】` / `問1.` / `第1問` /（フォールバック）`1.` `(1)`
- 選択肢: `①②③④` / `(1)(2)(3)(4)` / `1)` / `1.` / `ア イ ウ エ`
- 解答: 表組み（縦・横どちらの並びも）と本文形式の両方

設問見出しの番号は文書全体で単調増加するはずだ、という条件を課しています。
これが無いと `(1)(2)(3)(4)` の選択肢記号を設問見出しと取り違えます。

### うまく抽出できない回があったら

実行後に `extraction_report.md` が生成され、設問を取れなかった回や正解を
紐付けられなかった設問が列挙されます。該当回のレイアウトを確認するには:

```bash
python3 scripts/inspect_pdf.py past_exams/7_mondai.pdf --pages 1-2
python3 scripts/inspect_pdf.py past_exams/7_kaitou.pdf --tables
```

見えた実レイアウトに合わせて `extract_exams.py` の `QUESTION_PATTERNS_*` /
`CHOICE_PATTERNS` に候補を足し、その回だけ再実行して確認します:

```bash
python3 scripts/extract_exams.py --only 7
```

## テスト

ネットワーク不要。3系統のレイアウト（丸数字・括弧数字・カナ、解答は本文/表）の
疑似PDFを生成し、設問・選択肢・正解が復元できることを確認します。

```bash
python3 tests/test_extract.py
```

## ファイル構成

```
scripts/download_exams.py   PDF一括ダウンロード（リトライ・再開対応）
scripts/extract_exams.py    PDF解析とCSV生成
scripts/inspect_pdf.py      レイアウト確認用の診断ツール
tests/make_fixtures.py      検証用の疑似PDF生成
tests/test_extract.py       スモークテスト
run_all.sh                  一括実行
```

## 注意

`past_exams/` のPDFは配布元の著作物のため `.gitignore` で除外しています。
生成したCSVを再配布する場合は配布元の利用条件を確認してください。
