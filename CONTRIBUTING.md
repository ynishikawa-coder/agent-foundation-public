# 直す人のための決まり

この repo は、別々のアカウントで動く AI の窓（Javis＝ynishikawa-coder の窓と、UTC エージェント＝sharekeiri-gif の窓）が、同じ道具として一緒に使う土台です。どちらの窓も、この 1 枚の決まりで直し・試し・版を出します。

常時読む核の文（`plugins/core/核.md`）と、プラグインの配り方の器（`.claude-plugin/`）は別の持ち主が持ちます。ここには「直す人の手順」だけを書きます。

## 1. 枝と PR

- 枝の名は `claude/<日付>-<話題>`。日付は `YYYYMMDD`（例: `claude/20261111-hone`）。
- **1 枝 = 1 PR = 1 窓。** 1 つの窓が 1 本の枝を持ち、その枝から PR を 1 本だけ出す。他の窓の枝へは push しない。
- PR の base は `main`。本文は `.github/pull_request_template.md` の型で書く（冒頭 5 行: 親窓・書いた窓・job・触る path・検査）。
- **どちらの AI（Javis の窓・UTC エージェントの窓）からも、この repo へ直に PR を出してよい。**

## 2. レビュー

- レビューは **書いた窓と別の窓** がする（どちらのアカウントの窓でもよい）。書いた窓が自分で green を付けない。
- レビューした窓は PR に、次の 2 行で始まるコメントを残す。

  ```
  レビューした窓: <session id> 判定: green|red
  見た先端: <SHA の先頭 12 文字>
  ```

- `見た先端` が PR の今の先端と違う green は無効（見た後に push があった）。もう一度見てもらう。
- red の時は、同じ枝に直して push し、同じレビュー窓へ再レビューを頼む。

## 3. main へ入れる

- `main` へ入れるのは **Javis 側の親窓だけ**。書いた窓と別の窓の green が、今の先端に付いた PR だけを入れる。入れ方は **squash merge**。
- 書いた窓は `main` へ push しない。自分の PR を merge しない。
- 枝へ `main` を取り込む時は **merge**（`git merge origin/main`）。rebase と force push はしない（レビュー窓が見た SHA を消さないため）。
- 親窓から `合流済` が届いた枝には、もう push しない。続きは新しい枝で。

### main の守りの設定（推奨・repo の持ち主が GitHub の設定で入れる）

- `main` への直の push を禁止し、PR を必須にする。
- 必須の検査に CI の `check`（`.github/workflows/ci.yml`）を入れる。
- merge の仕方は squash だけを許す。
- `main` の force push と削除を禁止する。

## 4. 置かない物

- **顧客の語と実物を置かない。** 顧客の名前・ID・実データ・画面の写しを入れない。例は作り物で書く。
- **秘密を置かない。** 鍵・トークン・パスワード・接続文字列を、コード・試験・文書・PR 本文・ログのどこにも書かない。
- **土台は特定の業務を知らない。** 業務の語（特定業務の用語・計算の決まり）は、それを使う側の repo に置く。土台には、どの業務でも使える振る舞いと道具だけを置く。
- **個人の情報を置かない。** 個人を指すメールアドレス・電話番号・郵便番号・Notion のページや Google の文書の URL を書かない。commit の名義のメールは GitHub の noreply（`<id>+<名>@users.noreply.github.com`）か `noreply@anthropic.com` にする。
- **public なので外側も見える。** ファイルだけでなく、commit の説明・名義と PR の題・本文も世界に見える。どれにも上の物を書かない。
- 照らしの本体は `scripts/hygiene.py` の 1 本で、CI が止める（中身は `tests/test_hygiene.py`、外側の commit と PR は `scripts/checks/meta.sh`）。
  - **秘密と個人の情報**: 形で見る（表は `scripts/hygiene.py`）。
  - **業務の語**: `tests/data/denylist.txt`。足したい語があれば、その 1 行を PR で足す。
  - **顧客の語**: repo に書かない。環境から渡す。repo の secret `AF_DENY_BUNDLE`（使う側の repo の顧客の語の束 `pct1.…` と同じ値）か `AF_DENY_WORDS`（1 行 1 語）。手元は同じ名の環境変数か、`AF_DENY_WORDS_FILE` に置いた手元のファイルの path。**CI でどれも無い時は赤**（照合が飛んだまま緑にしない）。手元でどれも無い時だけ飛ばす。

## 5. 試験の置き方

**試験は小さく置く**。

- 試験は `tests/` に pytest で置く。ファイル名は `test_<何を見るか>.py`。
- この repo に置く試験は次だけ。
  1. **土台の自分の試験**（主）: 決まり・道具・skill・hook が約束どおり動くかを見る試験。骨の自己検査（一覧・置かない物・決まりの形）もここに入る。
  2. **作り物の例**: 国の率や表を使う所の、作り物の値で書いた例。
  3. **回帰の見張り**: 直した所の外の結果が変わらないことを見る試験（作り物の入力で）。
- 2・3 の入力は作り物だけ。`tests/data/` か試験の中に書く。**顧客の物（実データ・実 ID・実画面）はどの場合も置かない。**
- 1 つの試験は 1 つの約束を見る。名前で何を守るかが分かるようにする（例: `test_一覧の行が全部ある`）。
- まだ無い物（他の窓が先に置く物）に頼る試験は、無い間は `pytest.skip` で飛ばし、理由を書く。消さない・赤のまま置かない。
- 試験を飛ばして緑にしない。赤を消すために試験を消さない。
- 手元で走らせる: `python3 -m pytest -q tests/`

## 6. 検査の入口（CI）

- CI は `.github/workflows/ci.yml`。`main` への push と、すべての PR で走る。
- CI が呼ぶ入口は `bash scripts/check_all.sh` の 1 本だけ。中で pytest（`tests/`）と、`scripts/checks/*.sh` があればそれを順に走らせる。
- 検査を足す時は `scripts/checks/<名前>.sh` を足すか、`tests/` に試験を足す。`ci.yml` と `check_all.sh` は書き換えなくてよい。
- `check_all.sh` の最後の行が `check_all: 緑` なら通り、`check_all: 赤 …` なら止まり。

## 7. プラグインの一覧

- 何を・どの窓が・どこに置くかの正本は `plugins/README.md` の表。
- 物を置く PR は、同じ PR で自分の行の `状態` を替える（`未着手` → `作業中` → `出した`）。行を足す・消す時も同じ PR で。
- 表と実の dir が合っているかは CI が見る（`tests/test_plugins_list.py`）。

## 8. 版

- 版の出し方は `docs/版の出し方.md`。変わった事は `CHANGELOG.md` の `## [Unreleased]` に、PR ごとに 1 行足す。
