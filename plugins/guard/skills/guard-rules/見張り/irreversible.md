# irreversible（離席中の戻せない操作）

- 出来事: PreToolUse
- する事: この窓で選択肢モーダルが答えのないまま閉じ、オーナーがまだ戻っていない間だけ、DB の破棄・メールの送信・Notion の物理削除・git で戻せない rm -r を止める（作業場〔一時の置き場〕と変更の無い作業部屋の掃除は通す）

## 止められた・知らされた時の直し方

戻せる作業を先に進める。その操作が要るなら同じ問いをモーダルで出し直し、答えが返ってから行う（答えが返るかオーナーが打てば解ける）

## 値の表の鍵

repo の根の `config/skill-values.json` の `"guard"` に書く（鍵・型・既定・当て方〔`against`＝当てる相手・`match`＝`whole` は相手の全体・`part` は相手の一部〕の正本は土台の `skill-values/schema.json`）。

```json
{
  "guard": {
    "irreversible_bash_extra": [{"pattern": "\\bmy-db\\s+--wipe\\b", "why": "DB の破棄"}],
    "irreversible_tools_extra": ["^mcp__[^ ]*__delete_item$"]
  }
}
```

## 射程の外

- 戻せない操作の判定は列挙であって証明ではない（`find … -delete`・再帰なしの `rm -f`・`git restore .` などは素通り）。足したい形は値の表へ。
