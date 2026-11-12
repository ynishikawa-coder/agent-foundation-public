---
name: verify
description: 主張を真実源で 1 度確かめる。着手前は受けた self-report（引き継ぎ・完了報告・memory）と自分の「止まった/未着手」断定・「原因は X」の因果診断を、終わる前はゴールの完了を Completion Report（4 状態）で確かめる。コードの完了は PR の CI 緑＋別窓レビューが決める＝ここはコードの外（外の文書・本番 URL・表示層）。「確認して」「抜け漏れない？」「嘘ない？」「本当に完了？」で起動。合言葉:「抜け漏れない?」「原因を調べて」「なぜこうなった」「diagnose」「調べて直して」「原因究明」「何が原因?」「本当に完了?」。
---

# /verify — 確かめてから言う

達してないなら達してないと言う。silent failure は禁止。設計を疑う、機構を疑わない。

## repo ごとの値（config/skill-values.json）

repo ごとに違う値は、repo の根（`git rev-parse --show-toplevel`）の `config/skill-values.json` の `dev-flow.verify.<鍵>` と `common.<鍵>` から読む。**鍵が無い・値が空なら右の既定で動く**。

| 鍵 | 使う所 | 無い時の既定 |
|---|---|---|
| `code_done_rule` | コードの完了の決め方の正本 | PR の CI 緑＋別の窓のレビュー 1 回 |
| `completion_states_doc` | 4 状態の定義表の正本 | この SKILL の §2 |
| `completion_sop` | 上位の完了判定の正本 | 無し |
| `report_writer` | Completion Report を書く役（書かない窓） | この窓が書く |
| `report_place` | Completion Report の置き場の決まり | 会話の返事の中 |
| `learning_record` | Stopped / Failed の学びの書き先 | 無し（返事の中に 1 行） |

## 範囲（クラウドが主）

- **コード（repo の中身）の完了は PR の CI 緑＋別の窓のレビュー 1 回で決まる**（正本は表の `code_done_rule`）。ここで差分を読み直して判定し直さない。照らすのは PR の事実だけ（`gh api repos/<owner>/<repo>/pulls/<番号>` の state・merged と check-runs の結論）。
- **この skill の本務はコードの外**: 外の文書・DB の行・本番 URL・表示層・外部の状態についての主張と、自分の否定的断定・因果診断。
- Completion Report を誰が書くか: 表の `report_writer` に在ればそれに従う（無ければこの窓が書く）。

## 1. 着手前（軽い確かめ）

**疑う対象は 2 種**＝ⓐ受けた self-report（完了報告・引き継ぎ・memory・過去議事録の「決定」「完了」）ⓑ自分が出した帰結の断定（「停止した」「消えた」「壊れている」「未着手」「未完了」と、肯定形の因果診断「原因は X」「X のせいで」）。どちらも**主張**であって事実ではない＝その上に処方（直しの提案・オーナーへの作業依頼・再設計）を積む前に、live の真実源で 1 度確かめる（診断を処方より先に置く）。派生・キャッシュ（watchdog cache・一覧の 404 等）から重い否定的断定を出さない。

| 主張 | 真実源 | 照合 |
|---|---|---|
| ファイル作成・編集済 | filesystem | `ls -la`・`wc -c`（空ファイルを「作成済」と読まない）・Read |
| commit・push・PR | GitHub | `gh api`（PR は state・merged と check-runs の結論だけ） |
| 文書・ページの作成・更新（外の文書の道具） | その道具 | 読みの道具で取り直す（404・保管・ごみ箱なら critical） |
| deploy 済・本番に出た | 本番 URL | HTTP GET（2xx/3xx ＋期待の欄・文言が本番の応答に在る） |
| 外のサービスへの投入済（データ・関数） | そのサービス | そのサービスの読みの道具・API で実値を取る |
| 因果診断「X のせいで Y」 | 実ログ・実挙動・実コード | live で 1 度裏取り（相関を原因と即断しない・裏取りが無ければ処方の規模を決めない） |
| タスク・案件の「未着手/未完了」 | 人・相手の実際の動き | 返事・成果物で確かめる（凍結したタスクの表を現状の真実源にしない） |

