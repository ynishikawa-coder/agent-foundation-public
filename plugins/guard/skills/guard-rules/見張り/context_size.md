# context_size（文脈の量）

- 出来事: PostToolUse・Stop
- する事: 文脈が目安を越えた最初の 1 回だけ知らせる。越えた後、引き継ぎの跡（値の表 `context_handoff` の正規表現に当たる道具の呼び出し。既定は後継の窓を立てる `create_session`・返し先へ送る `send_message`・名に「引き継ぎ」か handoff を含む file を書く）が無いまま AI が締めようとしたら、締めを差し戻す（同じターンで `context_stop_max` 回〔既定 2〕まで・越えたら通して届ける）。引き継いだ後と、まとめ直して目安の手前に縮んだ後は差し戻さない

## 止められた・知らされた時の直し方

人のいる窓は区切りで引き継ぎを書き、後継の窓を立てて渡し、返事で続きをどの窓で見るかを書く。返し先が別の窓の窓・人のいない窓は今の段を終えて引き継ぎを書き、返し先へ送って止まる。別の道で引き継いだのに差し戻されたら、その道の形を `context_handoff` に足す。差し戻しそのものは `context_stop_max` を 0 で外す（PR とレビューを通す）

## 値の表の鍵

repo の根の `config/skill-values.json` の `"guard"` に書く（既定はこの見張りの file の頭の `VALUES`）。

```json
{
  "guard": {
    "context_limit": 300000,
    "context_stop_max": 2,
    "context_handoff": ["create_session\\b", "send_message\\b", "\"file_path\": \"[^\"]*(?:引き継ぎ|handoff)[^\"]*\""]
  }
}
```

## 射程の外

- 文脈の差し戻しは、引き継ぎらしい道具を呼んだかだけを見る（引き継ぎの中身・後継の窓の最初の出し方は見ない）。上限を越えたターンは通して届く。
