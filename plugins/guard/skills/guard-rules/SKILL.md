---
name: guard-rules
description: 守りの hook（guard）に止められた・知らされた時の直し方と、guard の値（値の表 config/skill-values.json）の変え方。止められた見張りの名から引く。
---

# 守りの hook（guard）

1 本の入口（`${CLAUDE_PLUGIN_ROOT}/scripts/guard.py`）を、プラグインの `hooks/hooks.json` が 3 つの出来事（PreToolUse・PostToolUse・SessionStart）で回す。止めるのは PreToolUse（AI の道具の呼び出し）だけで、他は隣に文を出すだけ（AI の締めを差し戻す口は持たない）。どれも壊れた時は黙って通す。止められた・知らされた時は下の直し方でその場を出し直すだけで済ませず、その形が出た原因を細目 §3「まず構造を疑う」で探して直す。

目次: 見張りごとの出来事・する事・止められた・知らされた時の直し方は `見張り.md`、値の鍵の当て方（何に・全体か一部か）は `値の当て方.md`、見分けの届かない所は `射程の外.md`。止められた・知らされた時は、知らせに出た見張りの名で `見張り.md` の節を引く。

| 見張り | 出来事 | 何を見るか（直し方の全文は `見張り.md` の同じ名の節） |
|---|---|---|
| irreversible（離席中の戻せない操作） | PreToolUse | 答えの無い問いを残してオーナーが離れている間の、戻せない操作（DB の破棄・送信・物理削除・戻せない rm -r） |
| paid_upstream（試験から有料の上流） | PreToolUse | 試験へ書く中身の、AI の API の鍵名・公式のエンドポイント |
| qa_page（問いのページの検査） | PreToolUse | Artifact で出す問いのページが qa-html の検査を通っているか |
| ask_shape（選択肢の画面の問いの形） | PreToolUse | 選択肢の画面の問いの形（`long`・`inner`・`topic`・`rec`）。`long`＝問いの文が `ask_question_max_chars` 字（既定 60）か `ask_question_max_sentences` 文（既定 1）を越える。`rec`＝推奨の印の付け方: 選択肢の見出しに推奨の語（推奨・おすすめ・お勧め・お薦め・オススメ・おススメ・イチオシ・recommend・suggested。大小を問わない・確認ページの検査 qa-html の `check.mjs` の `recommend` も同じ並び）が決まりの形（見出しの末の `(推奨)`・`（推奨）`・`(Recommended)`）以外で在る（「非推奨」「推奨なし」「推奨どおり」も見出しでは止まる・説明の文の中は数えない）・1 問に 2 つ以上・1 つ目でない選択肢・「分からない」の選択肢（見出しの頭が分からない・分かりません・知らない・不明・Unknown・I don't know）に在る（この見分け `ask_shape.is_dunno` は session-watch の「分からない」の無い問いの見張りも直に呼ぶ） |
| ask_shape の notice（推奨の印の知らせ） | PostToolUse | 推奨の印が、済んだかの確認・意図を聞く問いに付いた（知らせるだけ） |
| pick_one（1 つだけ選ばせる問い） | PreToolUse | やる物・順を 1 つだけ選ばせる問い。直し方: 相談で出た事は全部やる。①順と窓の分け方は AI が決めて進める（問わない）②全部を選べる形にする（multiSelect か「全部」）③原因は AI が見立てて示し（合意した全体の絵があれば絵の上で）、合っているかを問う ④調べれば決まる順は問わずに AI が決めて全部進める。 |
| outbound（外へ渡す道具の入力） | PreToolUse・PostToolUse（知らせる） | 外へ渡す入力の鍵の形（`secret`）・番号だけの文（`number`）・窓の題の形（`title`）。`number` の直し方: 番号にそれが何か（物の名と中身）を同じ文で添える。オーナーが番号で返した答え（「1 は残す」）を他の窓へ渡す時も、番号を中身に戻して渡す。 |
| spec_gate（設計書の型の gate を直に呼ぶ手） | PreToolUse | 設計書の型の gate を `--lock` で直に呼ぶ命令 |
| pr_text（GitHub へ出す前の PR の文） | PreToolUse・PostToolUse（知らせる） | GitHub へ出す PR の題・本文・コメント（判定の形・整地の欄・窓の id・公開の repo に置かない物） |
| values_keys（値の表の知らない鍵） | PreToolUse・SessionStart | 値の表の、土台が読まない鍵・型の違う値 |
| prior_ask（聞く前に引いた跡） | PreToolUse | 選択肢の画面の前に決定の記録と問いの表を引いた跡が無い問い（同じ頼みの中で 2 回まで・越えたら通す） |
| unanswered（未回答の台帳） | PostToolUse・SessionStart | 答えの無いまま閉じた問いを台帳に積み、次の窓の冒頭に渡す |

