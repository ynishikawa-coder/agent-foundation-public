---
name: pdf-read
description: PDF 完璧読取＝実務 PDF（集計表・請求書・帳票など数字が主役の文書）の数字を一つも黙って落とさず・間違えず・「何の数字か」（行/列ラベル）まで正しく結んで Excel/Word/JSON へ落とす skill。**特別な指示が無ければ既定で「完全再現」**（原本そっくり×抜け漏れゼロ・加工は別仕事）。「PDF読んで」「PDFをExcelに」「この表/請求書をExcelに」「PDF読み取って」「PDFから数字抜いて」または /pdf-read <pdf> で起動。
---

# /pdf-read — PDF 完璧読取（数字を黙って間違えず・正しいラベルに結んで Excel/Word へ）

> **渡してよい基準（唯一の合格線）**: engine 出力の **`clean=True` かつ BLOCKING flag ゼロ** の時だけ「裏が取れた」と言える。**`fail=0 かつ 未解決=0` だけでは合格にしない**（clean は値の忠実〔VF〕と位置の忠実〔PF〕の**両軸**が裏取れて初めて立つ＝どちらか一方でも未裏取りなら `clean=False`）。判断は必ず `clean` と BLOCKING flag を合わせて見る。scanned・digital-no-cjk は clean の外（数字は拾えてもラベル未確定＝要 Vision）。

## ★ 既定モード＝完全再現（このスキルの目的・owner の決定）

**特別な指示が無い限り、このスキルは常に「完全再現」を出す**（＝超ハイクオリティな原本忠実再現。owner が明示で「数字だけ」「この表だけ」等に絞った時のみ縮小する）。

**目的**: PDF に **何が・どういうデータで・何のために書かれているか** を、**一つも漏らさず正確に読み切る**こと。加工（別用途への変換・集計・再設計）は **スコープ外＝下流の別エージェント／別指示の仕事**。このスキルの完全再現出力さえ在れば後段で自由に加工できる、という位置づけ＝入口の「正確な全量抽出」に責務を集中する。「ただ読むだけ」なら PDF をそのまま貼れば済む＝**わざわざスキルにする意味は"完全再現"にある**（商品化を狙う品質水準）。

**既定で必ず走る完全再現の手順**（engine の慎重な headless 出力＝`clean=False` で止めない）:
1. engine 実行（数値抽出＋検算＋完全性台帳）。数字は engine が機械証明。
2. **Vision で全ラベル・見出し・氏名を復元**。特に **digital-no-cjk（Print-To-PDF で日本語が text 層に無い）／ scanned は必須**。潰れた多段ヘッダー・区分ごとの分割・属性のブロックも **原本の並びのまま**再構成（1 情報も落とさない）。
3. **sum-linked セルは列/行合計の算術で"位置まで"全数検証**（値の一致だけで満足しない＝隣列混入を捕まえる）。
4. **検算材料の無いセル（氏名・日付・独立した日数・人数など）は "要目視" と明示**（silent 禁止）＝原理的に証明不能な唯一の残り。
5. **開ける形（Excel／スプレッドシート）で提出**。

**二層の合格線（矛盾でなく役割分担）**:
- **①engine `clean`（機械層）** = sum-linked セルの値〔VF〕・位置〔PF〕の **機械証明**。mutation/golden テストの load-bearing・不変（下記「渡してよい基準」の芯）。
- **②完全再現（owner 向け成果物層・このスキルの既定納品物）** = 原本そっくり×抜け漏れゼロ。**単軸台帳（行計のみ）や digital-no-cjk は engine `clean=False` が正**＝①が False でも Vision 層で②を完成させる（①の False を"未完成／渡せない"の理由にしない）。②に残る不確実性は手順4の "要目視" で正直に可視化する。

