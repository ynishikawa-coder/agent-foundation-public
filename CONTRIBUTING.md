# 直す人のための決まり

この repo は、別々のアカウントで動く AI の窓（Javis＝ynishikawa-coder の窓と、UTC エージェント＝sharekeiri-gif の窓）が、同じ道具として一緒に使う土台です。どちらの窓も、この 1 枚の決まりで直し・試し・合流します。

常時読む核の文（`plugins/core/核.md`）と、プラグインの配り方の器（`.claude-plugin/`）は別の持ち主が持ちます。ここには「直す人の手順」だけを書きます。

## 1. 枝と PR

- 枝の名は `claude/<日付>-<話題>`。日付は `YYYYMMDD`（例: `claude/20261111-hone`）。
- **1 枝 = 1 PR = 1 窓。** 1 つの窓が 1 本の枝を持ち、その枝から PR を 1 本だけ出す。他の窓の枝へは push しない。1 本に入らなかった仕事は各社の原因の台帳の行にし、直す窓を付けて PR 本文の「残り」に書く（細目 §3）。土台を直す時は、使う側の repo に残った写しも同じ仕事の中で直し、PR 本文の「使う側の写しの残り」に書く（細目 §7「土台の直しの終わり」）。
- PR の base は `main`。本文は `.github/pull_request_template.md` の型で書く（冒頭 3 行: 書いた窓・job・検査。親窓の欄は置かない＝窓の親は照らせない写しにせず、サーバの記録〔`get_session` の `parent_session_id`〕を読む。触った path は本文に手で書かず、レビューの窓が `git diff --name-only` で取る）。書いた窓は先端の commit の `Claude-Session:` の窓（直しの往復で別の窓が commit したらその窓に書き換える。違えば CI の job check が赤＝`plugins/checker/scripts/pr_writer.py`）。
- **どちらの AI（Javis の窓・UTC エージェントの窓）からも、この repo へ直に PR を出してよい。**

## 2. レビュー

- レビューは **書いた窓と別の窓** がする（どちらのアカウントの窓でもよい）。書いた窓が自分で green を付けない。
- レビューした窓は PR に、次の 2 行で始まるコメントを残す。

  ```
  レビューした窓: <session id> 判定: green|red
  見た先端: <SHA の先頭 12 文字>
  ```

- `見た先端` が PR の今の先端と違う green は無効（見た後に push があった）。もう一度見てもらう。
- red の時は、指摘を単発の手直しで済ませず、外れた意図とのずれから入って細目 §3「まず構造を疑う」で原因を探して直し、同じ枝に push して、同じレビュー窓へ再レビューを頼む。

## 3. main へ入れる

- `main` へ入れるのは **親窓**（Javis の窓・UTC エージェントの窓のどちらでもよい）。書いた窓と別の窓の green が今の先端に付き、全体の絵と照らして差が無い PR だけを入れる。入れ方は **squash merge**。
- 入れる前にオーナーへ「入れてよいですか」と聞かない。揃える物（レビュー green・試験が緑で衝突なし・実物が合意済みの全体の絵どおり）と、絵と差がある時に止めて聞く事、絵の照らし方（checker の review-pr 点 13）は、核 §7 と細目 §7 の「main へ入れる」が正本。
- 書いた窓は `main` へ push しない。自分の PR を merge しない。
- 枝へ `main` を取り込む時は **merge**（`git fetch origin main && git merge origin/main`＝取り直してすぐ取り込む。手元の origin/main は fetch から時間が空くと古い）。rebase と force push はしない（レビュー窓が見た SHA を消さないため）。
- 親窓から `合流済` が届いた枝には、もう push しない。続きは原因の台帳の行にし、新しい枝の窓をその行の直す窓にする。

### main の守りの設定

