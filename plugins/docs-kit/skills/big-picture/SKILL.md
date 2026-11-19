---
name: big-picture
description: 仕組みの「全体の絵」を描く・合意した版に固定する・実物と照らす・「なんでこうなるの？」を絵の上で説明する skill。絵の正は JSON 1 つ（箱と矢印ごとに 何か／記録にある理由／オーナーの意図）で、HTML はそこから描き直す写し（4 タブ・白地・箱を押すと意図・層は 意図／起きた問題／説明）。意図が空の箱は赤い点と検査の警告。「全体の絵を描いて」「完成像を絵にして」「なんでこうなるの？」「絵どおりか照らして」で起動。全 agent 共通。
---

# 全体の絵（big-picture）

全体の絵は使い捨ての HTML でなく **設計の正**。設計の初めの合意・作り終わりの確かめ・問題が起きた時・仕組みを変える時に使う。必ず載せる物は 4 つ（照らす時の 4 欄も同じ）:

1. **解決したい問題と完成像**（`meta.problem`・`meta.goal`）
2. **部品と流れ**（箱 `boxes` と矢印 `arrows`）
3. **共通と個別の境**（箱ごとの `side`＝`共通`／`個別`／`外`）
4. **人が見る所・決める所**（箱ごとの `role`＝`決める`／`見る`。人の箱には必ず付ける）

## 道具（scripts/big_picture.py・標準ライブラリだけ）

```
python3 <この skill>/scripts/big_picture.py check   <絵.json>                 # 形の誤り＝exit 1／赤い点は警告（exit 0）
python3 <この skill>/scripts/big_picture.py render  <絵.json> -o <出す.html>  # check を通った絵だけ描く
python3 <この skill>/scripts/big_picture.py compare <合意した絵.json> <実物の絵.json>  # 差なし 0／差あり 1／照らせない 2
python3 <この skill>/scripts/big_picture.py explain <絵.json> <問題 id>        # 説明のチャットの文
```

HTML の型は `references/template.html`（手で直さない・外の物を読まない・`file://` で動く）。URL の `?tab=flow&layer=explain&p=<問題 id>` で開く所を指せる。

## 絵の JSON（form `big-picture/1`）

| 欄 | 形 | 意味 |
|---|---|---|
| `meta.title`・`meta.problem`・`meta.goal` | 文字列 | 題・解決したい問題・完成像 |
| `meta.kind` | `合意`／`実物` | オーナーと合意した版か、レビューの窓がコードから描いた実物か |
| `meta.version` | `YYYY-MM-DD.n` | 版。合意した絵を変える時は必ず上げる（同じ日の 2 本目は `.2`） |
| `meta.agreed` | `{by:"owner", date, record}` | 合意の印（`合意` に要る）。`record` はオーナーの決定の在り処を名で書く（公開の repo では URL を書かない） |
| `meta.drawn_from`・`meta.drawn_by` | 文字列 | 実物を描いた元（`<repo>@<SHA12>`）と描いた窓（`実物` に要る） |
| `tabs.<ctx｜flow｜arch>` | `{w, h, lanes?, areas?}` | 1. 全体の文脈／2. ワークフロー／3. 仕組みの構成。4. 決めた事と意図 は箱から自動で表にする。`lanes`＝`[{t, y, h}]`（流れの帯）・`areas`＝`[{t, k, x, y, w, h}]`（共通と個別の点線の枠） |
| `boxes[]` | `{id, tab, t, k, side, role?, x, y, w, h, what, why, intent}` | `k`＝`owner`（人）・`ai`（AI の窓）・`part`（部品）・`store`（置き場・記録）・`ext`（外の物）。`what`＝何か・`why`＝記録にある理由（AI の文・出所つき）・`intent`＝**オーナーの意図（聞いた物だけ・聞いていなければ `null`）** |
| `arrows[]` | `{from, to, label?}` | 同じタブの箱どうし |
| `problems[]` | `{id, title, date, at[], cause, via[], origin, why_here}` | 起きた問題の層（意図とは分ける）。`at`＝起きた所の箱・`cause`＝原因の箱・`via`＝原因から起きた所までの間の箱・`origin`＝`構造`／`単発`・`why_here`＝なぜここから起きたか |

- **意図は作らない**: 意図はオーナーに問うしか得られない。記録から拾った理由は `why` に置き、`intent` は `null` のまま＝**赤い点**（check が「意図をまだ聞いていない」と 1 行ずつ出す）。記録の解決策を意図として書かない。意図を問う時は核 §4 の選択肢の画面で、前提を 1〜2 文・選択肢は短く・推奨の印なし・1 画面 2〜3 問。
- **単発と書くのは**、絵の上で構造に原因が無いと示せた時だけ（`why_here` にその根拠を書く）。

## 使い方

1. **設計の初め**: 頼まれた仕組みの絵を描く（新しい仕組みは要件から・在る仕組みは先にコードから実物の絵を描く）。赤い点の意図を問うて埋め、`render` した HTML をオーナーに見せて OK を取る。OK が出たら `meta.kind: 合意`・`meta.agreed`・`meta.version` を付けて固定する。
2. **置き場**: 合意した絵の正は案件のページ（Javis は Notion の案件ページ）。土台（この repo）の絵だけは土台の repo の `docs/全体の絵.json`（UTC のレビューの窓も読むため）。repo ごとの置き場は値の表で指す（下）。HTML は毎回 JSON から描き直す写しで、正にしない。
3. **作り終わり**: 書いた窓と別の目（checker の review-pr 点 13）が、コードから実物の絵を **自分で** 描いて（書いた窓の申告・PR 本文の絵は使わない）`compare` で合意した版と照らす。差なし＝green／差あり＝red で main へ入れずに止め、差を見せてオーナーに決めてもらう。
4. **「なんでこうなるの？」と聞かれた時**: 3 つの形を全部出す。①`problems` に問題を足して `render` した絵を `?layer=explain&p=<id>` で渡す（起きた所・原因の箱に印・間の流れが光る）②`explain` の文をチャットに貼る（箱の名を挙げる）③原因の箱を押すと、その箱の意図と「なぜここから起きたか」が並ぶ（型がする）。足した問題は絵に残し、同じ箱で何度起きたかを「起きた問題」の層で見せる。
5. **仕組みを変える時**: 先に合意した絵を直して OK を取り（版を上げる）、その絵と照らしてから入れる。

## repo ごとの値（config/skill-values.json）

| 鍵 | 使う所 | 無い時の既定 |
|---|---|---|
| `docs-kit.big-picture.agreed` | 合意した絵の在り処（repo の中の path か、案件のページの名） | repo の根の `docs/全体の絵.json`。それも無ければ「絵が無い」＝照らせない（黙って通さない） |
| `common.delivery` | HTML の渡し方 | Artifact で publish（非公開のまま）か `file:///…` の絶対パスを 1 行 |

## 渡す前に

- `check` が `CHECK OK`（exit 0）。赤い点の数を見どころに 1 行で書く（埋まっていないと言う）。
- 渡す HTML は `render` で描き直した物だけ。チャットには URL 1 行と見どころ（赤い点の数・起きた問題の数）だけ。
