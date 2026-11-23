# プラグインの一覧

この repo に置く道具の正本の一覧です。行は先に全部置いてあり、物を置く窓は **自分の行の `状態` だけ** を替えます。新しい道具の行を足す・消す時は、置き場と同じ PR で替えます（`CONTRIBUTING.md` §7）。

- `種類`: `plugin`（`plugins/<名前>/` に置くプラグイン）
- `状態`: `未着手`（置き場はまだ無い）／`作業中`（置き場がある・まだ配らない）／`出した`（置き場があり、`中身` が全部ある・配りの器に載る）
- `中身`: skills の名前を `・` で区切る（skill を持たない plugin は `—`）。`出した` の時、`plugins/<名前>/skills/<skill>/SKILL.md` が全部あり、余りが無いことを CI が見る。
- 配りの器（`.claude-plugin/marketplace.json`）は別の窓が持つ。器がある時、`出した` の plugin が全部器に載り、器に載る物が全部この表にあることを CI が見る。

<!-- 一覧の表: tests/test_plugins_list.py が読む。列の順と見出しを変えない。 -->

| 名前 | 種類 | 持つ窓 | 状態 | 置き場 | 中身 |
|---|---|---|---|---|---|
| docs-kit | plugin | A3 | 出した | plugins/docs-kit/ | big-picture・blueprint・compose-message・make-deck・mindmap・pdf-read・qa-html・theory-mock |
| dev-flow | plugin | A4 | 出した | plugins/dev-flow/ | codex・design-mode・public-repo・spec-doc・verify |
| checker | plugin | A4 | 出した | plugins/checker/ | review-pr |
| guard | plugin | A5 | 出した | plugins/guard/ | — |
| core | plugin | A2 | 出した | plugins/core/ | — |

## 行ごとの注

- **docs-kit**（A3）: 全体の絵（big-picture）の正は JSON 1 つで、HTML はそこから描き直す写し。土台の絵は `docs/全体の絵.json`。絵は設計の時に掘り下げる元の図で、合流を止めない（照らしは頼まれた時だけ）。確認のページ（Artifact・宛先がオーナーでも）と UTC の Artifact 型に、`qa-html` の検査をかける。
- **dev-flow**（A4）: 要件から brief を作る道具は Javis 固有なので入れない。
- **checker**（A4）: チェック役。skills の名前は A4 が決めて `中身` を書き替える。
- **guard**（A5）: 守りの hook（離席中の戻せない操作・試験から有料の上流・外へ渡す道具の入力の鍵の形・GitHub へ出す前の PR の文の公開の repo に置かない物・未回答の台帳）を 1 本の入口 `scripts/guard.py` で回す。見張りの一覧の正本は各見張りの頭の `HOOKS`（`scripts/guard.py` が読む）。値は `config/skill-values.json` の `guard`（鍵の意味は `skill-values/schema.json`）。
- **core**（A2）: 振る舞いの核 `核.md`・振る舞いの既定 `振る舞い.md`（AI の癖と逆を求める物）・形の細目 `細目/`（節ごとの file）。各 repo へは写さず、SessionStart の hook（`scripts/kaku.py inject`）が起動時に核と振る舞いの既定を毎回差し込む。使う側に残った写し・古い形（一覧 `古い形.json`・核の写しの枠など）・CLAUDE.md の量の上限越え・古い形の setup script・入っていない plugin は、起動の時に名指しで知らせる（核はいつも正本を差し込む）。量の上限は `scripts/kaku.py check`、使う側の checkout の古い形は `scripts/kaku.py olds`。使う側は土台の節を番号でなく名で指す。使う側の setup script が呼ぶ入口は repo の根の `scripts/setup_plugins.py`。土台の hook の命令は目録の clone の入口 `scripts/hook_run.py` を通り、古い土台で立った窓でも入った台帳の新しい版の script が回る（古ければ起動の hook が裏で入れ直す＝`kaku.py refresh`・`docs/核の届け方.md`「古い土台で立った窓」）。
