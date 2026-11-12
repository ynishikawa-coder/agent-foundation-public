# 変更の記録

形は `docs/版の出し方.md` の通り。v0.1.1 までの版は移す前の private の repo で出した（この repo には印を打たない・記録もここに持たない）。v0.2.0 の「足した」は、v0.1.1 の後・移す前に入った物。PR ごとに `## [Unreleased]` へ 1 行足し、版を出す時に合流役が見出しを版の名と日付に替える。

## [Unreleased]

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