## 何をする skill か（抽出忠実 2 軸を芯に）
これは「数字を取るスキル」ではなく **「PDF を正しく読み切るスキル」**。どんな実務 PDF（集計表・請求書・帳票など**数字が主役の構造化文書**）でも、数字を一つも黙って落とさず・間違えず、かつ **「何の数字か」（正しい行ラベル・列見出しに結ぶ）** まで含めて **Excel / Word / JSON** へ落とす。「完璧」は主張でなく**裏取り**で担保する＝裏が取れた箇所だけを clean とし、取れない箇所は必ず旗を立てて人に見せる（silent failure 禁止）。

**芯の保証は抽出忠実の 2 軸**:
- **値の忠実（VF: value fidelity）** — 出力した数字の桁列が原本ページの桁列と一致する。合計の有無に依存せず常に対象。
- **位置の忠実（PF: position fidelity）＝「何の数字か」** — その数字が正しい行ラベル・列見出し・表に結びついている（例:「品目A／取引先B／6月分」）。ここが難所＝合計の無い文書でも隣列への混入を捕まえる。

**文書内の合計整合（行合計・列合計）は "在れば足す" ボーナス**。理由＝行/項目の和が原本に必ず在るとは限らない＝合計の無い PDF でも読み切る（owner の要件）。**合計が無い＝裏取り不能ではない**（VF/PF の独立チャネルが引き継ぐ）。

**起動**: 「PDF読んで」「PDFをExcelに」「この表/請求書をExcelに」「PDF読み取って」「PDFから数字抜いて」または `/pdf-read <pdf>`。

## 2層構造（engine headless ⊥ この skill の Vision 薄層）
- **engine（`<engine>`）**（純 Python・Claude 非依存・移植可）: PDF→座標クラスタ→検算→中立IR→Excel/Word/JSON。**digital-text はこの層だけで headless 完走**（ネット/Claude 不要）。Vision が要る所は engine が **crop 画像を供給**（`backend.render_crop`）し、**narrow interface（Observation 契約）越しに** 神託を受け取るだけ＝engine 本体に LLM を埋めない。
- **この skill（Vision 薄層＝Claude が目で読む）**: 2 種類の「文字/位置を目で読む」仕事だけを Claude が担う:
  1. **digital-no-cjk / scanned の氏名・項目名**（engine が `vision_requests` / `labels_need_vision` 旗を出したセル）。
  2. **owner 指定 `position_readback` 様式の位置裏取り**（下 Step 3b）＝engine が供給した crop を Read で観測し、`structural_read`（位置）+ `raster_reread`（値）を engine に戻す。

**二層分担の要点（芯）**: engine は **headless で crop 供給と契約（Observation）まで**、**実 Vision 裏取りはこの skill 層の仕事**。headless CLI 単独では position_readback を指定しても oracle（目）が無い＝指定を記録するだけで `pf_unverified` を残す（honest fallback＝目が無ければ位置は裏取れない、と正直に落とす）。

engine 置き場: engine を持つ製品の repo の中の engine の dir。どの repo かは repo の根（`git rev-parse --show-toplevel`）の `config/skill-values.json` の鍵 `docs-kit.pdf-read.engine_source`、engine の module の名は鍵 `docs-kit.pdf-read.engine_module` に在る（無い・空なら人に聞く）。以下 `<engine>` はその module の名。本物の置き場は製品の repo＝作業中の repo に写しを置かない。repo の中の dir はその repo の CLAUDE.md が正本。

**受け取り方**（読む前に 1 回）:
- クラウドの窓: `add_repo`（その製品の repo・read）で付け、返ってきた clone の命令で作業場所の外（例 `/home/user/<製品の repo>`）へ clone する。以下 `<engine の親>` は clone の中の engine の dir の親。
- Mac の窓: 製品の repo の手元の clone を `git pull` してから同じく `<engine の親>` を使う。
- 拒まれた・付けられない時は読まずに止まり、親窓（無ければオーナー）へ 1 行で返す（engine の写しを自分で作らない）。

## 手順

