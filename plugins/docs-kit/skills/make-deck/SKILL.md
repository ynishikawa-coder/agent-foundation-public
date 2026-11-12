---
name: make-deck
description: NotebookLM で顧客向け資料（提案スライド/プレゼン）を作る2工程 skill。Claude が事実確定 Brief→NotebookLM が体裁/図/圧縮→表紙と透かし除去だけ finish_deck.py で固定。「NotebookLMで資料」「提案/プレゼン資料作って」「デッキ作って」「顧客向けスライド」で起動。全 agent 共通。合言葉:「提案資料作って」「顧客向けスライド作って」「NotebookLMでプレゼン」。
---

# make-deck — NotebookLM 2工程 資料作成

**一行**: 「何を伝えるか（WHAT）」は Claude が完成させ、「どう伝えるか（HOW）」は NotebookLM に任せ、**会社のフォーマットは表紙と仕上げだけ固定**する。HTML 箱組みに戻らずに、印象に残る顧客資料を最小手間で作る型。

## repo ごとの値（config/skill-values.json）

repo ごとに違う値は、repo の根（`git rev-parse --show-toplevel`）の `config/skill-values.json` の `docs-kit.make-deck.<鍵>` から読む（スクリプトは同じ dir の `scripts/skill_values.py` で同じ規則で読む）。**鍵が無い・値が空なら右の既定で動く**（表の無い会社でもそのまま使える）。

| 鍵 | 使う所 | 無い時の既定 |
|---|---|---|
| `design_doc` | 設計の正本・実測の根拠（第1事例の反復の記録） | 無し（この SKILL が型の正本） |
| `notebooklm_bin` | 工程4 の `$V`（NotebookLM 認証済み venv の bin） | `notebooklm` を入れた venv の bin を自分で指す |
| `research_copy` | プロンプトの研究用の写しの置き場（正本ではない） | 無し |
| `accent` / `accent_name` | 工程6 の `--accent` を省いた時の表紙の色 | `#334155`（中立の濃灰） |
| `cover_company` / `cover_logo` | 工程6 の `--company` / `--logo` を省いた時（logo は repo の根からの path） | 社名なし・ロゴなし |
| `font_hint` | 日本語が崩れる時に `--font` へ渡すフォント | 手元の日本語 TTF/TTC |
| `case_defaults` | 工程4 で case.json にスロット（`禁止表現`・`色hex`・`色名` 等）が欠けて render が止まった時に出す見本（埋めはしない） | 見本なし（止まるのは同じ） |
| `distribution` | この skill の配り方（agent ごとの入口のリンク等） | 無し（plugin を入れれば使える） |
| `common.rules` | 送信可否ゲート等で引く会社の規律 | この SKILL の本文の規則だけで動く |

**直すのは正本 1 本だけ**（土台の `plugins/docs-kit/skills/make-deck/`・使う repo はプラグインで入れる＝写しを作らない）。repo ごとの値は正本に書かず表に書く。

- **設計正本 / 実測の根拠**: 表の `design_doc`（無い会社はこの SKILL が型の正本）。本 SKILL はその型を機械化したもの。
- **役割分担（動かさない核）**:
  - Claude = Intelligence（調査・分析・事実確定・Brief）
  - NotebookLM = Expression（構成・図・短いコピー・情報圧縮）← **触らない＝ここが HTML を脱した理由**
  - finish_deck.py = 固定できる見た目だけ（**表紙 / 透かし除去 / 綴じ**）
- **なぜ体裁を NotebookLM で作り込まないか**: 背景色・配色・タイトル体裁の微調整が弱く、再指定するとデッキ全体が振り直る（良いコピー/構成を失う）。∴ 一貫性は「プロンプト規律＋表紙テンプレ」で担保し、本文の見た目は NotebookLM の型を「うちの型」として受け入れる。

## いつ起動するか
- 「NotebookLMで資料/プレゼン作って」「提案資料/プレゼン資料作って」「デッキ作って」「顧客向けスライド作って」。
- **前提**: 伝える材料（調査・分析・結論）が揃っていること。無ければ先に調査や聞き取りで「何を伝えるか」を固める（このskillは材料整形〜仕上げを担う）。

## 全体フロー（7工程）
```
調査・分析（Claude／このskillの前段）
  → 工程1 Brief 生成（事実確定・人名なし・禁止リスト・メタ隔離）
  → 工程2 Presentation Context 付与（Audience/Goal/Perception/Messages/Misunderstandings/Tone）
  → 工程3 Brief HTML → PDF（読めれば十分・デザインしない）
  → 工程4 NotebookLM 投入 + プロンプト（既定=CLI 自動・送信可否ゲートを通す）
  → 工程5 出力レビュー関門（事実/トーン/漏れ/生成バグ）→ 生成バグは決定論パッチ・中身変更は clean Source から全再生成（★日本語 revise 禁止）
  → 工程6 仕上げ finish_deck.py（表紙 + 透かし除去 + 綴じ）
  → 工程7 納品前チェックリスト → 顧客提出
```