正本は `.github/rulesets/main.json`。直す時は AI がこの file を PR で直し、main に入ると CI の job `rulesets` が GitHub へ書き戻す（クラウドの窓は設定の口へ直に書けない・鍵 `RULESET_TOKEN` が無い時は書き戻しが赤で止まる）。鍵は environment `rulesets` の秘密に置く（repo の秘密に置くと、どの枝の workflow からも読める）。持ち主が 1 回だけ、Settings → Environments で `rulesets` を作り、Deployment branches を「Selected branches and tags」にして `main` だけを足し、Environment secrets に `RULESET_TOKEN`（この repo だけ・Administration: Read and write の鍵）を置く。書く前に `scripts/ruleset_apply.py` が枝の制限を読み、main だけでなければ書かずに赤で止まる。

- `main` への直の push を禁止し、PR を必須にする。
- 必須の検査に CI の `check`・`public-guard`・`plugin-smoke`（`.github/workflows/ci.yml`）を入れる。土台は main の先端をそのまま全部の窓へ配るので、`plugin-smoke`（使う側と同じ入れ方で入れて起動する試験）が合流の前の守り。`public-guard` か `plugin-smoke` が必須でないと見回りが知らせる（`docs/公開の検査.md`）。
- merge の仕方は squash だけを許す。
- `main` の force push と削除を禁止する。

## 4. 置かない物

- **顧客の語と実物を置かない。** 顧客の名前・ID・実データ・画面の写しを入れない。例は作り物で書く。
- **秘密を置かない。** 鍵・トークン・パスワード・接続文字列を、コード・試験・文書・PR 本文・ログのどこにも書かない。
- **土台は特定の業務を知らない。** 業務の語（特定業務の用語・計算の決まり）は、それを使う側の repo に置く。土台には、どの業務でも使える振る舞いと道具だけを置く。
- **個人の情報を置かない。** 個人を指すメールアドレス・電話番号・郵便番号・Notion のページや Google の文書の URL を書かない。commit の名義のメールは GitHub の noreply（`<id>+<名>@users.noreply.github.com`）か `noreply@anthropic.com` にする。
- **public なので外側も見える。** ファイルだけでなく、commit の説明・名義と PR の題・本文も世界に見える。どれにも上の物を書かない。
- 照らしは公開の検査（`public-guard/guard.py`・`docs/公開の検査.md`）の 1 本。CI の job `public-guard` が中身・歴史・commit と PR の外側を照らして止める。手元は `scripts/checks/public_guard.sh`（渡す値は ci.yml の job `public-guard` の呼び口の `with:` から workflow の読み手で読む＝写さない）。PR の題・本文とコメントは、窓が出す前にも守りの hook（guard の `pr_text`）が同じ本体で照らす。
  - **秘密と個人の情報**: 形で見る（表は `public-guard/guard.py`）。
  - **業務の語**: `tests/data/denylist.txt`。足したい語があれば、その 1 行を PR で足す。
  - **顧客の語**: repo に書かない。repo の secret `AF_DENY_BUNDLE`（Javis の顧客の語の束 `pct1.…` と同じ値）か `AF_DENY_WORDS`（1 行 1 語）から渡す。手元は同じ名の環境変数か `AF_DENY_WORDS_FILE`。**CI でどれも無い時は赤**。手元でどれも無い時だけ飛ばす。

## 5. 試験の置き方

**試験は小さく置く**。

- 試験は `tests/` に pytest で置く。ファイル名は `test_<何を見るか>.py`。
- この repo に置く試験は次だけ。
  1. **土台の自分の試験**（主）: 決まり・道具・skill・hook が約束どおり動くかを見る試験。骨の自己検査（一覧・置かない物・決まりの形）もここに入る。
  2. **作り物の例**: 国の率や表を使う所の、作り物の値で書いた例。
  3. **回帰の見張り**: 直した所の外の結果が変わらないことを見る試験（作り物の入力で）。
