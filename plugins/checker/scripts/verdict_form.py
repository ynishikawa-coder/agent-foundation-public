#!/usr/bin/env python3
"""チェック役の判定のコメントが決まりの形かを見る（形だけ・中身の良し悪しは見ない）。

見る事:
  1. 1 行目 `レビューした窓: <session id> 判定: green|red`
  2. 2 行目 `見た先端: <SHA の先頭 12 文字>`
  3. `## verdict` の次の行が green／red／red（blocked: …）で、1 行目の判定と合う
  4. `## 所見` の各行の札 `- [止める|後の便|直った｜<段>] …`。`[止める｜…]` か点の fail が 1 つでも在れば red、無ければ green
  5. 別の目: 書いた窓（--writer）とレビューした窓が同じなら形の誤り（自分の PR に判定を付けない）
  6. `## 点` に、review-pr の SKILL.md の「見る点」の表の点（番号と名）が全部 1 行ずつ在り、
     各行の値が pass／fail／N/A のどれか（点 3 は `書いた窓 <id> ≠ この窓` も可）。
     欠け・重なり・表に無い点・選べる値の外・同じ見出しの節が 2 つ在るのは誤り。
     点「全体の絵」は N/A にできず、pass は `pass（差なし・版 <版>）` の形だけ（照らさずに通さない）。
     点の正本は SKILL.md の表 1 か所（ここに写さない）。表が読めない時は止まる（点を見ずに通さない）。

使い方: python3 verdict_form.py <コメントのファイル> [--writer <書いた窓の session id>] [--head <PR の先端の SHA>]
  誤りを 1 行ずつ出し、誤りがあれば exit 1。
"""
import re
import sys
from pathlib import Path

SKILL = Path(__file__).resolve().parent.parent / "skills" / "review-pr" / "SKILL.md"

LINE1 = re.compile(r"^レビューした窓: (session_[A-Za-z0-9]+) 判定: (green|red)$")
LINE2 = re.compile(r"^見た先端: ([0-9a-f]{12})$")
VERDICT = re.compile(r"^(green|red)(?:（blocked: .+）)?$")
CARD = re.compile(r"^- [\[［](止める|後の便|直った)[｜|](設計|整地|見本|承認|実装|レビュー)[\]］] \S")
CARDS = ("止める", "後の便", "直った")
POINT_ROW = re.compile(r"^\| (\d+) (\S[^|]*?) \|")
POINT_LINE = re.compile(r"^- (\d+) ([^:：]+)[:：] ?(.*)$")
VALUE = re.compile(r"^(pass|fail|N/A)(?:$|[ （(])")
PICTURE = "全体の絵"
PICTURE_PASS = re.compile(r"^pass（差なし・版 \d{4}-\d{2}-\d{2}\.\d+）$")
OTHER_EYE = re.compile(r"^書いた窓 (session_[A-Za-z0-9]+) ≠ この窓$")


def load_points(path=SKILL):
    """review-pr の「見る点」の表から {番号: 名}。表が読めなければ例外（黙って空で進めない）。"""
    text = Path(path).read_text(encoding="utf-8")
    points = {}
    for ln in section(text.splitlines(), "見る点") or []:
        m = POINT_ROW.match(ln)
        if m:
            points[int(m.group(1))] = m.group(2).strip()
    if not points:
        raise ValueError("見る点の表が読めない: %s" % path)
    return points


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


def check_points(lines, points, reviewer=None, writer=None):
    """`## 点` の欄の誤りと、fail の数。"""
    errs, fails = [], 0
    body = section(lines, "点")
    if body is None:
        return ["`## 点` の節が無い"], 0
    seen = set()
    for ln in body:
        s = ln.strip()
        if not s:
            continue
        m = POINT_LINE.match(s)
        if not m:
            errs.append("点の行が `- <番号> <名>: pass|fail|N/A` でない: %s" % s[:40])
            continue
        no, name, val = int(m.group(1)), m.group(2).strip(), m.group(3).strip()
        if no not in points:
            errs.append("点 %d は見る点の表に無い" % no)
            continue
        if no in seen:
            errs.append("点 %d が 2 度在る" % no)
        seen.add(no)
        if name != points[no]:
            errs.append("点 %d の名が `%s` でない（今は `%s`）" % (no, points[no], name))
        eye = OTHER_EYE.match(val) if no == 3 else None
        if eye:
            if reviewer and eye.group(1) == reviewer:
                errs.append("点 3: 書いた窓とレビューした窓が同じ（別の目でない）")
            if writer and eye.group(1) != writer:
                errs.append("点 3: 書いた窓 %s が --writer %s と違う" % (eye.group(1), writer))
            continue
        mv = VALUE.match(val)
        if not mv:
            errs.append("点 %d の値が pass／fail／N/A のどれでもない: %s" % (no, val[:20]))
            continue
        if points[no] == PICTURE:
            if mv.group(1) == "N/A":
                errs.append("点 %d %s は N/A にできない（絵が無ければ fail）" % (no, PICTURE))
            elif mv.group(1) == "pass" and not PICTURE_PASS.match(val):
                errs.append("点 %d %s の pass が `pass（差なし・版 YYYY-MM-DD.n）` でない（照らした版を書く）" % (no, PICTURE))
        if mv.group(1) == "fail":
            fails += 1
    for no in sorted(set(points) - seen):
        errs.append("点 %d %s の行が無い" % (no, points[no]))
    return errs, fails


def check(text, writer=None, head=None, points=None):
    if points is None:
        points = load_points()
    errs = []
    lines = (text or "").splitlines()
    m1 = LINE1.match(lines[0].strip()) if lines else None
    m2 = LINE2.match(lines[1].strip()) if len(lines) > 1 else None
    if not m1:
        errs.append("1 行目が `レビューした窓: <session id> 判定: green|red` でない")
    if not m2:
        errs.append("2 行目が `見た先端: <SHA12>` でない")
    reviewer, judged = (m1.group(1), m1.group(2)) if m1 else (None, None)
    for h in ("verdict", "点", "所見"):
        n = sum(1 for ln in lines if ln.strip() == "## " + h)
        if n > 1:
            errs.append("`## %s` の節が %d 個在る（1 つだけにする）" % (h, n))
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
    perrs, fails = check_points(lines, points, reviewer=reviewer, writer=writer)
    errs.extend(perrs)
    want = "red" if stops or fails else "green"
    blocked = bool(mv and "blocked" in body[0])
    if judged and not blocked and judged != want:
        errs.append("`[止める｜…]` が %d 個・点の fail が %d 個なので判定は %s（今は %s）" % (stops, fails, want, judged))
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