---

## 工程1 — Brief（Claude が WHAT を書く）

Brief は**プレゼンでなく完全な情報パッケージ**。評価軸は「美しいか」でなく「NotebookLM が今回のテーマを正確かつ深く理解できるか」。中身の節（案件で増減可）:

- **A. Executive Summary** — 何を調べ / 何が分かり / 結論は何か
- **B. Background / Context** — なぜ今検討しているか・現状・課題・これまでの議論
- **C. Research / Facts** — 数値・データ・事例・市場/技術/制度/競合（具体的に）
- **D. Analysis** — 事実→「何が言えるか」→示唆（事実で止めず含意まで）
- **E. Conclusion** — 推奨を曖昧にせず明記
- **F. Important Facts / Evidence** — プレゼンで使えそうな強い数字/事実/比較/象徴事例
- **G. Sources** — URL・文献・調査元・取得日（根拠を追える状態）

### Brief 作成の鉄則（手戻りを消す）
1. **事実は確定情報のみ**。未確認は「（想定）」と明記。**NotebookLM は誤りを検証せず増幅する**（開発中→「稼働中・実証済」と強調して載った実例）。
2. **個人名を書かない**（Audience も役割で。書くとスライドに出る）。
3. **「表現の禁止事項」を最初から入れる**（下記）。抽象指示（「煽らない」）だけでは効かない＝**NG フレーズを具体例で列挙**して初めて消える。
4. **指示メタと本文材料を厳密に分離**。NotebookLM 向けの注記（「〜という条件つきではなく」等）を本文・事実欄に混ぜると**顧客向けコピーとしてスライドに漏れる**（実例あり）。メタは工程2の Context / 禁止事項ブロックにだけ置く。
5. **キー用語は顧客語に**。社内ジャーゴン（例「外付けの推進担当」）を Brief に置くとそのまま出る。
6. **固有名の正式名称を最初に確定し全ページ・全資料で統一**（サービス名・製品名・会社名の表記ブレ＝1周分の手戻りになる）。
7. **数字は内訳/根拠つき ＋ 未確定は（想定）**。大きい数字ほど「何の合算か」を隣に置く（NotebookLM は曖昧な文を過信して断定に圧縮する）。
8. **料金は「含む」と「含まない（別途）」を両建て**で書く（片方だけ＝提案後に揉める）。
9. **物語順を Brief 段階で固定**: 顧客の課題 → 立ち位置（何を足す/足さない）→ 役割分担（AIと人）→ 対象範囲 → 期待できる効果 → 進め方 → 料金 → 最初の一歩。
10. **効果はラベルだけにせず数字を入れる**（「時間削減」でなく「月◯時間 → ◯時間」。数字が無いと空ページに見える）。
11. **事実・数値・キー文言は 100% source（Brief）に置く**＝NotebookLM は数字を発明しないが、Brief に無い曖昧点は分析文から派生させる。**（想定）タグは免罪符でない**＝工程5 で「その数字が Brief に辿れるか」を必ず照合する。

### 「表現の禁止事項」ブロック（Brief 末尾に必ず付ける・案件で育てる）
```
■ 表現の禁止事項（NotebookLM へ／スライドに出さない）
- 煽り・誇張の禁止フレーズ: 表の `case_defaults.禁止表現`（会社の既定）＋案件で足す物（例「劇的に」「圧倒的」等）
- 未確定を断定にしない（想定値に「稼働中/実証済」を付けない）
- 個人名・社内の呼称・社内メモの言い回しを本文に出さない
- （前案件で漏れた表現を次案件でここに add-one する）
```

## 工程2 — Presentation Context（Brief と分離して末尾に付ける）
「今回何のためにこの情報をプレゼンにするか」を NotebookLM へ渡す。**ここに表現方法（ページ構成/配色/レイアウト）は書かない**＝NotebookLM に考えさせる余地を残す。
```
■ Audience              誰に（役割で。個人名を書かない）
■ Presentation Goal     何を達成したいか
■ Desired Perception    見た後どう思ってほしいか
■ Most Important Messages   絶対に伝えたいこと 1./2./3.
■ Misunderstandings to Avoid 絶対に誤解されたくないこと（例：完全無人化ではない／AIが最終判断しない）
■ Tone / Impression     与えたい印象（例：先進的・シンプル・経営者向け・過度に未来的にしない）
```

