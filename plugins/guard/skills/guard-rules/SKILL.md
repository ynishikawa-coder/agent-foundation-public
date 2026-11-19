---
name: guard-rules
description: 守りの hook（guard の 7 つ）に止められた・知らされた時の直し方と、値の表での変え方。「戻せない操作が止められた」「試験に PAID_UPSTREAM_GUARD と言われた」「問いのページが qa-html の検査を通っていないと Artifact の publish を止められた」「選択肢の画面の問いが読みにくい形だと止められた（題が長い・中の言葉・話題が混ざる）」「PR の題・本文やコメントを GitHub へ出す前に止められた（判定の形・整地の欄・窓の id・公開の repo に置かない物）」「文脈が目安を越えたと出た」「前の窓の答えの無い問いが渡された」時、または guard の値（文脈の目安・人のいない窓の印・足す印・問いのページの検査から外す file・問いの形の上限と外す形・PR の文の照らしから外す repo）を変えたい時に使う。
---

# 守りの hook（guard）

1 本の入口（`${CLAUDE_PLUGIN_ROOT}/scripts/guard.py`）を、プラグインの `hooks/hooks.json` が 3 つの出来事で回す。止めるのは PreToolUse だけで、他は隣に文を出すだけ。どれも壊れた時は黙って通す。止められた・知らされた時は下の直し方でその場を出し直すだけで済ませず、その形が出た原因を細目 §3「まず構造を疑う」で探して直す。

