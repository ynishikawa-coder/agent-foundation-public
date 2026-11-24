# Actions の課金と workflow の形

GitHub Actions の workflow を書く・足す時の正本です。非公開の repo では、走らせ方の形がそのまま使う分の量になり、月の枠を使い切ると全部の非公開 repo の job が数秒で落ちます（2026-10 と 2026-11 に 2 度起きた）。形はここの 1 か所に置き、各 repo へは写しません。

## 数え方の前提

- **数えるのは非公開の repo だけ。** 公開の repo の標準の runner は数えない。
- **job ごとに分へ切り上げる。** 10 秒で終わる job も 1 分。job を細かく分けるほど切り上げの分が増える。
- **失敗した走り・待つだけの時間も数える。** 途中で落ちた走り、外の物を待って何もしていない時間（sleep・応答待ち・再試行の間）も runner が立っている間は数える。

## 既定の形

1. **PR の走りは、同じ PR の古い走りを止める。main への push は止めない。** 同じ PR に続けて push すると古い走りは結果を使わないのに最後まで数えられる。main への push の走りは記録として最後まで残す。

   ```yaml
   concurrency:
     group: ci-${{ github.workflow }}-${{ github.event.pull_request.number || github.ref }}
     cancel-in-progress: ${{ github.event_name == 'pull_request' }}
   ```

2. **全部の枝の push で走らせない。** `on: push` を絞らずに置くと、PR の走りと同じ中身が枝の push ごとにもう 1 度走る。push は `branches: [main]` に絞り、作業の枝は `pull_request` で照らす。
3. **新しい検査は、別の workflow でなく今の workflow の step に足す。** workflow・job が増えるごとに runner の立ち上げと分の切り上げが増える。
4. **待つだけの step には上限を付ける。** `timeout-minutes` を、記録に残る走りの時間（Actions の走りの一覧の所要時間）に余裕を足した値にする。上限が無いと、外の物が応答しない時に既定の 360 分まで数えられる。

## 起動の時の知らせ

土台の plugin core の起動の hook（`plugins/core/scripts/kaku.py` の `actions_text`）が、開いた repo の `.github/workflows/` を workflow の読み手（`public-guard/workflow_reader.py`）で読み、次の 2 つを file の名で窓に知らせます。止めはしません。

- PR（`pull_request`・`pull_request_target`）で走るのに、`concurrency` の `cancel-in-progress` が workflow にも全部の job にも無い。
- `push` で全部の枝に走る（`branches` も `tags` も無い・`branches-ignore` だけ・`branches` が `*` か `**`）。

公開の repo（公開の検査 `public-guard` を PR か push で呼ぶ repo、または GitHub が公開と答えた repo）には知らせません。公開か非公開かを窓で見分けられない時（origin が読めない・GitHub に聞けない）は、知らせる側に倒し、分からなかった訳を添えます。3・4 は字で見分けられないので知らせの対象外です（workflow を足す・直す時にここを読む）。
