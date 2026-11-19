# 変更の記録の書き方

使う側に関係する変更は、PR ごとに **この dir へ自分の file を 1 つ足す**。全部の PR が同じ所（`CHANGELOG.md` の先頭）へ行を足すと、1 本入るたびに残りの PR が全部衝突するので、行を同じ file に集めない。

- 名: `<YYYYMMDD>-<話題>.txt`。自分の枝 `claude/<日付>-<話題>` と同じにする（1 枝 = 1 file。他の窓の file は触らない）。
- 中身: 1 項を 1 行で、`- <札>: <何が変わったか>`。札は `壊れる`（使う側の振る舞いが変わる）・`足した`・`直した`・`畳んだ` のどれか。札の後に `（1 段目）` のような添えを付けてよい。1 つの file に何行でもよい。
- 合流の後に直す時も、その file を直す（新しい file を足さなくてよい）。
- `CHANGELOG.md` には記録の行を書かない。束ねて読むのは `python3 scripts/changelog.py`（main に入った順・新しい物が上）。
- 拡張子が `.txt` なのは、記録が経緯として古い言い回しを含むため（土台の文を照らす試験は `.md` などを見る）。
- 形は `python3 scripts/changelog.py check` が照らす（CI の `check` の中の `tests/test_changelog.py`）。古い形で `CHANGELOG.md` へ直に行を足すと赤。
- `CHANGELOG.md` は決まった文だけ（文の正本は `scripts/changelog.py` の `MAIN_TEXT`）。見出し・地の文・並びのどれで足しても赤。

## この形の前に枝を切った PR が main を取り込む時

`git merge origin/main` で `CHANGELOG.md` が衝突したら、自分の行を自分の断片へ移す（移す前の記録に在る行は移さない）:

```
git show HEAD:CHANGELOG.md | python3 scripts/changelog.py adopt - CHANGELOG.d/<枝の日付>-<話題>.txt
git checkout origin/main -- CHANGELOG.md
python3 scripts/changelog.py check
```