| 見張り | 出来事 | する事 | 止められた・知らされた時の直し方 |
|---|---|---|---|
| irreversible（離席中の戻せない操作） | PreToolUse | この窓で選択肢モーダルが答えのないまま閉じ、オーナーがまだ戻っていない間だけ、DB の破棄・メールの送信・Notion の物理削除・git で戻せない rm -r を止める（作業場〔一時の置き場〕と変更の無い作業部屋の掃除は通す） | 戻せる作業を先に進める。その操作が要るなら同じ問いをモーダルで出し直し、答えが返ってから行う（答えが返るかオーナーが打てば解ける） |
| paid_upstream（試験から有料の上流） | PreToolUse | 試験らしい path へ書く中身に、AI の API の鍵名・公式のエンドポイントがあれば止める | 既定を録画の再生か偽物にする。本物が要るなら環境変数 1 本で切り替える関所を通し、その file に `PAID_UPSTREAM_GUARD` を書く |
| qa_page（問いのページの検査） | PreToolUse | Artifact の publish（file_path が .html・.json）の前に、そのページが問いのページ（型の印 `<body data-dest>`・`CustomEvent('qa:submit')`／`<script>` の JSON に `questions`・`qs` と選択肢／radio と答えを外へ出す仕組み〔form・sendPrompt・window.claude の書く呼び出し・POST 等の fetch・clipboard への書き込み〕の両方／問いのデータの JSON。読むだけの fetch や表示の切り替えの radio は数えない）なら qa-html の `check.mjs` をかけ、赤なら止める。検査が見つからない・node が無い・検査が壊れた時も止める（緑を確かめられない物は出さない） | ①聞く前に引き（細目 §4）、答え済み・資料で決まる・道具の都合の問いを消す ②オーナーへの問いなら選択肢の画面で聞く ③ページで出すなら skill `docs-kit:qa-html` の型を写して作り直し、止めた文に出る `node <check.mjs> <file>` が緑になってから出し直す。検査が無いなら plugin docs-kit と node を入れる（`AF_QA_CHECK` で path を渡せる）。問いのページでないのに止まった時だけ、値の表の `qa_page_exempt` で外す（PR とレビューを通す） |
| ask_shape（選択肢の画面の問いの形） | PreToolUse | AskUserQuestion の画面が人に出る前に問いを照らし、崩れていれば AI だけを止める（人の操作は止めない）。`long`＝問いの文が `ask_question_max_chars` 字（既定 60）か `ask_question_max_sentences` 文（既定 1）を越える／`inner`＝問い・見出し・選択肢に AI の中の言葉らしい字（`E02`・`Q202611-67` のような番号・`#616`・`v0.21.0` のような版・file 名・path・snake_case や `直し_0020` のような識別子・窓の id・commit の印・`` ` `` で囲んだ字。URL は数えない）／`topic`＝2 問以上の画面で、問いと見出しの語（漢字・カタカナ・英字の 2 字の並び・送り仮名は詰める）を共にしない組に分かれる | `long`: 問いの文は何を決めるかの 1 文。背景と材料は先にチャットで見せ、違いと選ぶとどうなるかは選択肢の説明へ（細目 §4）。`inner`: それが何かを日常の言葉で言い換える。`topic`: 話題ごとに画面を分けて続けて出す（捨てない）。同じ話題なら問いか見出しにその語を入れる。字の形だけ当たった誤りは値の表の `ask_term_allow`（字）か `ask_shape_exempt`（問いの文）に足す（PR とレビューを通す） |
| pr_text（GitHub へ出す前の PR の文） | PreToolUse | GitHub の道具（名の末尾で見る: `create_pull_request`・`update_pull_request`・`add_issue_comment`・`update_issue_comment`・`add_reply_to_pull_request_comment`・`pull_request_review_write`・`add_comment_to_pending_review`・`issue_write`。MCP から出す commit の説明＝`merge_pull_request`・`push_files`・`create_or_update_file`・`delete_file` は `public` だけ）の文を、出す前に照らし AI だけを止める。`verdict`＝コメントがレビューの判定（どの行かに `レビューした窓: … 判定: green|red` が揃うか verdict の見出し〔# の数・大小を問わない〕が在る。文中に「判定: green」と書いた普通のコメント・「レビューした窓は…」の文・引用の中は見ない）なら checker の `verdict_form.py` を直に呼び、赤なら止める／`cleanup`＝PR の本文に、dev-flow の preimpl-cleanup の `整地受領証.template.md` の 4 つの見出し（名は雛形から読む・`##` でも `###` でもよい）が全部在り、雛形の `〔…〕` が残っていない。整地の要らない PR は `整地: 不要（<訳>）` の 1 行で通る／`words`＝PR の題・本文に窓の id（`session_01…`）がそのまま在る（頭の決まった欄・コード・URL の中は数えない）／`public`＝公開の repo（窓の repo の取り出しの workflow が action `public-guard` を呼ぶ・値の表 `public_repos_extra`）なら題・本文を `public-guard/guard.py --text` に渡す（置かない語の表はその workflow の `deny-words-file`）。判定の道具・雛形・公開の検査（と workflow が名指す置かない語の表）が見つからない・壊れた時と、照らしの途中で壊れた時（`broken`・一時の置き場に書けない等）も止める | `verdict`: skill `checker:review-pr` の形で書き直し、`verdict_form.py` が exit 0 になってから出す。`cleanup`: `## 整地（根治の 4 段）` の下に雛形の 4 つの見出しで書く（skill `dev-flow:preimpl-cleanup`）。振る舞いを変えない PR（誤字・記録だけ・版だけ等）は 4 欄の代わりに `整地: 不要（<なぜ要らないか>）`。`words`: 窓の id は開けるリンク（`https://claude.ai/code/<id>`）にして役の名を添えるか、役の名だけにする。`public`: 当たった所を書き直す（GitHub の本文は書き替えても古い版が編集の履歴に公開で残る）。道具が無い時は plugin checker・dev-flow を入れる（`AF_VERDICT_FORM`・`AF_CLEANUP_TEMPLATE`・`AF_PUBLIC_GUARD` で path を渡せる）。整地を PR 本文の外に置く repo・言葉の照らしが合わない repo だけ、値の表の `pr_cleanup_exempt_repos`・`pr_words_exempt_repos` で外す（PR とレビューを通す）。判定の形と公開の検査は外さない |
| context_size（文脈の量） | PostToolUse | 文脈が目安を越えた最初の 1 回だけ知らせる | 人のいる窓は区切りで引き継ぎを書き後継の窓へ替える。人のいない窓は今の段を終えて引き継ぎを書き止まる |
| unanswered（未回答の台帳） | PostToolUse・SessionStart | モーダルが答えのないまま閉じた問いを台帳に積み、24 時間の間、次の窓の冒頭に渡す。答えが返れば降ろす（同じ問いの見分けは文面の一致か含有だけ。字の形で別の問いを結ばない）。子の窓の問いも同じ | 1 件ずつ、今の窓の流れで扱う: ①答え済み・もう要らない → 出さずに `python3 <unanswered.py> drop <key> --why <訳>` で降ろす（渡された文に path が出る・`list` で一覧）②今の頼みと関わる → チャットで前提を 1〜2 文添えてから出し直す（問いの文は短く言い直してよい。言い直した問いに答えが返ったら、元の問いを drop で降ろす＝機械は結ばない）③関わらない → 冒頭で画面に出さず、締めの「あなたがやること」に 1 行で知らせ、求められたら出す。言い方だけ変えて何度も出さない |

