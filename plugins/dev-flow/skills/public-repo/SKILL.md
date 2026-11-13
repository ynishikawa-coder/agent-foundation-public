---
name: public-repo
description: 公開の repo を作る・非公開の repo を公開で出し直す・外れた公開 repo を直す時の手順。綺麗な新しい repo に照らした中身を置き、土台の公開の検査（action public-guard）を版の印で呼び、secret と main の守りを持ち主に頼む。「公開の repo を作って」「public にしたい」「公開で出し直して」「見回りで外れと出た」で起動。合言葉:「公開する」「public にして」「公開の検査を付けて」。
---

# /public-repo — 公開の repo を作る

核 §1 の「公開の repo は、いつ誰に見られてもよい状態に保つ」の手順です。仕組みの正本は土台の `docs/公開の検査.md`。

## 0. 前提を確かめる

- 公開にする事そのものはオーナーが決める（社外への公開・戻せない）。決まっていなければ先に聞く。
- 顧客の語の束（Javis は環境変数の顧客の語の束、UTC は自社の束）が窓の環境にあるかを、値を出さずに確かめる。無ければ照らせないので、持ち主に頼む。

## 1. 今の中身を照らす（AI）

非公開の元の repo の今の中身を、公開の検査の本体で照らす。土台を取り出して、元の repo の根で:

```bash
AF_DENY_BUNDLE="<顧客の語の束の環境変数>" python3 <土台>/public-guard/guard.py --repo . --files-only
```

- `--files-only` は中身だけを見る（歴史と名義は新しい repo へ持ち越さない）。当たりは 0 にしてから進む。当たりの直しは元の repo の PR で。
- 歴史ごと公開してよいかは、`--range ALL` で照らして歴史と名義も当たり 0 の時だけ。名義に事務所や個人のメールが 1 件でもあれば、歴史は持ち越さない。

## 2. 新しい repo を作る（持ち主の手）

非公開の repo を公開に切り替えない（歴史・名義・閉じた PR が全部見える）。手の窓で頼む:

1. GitHub の New repository で、名を決めて **Private で** 作る（中は空・README を付けない）。公開へは 4 の後、5 で切り替える。
2. 窓の環境から触れるよう、その repo を窓に足す（AI が `add_repo` を呼べるよう名を返してもらう）。

## 3. 中身を置く（AI）

- 1 で照らした今の中身を、名義を noreply にした 1 commit で置く（`git -c user.email=<noreply> commit`）。元の歴史は置かない。
- `.github/workflows/public-guard.yml` に土台の `public-guard/caller-template.yml` を写し、`@vX.Y.Z` を土台の一番新しい印にする。job の名 `public-guard` は変えない。
- その repo に置かない語の表があれば、雛形の `with:` に `deny-words-file:` を足す。
- 置いたら手元で `guard.py --range ALL` を顧客の語の束つきで回し、当たり 0 を確かめる。

## 4. secret（持ち主の手）

手の窓で、画面と押す所を番号つきで頼む:

1. Settings → Secrets and variables → Actions → New repository secret: 名 `AF_DENY_BUNDLE`、値は顧客の語の束の `pct1.` で始まる 1 行だけ（名前と `=` や引用符を付けない・窓に貼らない）。

済んだ目印: 中身を置く PR で `public-guard` が緑。形が違えば、CI のログに値を出さずにどこが違うかが出る。

## 5. 公開に切り替え、すぐ守る（持ち主の手）

個人の無料の plan では非公開の repo に ruleset が効かないので、守りは公開に切り替えた直後に入れる（間も CI の検査は回る）。

1. Settings → General → Danger Zone → Change visibility → Public。
2. Settings → Rules → Rulesets → New branch ruleset: 対象 Default branch・Enforcement Active・「Require a pull request before merging」・「Require status checks to pass」に `public-guard`・「Block force pushes」と「Restrict deletions」。
3. 土台の Actions の `patrol` を手で回し（Run workflow）、外れ 0 を確かめる。

済んだ目印: 次の PR の checks の欄で `public-guard` が必須（Required）と出る・`patrol` が緑。

## 外れを直す

見回りの issue「公開の検査の見回り」に出た外れは、その repo で直す: 呼び口が無い→3／版の印でない→`@vX.Y.Z` に／守りが無い→5 の 2。直したら `patrol` を手で回して issue が閉じるのを見る。