**影響範囲（mapping・schema・config・backend の定数・frontend の filter・外の DB の項目を 1 か所でも触った時は必須）**: 直した所だけでなく関連の entity・利用箇所の実値を照らす（直した所だけ見て完了にすると、関連箇所との食い違いが silent failure になる）。単一ファイルの文言だけの直しは省いてよい。

省略してよいのは確かめの手間が着手の手間を上回る時だけ。次は**省略しない**: 不可逆操作（削除・上書き・強制 push）・外部送信・課金・他の窓への委譲・規律や schema の改訂・真因分析を文書にする時。

出力:

```
判定: PASS / STOP / INCONCLUSIVE
照合結果:
- <主張>: 真実源 = <X>、結果 = 一致 / 不一致
差分（あれば）: self-report は <A> と言ったが真実源は <B>
次の一手: 採用 / 戻し / 部分採用
```

## 2. 終わる前（Completion Report）

1. **4 状態で機械的に判定**: Completed / Partially Completed / Stopped / Failed（定義表の正本は表の `completion_states_doc`、上位の完了判定は `completion_sop`＝在る時だけ）。Completion Criteria を 1 項目ずつ yes/no で照らす。「概ね完了」「総合的に見て」は書かない。
2. **一時しのぎを含めば Partially**＋恒久の対応を残りに書く（当て物を含んで Completed にしない）。
3. **設計と実物の差分を必ず書く**（無ければ「差分なし」と項目名つきで）。差分は「[改修] <案件>: 設計は X → 実物は Y（<設計書 path/版>）」の 1 行で残りに書く。
4. 真実源は §1 の表。web 面は本番 URL の HTTP 実測を証拠に付ける（自己申告・repo の状態だけで完了にしない）。UI を変えたゴールは主要導線の実ブラウザ完走・console/network の重大エラー 0・空/エラー/読み込み中の状態・SP=375 を含む画面幅を足す（Playwright か Claude-in-Chrome）。
5. MCP も直接の手段も無い時は人が運ぶ（逐語のコピペか原画像。人の「確認 OK」の要約は self-report 扱い）。

```markdown
# Goal Completion Report — <タスク名>
## Goal Status: Completed / Partially Completed / Stopped / Failed
## Completed Criteria / Unmet Criteria（未達は何が・なぜ）
## 設計と実物の差分
## Verification Results（Check｜Status｜真実源｜Notes）
## Unverified Items（確かめられなかった物と理由・無ければ「なし」）
## Runtime Stop Conditions Triggered（Stopped の時だけ）
## オーナーの業務がどう変わったか（真の完了条件）
## 次の作業
━━━ 🎯 次の作業 ━━━
🏁 終わり方: <① 閉じる（残り: なし） / ② メモ渡し（残り: <中身>）>
📊 状態: <4 状態のどれか>
🚀 オーナーの初手: <採用 / 戻し / 部分採用 の 1 つ ＋ 具体の一手>
⚠️ 人がやる残作業: <無ければ「なし」>
📎 参照: <絶対 path か URL・無ければ「なし」>
━━━━━━━━━━━━━━━
```

末尾は 🎯 の箱 1 個で終える（置き場は表の `report_place`・チャットは ①/② の 1 行＋URL だけ）。Stopped / Failed の時は、学びを表の `learning_record` へ（無ければ返事の中に 1 行）。

## やりがちな間違い

1. ❌ 「実装完了」を信じて即着手 → ✅ 着手前に 1 度確かめる
2. ❌ 「概ね完了」「全体としては OK」 → ✅ 4 状態のどれかで書き、Partially なら未達を並べる
3. ❌ 確かめられなかった物を「確認済」に丸める → ✅ Unverified Items に書く
4. ❌ Stopped を Completed に丸める → ✅ Runtime Stop Conditions に当たれば Stopped