強制 push・main への push・本番への出荷・sudo は、オーナーが居ても居なくても settings の `permissions.deny` の受け持ち（ここでは重ねない）。

## 値の表

repo の根の `config/skill-values.json` の `"guard"`（無ければ既定で動く）。

```json
{
  "guard": {
    "context_limit": 300000,
    "unattended_env": ["AF_UNATTENDED"],
    "state_dir": "~/.claude/af-guard",
    "paid_markers_extra": [],
    "irreversible_bash_extra": [{"pattern": "\\bmy-db\\s+--wipe\\b", "why": "DB の破棄"}],
    "irreversible_tools_extra": [],
    "qa_page_exempt": ["/quiz/[^/]+\\.html$"],
    "ask_question_max_chars": 60,
    "ask_question_max_sentences": 1,
    "ask_inner_terms_extra": ["例の関所"],
    "ask_term_allow": ["^ISO\\d+$"],
    "ask_topic_stopwords_extra": [],
    "ask_shape_exempt": [],
    "pr_cleanup_exempt_repos": [],
    "pr_words_exempt_repos": [],
    "public_repos_extra": ["^my-owner/far-public$"]
  }
}
```

- `unattended_env`: 真なら人のいない窓とみなす環境変数の名（夜の自走などの印）。人のいない窓では、離席の止めと台帳は働かず、文脈の知らせは「止まる」側になる。返し先が別の窓の子の窓（最初の頼みの文に `（親窓 session_… の子）` か `返し先=session_…`）は、問う窓として離席の止めと台帳が働き、文脈の知らせだけ「止まる」側。
- `state_dir`: 未回答の台帳の置き場（repo ごとに 1 冊）。窓の中だけで閉じる印（離席の印・文脈の知らせた印）は一時の箱に置く。

## 射程の外

- 戻せない操作の判定は列挙であって証明ではない（`find … -delete`・再帰なしの `rm -f`・`git restore .` などは素通り）。足したい形は値の表へ。
- 試験から有料の上流の見張りは、自分のサーバを経た中継と、Bash のリダイレクトで書く形を見ない。
- 選択肢の画面の問いの形の見張りは字の形の推し量り（意味は読まない）。日常の言葉で書いた内輪の呼び名（「例の関所」など）は値の表の `ask_inner_terms_extra` に足すまで素通り。日常の英数字の名（`B202` の部屋・`COVID19`・`見積書.xlsx`・`Node.js`・`Wi-Fi/LAN/USB` など）も字の形で止まる（`ask_term_allow` で外す）。話題の見分けは語の重なりなので、別の話題でも同じ語（「検査」など）を共にすれば通り、同じ話題でも語を共にしなければ止まる（見出しに話題の語を入れて直す）。案や前提をチャットで先に見せたかと、オーナーが決めなくてよい事を聞いていないかは見ない。
- 未回答の台帳の扱い（降ろす・前提を添えて出す・締めで知らせる）は AI の判断で、答え済みかを機械は確かめない。降ろした問いは台帳の `dropped_recent` に訳と一緒に残る。
- PR の文の見張りは、GitHub の MCP の道具の文だけを見る（Bash の `gh pr create --body` や git で打つ commit の説明は見ない。git の commit の説明は CI の公開の検査が拾う・MCP から出す commit の説明は `public` が照らす）。判定のコメントは形だけを見て、見た先端が PR の今の先端かは見ない（hook から PR の先端を引かない・合流の窓が照らす）。判定の形の道具と雛形は、窓の repo に在ればその版を、無ければ入れた plugin の版を使う（見る点の表を変える PR の判定は、その枝を取り出した窓で出す）。言葉は窓の id だけを見る（番号・file 名・commit の印・`#31` の PR の指しは、過去の PR 本文 41 本に当てると 37 本が当たり、ほとんどが正しい指し＝当て所が無い）。公開かの見分けは窓の repo の取り出しの workflow か値の表で、手元に取り出しが無く値の表にも無い公開の repo は照らさない（CI の公開の検査が出した後に拾う）。
- 問いのページの見張りは、Artifact の道具の publish の `file_path` だけを見る（`files` で足す別のページ・型から作る Artifact のデータの store・Artifact の外で配るページは見ない）。問いのページの見分けは印による推し量りで、印を持たない問いのページ（radio を使わずボタンだけで答えるページなど）は素通りする。
