---
name: guard-rules
description: 守りの hook（guard の 4 つ）に止められた・知らされた時の直し方と、値の表での変え方。「戻せない操作が止められた」「試験に PAID_UPSTREAM_GUARD と言われた」「文脈が目安を越えたと出た」「答えの無い問いを出し直せと出た」時、または guard の値（文脈の目安・人のいない窓の印・足す印）を変えたい時に使う。
---

# 守りの hook（guard）

1 本の入口（`${CLAUDE_PLUGIN_ROOT}/scripts/guard.py`）を、プラグインの `hooks/hooks.json` が 3 つの出来事で回す。止めるのは PreToolUse だけで、他は隣に文を出すだけ。どれも壊れた時は黙って通す。

| 見張り | 出来事 | する事 | 止められた・知らされた時の直し方 |
|---|---|---|---|
| irreversible（離席中の戻せない操作） | PreToolUse | この窓で選択肢モーダルが答えのないまま閉じ、オーナーがまだ戻っていない間だけ、社外への送信・課金・本番への出荷・git で戻せない削除を止める | 戻せる作業を先に進める。その操作が要るなら同じ問いをモーダルで出し直し、答えが返ってから行う（答えが返るかオーナーが打てば解ける） |
| paid_upstream（試験から有料の上流） | PreToolUse | 試験らしい path へ書く中身に、AI の API の鍵名・公式のエンドポイントがあれば止める | 既定を録画の再生か偽物にする。本物が要るなら環境変数 1 本で切り替える関所を通し、その file に `PAID_UPSTREAM_GUARD` を書く |
| context_size（文脈の量） | PostToolUse | 文脈が目安を越えた最初の 1 回だけ知らせる | 人のいる窓は区切りで引き継ぎを書き後継の窓へ替える。人のいない窓は今の段を終えて引き継ぎを書き止まる |
| unanswered（未回答の台帳） | PostToolUse・SessionStart | モーダルが答えのないまま閉じた問いを台帳に積み、次の窓の冒頭で出し直させる。答えが返れば降ろす | 冒頭で渡された文面と選択肢をそのまま AskUserQuestion で出し直す（要約しない） |

締めで答えの無い問いを止めるのは `session-watch` の `unanswered` の受け持ち（ここでは重ねない）。

## 値の表

repo の根の `config/skill-values.json` の `"guard"`（無ければ既定で動く）。

```json
{
  "guard": {
    "context_limit": 300000,
    "unattended_env": ["AF_UNATTENDED"],
    "state_dir": "~/.claude/af-guard",
    "paid_markers_extra": [],
    "irreversible_bash_extra": [{"pattern": "\\bmy-deploy\\s+--prod\\b", "why": "本番への出荷"}],
    "irreversible_tools_extra": []
  }
}
```

- `unattended_env`: 真なら人のいない窓とみなす環境変数の名（夜の自走などの印）。人のいない窓では、離席の止めと台帳は働かず、文脈の知らせは「止まる」側になる。返し先が別の窓の子の窓（最初の頼みの文に `（親窓 session_… の子）` か `返し先=session_…`）も、文脈の知らせは「止まる」側。
- `state_dir`: 未回答の台帳の置き場（repo ごとに 1 冊）。窓の中だけで閉じる印（離席の印・文脈の知らせた印）は一時の箱に置く。

## 射程の外

- 戻せない操作の判定は列挙であって証明ではない（`find … -delete`・再帰なしの `rm -f`・`git restore .` などは素通り）。足したい形は値の表へ。オーナーが居る間の破壊操作は `permissions.deny` の受け持ち。
- 試験から有料の上流の見張りは、自分のサーバを経た中継と、Bash のリダイレクトで書く形を見ない。
