#!/usr/bin/env python3
"""チェック役の判定のコメントが決まりの形かを見る（形だけ・中身の良し悪しは見ない）。

見る事:
  1. 1 行目 `レビューした窓: <session id> 判定: green|red`
  2. 2 行目 `見た先端: <SHA の先頭 12 文字>`
  3. `## verdict` の次の行が green／red／red（blocked: …）で、1 行目の判定と合う
  4. `## 所見` の各行の札 `- [止める|台帳へ|直った｜<段>] …`。`[止める｜…]` か点の fail が 1 つでも在れば red、無ければ green
  5. 別の目: 書いた窓（--writer）とレビューした窓が同じなら形の誤り（自分の PR に判定を付けない）
  6. `## 点` に、review-pr の SKILL.md の「見る点」の表の点（番号と名）が全部 1 行ずつ在り、
     各行の値がその点に選べる値のどれか。選べる値は SKILL.md の「判定の形」の雛形の `## 点` の行
     （`- 1 依頼の充足: pass/fail`・`- 8 歯と口・注入の試験: pass/fail/N/A`・点 3 は `書いた窓 <id> ≠ この窓`）から点ごとに読む。
     欠け・重なり・表に無い点・その点に選べる値の外（例: 点 1〜7 の N/A）・同じ見出しの節が 2 つ在るのは誤り。
     点と選べる値の正本は SKILL.md の 1 か所（ここに写さない）。読めない時は止まる（点を見ずに通さない）。
  7. red（blocked を除く）は `## verdict` に `直し: 細目 §3「まず構造を疑う」` の行が在る
     （所見を直す行の一覧として返さず、根治の入口を指す。中身は細目が正本＝ここは指すだけ）。

  8. 所見の札（止める・台帳へ・直った）と段（設計・整地…）は、review-pr の SKILL.md の「判定の形」の節の
     「- 札は」の行から読む（ここに写さない＝札や段を足す PR がこの file の定数を触らない）。読めない時は止まる。

  9. 判定のコメントかの見分け（looks_verdict）も、判定を返す 1 行（return_line）もここが正本。guard の pr_text は
     looks_verdict を直に呼び、返しの 1 行は --return-line が組む（手で組まない）。判定の決まりの文 JUDGE_RULE・
     SAME_EYE_RULE は review-pr の SKILL.md がそのまま載せ、試験が一致を照らす。窓の id の形は window_shape（lib）。

使い方: python3 verdict_form.py <コメントのファイル> [<ファイル> …] --writer <書いた窓の session id> --head <PR の先端の SHA>
        [--return-line --pr <PR の番号> --branch <枝> --ruler <物差しの最後の行>]
  --return-line: 形に誤りが無い時だけ、返しの 1 行（RETURN_LINE の形）を出す（ファイルは 1 つだけ）。
       python3 verdict_form.py --looks <コメントのファイル>
  --looks: 判定のコメントかだけを `verdict`／`other` の 1 行で出す（exit 0）。guard の pr_text がこれを呼ぶ。
  --writer と --head は欠かせない（欠けたら別の目と先端を照らさずに通さない＝exit 2）。
  助手（Agent）の判定は立てた窓の session id で書く。書いた窓が立てた助手の判定は --writer と同じになり誤り。
  ファイルは全部照らす（2 つ以上の時は誤りの頭にファイルの名）。誤りを 1 行ずつ出し、どれかに誤りがあれば exit 1。
"""
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "lib"))
from window_shape import SESSION_ID_PAT  # noqa: E402  窓の id の形の正本（土台の window-shape/ への symlink）

SKILL = Path(__file__).resolve().parent.parent / "skills" / "review-pr" / "SKILL.md"

# 判定の決まりの文（review-pr の SKILL.md はこの文をそのまま載せる＝試験が照らす。決め方は check の want）。
JUDGE_RULE = "`[止める｜…]` か点の fail が 1 つでも在れば red、どちらも無ければ green（1 行目の `判定:` と合わせる）。"
SAME_EYE_RULE = "書いた窓と同じ窓は判定を書かない（名乗りが無い・合わない時は `red（blocked: …）`）。"

LINE1 = re.compile(r"^レビューした窓: (%s) 判定: (green|red)$" % SESSION_ID_PAT)
LINE2 = re.compile(r"^見た先端: ([0-9a-f]{12})$")
VERDICT = re.compile(r"^(green|red)(?:（blocked: .+）)?$")
STOP_CARD = "止める"   # 1 つでも在れば red になる札（判定の決まりの軸。名は SKILL.md の札の並びに在ることを load_cards が確かめる）
POINT_ROW = re.compile(r"^\| (\d+) (\S[^|]*?) \|")
POINT_LINE = re.compile(r"^- (\d+) ([^:：]+)[:：] ?(.*)$")
VALUE = re.compile(r"^(pass|fail|N/A)(?:$|[ （(])")
OTHER_EYE = re.compile(r"^書いた窓 (%s) ≠ この窓$" % SESSION_ID_PAT)
TEMPLATE_EYE = "書いた窓 <id> ≠ この窓"   # 雛形の点 3 の値の書き方（OTHER_EYE の雛形の形）
TEMPLATE_VALUES = re.compile(r"^((?:pass|fail|N/A)(?:/(?:pass|fail|N/A))*)(?:$|[ （(])")
ROOT_CAUSE = "直し: 細目 §3「まず構造を疑う」"

