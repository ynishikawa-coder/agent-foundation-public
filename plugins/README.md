# プラグインの一覧

この repo に置く道具の正本の一覧です。行は先に全部置いてあり、物を置く窓は **自分の行の `状態` だけ** を替えます。新しい道具の行を足す・消す時は、置き場と同じ PR で替えます（`CONTRIBUTING.md` §7）。

- `種類`: `plugin`（`plugins/<名前>/` に置くプラグイン）
- `状態`: `未着手`（置き場はまだ無い）／`作業中`（置き場がある・まだ配らない）／`出した`（置き場があり、`中身` が全部ある・配りの器に載る）
- `中身`: skills の名前を `・` で区切る（skill を持たない plugin は `—`）。`出した` の時、`plugins/<名前>/skills/<skill>/SKILL.md` が全部あり、余りが無いことを CI が見る。
- 配りの器（`.claude-plugin/marketplace.json`）は別の窓が持つ。器がある時、`出した` の plugin が全部器に載り、器に載る物が全部この表にあることを CI が見る。

<!-- 一覧の表: tests/test_plugins_list.py が読む。列の順と見出しを変えない。 -->

| 名前 | 種類 | 持つ窓 | 状態 | 置き場 | 中身 |
|---|---|---|---|---|---|
| docs-kit | plugin | A3 | 出した | plugins/docs-kit/ | blueprint・compose-message・make-deck・mindmap・pdf-read・qa-html・theory-mock |
| dev-flow | plugin | A4 | 出した | plugins/dev-flow/ | codex・design-mode・preimpl-cleanup・public-repo・register-rule・spec-doc・verify |
| session-watch | plugin | A4 | 出した | plugins/session-watch/ | title-mark・watch-log |
| checker | plugin | A4 | 出した | plugins/checker/ | review-pr |
| guard | plugin | A5 | 出した | plugins/guard/ | guard-rules |
| core | plugin | A2 | 出した | plugins/core/ | — |

## 行ごとの注

- **docs-kit**（A3）: 確認のページ（Artifact・宛先がオーナーでも）と UTC の Artifact 型に、`qa-html` の検査をかける。publish の前は guard の `qa_page` が同じ検査で止める。
- **dev-flow**（A4）: 要件から brief を作る道具は Javis 固有なので入れない。
- **session-watch**（A4）: 会話ログを見て、題の目印・平文で書いた問い・答えの無い問いを拾う。クラウドの窓で題に種類の印（🙋／🤖）がまだ無い間は、UserPromptSubmit の hook が付けるよう知らせる。前の返事の「あなたがやること」に人の手の手順を直に書いた時も、手の窓で頼んで URL だけを書くよう同じ hook が知らせる（どちらも止めない）。返事の形（題の印・1 行目の札・締めの 2 行）や中身（平文の問い・中の言葉・日本時間でない時刻・完了の言い切り・鍵）が崩れたまま締めようとすると、Stop の hook が AI だけを差し戻して書き直させる（人の操作は止めない）。中の言葉は guard の `ask_shape`、鍵の形は公開の検査 `public-guard/guard.py` を直に呼ぶ。skills の名前は A4 が決めて `中身` を書き替える。
- **checker**（A4）: チェック役。skills の名前は A4 が決めて `中身` を書き替える。
- **guard**（A5）: 守りの hook（離席中の戻せない操作・試験から有料の上流・問いのページを Artifact で出す前の qa-html の検査・選択肢の画面の問いの形・選択肢の画面で 1 つだけ選ばせる問い・設計書の型の gate を封の入口を通さず呼ぶ手・外へ渡す道具の入力〔鍵・番号だけの頼み・窓の題〕・値の表に土台が読まない鍵・GitHub へ出す前の PR の文・Bash から GitHub へ PR の文を書く命令・選択肢の画面の前に引いた跡・文脈の量と越えた後の締めの差し戻し・未回答の台帳。見張りの一覧の正本は各見張りの頭の `HOOKS`（`scripts/guard.py` が読む））を 1 本の入口 `scripts/guard.py` で回す。Javis 側（pixel-office の `core/hooks/`）から移した。値は `config/skill-values.json` の `guard`。skill は止められた時の直し方。
- **core**（A2）: 振る舞いの核 `核.md`・振る舞いの既定 `振る舞い.md`（AI の癖と逆を求める物）・形の細目 `細目.md`。各 repo へは写さず、SessionStart の hook（`scripts/kaku.py inject`）が起動時に核と振る舞いの既定を毎回差し込む。使う側に残った写し・古い形（一覧 `古い形.json`・核の写しの枠など）・CLAUDE.md の量の上限越え・古い形の setup script・入っていない plugin は、起動の時に名指しで知らせる（核はいつも正本を差し込む）。量の上限は `scripts/kaku.py check`、使う側の checkout の古い形は `scripts/kaku.py olds`。使う側の setup script が呼ぶ入口は repo の根の `scripts/setup_plugins.py`。
