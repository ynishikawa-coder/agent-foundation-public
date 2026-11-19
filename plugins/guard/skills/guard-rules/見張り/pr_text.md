# pr_text（GitHub へ出す前の PR の文）

- 出来事: PreToolUse
- する事: GitHub の道具（名の末尾で見る: `create_pull_request`・`update_pull_request`・`add_issue_comment`・`update_issue_comment`・`add_reply_to_pull_request_comment`・`pull_request_review_write`・`add_comment_to_pending_review`・`issue_write`。MCP から出す commit の説明＝`merge_pull_request`・`push_files`・`create_or_update_file`・`delete_file` は `public` だけ）の文を、出す前に照らし AI だけを止める。`verdict`＝コメントがレビューの判定（どの行かに `レビューした窓: … 判定: green|red` が揃うか verdict の見出し〔# の数・大小を問わない〕が在る。文中に「判定: green」と書いた普通のコメント・「レビューした窓は…」の文・引用の中は見ない）なら checker の `verdict_form.py` を直に呼び、赤なら止める／`cleanup`＝PR の本文に、dev-flow の preimpl-cleanup の `整地受領証.template.md` の 4 つの見出し（名は雛形から読む・`##` でも `###` でもよい）が全部在り、雛形の `〔…〕` が残っていない。整地の要らない PR は `整地: 不要（<訳>）` の 1 行で通る／`words`＝PR の題・本文に窓の id（`session_01…`）がそのまま在る（本文の頭の塊〔最初の空行まで〕の `書いた窓:` の欄・コード・URL の中は数えない。job・検査の欄や頭の塊の外の行は数える。`親窓:` の欄は PR の型から畳んだ＝窓の親はサーバの記録 `get_session` の `parent_session_id`。使う側の型に残る間は頭の塊の `親窓:` も数えない）／`public`＝公開の repo（窓の repo の取り出しの workflow が action `public-guard` を呼ぶ・値の表 `public_repos_extra`）なら題・本文を `public-guard/guard.py --text` に渡す（置かない語の表は public-guard を呼ぶ step の `with:` の `deny-words-file`・別の step・job の物は読まない）。判定の道具・雛形・公開の検査（と workflow が名指す置かない語の表）が見つからない・壊れた時と、照らしの途中で壊れた時（`broken`・一時の置き場に書けない等）も止める

## 止められた・知らされた時の直し方

`verdict`: skill `checker:review-pr` の形で書き直し、`verdict_form.py` が exit 0 になってから出す。`cleanup`: `## 整地（根治の 4 段）` の下に雛形の 4 つの見出しで書く（skill `dev-flow:preimpl-cleanup`）。振る舞いを変えない PR（誤字・記録だけ・版だけ等）は 4 欄の代わりに `整地: 不要（<なぜ要らないか>）`。`words`: 窓の id は開けるリンク（`https://claude.ai/code/<id>`）にして役の名を添えるか、役の名だけにする。`public`: 当たった所を書き直す（GitHub の本文は書き替えても古い版が編集の履歴に公開で残る）。道具が無い時は plugin checker・dev-flow を入れる（`AF_VERDICT_FORM`・`AF_CLEANUP_TEMPLATE`・`AF_PUBLIC_GUARD` で path を渡せる）。整地を PR 本文の外に置く repo・言葉の照らしが合わない repo だけ、値の表の `pr_cleanup_exempt_repos`・`pr_words_exempt_repos` で外す（PR とレビューを通す）。判定の形と公開の検査は外さない

## 値の表の鍵

repo の根の `config/skill-values.json` の `"guard"` に書く（鍵・型・既定・当て方〔`against`＝当てる相手・`match`＝`whole` は相手の全体・`part` は相手の一部〕の正本は土台の `skill-values/schema.json`）。

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
- `pr_cleanup_exempt_repos`・`pr_words_exempt_repos`・`public_repos_extra`: owner/repo の名の全体に当てる正規表現の並び（型 `repo_names`・大小を問わない）。各行を `^` で始め `$` で終える（repo 1 つなら `^owner/repo$`・owner ごとなら `^owner/.*$`）。頭だけ（`^owner/`）・錨なし（`owner/repo`）の行は名の一部に当てる読み方と取り違えるので、値の表の照らしが型の違いとして名指し（起動の知らせ・`values_keys.py`・AI の書き込みは止まる）、外す側の鍵では外さず照らし、`public_repos_extra` では公開の照らしを外さない。

## 射程の外

- PR の文の見張りは、GitHub の MCP の道具の文だけを見る（Bash の `gh pr create --body` や git で打つ commit の説明は見ない。git の commit の説明は CI の公開の検査が拾う・MCP から出す commit の説明は `public` が照らす）。判定のコメントは、出す先の PR の先端と PR の commit 全部の `Claude-Session:` の窓（書いた窓の組・本文の `書いた窓:` の写しも足す）を gh で引き、出す窓の本物の id を窓の環境の記録（`CLAUDE_CODE_REMOTE_SESSION_ID`）から読んで verdict_form.py に渡す（見た先端の古い判定・書いた窓の組の窓が出す判定・名乗りの字が出す窓と違う判定も止める・どれかが引けなければ止める＝判定はクラウドの窓で出す）。判定の形の道具と雛形は、窓の repo に在ればその版を、無ければ入れた plugin の版を使う（見る点の表を変える PR の判定は、その枝を取り出した窓で出す）。言葉は窓の id だけを見る（番号・file 名・commit の印・`#31` の PR の指しは、過去の PR 本文 41 本に当てると 37 本が当たり、ほとんどが正しい指し＝当て所が無い）。公開かの見分けは窓の repo の取り出しの workflow か値の表で、手元に取り出しが無く値の表にも無い公開の repo は照らさない（CI の公開の検査が出した後に拾う）。
