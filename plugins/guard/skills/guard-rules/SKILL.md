---
name: guard-rules
description: 守りの hook（guard）に止められた・知らされた時の直し方と、値の表での変え方。止めた文・知らせた文の末に出る「直し方と値の表の鍵」の file（見張りごとに 1 つ）を読んで直す。「守りに止められた」「guard に止められた」「hook に止められた・知らされた」「出す前に止められた」「前の窓の答えの無い問いが渡された」時、または guard の値を変えたい・見張りを足したい時に使う。
---

# 守りの hook（guard）

1 本の入口（`${CLAUDE_PLUGIN_ROOT}/scripts/guard.py`）を、プラグインの `hooks/hooks.json` が 4 つの出来事で回す。止めるのは PreToolUse（AI の道具の呼び出し）と Stop（AI の締めの差し戻し・上限つき）だけで、他は隣に文を出すだけ。どれも壊れた時は黙って通す。止められた・知らされた時はその場を出し直すだけで済ませず、その形が出た原因を細目 §3「まず構造を疑う」で探して直す。

## 見張りごとの直し方は 1 見張り 1 file

- 止めた文・知らせた文の末に `直し方と値の表の鍵: <path>` が付く。その file（この dir の `見張り/<見張りの名>.md`）を読んで直す。
- 見張りの一覧はここに書かない。どの見張りが在り、どの出来事で回るかの正本は `scripts/` の各見張りの file の頭の `HOOKS`、その見張りだけが読む値の表の鍵と既定の正本は同じ頭の `VALUES`。
- 1 つの file の形: 見出し（見張りの名と呼び名）・出来事とする事・止められた・知らされた時の直し方・値の表の鍵・射程の外。
- 見張りを足す PR は `scripts/<名>.py`（頭に `HOOKS` と `VALUES`）と `見張り/<名>.md` を足すだけにする。この SKILL・plugin の説明・`plugins/README.md`・`guard_common.py` に見張りの名や鍵を並べない（並ぶ PR が全部同じ所へ足して衝突した。`tests/test_guard_rules_per_watch.py` が赤にする）。

強制 push・main への push・本番への出荷・sudo は、オーナーが居ても居なくても settings の `permissions.deny` の受け持ち（ここでは重ねない）。

## 値の表（皆の鍵）

repo の根の `config/skill-values.json` の `"guard"`（無ければ既定で動く）。見張りごとの鍵は各 `見張り/<名>.md`。

```json
{
  "guard": {
    "unattended_env": ["AF_UNATTENDED"],
    "state_dir": "~/.claude/af-guard"
  }
}
```

- `unattended_env`: 真なら人のいない窓とみなす環境変数の名（夜の自走などの印）。人のいない窓では、離席の止めと答えの無い問いの控えは働かず、文脈の知らせは「止まる」側になる。返し先が別の窓の子の窓（最初の頼みの文に `（親窓 session_… の子）` か `返し先=session_…`）は、問う窓として離席の止めと控えが働き、文脈の知らせだけ「止まる」側。
- `state_dir`: 見張りが窓をまたいで持つ控え（答えの無い問いなど）の置き場（repo ごとに 1 つ）。窓の中だけで閉じる印（離席の印・文脈の知らせた印）は一時の箱に置く。

## この形の前に枝を切った PR が main を取り込む時

この SKILL の表・値の表の例・`guard_common.py` の `DEFAULTS` で衝突したら、main の側を取り、自分の行を移す:

1. 表の自分の行（する事・直し方）と射程の外の自分の項 → `見張り/<名>.md`（形は同じ dir の他の file）
2. 自分の見張りの鍵と既定 → 見張りの file の頭の `VALUES = {...}`（`guard_common.py` の `DEFAULTS` には足さない）
3. `python3 -m pytest -q tests/test_guard_rules_per_watch.py` が緑になるのを見る
