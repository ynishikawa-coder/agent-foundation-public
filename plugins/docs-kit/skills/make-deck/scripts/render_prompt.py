#!/usr/bin/env python3
"""render_prompt.py — make-deck 標準プロンプト正本に案件値を差し込み一時プロンプトを作る（工程4 前段）.

なぜ必要か: 正本 base.txt にプレースホルダを置くだけでは
  ① 未置換のまま NotebookLM へ送る（<<対象>> がそのまま顧客資料に出る）
  ② 案件値を正本へ直書き → 次案件へ混入
の二つの穴が開く。∴ 正本=不変テンプレ / 案件値=別ファイル(JSON) / 実行時に一時プロンプトを
生成し、**未指定・未置換スロットが1つでも残れば非0で止める** renderer を関所にする。

契約（この芯は動かさない）:
  - スロットは <<キー>>。テンプレに在る全スロットを values(JSON) で埋める。欠落 or 空白のみ → 非0。
  - 差し込み後に <<...>> が1つでも残る → 非0（未置換の送信を塞ぐ）。
  - [[LEVER:名前 · 注記…]] … [[/LEVER]] は既定 OFF（出力に含めない）。--lever <名前> で有効化した
    時だけ中身を残しマーカー行を落とす。**未知の --lever 名は非0**（typo でこっそり無効化を防ぐ）。
    [[/LEVER]] の閉じ忘れ → 非0。
  - ##! で始まる行はメタ（人間向け）＝出力に含めない。
  - template/values は skill-root（このファイルの2つ上）基準で絶対解決（cwd 非依存）。
  - case.json に無いスロットは埋めない（欠落は非0で止まる）。止まった時は、repo ごとの値の表（repo の根の
    config/skill-values.json の docs-kit.make-deck.case_defaults・読み口は同じ dir の skill_values.py）に在る値を
    「case.json に書く見本」として stderr に出すだけ（黙って埋めない）。
  - 生成プロンプトは stdout に表示（人間確認）＋ --out に書く。--out 無しは表示のみ。

使い方:
  python3 render_prompt.py render --values <案件>/case.json [--template <base.txt>] \
      [--out /tmp/deck_prompt.txt] [--lever 左右対称と表書式]
  python3 render_prompt.py --self-test    # 正/負ケースの回帰ゲート（納品前の器の健全性確認）

case.json の例:
  {"対象":"中小企業の経営者（AI専門知識なし）","目的":"…","トーン":"経営者向け・信頼・具体的・煽らない",
   "禁止表現":"「わずか」「劇的」「圧倒的」「安心の〜から」","枚数":"6","色hex":"#1F4E79","色名":"濃紺"}
"""
import argparse
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import skill_values  # noqa: E402  同じ dir の読み口（repo ごとの値の表）

SKILL_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_TEMPLATE = os.path.join(SKILL_ROOT, "prompts", "base.txt")

_LEVER_OPEN = re.compile(r"^\s*\[\[LEVER:(.+?)\]\]\s*$")
_LEVER_CLOSE = re.compile(r"^\s*\[\[/LEVER\]\]\s*$")
_SLOT = re.compile(r"<<([^<>]+)>>")


class RenderError(Exception):
    """render 契約違反（呼び出し側は非0で落とす）。"""


def _resolve(path):
    """cwd 非依存: 絶対ならそのまま、相対なら skill-root 基準で解決。"""
    if not path:
        return path
    return path if os.path.isabs(path) else os.path.join(SKILL_ROOT, path)


def _lever_name(marker_line):
    """'[[LEVER:左右対称と表書式 · 既定OFF · …]]' → '左右対称と表書式'（先頭トークン）。"""
    inner = _LEVER_OPEN.match(marker_line).group(1)
    return inner.split("·")[0].strip()


