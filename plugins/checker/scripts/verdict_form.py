#!/usr/bin/env python3
"""チェック役の判定のコメントが決まりの形かを見る（形だけ・中身の良し悪しは見ない）。

見る事:
  1. 1 行目 `レビューした窓: <session id> 判定: green|red`
  2. 2 行目 `見た先端: <SHA の先頭 12 文字>`
  3. `## verdict` の次の行が green／red／red（blocked: …）で、1 行目の判定と合う
  4. `## 所見` の各行の札 `- [止める|後の便|直った｜<段>] …`。`[止める｜…]` が 1 つでも在れば red、無ければ green
  5. 別の目: 書いた窓（--writer）とレビューした窓が同じなら形の誤り（自分の PR に判定を付けない）

使い方: python3 verdict_form.py <コメントのファイル> [--writer <書いた窓の session id>] [--head <PR の先端の SHA>]
  誤りを 1 行ずつ出し、誤りがあれば exit 1。
"""
import re
import sys

LINE1 = re.compile(r"^レビューした窓: (session_[A-Za-z0-9]+) 判定: (green|red)$")
LINE2 = re.compile(r"^見た先端: ([0-9a-f]{12})$")
VERDICT = re.compile(r"^(green|red)(?:（blocked: .+）)?$")
CARD = re.compile(r"^- [\[［](止める|後の便|直った)[｜|](設計|整地|見本|承認|実装|レビュー)[\]］] \S")
CARDS = ("止める", "後の便", "直った")


def section(lines, head):
    """`## <head>` の下から次の `## ` までの行。"""
    out, inside = [], False
    for ln in lines:
        if ln.startswith("## "):
            if inside:
                break
            inside = ln.strip() == "## " + head
            continue
        if inside:
            out.append(ln)
    return out if inside or out else None


def check(text, writer=None, head=None):
    errs = []
    lines = (text or "").splitlines()
    m1 = LINE1.match(lines[0].strip()) if lines else None
    m2 = LINE2.match(lines[1].strip()) if len(lines) > 1 else None
    if not m1:
        errs.append("1 行目が `レビューした窓: <session id> 判定: green|red` でない")
    if not m2:
        errs.append("2 行目が `見た先端: <SHA12>` でない")
    reviewer, judged = (m1.group(1), m1.group(2)) if m1 else (None, None)
    if m2 and head and not head.startswith(m2.group(1)):
        errs.append("見た先端 %s が PR の今の先端 %s と違う（見直して判定を足す）" % (m2.group(1), head[:12]))
    if writer and reviewer and writer == reviewer:
        errs.append("書いた窓とレビューした窓が同じ（別の目でない）")

    verdict = section(lines, "verdict")
    body = [ln.strip() for ln in (verdict or []) if ln.strip()]
    mv = VERDICT.match(body[0]) if body else None
    if not mv:
        errs.append("`## verdict` の次の行が green／red／red（blocked: …）でない")
    elif judged and mv.group(1) != judged:
        errs.append("1 行目の判定 %s と `## verdict` の %s が違う" % (judged, mv.group(1)))

    findings = section(lines, "所見")
    if findings is None:
        errs.append("`## 所見` の節が無い")
        findings = []
    stops = 0
    for ln in findings:
        s = ln.strip()
        if not s.startswith("- "):
            continue
        if not CARD.match(s):
            errs.append("所見の行の札が `- [止める|後の便|直った｜<段>] …` でない: %s" % s[:40])
            continue
        if re.match(r"^- [\[［]止める", s):
            stops += 1
    want = "red" if stops else "green"
    blocked = bool(mv and "blocked" in body[0])
    if judged and not blocked and judged != want:
        errs.append("`[止める｜…]` が %d 個なので判定は %s（今は %s）" % (stops, want, judged))
    return errs


def main(argv):
    args = argv[1:]
    if not args:
        sys.stderr.write(__doc__)
        return 2
    path, writer, head = args[0], None, None
    if "--writer" in args:
        writer = args[args.index("--writer") + 1]
    if "--head" in args:
        head = args[args.index("--head") + 1]
    with open(path, encoding="utf-8") as f:
        errs = check(f.read(), writer=writer, head=head)
    for e in errs:
        print(e)
    return 1 if errs else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