- 2・3 の入力は作り物だけ。`tests/data/` か試験の中に書く。**顧客の物（実データ・実 ID・実画面）はどの場合も置かない。**
- 1 つの試験は 1 つの約束を見る。名前で何を守るかが分かるようにする（例: `test_一覧の行が全部ある`）。
- 道具（script・hook）と試験の頭の説明は `意図:`・`課題:`・`原因:` の 3 欄で書き、`なぜ在るか:` の 1 欄に混ぜない（根治の 5 段＝細目 §3）。この形は `tests/test_atama_3_ran.py` が照らす。
- **決まりの文は、消すと試験が赤になる形で照らす。** 核・振る舞いの既定・細目の文は `tests/test_rule_holes.py` が 1 文ずつ消して決まりの試験を回し、赤にならない文は `tests/data/試験で守らない文.txt` に載った物だけを許す。新しい文・書き換えた文は、その文を照らす試験（文をそのまま照らすのが一番強い）を同じ PR で足す。語がどこかに在るかだけの照らしは、照らしていない文を消しても緑のままになる。
- **新しい試験は守る約束の名の新しい file に置く**（元から在る `tests/test_*.py` の試験を増やさない）。並ぶ PR が同じ file の末尾へ足すと 1 本入るたびに残りが全部衝突するので、足す所を PR ごとに分ける。直す・消す・parametrize の行を足すのはよい。AI の窓の枝（`claude/`）の PR の差分で `scripts/pr_shape.py` が照らす（CI の `check`・人の枝は止めない）。
- まだ無い物（他の窓が先に置く物）に頼る試験は、無い間は `pytest.skip` で飛ばし、理由を書く。消さない・赤のまま置かない。
- 赤は試験を飛ばす・消すで消さず、その試験が守る意図とのずれから入って細目 §3「まず構造を疑う」で原因を探して直す。
- 手元で走らせる: `bash scripts/pytest.sh -q tests/`（pytest の設定の file・環境変数・tests の外の conftest・plugin を読まない入口。pytest を直に呼ばない）

## 6. 検査の入口（CI）

- CI は `.github/workflows/ci.yml`。`main` への push と、すべての PR で走る。
- CI の job は `check`（入口は `bash scripts/check_all.sh` の 1 本）と `public-guard`（公開の検査）と `plugin-smoke`（PR の枝を使う側と同じ入れ方で入れて窓を起動し、核の差し込み・守りの hook・skill の読み込みを見る。`scripts/plugin_smoke.py` は PR の枝の先端の木（`pr-head`）で、本物の claude を要る試験＝印 `real_claude` の付いた試験は PR の枝に main を合わせた木で試験の入口 `bash scripts/pytest.sh -m real_claude --af-judge=real-claude tests/` で全部（印の試験が 1 本でも飛ぶ・xfail・外れると赤）。合わせた木で回すので、枝と main の変更が合わさって初めて壊れる組み合わせを合流の前に見つける）と、止めない知らせの `overlap`（開いている他の PR が同じ file の同じ行の辺りを書き換えていれば名指す・見ていない時は exit 3 と注記 `::warning::` で名指し、緑の印にしない・`scripts/pr_overlap.py`）。`check_all.sh` は中で pytest（`tests/`）と、`scripts/checks/*.sh` があればそれを順に走らせる（claude の命令が無い所では印 `real_claude` の試験を飛ばす。飛ばす条件は `tests/conftest.py` の 1 か所で、試験の file に書かない。その条件は `scripts/checks/conftest_teeth.sh` が conftest を読まない pytest で照らす）。
- 検査を足す時は `scripts/checks/<名前>.sh` を足すか、`tests/` に試験を足す。`ci.yml` と `check_all.sh` は書き換えなくてよい。`scripts/checks` には 1 段の `*.sh` だけを置く（`.py` や下の dir は回らないので赤）。その場で照らせない検査は `scripts/af_unchecked.sh` の `af_unchecked 対象外|照らせない <訳>` で終える（訳の無い終わり方 3 は赤・CI の「照らせない」は赤）。
- pytest の版は `scripts/pytest_plugin/requirements.txt` の 1 か所。試験が要る部品（node・playwright・ブラウザ）が無くて飛ばす時は `tests/needs.py` を試験の頭で呼ぶ。小箱で入口を回す試験は `tests/entry_box.py` の `box_env` の環境で回す。tests/ の conftest には印の登録と印 `real_claude` の飛ばす条件の外の hook を置かない（結果・集めを変える hook は赤）。
- `check_all.sh` の最後の行が `check_all: 緑` なら通り、`check_all: 赤 …` なら止まり。緑の行は回した場を書く: `場 CI` は CI の数え方、`場 手元（…）` は飛ばしと照らせない検査を赤にしていない手元の緑（CI の緑と同じに読まない。PR 本文の「検査:」には CI の行を書く）。止まったら赤の行を 1 つずつ潰さず、細目 §3「まず構造を疑う」で原因から直す。

