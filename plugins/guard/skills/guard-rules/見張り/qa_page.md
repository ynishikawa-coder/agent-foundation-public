# qa_page（問いのページの検査）

- 出来事: PreToolUse
- する事: Artifact の publish（file_path と `files` で足す file のうち .html・.json）の前に、そのページが問いのページ（型の印 `<body data-dest>`・`CustomEvent('qa:submit')`／`<script>` の JSON に `questions`・`qs` と選択肢／radio と答えを外へ出す仕組み〔form・sendPrompt・window.claude の書く呼び出し・POST 等の fetch・clipboard への書き込み〕の両方／問いのデータの JSON。読むだけの fetch や表示の切り替えの radio は数えない）なら qa-html の `check.mjs` をかけ、赤なら止める。検査が見つからない・node が無い・検査が壊れた時も止める（緑を確かめられない物は出さない）

## 止められた・知らされた時の直し方

①聞く前に引き（細目 §4）、答え済み・資料で決まる・道具の都合の問いを消す ②オーナーへの問いなら選択肢の画面で聞く ③ページで出すなら skill `docs-kit:qa-html` の型（`check.mjs --template` が出す正本）で作り直し、止めた文に出る `node <check.mjs> <file>` が緑になってから出し直す。検査が無いなら plugin docs-kit を guard と同じ版で入れ直し、node を入れる（別の版の検査・path を渡す口では照らさない）。問いのページでないのに止まった時だけ、値の表の `qa_page_exempt` で外す（PR とレビューを通す）

## 値の表の鍵

repo の根の `config/skill-values.json` の `"guard"` に書く（鍵・型・既定・当て方〔`against`＝当てる相手・`match`＝`whole` は相手の全体・`part` は相手の一部〕の正本は土台の `skill-values/schema.json`）。

```json
{
  "guard": {
    "qa_page_exempt": ["^quiz/[^/]+\\.html$"]
  }
}
```

## 射程の外

- 問いのページの見張りは、Artifact の道具の publish の `file_path` と `files` の手元の元を見る（`files` で別の Artifact から写す物・型から作る Artifact のデータの store・Artifact の外で配るページは見ない）。問いのページの見分けは印による推し量りで、印を持たない問いのページ（radio を使わずボタンだけで答えるページなど）は素通りする。