### Step 1. 一発 read（triage 込み）
engine の親へ入ってコマンド一発（digital-text は Claude 不要）:
```bash
cd <engine の親>
python3 -m <engine> read "<pdf 絶対パス>" --to excel --out "<出力ベース（拡張子なし）>"
# --to は excel,word,json をカンマ区切りで複数可。--out 省略時は PDF と同じ場所に _<engine>
# owner が「この様式は位置も裏取れ」と指定する時のみ: --position-readback all（or カンマ区切り table id）
#   ※headless CLI は指定を記録するだけ＝実際の位置裏取りは skill 層が oracle(Claude の目)を差す（Step 3b）
# owner が「値も二重で裏取れ（上位保証＝二重裏取り）」と要求する時のみ: --guarantee independent（既定 single）
#   ※VALUE 軸の保証水準。single=多軸整合（行計×列計が両軸を挟む）で足す。independent=独立チャネル
#     （raster_reread 等の independently_verified / 人手 confirmed）を各数値セルに要求＝多軸整合だけでは非-clean。
#     headless CLI は oracle 無し＝independent 指定で多軸整合セルは「独立チャネル未達」で clean=False へ正直落ち。
#     実 VALUE 独立チャネルは skill 層が oracle(Claude の目)を差して走る（Step 3b の raster_reread が VALUE 軸）。
```
stdout にサマリが出る（実際の行）:
```
対象: <basename> / <N>ページ / <M>表
数値token: <n> / 未解決(旗): <u>
検算 pass=<p> fail=<f>
clean=<True|False> 保証水準=<single_token_resistant|independent_channel_confirmed>
独立チャネル未達(independent_channel_unmet)=<iu>                                            # --guarantee independent 時のみ
位置未裏取り(pf_unverified)=<pf> 位置誤バインド(position_claim_mismatch)=<pm> ラベル低信頼=<lab>
残差注記(clean でも証明範囲外): value_provenance_residual, position_provenance_residual   # clean 時のみ
BLOCKING flag <k>件: <kind>(<detail>); ...                                                  # 非-clean 時
出力: <path>
```

### Step 2. 出力の読み方（オーナーに渡す時の翻訳）
- **`clean=True` かつ BLOCKING flag ゼロ** → 「拾った全数値が原本の桁と一致（VF）し、かつ **正しいラベルに結ばれている（PF）** ことまで裏取り済」。ここまで揃って初めて安心して渡せる。**clean 時も出る「残差注記」は正直な但し書き**（下記）＝データ誤りの警告ではない。
- **`clean=False`** → まだ渡さない。理由を summary と BLOCKING flag で必ず特定してから渡す。主な内訳:
  - **未解決(旗) > 0** → token が cell に割り当てられず旗が立っている（parse 失敗の数字らしき token 含む＝黙って消えない・完全性台帳に残る）。Excel の黄色セルを要確認。
  - **fail > 0** → 検算不一致＝**データ誤りの疑い**。赤セルを確認。
  - **`位置未裏取り(pf_unverified)` > 0（PF 軸）** → 数字（値=VF）は拾えているが **「何の数字か」（位置）が裏取れていない**セルがある。合計/多軸ピンでも構造読みでも位置を確定できず、幾何マージンが健全なだけでは clean にしない（隣列へ綺麗にシフトした誤割当を silent 通過させないため）。Excel の**薄橙セル**が該当。**owner が `position_readback` を指定してこの skill が Vision で裏取れば解消**（Step 3b）。
  - **`位置誤バインド(position_claim_mismatch)` > 0** → 構造読みで、観測した数値の画素位置から再導出したセルが主張セルと食い違った＝位置の誤バインドを検知（clean にしない）。
  - **`ラベル低信頼` > 0** → 行/列ラベルや表種別の確信度が閾値未満＝誤ラベルを断定しないため旗。
  - **`独立チャネル未達(independent_channel_unmet)` > 0（`--guarantee independent` 要求時のみ）** → owner が上位保証（値の二重裏取り）を要求したが、独立チャネル（`raster_reread` 等の `independently_verified` / 人手 `confirmed`）に達していない数値セルがある。多軸整合（行計×列計の内部整合）**だけ**では上位バーを満たさない＝内部の算術一致に加えて "別系統でもう一度読む" 独立チャネルを求める水準。headless CLI は oracle 無しゆえ多軸整合止まりのセルは全てここに数える（honest fallback）。**解消＝owner が `--position-readback` を指定しこの skill が Vision で raster_reread（VALUE 軸）まで走らせる**（Step 3b）。上位を要求しない通常運用（既定 single）ではこの行は出ない。
  - **BLOCKING flag** → truncation / scanned / no-cjk ラベル未確定 / channel 偽装 / pf_unverified / position_claim_mismatch / label_low_confidence 等。flag の kind と detail をそのまま人に見せる。