## 7. プラグインの一覧

- 何を・どの窓が・どこに置くかの正本は `plugins/README.md` の表。
- 物を置く PR は、同じ PR で自分の行の `状態` を替える（`未着手` → `作業中` → `出した`）。行を足す・消す時も同じ PR で。
- 表と実の dir が合っているかは CI が見る（`tests/test_plugins_list.py`）。

## 8. 配り方と「壊れる:」変更

- 版は無い。窓は setup script で **main の先端** を入れる（`docs/核の届け方.md`）。合流した時から、次に立つ窓に届く。版の印を打つ手・版を上げる PR は無い。立った後に土台が変わった窓は、AI が自分で新しい窓へ引き継ぐ（同じ文書の「古い土台で立った窓」）。
- 使う側に関係する変更は、PR ごとに自分の file を `CHANGELOG.d/<日付>-<話題>.txt` に 1 つ足す（`CHANGELOG.md` へは足さない・書き方は `CHANGELOG.d/README.md`）。使う側の振る舞いが変わる物は、行の札を「壊れる」にする。
- **「壊れる:」変更は 2 段で入れる**（main の先端は合流した時に全部の窓・全部の公開 repo へ届き、版で待ってもらえないため）:
  1. **1 段目**: 土台は新しい形を足し、古い形も通し続ける（新旧の両方を受ける）。使う側の物（repo の file・setup script の行）が古い形を持つなら、その形を `plugins/core/古い形.json` に 1 行足す（見つけ方の正規表現・当たる作り物の例・直し方）。足すと、古い形が残る repo を開いた窓に plugin core の起動の hook が file の名で知らせ、その窓が同じ仕事で消す（`docs/核の届け方.md`「使う側に残った写し・古い形」）。環境の setup script は土台の入口 `scripts/setup_plugins.py` を通らない古い形を、起動の hook が名指しする。断片の行の札を「壊れる（1 段目）」にし、使う側がやる事を書く。
  2. **使う側が移る**: 土台の外の物（使う側の repo・環境の setup script・Artifact 型など）を、土台を直した同じ仕事で直す（オーナー決定 2026-11-19）。使う側の一覧は公開の repo に置かない（repo の名が顧客の語を含みうる）。Javis 側は Notion の原因の台帳と同じ所の「土台の使う側」、UTC 側は連絡板の issue に持つ。2 つのアカウントにまたがる物（UTC の repo と環境）は連絡板の issue で頼む。
  3. **2 段目**: 使う側が移ったのを **記録で** 確かめてから、古い形を畳む PR を出す。確かめは `python3 plugins/core/scripts/kaku.py olds <使う側の一覧の各 repo の checkout>...` が全部「古い形 0」（読めない repo は名と理由を書く）。同じ PR で `古い形.json` の行を消す。断片の行の札を「壊れる（2 段目）」にし、olds の出力（見た repo と結果）を書く。一覧に無い使う側が古い形のまま残っても、開いた窓に起動の hook が名指しする。
  - 見出しの名・太字の名（`refs.py list` が約束として出す名）を変える・消すのは、使う側の名の指しを壊すので「壊れる」。節の番号だけを変えるのは壊れない（使う側は名で指す・`docs/核の届け方.md`「使う側が土台の文書を指す」）。
  - 土台の中だけで閉じる変更（使う側の物が古い形に頼っていない）は 1 段でよい。その時は行に「土台の中だけ」と書く。
  - レビューは点 10（呼ぶ側と呼ばれる側）で、この 2 段を見る（skill `checker:review-pr`）。
