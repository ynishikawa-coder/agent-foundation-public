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

- **docs-kit**（A3）: 確認のページは UTC の Artifact 型に、`qa-html` の検査をかける。
- **dev-flow**（A4）: 要件から brief を作る道具は Javis 固有なので入れない。
- **session-watch**（A4）: 会話ログを見て、題の目印・平文で書いた問い・答えの無い問いを拾う。クラウドの窓で題に種類の印（🙋／🤖）がまだ無い間は、UserPromptSubmit の hook が付けるよう知らせる（止めない）。skills の名前は A4 が決めて `中身` を書き替える。
- **checker**（A4）: チェック役。skills の名前は A4 が決めて `中身` を書き替える。
- **guard**（A5）: 守りの hook 4 つ（離席中の戻せない操作・試験から有料の上流・文脈の量・未回答の台帳）を 1 本の入口 `scripts/guard.py` で回す。Javis 側（pixel-office の `core/hooks/`）から移した。値は `config/skill-values.json` の `guard`。skill は止められた時の直し方。
- **core**（A2）: 振る舞いの核 `核.md` と細目 `細目.md`。各 repo へは写さず、SessionStart の hook（`scripts/kaku.py inject`）が起動時に核を差し込む。開いた repo の根の `CLAUDE.md` に写しの枠（`AF-CORE:BEGIN`）がまだ在る時は差し込まない（移る間の二重を避ける）。量の上限は `scripts/kaku.py check`。
