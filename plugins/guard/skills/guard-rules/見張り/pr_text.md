# pr_text（GitHub へ出す前の PR の文）

- 出来事: PreToolUse
- する事: GitHub の道具（名の末尾で見る: `create_pull_request`・`update_pull_request`・`add_issue_comment`・`update_issue_comment`・`add_reply_to_pull_request_comment`・`pull_request_review_write`・`add_comment_to_pending_review`・`issue_write`。MCP から出す commit の説明＝`merge_pull_request`・`push_files`・`create_or_update_file`・`delete_file` は `public` だけ）の文を、出す前に照らし AI だけを止める。`verdict`＝コメントがレビューの判定（どの行かに `レビューした窓: … 判定: green|red` が揃うか verdict の見出し〔# の数・大小を問わない〕が在る。文中に「判定: green」と書いた普通のコメント・「レビューした窓は…」の文・引用の中は見ない）なら checker の `verdict_form.py` を直に呼び、赤なら止める／`cleanup`＝PR の本文に、dev-flow の preimpl-cleanup の `整地受領証.template.md` の 4 つの見出し（名は雛形から読む・`##` でも `###` でもよい）が全部在り、雛形の `〔…〕` が残っていない。整地の要らない PR は `整地: 不要（<訳>）` の 1 行で通る／`words`＝PR の題・本文に窓の id（`session_01…`）がそのまま在る（頭の決まった欄・コード・URL の中は数えない）／`public`＝公開の repo（窓の repo の取り出しの workflow が action `public-guard` を呼ぶ・値の表 `public_repos_extra`）なら題・本文を `public-guard/guard.py --text` に渡す（置かない語の表はその workflow の `deny-words-file`）。判定の道具・雛形・公開の検査（と workflow が名指す置かない語の表）が見つからない・壊れた時と、照らしの途中で壊れた時（`broken`・一時の置き場に書けない等）も止める

## 止められた・知らされた時の直し方

`verdict`: skill `checker:review-pr` の形で書き直し、`verdict_form.py` が exit 0 になってから出す。`cleanup`: `## 整地（根治の 4 段）` の下に雛形の 4 つの見出しで書く（skill `dev-flow:preimpl-cleanup`）。振る舞いを変えない PR（誤字・記録だけ・版だけ等）は 4 欄の代わりに `整地: 不要（<なぜ要らないか>）`。`words`: 窓の id は開けるリンク（`https://claude.ai/code/<id>`）にして役の名を添えるか、役の名だけにする。`public`: 当たった所を書き直す（GitHub の本文は書き替えても古い版が編集の履歴に公開で残る）。道具が無い時は plugin checker・dev-flow を入れる（`AF_VERDICT_FORM`・`AF_CLEANUP_TEMPLATE`・`AF_PUBLIC_GUARD` で path を渡せる）。整地を PR 本文の外に置く repo・言葉の照らしが合わない repo だけ、値の表の `pr_cleanup_exempt_repos`・`pr_words_exempt_repos` で外す（PR とレビューを通す）。判定の形と公開の検査は外さない

## 値の表の鍵

repo の根の `config/skill-values.json` の `"guard"` に書く（既定はこの見張りの file の頭の `VALUES`）。

```json
{
  "guard": {
    "pr_cleanup_exempt_repos": [],
    "pr_words_exempt_repos": [],
    "public_repos_extra": ["^my-owner/far-public$"]
  }
}
```

- `pr_cleanup_exempt_repos` … PR 本文の整地の欄を照らさない repo（owner/repo に当てる正規表現の並び・整地を PR 本文の外に置く repo だけ）
- `pr_words_exempt_repos` … PR の題・本文の言葉を照らさない repo（同じ形）
- `public_repos_extra` … 手元に取り出しが無くても公開とみなす repo（同じ形）

## 射程の外

- PR の文の見張りは、GitHub の MCP の道具の文だけを見る（Bash の `gh pr create --body` や git で打つ commit の説明は見ない。git の commit の説明は CI の公開の検査が拾う・MCP から出す commit の説明は `public` が照らす）。判定のコメントは、出す先の PR の先端と PR 本文の頭の `書いた窓:` を gh で引いて verdict_form.py に渡す（見た先端の古い判定・自分の PR への判定も止める・引けなければ止める）。判定の形の道具と雛形は、窓の repo に在ればその版を、無ければ入れた plugin の版を使う（見る点の表を変える PR の判定は、その枝を取り出した窓で出す）。言葉は窓の id だけを見る（番号・file 名・commit の印・`#31` の PR の指しは、過去の PR 本文 41 本に当てると 37 本が当たり、ほとんどが正しい指し＝当て所が無い）。公開かの見分けは窓の repo の取り出しの workflow か値の表で、手元に取り出しが無く値の表にも無い公開の repo は照らさない（CI の公開の検査が出した後に拾う）。