def render(template_text, values, enabled_levers):
    """テンプレ本文 + 案件値 + 有効 lever から NotebookLM へ送るプロンプトを組む。

    返り値: (rendered_text, meta) — meta は {"levers_found","levers_used","slots"}。
    契約違反は RenderError を送出（欠落スロット / 未置換 / 未知 lever / 閉じ忘れ）。
    """
    enabled = list(dict.fromkeys(enabled_levers or []))   # 重複除去・順序保持
    lines = template_text.split("\n")
    out, found = [], set()
    i = 0
    while i < len(lines):
        line = lines[i]
        mo = _LEVER_OPEN.match(line)
        if mo:
            name = _lever_name(line)
            found.add(name)
            j = i + 1
            block = []
            while j < len(lines) and not _LEVER_CLOSE.match(lines[j]):
                if _LEVER_OPEN.match(lines[j]):
                    raise RenderError("LEVER ブロックが入れ子（未対応）: %r" % lines[j])
                block.append(lines[j])
                j += 1
            if j >= len(lines):
                raise RenderError("LEVER '%s' の閉じ [[/LEVER]] が無い" % name)
            if name in enabled:
                out.extend(block)
            i = j + 1
            continue
        if _LEVER_CLOSE.match(line):
            raise RenderError("対応する [[LEVER:…]] の無い [[/LEVER]] がある")
        if line.startswith("##!"):
            i += 1
            continue
        out.append(line)
        i += 1

    unknown = [name for name in enabled if name not in found]
    if unknown:
        raise RenderError("未知の --lever（テンプレに無い・typo?）: %s / 実在: %s"
                          % (", ".join(unknown), ", ".join(sorted(found)) or "(なし)"))

    body = "\n".join(out)
    slots = list(dict.fromkeys(_SLOT.findall(body)))   # 出現順・重複除去
    missing = [k for k in slots if not str(values.get(k, "")).strip()]
    if missing:
        raise RenderError("案件値(values)が埋まっていないスロット: %s" % ", ".join(missing))

    for k in slots:
        body = body.replace("<<%s>>" % k, str(values[k]))

    residual = _SLOT.findall(body)
    if residual:
        raise RenderError("差し込み後も未置換のスロットが残った: %s"
                          % ", ".join(dict.fromkeys(residual)))

    return body, {"levers_found": sorted(found), "levers_used": enabled, "slots": slots}


def case_default_hint(template_text, values):
    """欠けたスロットのうち会社の表に既定がある物を {スロット: 値} で返す（埋めない・見本として出すだけ）。"""
    defaults = skill_values.get("docs-kit", "make-deck", "case_defaults", default={})
    if not isinstance(defaults, dict):
        return {}
    slots = dict.fromkeys(_SLOT.findall(template_text))
    return {k: v for k, v in defaults.items()
            if k in slots and not str(k).startswith("_") and str(v).strip() and not str(values.get(k, "")).strip()}


def cmd_render(args):
    # template（正本）は skill-root 基準・cwd 非依存。案件値/出力は **cwd 基準**（利用者の居場所の
    # 相対 path をそのまま受ける＝作業場所の case.json を渡せる。reviewer 指摘の should-fix）。
    tpath = _resolve(args.template) if args.template else DEFAULT_TEMPLATE
    vpath = args.values if os.path.isabs(args.values) else os.path.abspath(args.values)
    if not os.path.isfile(tpath):
        sys.stderr.write("テンプレートがありません: %s\n" % tpath)
        return 2
    if not os.path.isfile(vpath):
        sys.stderr.write("案件値ファイル(--values)がありません: %s\n" % vpath)
        return 2
    with open(tpath, encoding="utf-8") as f:
        template_text = f.read()
    try:
        with open(vpath, encoding="utf-8") as f:
            values = json.load(f)
    except Exception as exc:
        sys.stderr.write("--values の JSON が読めません: %s\n" % exc)
        return 2
    if not isinstance(values, dict):
        sys.stderr.write("--values は {\"対象\":..} の JSON オブジェクトで渡す\n")
        return 2
    try:
        body, meta = render(template_text, values, args.lever)
    except RenderError as exc:
        sys.stderr.write("❌ render 中止: %s\n" % exc)
        hint = case_default_hint(template_text, values)
        if hint:
            sys.stderr.write("  見本（会社の既定 docs-kit.make-deck.case_defaults・使うなら case.json に書く）: %s\n"
                             % json.dumps(hint, ensure_ascii=False))
        return 1

    if args.out:
        opath = args.out if os.path.isabs(args.out) else os.path.abspath(args.out)
        with open(opath, "w", encoding="utf-8") as f:
            f.write(body + ("\n" if not body.endswith("\n") else ""))
    # 生成プロンプトは人間確認のため stdout に出す（中身を見せる関所）
    print("=" * 60)
    print(body)
    print("=" * 60)
    print("スロット %d 埋め / lever %s / 出力: %s"
          % (len(meta["slots"]), (",".join(meta["levers_used"]) or "なし"),
             (opath if args.out else "(stdout のみ)")))
    return 0


