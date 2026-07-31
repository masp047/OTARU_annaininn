# おたる案内人検定 学習システム

第1回〜第23回の過去問**2,298問**を収録した学習アプリと、その元データ・生成
パイプライン。ブラウザで `study_app.html` を開けばすぐ使えます。

```bash
open study_app.html      # macOS
xdg-open study_app.html  # Linux
```

外部サーバー不要・通信不要。学習の記録はブラウザの localStorage に残ります。

## 収録状況

| | |
| --- | --- |
| 収録回 | 第1回〜第23回（全23回） |
| 設問行数 | 2,298行（枝番つきの小問は行を分けている） |
| 内訳 | 選択式 1,556 / 記述式 732 / 写真選択 10 |
| 写真つき設問 | 50問（切り抜き画像80枚を `images/` に収録） |
| 正解未確定 | 0行 |

## 学習アプリの使い方

- **出題モード**: 要復習・未挑戦 / 全問ランダム / 未挑戦のみ。回ごとの絞り込みも可能
- **選択式**: 選択肢を押すと即座に正誤と正解を表示。間隔反復（Leitner方式）で
  間違えた問題ほど早く再出題されます
- **写真の設問**: 写真そのものが選択肢の問題は、写真を押して答えます。
  参考写真つきの問題は写真を見ながら答えます
- **記述式**: 自己採点ではありません。答えを入力すると「採点待ち」に積まれ、
  ボタンでプロンプトをコピーできます。それをこのチャットに貼れば、
  あなたの答えと模範解答を比べて採点します。結果は ○/× で記録に反映します

## 正解の信頼性について

**正解は必ず解答PDFのテキスト層から機械的に取り込んでいます。**

問題PDFはスキャン画像なので、問題文はページ画像を読んで書き起こしました。
一方、解答PDFにはテキスト層が生きているため、`extract_answers.py` が座標
ベースで「問N → 正解」を抽出し、`apply_answers.py` が
`data/exam_NN.json` の `a` を機械的に上書きします。書き起こし時の読み違いが
正解に混入しない構造になっています。

### 解答用紙側の既知の落とし穴

解答PDFにも次のような癖があり、いずれも誌面を確認して手で直しています。

- **吹き出しの注記が答えの位置に混入する** — 第4回 問10・問11、第5回 問19
- **前版の数字がテキスト層に残り、罫線に隠れて見えないのに抽出される** —
  第6回 問15・17・18・23・59・61・91
- **番号欄と答え欄が座標順で入れ替わる** — 第5回 問8

これらを見つけるため、`apply_answers.py` は**選択肢があるのに正解が1〜4で
ない設問**を「要確認」として報告します。第6回の7問はこの検出で見つかりました。

### 出題側の不備で正解が一つに定まらない設問

- 第3回 問97 — 公式解答が「全員に1点加点」。どれを選んでも正解として扱う
- 第13回 問12A — 選択肢1と3がどちらも「運上屋」。公式解答も「1又は3」
- 第21回 問74 — 公式解答が「2（3も正解とする）」

## 重要: 日本語CMapが必要です

解答PDFは Adobe-Japan1 の日本語CIDフォントを参照しています。CMapデータが
無い環境では `pdftotext` が文字化けするか空文字列を返し、「PDFが壊れている」
ように見えます。**poppler-data を入れれば解決します。**

```bash
sudo apt-get install -y poppler-data   # Debian/Ubuntu
brew install poppler                   # macOS（poppler-dataを含む）
```

## データの作り方

```bash
pip install -r requirements.txt

# 1. 解答PDFから「問N → 正解」を抽出（回ごとに data/answers/answers_N.json）
python3 scripts/extract_answers.py past_exams/7_kaitou.pdf --json

# 2. 解答を正として data/exam_NN.json の a を上書きする
python3 scripts/apply_answers.py            # 全回
python3 scripts/apply_answers.py --only 7

# 3. 写真つき設問の画像を切り抜く
python3 scripts/crop_photos.py --only 7

# 4. 学習アプリとCSVを生成
python3 scripts/build_app.py
python3 scripts/build_csv.py
```

問題文は `data/exam_NN.json` に手で書き起こします。1問は次の形です。

```json
{"no": 22, "type": "選択", "q": "問題文…",
 "c": ["選択肢1", "選択肢2", "選択肢3", "選択肢4"], "a": ""}
```

`a` は空のままで構いません（手順2で解答PDFから埋まります）。枝番のある小問は
`"sub": "A"` を足して行を分けます。

### 写真つき設問

指定の書き方は `scripts/photo_spec.py` に一本化しています。切り抜く側と
参照する側で名前の付け方が食い違わないようにするためです。

```json
"photo": {"page": 3, "n": 4}                          写真4枚がそのまま選択肢
"photo": {"page": 4, "n": 1, "role": "stem"}          問題文につく参考写真
"photo": {"page": 9, "n": 4, "order": [1, 3, 4, 2]}   誌面の並びが選択肢番号と違う
"photo": {"page": 9, "n": 2, "start": 2}              1ページに写真つき設問が複数
"photo": {"page": 9, "n": 2, "labels": ["A", "B"]}    番号ではなくA・Bの見出し
"photo": {"page": 4, "n": 1, "bbox": [[105,83,240,173]]}
```

`bbox` は、ページ全体が1枚のスキャン画像になっているPDF（第19回）で使います。
埋め込み画像を数えても写真を切り出せないため、誌面上の位置をPDFの座標
（左, 上, 右, 下 / 単位はpt）で直接指定します。

## 出力CSV

`otaru_kanko_past_exams.csv`（UTF-8 BOM付き / Excelでも文字化けしません）

| 列 | 内容 |
| --- | --- |
| `問題ID` | `R03-Q012` 形式の一意キー（枝番つきは `-A`） |
| `回数` / `検定回` | `3` / `第3回` |
| `問題番号` / `枝番` | 回の中での設問番号と小問記号 |
| `形式` | 選択 / 記述 / 写真選択 |
| `問題文` | 設問本文 |
| `選択肢1`〜`選択肢4` | 選択肢 |
| `正解` / `正解本文` | 正解番号（または記述の模範解答）と選択肢のテキスト |
| `画像` | 写真つき設問の切り抜き画像パス |
| `注意` | 出題不備などの注記 |
| `全文` | 1問を1かたまりに整形したテキスト |

## ファイル構成

```
study_app.html              学習アプリ（生成物・これを開く）
otaru_kanko_past_exams.csv  CSV（生成物）
images/                     写真つき設問の切り抜き画像

data/exam_NN.json           問題文の書き起こし（手入力）
data/answers/answers_N.json 解答PDFから抽出した正解

scripts/extract_answers.py  解答PDFから座標ベースで正解を抽出
scripts/apply_answers.py    解答を正として exam_NN.json の a を上書き
scripts/crop_photos.py      写真つき設問の画像を切り抜く
scripts/photo_spec.py       photo 指定と画像ファイル名の規則
scripts/build_app.py        study_app.html を生成
scripts/build_csv.py        CSVを生成
scripts/split_pdf.py        大きいPDFをGitHubの制限内に分割
scripts/inspect_pdf.py      レイアウト確認用の診断ツール
```

`extract_exams.py` は当初の正規表現ベースの一括抽出パイプラインです。問題PDFが
スキャン画像だったため現在は使っていませんが、テストとともに残してあります。

## 注意

`past_exams/` `past_exams_ocr/` のPDFは配布元の著作物のため `.gitignore` で
除外しています。生成物を再配布する場合は配布元の利用条件を確認してください。
`images/` は除外していません（クローン直後にアプリが動くようにするため）。