強制 push・main への push・本番への出荷・sudo は、オーナーが居ても居なくても settings の `permissions.deny` の受け持ち（ここでは重ねない）。

## 値の表

repo の根の `config/skill-values.json` の `"guard"`（無ければ既定で動く）。鍵・型・既定の正本は土台の `skill-values/schema.json`（plugin の `lib/` へ symlink で届く）。知らない鍵・畳んだ鍵・型の違う値は、その鍵だけ既定で動き（守りは止めない）、窓の起動の時に values_keys が表全体を名指しで知らせる。表を直したら `python3 "${CLAUDE_PLUGIN_ROOT}/lib/skill_values.py" check` で確かめる。

```json
{
  "guard": {
    "unattended_env": ["AF_UNATTENDED"],
    "state_dir": "~/.claude/af-guard",
    "paid_markers_extra": ["api.example-paid.com"],
    "irreversible_bash_extra": [{"pattern": "\\bmy-db\\s+--wipe\\b", "why": "DB の破棄"}],
    "irreversible_tools_extra": ["^mcp__[^ ]*__delete_item$"],
    "qa_page_exempt": ["^quiz/[^/]+\\.html$"],
    "ask_question_max_chars": 60,
    "ask_question_max_sentences": 1,
    "ask_inner_terms_extra": ["例の関所"],
    "ask_term_allow": ["^ISO\\d+$"],
    "ask_topic_stopwords_extra": [],
    "ask_shape_exempt": [],
    "ask_rec_notice_kinds": {"済んだかの確認": ["終わりましたか"]},
    "ask_rec_notice_exempt": [],
    "ask_pick_one_exempt": ["^作り物の試しの順"],
    "ask_prior_lookup": ["^mcp__[^ ]*__notion-(?:search|fetch|query-data-sources) \\{.*決定.*\\}$", "^Grep \\{.*問いの表.*\\}$"],
    "ask_prior_exempt": ["終わりましたか|済みましたか"],
    "outbound_secret_allow": ["^作り物の見本の字$"],
    "number_request_exempt": [],
    "pr_cleanup_exempt_repos": [],
    "pr_words_exempt_repos": [],
    "public_repos_extra": ["^my-owner/far-public$"]
  }
}
```

- `unattended_env`: 真なら人のいない窓とみなす環境変数の名（夜の自走などの印）。人のいない窓では、離席の止めと台帳は働かない。返し先が別の窓の子の窓（最初の頼みの文に `（親窓 session_… の子）` か `返し先=session_…` が在り、かつその頼みの行の記録が人の打った物でない＝別の窓や仕組みから来た頼み）は、問う窓として離席の止めと台帳が働く。
- `pr_cleanup_exempt_repos`・`pr_words_exempt_repos`・`public_repos_extra`: owner/repo の名の全体に当てる正規表現の並び（型 `repo_names`・大小を問わない）。各行を `^` で始め `$` で終える（repo 1 つなら `^owner/repo$`・owner ごとなら `^owner/.*$`）。頭だけ（`^owner/`）・錨なし（`owner/repo`）の行は名の一部に当てる読み方と取り違えるので、値の表の照らしが型の違いとして名指し（起動の知らせ・`values_keys.py`・AI の書き込みは止まる）、外す側の鍵では外さず照らし、`public_repos_extra` では公開の照らしを外さない。
- 字・正規表現の鍵の当て方は `値の当て方.md`。
- `state_dir`: 未回答の台帳の置き場（repo ごとに 1 冊）。窓の中だけで閉じる印（離席の印）は一時の箱に置く。
