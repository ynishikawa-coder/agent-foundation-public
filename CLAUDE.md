# agent-foundation

## この repo に固有の決まり

- この repo は、別々のアカウントの 2 つの AI（Javis と UTC エージェント）が道具として一緒に使う振る舞いの土台。仕事の中身（顧客・業務の語）は持たない。
- 核の正本は `plugins/core/核.md`（細目は同じ dir の `細目.md`）。各 repo へは写さず、plugin `core` の SessionStart の hook が起動時に差し込む。届け方は `docs/核の届け方.md`。
- この repo の窓も、土台の plugin を起動前の setup script で入れて使う（repo の中に skill・hook の写しを置かない）。
- 直す人の手順は `CONTRIBUTING.md`、道具の一覧は `plugins/README.md`。
