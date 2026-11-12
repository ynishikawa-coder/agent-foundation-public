# 変更の記録

形は `docs/版の出し方.md` の通り。v0.1.1 までの版は移す前の private の repo で出した（この repo には印を打たない・記録もここに持たない）。v0.2.0 の「足した」は、v0.1.1 の後・移す前に入った物。PR ごとに `## [Unreleased]` へ 1 行足し、版を出す時に親窓が見出しを版の名と日付に替える。

## [Unreleased]

### 変えた
- docs-kit: skill の聞き方の文（compose-message の「1 問だけ」・qa-html／mindmap／theory-mock／blueprint の AskUserQuestion の並べ方・dev-flow の spec-doc の「1 回確定」）を核 §4 を指す形に畳み、pdf-read の Mac の窓の行を消した。PR の型の合流役を親窓にした。

## [v0.3.0] - 2026-11-12

### 変えた（壊れる: 窓の振る舞いが変わる）
- 核 §4 聞き方: 「選択肢の画面で 1 問だけ・テキストで聞かない」の固定を外し、問いの形で道具を選ぶ（1 つを選ぶ＝選択肢の画面・論点が幾つも＝確認 HTML・出し合い＝マインドマップかテキスト）。問いは前提から聞く。子窓も題に ❓ を付けて直に問う。人にしか打てない手は手の窓（`🙋⏳ 手: <何を>`）で頼む。窓の役は 親・書く・レビュー・調べ・手 の 5 つ。
- 核 §5 の締めを 2 行にした: `AI の残り: …` と `オーナーの残り: なし ／ 答える: <問いの窓 URL> ／ 手: <手の窓 URL>`（`この窓: 残りなし` 等の 1 行の締めは無くした）。AI が立てた 🤖 の窓は終わったら AI が閉じる。
- 核 §8 記録: 記録は各社の決まった置き場（Javis は Notion と Drive）。git には動く時に読む物だけ。2 アカウントをまたぐ連絡だけ連絡板の issue。
- 核 §3 に規律を足せる線: 畳む・直す・言い換え・止めずに知らせる物は AI が入れてよい。新しく止める物と核の原則の変更はオーナーの同意。
- 細目: 親が子の答えの無い問いを 1 時間で知らせる・手の窓の型・並走（5 分を超えそうなら分ける・助手と窓の使い分け）・Auto で開き子は継ぐ。土台へ出した決まり（範囲を縮めない・膨らませない・ゴールの任され方・聞かない問い・二重出力とぼかしの禁止・完了の報告の差分・情報の取り方・道具の呼び出しが崩れた時・後継の第一声・試験から有料の上流を叩かない）。
- register-rule: 最初の段で「これは止める物か」を問う。置き場の表は 土台／各 repo の固有 の 2 行。1 つ足したら 1 つ以上畳む。値の表の鍵は 4 つに畳んだ。
- 守りを戻せない事故だけに畳んだ: session-watch の Stop の hook を外した。guard irreversible を DB の破棄・メール送信・Notion の物理削除・git で戻せない rm -r に絞った。未回答の台帳の寿命は 24 時間。
- 合流役の呼び名を親窓にそろえた（CONTRIBUTING・docs/版の出し方.md）。

### 足した
- skill `design-mode`（dev-flow）: 作る前の相談の間は調べる・整理する・問うだけをし、論点の表と「ほんまにできる表」が揃うまで実装へ進まない。

### 畳んだ
- 細目の §1（中身無し）と、核と同じ事を言う細目の行（根治の言い換え・途中確認の原則・一時しのぎ）。
- verify の 🎯 の締めの箱（核 §5 の 2 行へ）・preimpl-cleanup の根治の 3 つの問いの写し（核 §3 を指す）。
- docs/核の届け方.md の Mac の道。決まりの文の中の日付と出所の注。

## [v0.2.0] - 2026-11-12

### 変えた
- 土台を public の repo（agent-foundation-public）へ移した（private の agent-foundation の main@59927ce の今の物だけ・履歴なし）。どの環境・どの窓でも起動前に plugin を取れるようにするため。
- 核の届け方を「各 repo へ写す＋CI で一致を照らす」から「plugin `core` が起動時に差し込む」へ変えた: 核と細目は `plugins/core/` へ移し、SessionStart の hook（`scripts/kaku.py inject`）が核を差し込み細目の在り処を知らせる。写しの枠が在る repo では差し込まない。量の上限は `kaku.py check`（docs/核の届け方.md）。入れ損ねを起動時に知らせる setup script の型も同じ文書に置いた。
- 核 §8 の連絡板の在り処を、private の `ynishikawa-coder/agent-foundation` の issue と名指した（土台が public の repo へ移ったため）。細目 §6 の時計は各 repo が自分の settings に置く形にした。

### 畳んだ
- 写す道具 `core/af_sync.py` とその試験・検査（`scripts/checks/core_sync.sh`）、この repo 自身の写し（`.claude/af/`・`.claude/skills/`・`CLAUDE.md` の写しの枠・settings の hook）、`docs/核の写し方.md`。受けない物の一覧（`.claude/af/exclude`）も写しと一緒に畳んだ（使わない plugin は入れない）。
- 通し道の試しの記録（`docs/通し道.md`）は経緯の記録なので移さない（private の agent-foundation に残る）。

### 足した
- 版の印（git の tag）を GitHub Actions が自動で打つ: main に入った時に CHANGELOG の版の見出しからまだ無い印を打つ（.github/workflows/tag.yml・scripts/release/tags_from_changelog.py）。版の節を持たない過去の版は手で回す時の入力 version・sha で打つ。使う側へ写す型は docs/版の印.md。
- 細目に、核に無い決まり 7 つを足した（UTC 側の勧め・連絡板 #2）: §4 クラウドの窓が本体・窓に分けて並走／§5 止まる時は理由と次にやる事／§6 計画に終わる時刻／§7 別の道で確かめる／§8 Git に入れるのは動くのに読む物だけ・決定の記録に原文つき。核は変えない。