## 工程3 — Brief HTML → PDF
- HTML は **NotebookLM が読み取るための情報資料**。見出し/段落/箇条書き/表/数字が読みやすければ十分＝**デザインに時間を使わない**。
- PDF 化: この skill の `scripts/` に依存なし。任意の HTML→PDF（ブラウザ印刷 / `wkhtmltopdf` 等）で可。文字が読めれば OK。

## 工程4 — NotebookLM 投入 + プロンプト（既定＝notebooklm-py CLI 自動・Chrome/手貼り不要）
**送信可否ゲート（必須）**: NotebookLM は外部サービス（Google）。**顧客の機微（個人名・個人の金額・未公開の内部情報）を含む素材は投入前に送信可否を確認**（会社の規律があれば表の `common.rules` の外へ出す原則に従う）。機微は Brief 段階で落とすのが原則。

**標準プロンプトは正本 1 本＝`prompts/base.txt`**（規律を焼き込む唯一の場所）。**プロンプトを手書きしない／正本に案件値を直書きしない**（次案件へ混入する）。案件ごとに変わる値だけを JSON に書き、`render_prompt.py` が一時プロンプトへ差し込む（**未指定スロットが1つでも残れば非0で止まる**＝未置換の `<<対象>>` が顧客資料に出る事故を関所で塞ぐ）:
```bash
V=<表の notebooklm_bin・無ければ notebooklm を入れた venv の bin>  # 認証済 venv（無ければ下の doctor が赤＝フォールバックへ）
S=<この SKILL.md の dir>  # プラグインの中の skill 正本（写しでなく源を実行）
# 0) 案件値を JSON で書く（schema は $S/prompts/case.example.json）: 対象/目的/トーン/禁止表現/枚数/色hex/色名
#    スロットが 1 つでも欠ければ止まる（表の case_defaults は止まった時に見本として出るだけ＝使うなら case.json に書く）
# 1) 正本テンプレ + 案件値 → 一時プロンプト（未置換は非0で停止・生成物を目視確認）
python3 "$S/scripts/render_prompt.py" render --values <案件>/case.json --out /tmp/deck_prompt.txt
#    実験レバー（既定OFF・未昇格）を試す時だけ: --lever 左右対称と表書式
# 2) NotebookLM 生成（--prompt-file は render 済み一時プロンプト＝正本を直接渡さない）
"$V/notebooklm" doctor                        # Auth ✓ を確認（赤ならフォールバックへ）
"$V/notebooklm" create "<案件> 提案デッキ"      # 実データは実験用 NB と分ける
"$V/notebooklm" source add <nb_id> <BriefのPDF>
"$V/notebooklm" generate slide-deck -n <nb_id> --format presenter --length default --language ja --wait --prompt-file /tmp/deck_prompt.txt
"$V/notebooklm" download slide-deck <out.pdf> -n <nb_id>
```
- **標準規律（1枚1メッセージ／太字ゴシック／白背景／図中は短文／物語順／色 hex 統一／枚数目安）は `prompts/base.txt` に焼き込み済＝ここを直せば全案件に効く**（skill 出力の唯一の焼き先＝`$S/prompts/base.txt`。表の `research_copy` にある研究用の写しは正本ではない）。
- **枚数・色は best-effort（保証されない）**＝正本は「およそ N 枚」「色 hex で統一」と書くが、**工程5 のレビューで必ず検算**する（NotebookLM は指定を守らない回がある）。
**フォールバックは明示のみ（無言禁止）**: `doctor` が赤 / `generate` がエラーの時だけ、**その旨とエラーを告げてから** 手動 NotebookLM web か Chrome 自動化へ切替える。notebooklm-py は非公式＝壊れうるので `--wait` で結果を検算し、**黙って手貼り/Chrome に落とさない**（落ちた事実が消えると「なぜ手動なのか」が分からなくなる）。