- **clean の定義（2 軸連言・canonical 6 条件は不変）**: 「合計に絡む数値セルが**値チャネルで裏取り済〔VALUE 軸〕∧ 位置が裏取り済〔POSITION 軸＝pf_unverified 無し〕** ∧ 台帳全解決 ∧ blocking ゼロ ∧ 全ページ completed」。日付・単価など検算に絡まないセルは clean 対象外（それ自体は正常）。**「fail でも未解決でもない＝安全」ではない**（値だけ取れて位置未裏取り＝pf_unverified が残ると非-clean）。
- **残差注記（clean でも正直に告げる証明範囲外）**: Vision 裏取りは信頼を 1 段下げるが「その値/位置が crop の**画素**から来た」ことは型では証明しきれず oracle の誠実さに依存する。よって clean 出力にも 2 つの但し書きを必ず出す＝`value_provenance_residual`（値が text 層と本当に別系統で読まれた保証はしない）/ `position_provenance_residual`（観測 bbox が画素の真の位置である保証はしない）。**これはデータ誤りの警告ではなく「clean が証明する範囲の正直な境界」**（over-claim 禁止）。

### Step 3. Vision 薄層（Claude が目で読む 2 経路）

#### 3a. digital-no-cjk / scanned の氏名・項目名
- engine が page を `digital-no-cjk`（Print-To-PDF で日本語がテキスト非埋め込み等）や `scanned` と分類すると **BLOCKING flag（`labels_need_vision` / `scanned_all_unresolved`）＋ `vision_requests`** が立ち、**文書 `clean=False`** になる。
- **数字は拾えているが「確定」ではない**: no-cjk は行/列ラベルが未確定＝正しい数字が誤ったラベルに付きうる（だから clean にしない）。scanned は数字自体も未 OCR。該当 page/crop を画像化 → Claude（この場のわたし）が Read で読み → Excel のラベル/値を手当て → 検算が通って初めて確定。
- MVP は **scanned・no-cjk を clean 保証の外**に置く（要 Vision）。

#### 3b. owner 指定 `position_readback` 様式の位置裏取り（PF エスカレーション）
- **既定は headless＝この経路を焚かない**。合計ゼロ×digital-text×幾何マージン健全でも、owner 未指定の様式は Vision を焚かず PF 未裏取りセルを `pf_unverified`(blocking) で非-clean に落とす（silent を作らない・コストは "怪しさ" に比例）。
- **owner が「この様式は位置も裏取れ」と指定した table だけ**（`--position-readback` or template `position_readback:true`）、engine が各数値セルの **crop を供給**（`backend.render_crop`）し、この skill が **Claude の目で crop を観測**して 2 つを併産する:
  - `structural_read`（**POSITION 軸**）＝「この数字は当該見出し領域の下にある」を裏取る。
  - `raster_reread`（**VALUE 軸**）＝画素から値を読み直し text 層値と照合（値の独立チャネル）。
  - **両方 pass で初めて clean**＝位置専用の structural_read だけでは VALUE 軸を満たさない（値ズレは raster_reread fail→conflict、位置ズレは structural_read fail→conflict）。
