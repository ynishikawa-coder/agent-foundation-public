# paid_upstream（試験から有料の上流）

- 出来事: PreToolUse
- する事: 試験らしい path へ書く中身に、AI の API の鍵名・公式のエンドポイントがあれば止める。Bash で試験らしい path へ書く形（`>`・`>>`・`tee`・`sed -i`／`perl -i` の的）も、命令の文全体（heredoc の中身を含む）に印があれば止める

## 止められた・知らされた時の直し方

既定を録画の再生か偽物にする。本物が要るなら環境変数 1 本で切り替える関所を通し、その file に `PAID_UPSTREAM_GUARD` を書く

## 値の表の鍵

repo の根の `config/skill-values.json` の `"guard"` に書く（既定はこの見張りの file の頭の `VALUES`）。

```json
{
  "guard": {
    "paid_markers_extra": []
  }
}
```

## 射程の外

- 試験から有料の上流の見張りは、自分のサーバを経た中継を見ない。Bash は書く的と命令の文の推し量りで、書く中身が命令の外にある形（`cp`・`mv`・別の script の中で書く・`python -c` の中の `open`）は見ない。