**指定する**: Audience(役割)/Goal/Desired Perception/ページ数/構成の流れ/トーン/**禁止表現**。
**任せる**: ページ内の図・レイアウト・コピーの言い回し・情報の取捨。

## 工程5 — 出力レビュー関門（Claude が点検）
NotebookLM 出力を**そのまま採用しない**。4点を点検して直す:
1. **事実** — 数字/主張が Brief と一致するか（増幅・断定化していないか）
2. **トーン** — 禁止フレーズ（煽り・誇張）が足されていないか
3. **漏れ** — 個人名・社内メモ・指示メタが本文に出ていないか
4. **生成バグ** — 重複行・欠落・崩れ

**★revise 一元規則（工程4・工程5 双方が従う）**: NotebookLM の `revise` は **1枚だけ直せない＝全デッキを再生成し、しかも source を見ない**（documented）。∴ **日本語デッキで局所 revise は使わない**。直しは 2 経路だけ:
- **生成バグ（重複行・崩れ・不要要素）→ 決定論パッチ**（NotebookLM を再度回さない）: 崩れの無い**元 artifact** を採り、不要行だけを PyMuPDF で白塗り除去（塗る前後の暗ピクセル検算付き・finish_deck と同じ発想）。生成物は `get_text` 空＝図形埋め込みなので、行位置は右カラムの暗行プロファイルで**機械検出**してから塗る（目測禁止）。
- **中身・コピーを変えたい → clean な Source（Brief 1本）から全再生成**: revise で崩すより安全。一貫性は正本 `prompts/base.txt`（`render_prompt.py` で差し込む）が担保する。**Source に前回 artifact を戻さない**（文脈が濁る）。
- ⚠️ 補足（実測）: 日本語で revise すると漢字が化ける（「転換」→「転栂換」・2回試しても直らない＝描画バグ）＝上の 2 経路以外を使わない理由。

## 工程6 — 仕上げ（finish_deck.py・フォーマット固定の在り処）
NotebookLM 出力（透かし入り・自前表紙付き）を PDF で書き出し → **自前表紙の除去（任意）+ 会社の表紙付与 + 透かし除去（塗る前 preflight）+ 綴じ**を**外で決定的に**行う。本文スライドは**無加工で流用**（画質・レイアウト保持）。
```bash
S=<この SKILL.md の dir>  # プラグインの中の skill 正本（cwd に依らない）
python3 "$S/scripts/finish_deck.py" finish \
  --body <notebooklm出力.pdf> --out <納品.pdf> \
  --company "株式会社○○" --title "資料タイトル" --subtitle "サブ" --date YYYY-MM-DD \
  [--accent "#RRGGBB"] [--logo logo.png] [--font 日本語TTF] \
  --drop-first-page --remove-watermark [--wm-rect x0,y0,x1,y1]
```
- **表紙 = フォーマット固定**: 左アクセント帯 / 社名 / タイトル / 下線 / サブ / 日付 の固定レイアウト。色は `--accent`、ロゴは `--logo`、社名は `--company`（省けば表の `accent`・`cover_logo`・`cover_company`、それも無ければ中立の既定）。案件で変えるのは値だけ。
- **`--drop-first-page`（推奨・C13）**: NotebookLM は先頭に**自前のタイトル表紙**（透かし付き）を作る。既定では会社の表紙を正とするので、`--drop-first-page` で NotebookLM 表紙を綴じ前に落とす（付けないと**表紙が2枚**になる）。NotebookLM 表紙を採るなら `--no-cover` で通す（この時 p1 も透かし除去対象）。
- **透かし除去（塗る前 preflight・二段階）**: 既定 rect は**右下角 右12%×下5.5%**（透かしを extremal+margin で覆う実測値）。**全ページを塗る前に判定 → 安全ページだけ白塗り**。①有色/非白背景（灰キャプション等）②本文が rect に侵入（塗ると本文を消す）③透かしが rect 外へはみ出す ④透かし不在（rズレ）の**いずれかが 1 枚でもあれば納品 `--out` を作らず、診断 `*.preflight.pdf` と要確認ページのみ出す**（＝report-only を制御フローで本当に成立させる／silent に本文を消さない）。合わなければ `--wm-rect` で領域を当て直す（位置は固定なので一度当てれば安定）。
- **日本語**: 内蔵CJKで描画。崩れる時は `--font <表の font_hint・無ければ手元の日本語 TTF/TTC>` で差し替え。
- 器の健全性確認: `python3 "$S/scripts/finish_deck.py" --self-test`（実物同型ラスタ fixture の verdict + 本文画素不変 + under-coverage + drop-first + mutation-killed をダミー実走）。

## 工程7 — 納品前チェックリスト
- [ ] 事実・数字が正しい（「（想定）」表記の付け忘れが無いか）
- [ ] 個人名が入っていない
- [ ] 禁止表現（煽り・ジャーゴン・社内メモの漏れ）が無い
- [ ] 透かしが除去されている（finish_deck の機械検算 clean）
- [ ] 表紙がある／社名・ロゴ・日付が正しい
- [ ] ページ数・順序が指定通り

---

## 案件横断の注意
- **変わるのは Brief の中身と Presentation Context だけ**。工程（型）は流用する。
- **禁止事項リストは育てる**: 前案件で漏れた表現を次案件の禁止に足す（add-one）。
- **顧客機微を NotebookLM/外部に載せない**（全案件共通・送信可否ゲート）。
- **NotebookLM に質問だけしたい時**はこの skill を使わない。本 skill は「資料を作る」型。
