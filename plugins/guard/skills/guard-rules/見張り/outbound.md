# outbound（外へ渡す道具の入力）

- 出来事: PreToolUse
- する事: 人や他の窓へ渡る道具の入力を出る前に照らし、崩れていれば AI だけを止める（人の操作は止めない）。`secret`＝MCP の道具（`mcp__…`）・Artifact・SendMessage の入力の全部の字と Artifact で出す file の中身に、鍵・トークンの形（正本は公開の検査 `public-guard/guard.py` の `SECRET_PATTERNS` を直に読む。見つからない時は止める）／`number`＝send_message・SendMessage の文と create_session の頼みの文に、番号（`E02`・`#3` の形）だけで中身の名の無い文（番号の見分けは ask_shape の中の言葉、中身の語は ask_shape の話題の語を直に呼ぶ）／`title`＝set_session_title と create_session の title が `<種類><状態> <作業名>` でない・手の窓（`🙋⏳ 手: <何を>`）を立てる頼みの文に目的・手順・済んだ目印・済んだ後が揃わない（正本は session-watch の `title_shape`・`HAND_PARTS`）

## 止められた・知らされた時の直し方

`secret`: 鍵の値を文から抜き、名だけ書く。鍵が要る相手には環境の秘密（request_credential）で渡す。正本が無いと出たら土台の plugin を市場から入れ直す（`AF_PUBLIC_GUARD` で path を渡せる）。作り物の見本だけ値の表の `outbound_secret_allow` で外す。`number`: 番号にそれが何か（物の名と中身）を同じ文で添える。誤りは `number_request_exempt`。`title`: skill `session-watch:title-mark` の形に直す。手の窓は頼みの文に 4 欄を書く

## 値の表の鍵

repo の根の `config/skill-values.json` の `"guard"` に書く（鍵・型・既定・当て方〔`against`＝当てる相手・`match`＝`whole` は相手の全体・`part` は相手の一部〕の正本は土台の `skill-values/schema.json`）。

```json
{
  "guard": {
    "outbound_secret_allow": ["^作り物の見本の字$"],
    "number_request_exempt": []
  }
}
```

## 射程の外

- 外へ渡す道具の入力の見張りの `secret` は公開の検査と同じ鍵の形だけ（パスワード・接続文字列・JWT など形の決まらない秘密は素通り）。返事の本文・Bash で外へ出す形（`curl`・`gh`）は見ない。`number` は字の形の推し量りで、番号の横に中身と関係ない語（「main に入れて」の main など）があれば通る。`title` は題の形だけで、種類が窓の返し先と合っているか（会話ログの最初の頼み）は見ない（session-watch の点検と Stop の差し戻しの受け持ち）。