# 判定のコメントかの見分け（guard の pr_text が直に呼ぶ）: 名乗りの欄と判定が 1 行に揃う行（どの行でも・`:` の全角半角を
# 問わない）か、verdict の見出し（# の数・大小文字を問わない）。コードの囲み・HTML のコメントの中は数えない。崩れた判定も
# 判定として拾い、上の形で照らす（形の崩れを見分けの外へ逃がさない）。
LOOKS_LINE = re.compile(r"^[ \t]*レビューした窓\s*[:：].*判定\s*[:：]\s*(?:green|red)\b", re.M | re.I)
LOOKS_HEAD = re.compile(r"^[ \t]*#{1,6}\s*verdict\s*$", re.M | re.I)
_FENCE = re.compile(r"^\s*(```|~~~).*?^\s*\1", re.M | re.S)
_COMMENT = re.compile(r"<!--.*?-->", re.S)

# 判定を返す 1 行の形（review-pr の手順 5。--return-line が組む）。
RETURN_LINE = "判定 {pr} {branch}@{sha} verdict={verdict} レビューした窓={reviewer} 物差し={ruler}"
RETURN_RED = " 直し=細目 §3「まず構造を疑う」"


def looks_verdict(body):
    """判定のコメントか。文中に「判定: green」と書いた普通のコメントや「レビューした窓は…」の文は判定と見なさない。"""
    body = _FENCE.sub(" ", _COMMENT.sub(" ", body or ""))
    return bool(LOOKS_LINE.search(body) or LOOKS_HEAD.search(body))


def return_line(text, pr, branch, ruler):
    """形の通った判定から返しの 1 行。1 行目・2 行目が読めなければ None。"""
    lines = (text or "").splitlines()
    m1 = LINE1.match(lines[0].strip()) if lines else None
    m2 = LINE2.match(lines[1].strip()) if len(lines) > 1 else None
    if not (m1 and m2):
        return None
    out = RETURN_LINE.format(pr=pr, branch=branch, sha=m2.group(1), verdict=m1.group(2), reviewer=m1.group(1),
                             ruler=" ".join(str(ruler).split()))
    return out + (RETURN_RED if m1.group(2) == "red" else "")


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


def load_values(path=SKILL):
    """review-pr の「判定の形」の雛形の `## 点` の行から {番号: 選べる値の組}。点 3 の別の目の形は {"eye"}。
    雛形が読めない・点の値が読めない行が在る時は例外（黙って pass／fail／N/A を全部許さない）。"""
    lines = [ln.strip() for ln in Path(path).read_text(encoding="utf-8").splitlines()]
    try:
        start = lines.index("## 点")
    except ValueError:
        raise ValueError("判定の形の雛形の `## 点` が読めない: %s" % path)
    out = {}
    for ln in lines[start + 1:]:
        if not ln.startswith("- "):
            break
        m = POINT_LINE.match(ln)
        if not m:
            raise ValueError("雛形の点の行が読めない: %s" % ln[:40])
        val = m.group(3).strip()
        if val == TEMPLATE_EYE:
            out[int(m.group(1))] = frozenset({"eye"})
            continue
        mv = TEMPLATE_VALUES.match(val)
        if not mv:
            raise ValueError("雛形の点 %s の選べる値が読めない: %s" % (m.group(1), val[:30]))
        out[int(m.group(1))] = frozenset(re.findall(r"pass|fail|N/A", mv.group(1)))
    if not out:
        raise ValueError("判定の形の雛形の `## 点` に行が無い: %s" % path)
    return out


def load_cards(path=SKILL):
    """review-pr の「判定の形」の「札は」の行から (札の並び, 段の並び)。読めなければ例外（黙って既定で進めない）。"""
    text = Path(path).read_text(encoding="utf-8")
    for ln in text.splitlines():
        if ln.startswith("- 札は") and "段は" in ln:
            cards = re.findall(r"`\[([^｜|\]`]+)[｜|]<段>\]`", ln)
            m = re.search(r"段は((?:\s*`[^`]+`\s*・?)+)", ln)
            steps = re.findall(r"`([^`]+)`", m.group(1)) if m else []
            if cards and steps and STOP_CARD in cards:
                return tuple(cards), tuple(steps)
    raise ValueError("判定の形の札と段が読めない: %s" % path)


def card_re(cards, steps):
    return re.compile(r"^- [\[［](%s)[｜|](%s)[\]］] \S" % ("|".join(map(re.escape, cards)), "|".join(map(re.escape, steps))))


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