def self_test():
    """正/負ケースの回帰ゲート（歯: 未置換・欠落・未知lever・閉じ忘れ を必ず赤にする）。"""
    tmpl = (
        "##! これはメタ行・出力に出ない\n"
        "対象は<<対象>>、色は<<色hex>>。\n"
        "[[LEVER:実験レバー · 既定OFF]]\n"
        "これは実験行。\n"
        "[[/LEVER]]\n"
        "末尾。\n"
    )
    results = []

    # ① 正: 全スロット埋め・lever OFF → 成功・残留なし・メタ行/実験行が出ない
    body, meta = render(tmpl, {"対象": "経営者", "色hex": "#1F4E79"}, [])
    ok1 = ("経営者" in body and "#1F4E79" in body
           and "メタ行" not in body and "実験行" not in body and "<<" not in body)
    results.append(("① 正(全埋め・leverOFF)", ok1))

    # ② lever ON → 実験行が出る
    body2, _ = render(tmpl, {"対象": "経営者", "色hex": "#1F4E79"}, ["実験レバー"])
    ok2 = ("実験行" in body2 and "[[LEVER" not in body2 and "[[/LEVER" not in body2)
    results.append(("② lever ON で実験行が入る", ok2))

    # ③ 負: スロット欠落 → RenderError
    try:
        render(tmpl, {"対象": "経営者"}, [])
        ok3 = False
    except RenderError:
        ok3 = True
    results.append(("③ 負(スロット欠落→赤)", ok3))

    # ④ 負: 空白のみ → RenderError（空を埋めた扱いにしない）
    try:
        render(tmpl, {"対象": "経営者", "色hex": "   "}, [])
        ok4 = False
    except RenderError:
        ok4 = True
    results.append(("④ 負(空白スロット→赤)", ok4))

    # ⑤ 負: 未知 lever（typo）→ RenderError
    try:
        render(tmpl, {"対象": "経営者", "色hex": "#1F4E79"}, ["存在しないレバー"])
        ok5 = False
    except RenderError:
        ok5 = True
    results.append(("⑤ 負(未知lever→赤)", ok5))

    # ⑥ 負: [[/LEVER]] 閉じ忘れ → RenderError
    try:
        render("[[LEVER:x · a]]\n中身\n末尾（閉じ無し）\n", {}, [])
        ok6 = False
    except RenderError:
        ok6 = True
    results.append(("⑥ 負(LEVER閉じ忘れ→赤)", ok6))

    # ⑦ 実正本 base.txt が実在し・全スロットを埋めれば通る（正本の健全性）
    ok7 = True
    try:
        if os.path.isfile(DEFAULT_TEMPLATE):
            with open(DEFAULT_TEMPLATE, encoding="utf-8") as f:
                real = f.read()
            real_slots = list(dict.fromkeys(_SLOT.findall(
                "\n".join(l for l in real.split("\n") if not l.startswith("##!")))))
            vals = {k: "x" for k in real_slots}
            rb, _ = render(real, vals, [])
            ok7 = ("<<" not in rb and "[[LEVER" not in rb)
        else:
            ok7 = False
    except Exception:
        ok7 = False
    results.append(("⑦ 実正本 base.txt が埋めれば通る", ok7))

    print("[render_prompt self-test]")
    for name, ok in results:
        print("  %s → %s" % (name, "OK" if ok else "NG"))
    verdict = all(ok for _, ok in results)
    print("判定:", "PASS ✅" if verdict else "FAIL ❌")
    return 0 if verdict else 1


def build_parser():
    p = argparse.ArgumentParser(description="make-deck 標準プロンプトに案件値を差し込む renderer")
    p.add_argument("--self-test", action="store_true", help="正/負ケースの回帰ゲート")
    sub = p.add_subparsers(dest="cmd")
    r = sub.add_parser("render", help="正本テンプレ + 案件値(JSON) → 一時プロンプト")
    r.add_argument("--values", required=True, help="案件値 JSON（対象/目的/トーン/禁止表現/枚数/色hex/色名）")
    r.add_argument("--template", help="テンプレ path（既定: prompts/base.txt）")
    r.add_argument("--out", help="出力プロンプト path（既定: stdout のみ）")
    r.add_argument("--lever", action="append", default=[],
                   help="既定OFF の実験レバーを有効化（例 --lever 左右対称と表書式・複数可）")
    return p


def main():
    args = build_parser().parse_args()
    if args.self_test:
        sys.exit(self_test())
    if args.cmd == "render":
        sys.exit(cmd_render(args))
    build_parser().print_help()
    sys.exit(0)


if __name__ == "__main__":
    main()
