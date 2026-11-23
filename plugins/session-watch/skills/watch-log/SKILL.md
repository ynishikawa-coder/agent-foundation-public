---
name: watch-log
description: 会話ログ（transcript の JSONL）を手で点検し、返事の形と問いの崩れを拾う。「会話ログを点検して」「この窓の返事を点検して」で使う。
---

# 会話ログの点検

点検は会話ログだけを読む（環境の値・外の台帳・`get_session` の返りを見ない）。手で回す: `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/session_watch.py" <transcript.jsonl>`。拾った物を 1 行ずつ出し、拾えば exit 1（最後の行で細目 §3「まず構造を疑う」 を指す）。知らない印・読めないログ・照らしの故障は exit 2 で止まる（拾う物なしの緑に化けない）。会話ログの番（ターン）は人が打った行だけで切る（正本は plugin guard の `guard_common.starts_turn`＝別の窓・仕組みの知らせの行と要約の行は番を切らない）。拾われた物は下の直し方で出し直すだけで済ませず、返事の形が守る意図とのずれから入り、細目 §3「まず構造を疑う」で原因を探して直す。

`title`（今の題で直せる物）・`card`・`close`・`plain`・`inner`・`time`・`done`・`secret`・`neighbor`・`unread`・`nolog` は、Stop の hook（`session_watch.py --stop`）も同じ見張りで見て、崩れていれば次の頼みの時に UserPromptSubmit の hook（`--remind`）が隣へ知らせる（差し戻さない＝`decision: block` を出さない・返事はそのまま届き書き直さない・次の返事から合わせる）。知らせの文に直し方と誤った時の外し方を出す。誤って当たる行は値の表 `config/skill-values.json` の `session-watch.watch-log.reply_exempt`（行に当てる正規表現の並び・`inner`・`time`・`done` で見ない）に、中の言葉の字は `guard.ask_term_allow` に足す（PR とレビューを通す）。「問いを出す前に ❓ を付けていない」は過ぎた事で今は直せないので知らせない。ほかの札（`idk`・`unanswered`・`rest`・`hand`）は手で回す点検と知らせるだけ。`neighbor`・`unread`・`nolog` は AI には直せないので窓ごとに 1 回だけ知らせる。hook の口で照らしそのものが壊れた時も、窓は止めずに窓ごとに 1 回だけ壊れたと知らせる（黙って「崩れなし」にしない）。

## 札の目次

返事の形の札（`rest` から `hand`）と返事の中身の札（`inner` から `neighbor`）。拾う時・直し方の全文と、点検の外（見ない物）は `札.md`。

| 札 | 拾う物（拾う時と直し方の全文は `札.md` の同じ札の節） |
|---|---|
| `rest` | 締めの `AI がこの後やること` が「なし」でないのに、その窓で残りを動かす手（`create_session`・`send_message`・`send_later`・`subscribe_pr_activity`・背で走らせた `Agent`・`Workflow` 等）を一度も打っていない（題が ❓／💤 の待ちの窓・✋ の手の窓と、既に子窓・見張りを動かした窓は除く）。直し方: 子窓や背で走る助手に頼む・PR を見張る・後で起こすのどれかを打ってから締める（核 §5） |
| `title` | 窓の題の目印の崩れ・問いの前の ❓ の抜け |
| `close` | 締めの 2 行が無い |
| `card` | 1 行目が 4 札で始まらない |
| `plain` | 選択肢の画面なしに平文の問いで締めた |
| `idk` | 選択肢の画面に「分からない」が無い |
| `unanswered` | 答えの返っていない選択肢の画面の問い |
| `hand` | 手の窓の型の欠け・人の手の手順を手の窓の外で直に書いた |
| `inner` | 人への返事の中の言葉（中身の無い番号・窓の id など） |
| `time` | 日本時間の印の無い時刻 |
| `done` | ✅ の言い切りに言い切らない語 |
| `secret` | 返事の鍵・トークンの形 |
| `unread` | 会話ログの読めない行 |
| `nolog` | hook の口で会話ログが無い |
| `neighbor` | 正本が見つからず照らせない・`reply_exempt` に読めない形 |

## repo ごとの値

値の表は使う repo の根の `config/skill-values.json`（在る時だけ読む・無ければ外す形なしで照らす）。

| 鍵 | 中身 | 既定 |
|---|---|---|
| `reply_exempt` | 返事の行に当てる正規表現の並び。当たる行は `inner`・`time`・`done` で見ない（引いた記録・誤って止まる形だけ。PR とレビューを通す）。読めない形は捨てて `neighbor` で名指す | `[]` |