- **★トートロジー回避（芯）**: 観測した値/位置（`reread_value` / `observed_value_bbox`）は **oracle が crop の画素を見た結果**を使い、text 層の cell.value / cell.bbox を流用しない。engine は観測 bbox から grid セルを再導出し、主張セルを信頼しない（隣セルの位置・別値を返せば mismatch / fail で弾かれる＝同じ幾何から位置を「洗浄」できない）。
- **honest fallback**: oracle（目）が読めない/観測を返さないセルは check を生成せず `pf_unverified` を残す（owner が指定しても目が無ければ裏取れない、と正直に落とす）。
- **engine と skill の境界**: engine は crop 供給（`render_crop`）と契約（`Observation` = `.value` / `.value_bbox` / `.heading_bbox` / `.confidence`）まで＝**実 Vision 観測はこの skill（Claude）が担う**。将来アプリは自前の API を同契約に差せる。

## 限界（正直に）
- **効く芯は表形式の数字**。自由文/長文の意味要約・フォーム対話入力・見た目クローンは対象外（ベストエフォートの text ダンプ止まり）。
- **PF が機械保証するのは「値の位置バインディング」まで**＝値が正しい幾何セル（行×列）に結ばれ、構造読みが通れば当該見出し**領域**の下に在ること。その見出し**テキストが正しく読めているか**（見出しの語を誤読していないか）は PF の保証外＝ラベル側の確信度と旗（`label_low_confidence`）に従属する。「PF＝機械保証」は無保証の非数字ラベルの正しさまで含意しない。
- 未知様式の**行/列ラベル**は auto 連結で粗くなることがある（**値は保証・ラベルは要確認**＝誤ラベルを断定しない）。
- scanned・digital-no-cjk のラベルは Vision 依存（Step 3a）。位置裏取りは owner 指定様式のみ（Step 3b）。
- **合計整合はボーナス**＝合計が原本に在るのに不整合なら従来どおり `conflict`（データ誤りの疑い）、合計が無い文書は VF/PF チャネルで clean を目指す。

## 機構・検証
- 完全性台帳 + 検算群 + clean 2 軸連言（VALUE 軸=Cell.state / POSITION 軸=pf_unverified 無し）は engine が機械執行（Check/Cell の自己申告を信じない）。enforceability は mutation ①〜⑯ pytest（⑪〜⑯ は observation-binding 攻撃）、production 経路（extract→build_checks→verify / 実 PDF backend）は production-path テスト、実経路（position_readback）は `test_position_readback.py`、実PDF回帰は 5型 golden で固定:
```bash
cd <engine の親> && python3 -m pytest tests/ -q
# 個人情報 PDF 不在環境: golden 5 型が skip（fitz 依存の production/synthetic/position は走る）
```
- **golden の独立性**: 正解は原本 text 層 + 内部検算から起こす（生成 xlsx からは起こさない＝循環検証回避）。実PDF は個人情報ゆえ repo の外（置き場は engine の repo の決まりに従う・不在時 skip）。fitz さえ在れば走る **cell 単位 synthetic golden**（既知グリッドを描画→抽出照合）を production に同梱＝環境非依存の抽出忠実性 backstop。5型 golden は fail=0・完全性 unresolved 凍結不変・**pf_unverified 件数を drift backstop に凍結**（行計だけの実物の表は単軸ピン止まりゆえ headless で clean=False が正）。
- **偽合計の扱い**: 計列/計行は「非自明な全 eligible 行が reconcile する時のみ確定」。非自明に不一致の行が在れば per-cell conflict にせず **blocking `ambiguous_total_column/row`** で可視化（左連続和モデルが破れる集計行を "データ誤り" と誤断しない）。全ゼロ body の vacuous 一致は確定に数えない。

## 関連
- engine: 製品の repo の `<engine>`（backend/checks/extract/verify/render/ir/oracle/geometry/position/cli）。位置裏取りの芯＝`position.py`（owner 指定様式のみ structural_read/raster_reread を Vision 観測から併産・トートロジー回避）
- enforceability ゲート: 製品の repo の `tests/test_position_readback.py`（headless→pf_unverified / honest oracle→clean / 偽値→conflict / 偽位置→mismatch）+ `tests/test_golden_real.py`（5型実PDF golden・pf 件数凍結）