def check_points(lines, points, reviewer=None, writer=None, values=None):
    """`## 点` の欄の誤りと、fail の数。values は {番号: 選べる値の組}（既定は SKILL.md の雛形から読む）。"""
    if values is None:
        values = load_values()
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
        allowed = values.get(no)
        if allowed is None:
            errs.append("点 %d の選べる値が判定の形の雛形に無い（SKILL.md の雛形に足す）" % no)
            continue
        eye = OTHER_EYE.match(val) if "eye" in allowed else None
        if eye:
            if reviewer and eye.group(1) == reviewer:
                errs.append("点 3: 書いた窓とレビューした窓が同じ（別の目でない）")
            if writer and eye.group(1) != writer:
                errs.append("点 3: 書いた窓 %s が --writer %s と違う" % (eye.group(1), writer))
            continue
        mv = VALUE.match(val)
        if not mv or mv.group(1) not in allowed:
            want = "書いた窓 <id> ≠ この窓" if "eye" in allowed else "／".join(v for v in ("pass", "fail", "N/A") if v in allowed)
            errs.append("点 %d の値が %s のどれでもない: %s" % (no, want, val[:20]))
            continue
        if mv.group(1) == "fail":
            fails += 1
    for no in sorted(set(points) - seen):
        errs.append("点 %d %s の行が無い" % (no, points[no]))
    return errs, fails


def check(text, writer=None, head=None, points=None, cards=None, values=None):
    if points is None:
        points = load_points()
    if values is None:
        values = load_values()
    if cards is None:
        cards = load_cards()
    card = card_re(*cards)
    shape = "- [%s｜<段>] …" % "|".join(cards[0])
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
        if not card.match(s):
            errs.append("所見の行の札が `%s` でない: %s" % (shape, s[:40]))
            continue
        if re.match(r"^- [\[［]%s" % STOP_CARD, s):
            stops += 1
    perrs, fails = check_points(lines, points, reviewer=reviewer, writer=writer, values=values)
    errs.extend(perrs)
    want = "red" if stops or fails else "green"
    blocked = bool(mv and "blocked" in body[0])
    if judged == "red" and not blocked and not any(ln.startswith(ROOT_CAUSE) for ln in body[1:]):
        errs.append("red なのに `## verdict` に `%s` の行が無い（指摘を 1 つずつ手直しで返さない）" % ROOT_CAUSE)
    if judged and not blocked and judged != want:
        errs.append("`[止める｜…]` が %d 個・点の fail が %d 個なので判定は %s（今は %s）" % (stops, fails, want, judged))
    return errs


def main(argv):
    args = argv[1:]
    if not args:
        sys.stderr.write(__doc__)
        return 2
    if args[0] == "--looks":
        if len(args) != 2:
            sys.stderr.write("--looks はファイル 1 つ\n")
            return 2
        with open(args[1], encoding="utf-8") as f:
            print("verdict" if looks_verdict(f.read()) else "other")
        return 0
    opts, paths, i = {"--writer": None, "--head": None, "--pr": None, "--branch": None, "--ruler": None}, [], 0
    want_return = "--return-line" in args
    args = [a for a in args if a != "--return-line"]
    while i < len(args):
        a = args[i]
        if a in opts:
            if opts[a] is not None:
                sys.stderr.write("%s を 2 度書いている（どちらを使うか決められない）\n" % a)
                return 2
            if i + 1 >= len(args) or args[i + 1].startswith("--"):
                sys.stderr.write("%s の後に値を書く\n" % a)
                return 2
            opts[a] = args[i + 1]
            i += 2
            continue
        if a.startswith("--"):
            sys.stderr.write("知らない印: %s\n" % a)
            return 2
        paths.append(a)
        i += 1
    if not paths:
        sys.stderr.write(__doc__)
        return 2
    if not opts["--writer"] or not opts["--head"]:
        # 欠けた材料で通さない: 書いた窓が無いと別の目を、先端が無いと見た後の push を照らせない
        sys.stderr.write("--writer <書いた窓の session id> と --head <PR の先端の SHA> の両方が要る（欠けたまま形を通さない）\n")
        return 2
    if want_return and (len(paths) != 1 or not all(opts[k] for k in ("--pr", "--branch", "--ruler"))):
        sys.stderr.write("--return-line はファイル 1 つと --pr・--branch・--ruler が要る（欠けたまま返しの行を組まない）\n")
        return 2
    bad = 0
    for path in paths:
        with open(path, encoding="utf-8") as f:
            errs = check(f.read(), writer=opts["--writer"], head=opts["--head"])
        bad += bool(errs)
        for e in errs:
            print(("%s: %s" % (path, e)) if len(paths) > 1 else e)
    if len(paths) > 1:
        print("照らしたファイル %d・誤りのあるファイル %d" % (len(paths), bad))
    if want_return and not bad:
        with open(paths[0], encoding="utf-8") as f:
            print(return_line(f.read(), opts["--pr"], opts["--branch"], opts["--ruler"]))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
