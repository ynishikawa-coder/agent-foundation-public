#!/usr/bin/env python3
"""Blueprint HTML の検査と比較（/blueprint の出口）。

検査: Chrome の headless で `<html>?selftest` を開き、枠の selftest が書いた
`<pre id="selftest">` を読む。全タブを描いて、例外・console.error・飛び先の無い
data-go / data-tab-go・HOLES に無い穴番号・現状版で根拠（path:行）の無い段・
段 id の重複が 0 なら OK。

比較: 現状版と設計版の両方を `?dump` で開き、段の一覧（name・where・fate・basis）を
name で突き合わせて Markdown で出す（①片方にしか無い段 ②書き先の違い ③札の違い
④設計版で未定のまま）。差分を見せる道具で関所ではない＝差があっても exit 0。

使い方:
    python3 check_blueprint.py <blueprint.html>
    python3 check_blueprint.py compare <現状版.html> <設計版.html>

終了コード:
    0 = SELFTEST OK ／ compare できた
    1 = SELFTEST NG（NG 行と、最後に根治の入口を指す `直し:` の行を出す）／結果が DOM に無い
    2 = Chrome が無い・起動できない
標準ライブラリだけ。
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

# Chrome の探し方・?selftest の読み方は docs-kit の共通の口が正本（型ごとに写さない）
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "scripts"))
import page_selftest as PS  # noqa: E402
from page_selftest import ChromeMissing, open_dom, pre_text, resolve  # noqa: E402,F401

# NG の時の最後の行（中身は細目 §3 が正本＝ここは指すだけ）
ROOT_CAUSE = "直し: NG の行を 1 つずつ潰さず、細目 §3「まず構造を疑う」で原因（材料の読み方・段の組み方）から直す"
FATE_TEXT = {"keep": "保存される", "lost": "消える", "calc": "その場で計算", "gap": "未定"}


def check(path: str) -> int:
    return PS.check(path, ROOT_CAUSE)


def load_dump(target: Path) -> list[dict]:
    text = pre_text(open_dom(target, "dump"), "bpdump")
    if text is None:
        raise ValueError(f"dump の結果が DOM に無い（枠が起動前に落ちた／template の枠でない）: {target.name}")
    return json.loads(text)


def fate_label(f: str) -> str:
    return FATE_TEXT.get(f, f)


def compare(cur_path: str, des_path: str) -> int:
    cur_t, des_t = resolve(cur_path), resolve(des_path)
    if cur_t is None or des_t is None:
        return 1
    try:
        cur, des = load_dump(cur_t), load_dump(des_t)
    except ChromeMissing as e:
        print(e)
        return 2
    except ValueError as e:
        print(f"NG {e}")
        print(ROOT_CAUSE)
        return 1
    ci = {r["name"]: r for r in cur}
    di = {r["name"]: r for r in des}

    def at(r: dict) -> str:
        return f"{r['tab']} › {r['name']}"

    only_cur = [r for r in cur if r["name"] not in di]
    only_des = [r for r in des if r["name"] not in ci]
    both = [(ci[n], di[n]) for n in ci if n in di]
    where_diff = [(c, d) for c, d in both if c["where"].strip() != d["where"].strip()]
    fate_diff = [(c, d) for c, d in both if c["fate"] != d["fate"]]
    gaps = [r for r in des if r["fate"] == "gap"]

    out = [f"# Blueprint 比較 — 現状版 {cur_t.name} ／ 設計版 {des_t.name}", ""]
    out.append(f"## ① 片方にしか無い段（現状だけ {len(only_cur)}・設計だけ {len(only_des)}）")
    out += [f"- 現状だけ: {at(r)}" for r in only_cur]
    out += [f"- 設計だけ: {at(r)}" for r in only_des]
    if not (only_cur or only_des):
        out.append("- なし")
    out += ["", f"## ② 書き先の違い（{len(where_diff)}）"]
    out += [f"- {c['name']}: 現状=`{c['where'] or '（空）'}` ／ 設計=`{d['where'] or '（空）'}`" for c, d in where_diff] or ["- なし"]
    out += ["", f"## ③ 札の違い（{len(fate_diff)}）"]
    out += [f"- {c['name']}: 現状={fate_label(c['fate'])} ／ 設計={fate_label(d['fate'])}" for c, d in fate_diff] or ["- なし"]
    out += ["", f"## ④ 設計版で未定のまま（{len(gaps)}）"]
    out += [
        "- {}: 欠け={}".format(
            at(r),
            "・".join(k for k, v in (("根拠", r["basis"]), ("書き先", r["where"])) if not v.strip()) or "札が未定",
        )
        for r in gaps
    ] or ["- なし"]
    print("\n".join(out))
    return 0


def main(argv: list[str]) -> int:
    if len(argv) == 4 and argv[1] == "compare":
        return compare(argv[2], argv[3])
    if len(argv) == 2 and argv[1] != "compare":
        return check(argv[1])
    print("使い方: check_blueprint.py <blueprint.html>\n"
          "        check_blueprint.py compare <現状版.html> <設計版.html>", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
