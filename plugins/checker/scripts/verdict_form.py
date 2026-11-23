#!/usr/bin/env python3
"""チェック役の判定のコメントが決まりの形かを見る（形だけ・中身の良し悪しは見ない）。

見る事:
  1. 1 行目 `レビューした窓: <session id> 判定: green|red`
  2. 2 行目 `見た先端: <SHA の先頭 12 文字>`
  3. `## verdict` の次の行が green／red／red（blocked: …）で、1 行目の判定と合う
  4. `## 所見` の各行の札 `- [止める|台帳へ|直った｜<段>] …`。`[止める｜…]` か点の fail が 1 つでも在れば red、無ければ green
  5. 別の目: 書いた窓（--writer）のどれかとレビューした窓が同じなら形の誤り（自分の PR に判定を付けない）。
     --writer は PR の commit の `Claude-Session:` の窓の全部を `,` で並べて渡す（同じ plugin の scripts/pr_writer.py --writers が出す。
     途中の commit を書いた窓も書いた側）。
  9. 名乗り: --reviewer（判定を出す窓の本物の id＝守りの hook が窓の環境の記録から読んで渡す）が在れば、1 行目の
     `レビューした窓:` の字はその写しとして照らす: 違えば誤り。別の目もその本物の id で照らす（手で書いた名乗りで決めない）。
     読むだけの助手（Agent）は立てた窓の環境を受け継ぐので、立てた窓の id で名乗る今の形のまま通る。
  6. `## 点` に、review-pr の SKILL.md の「見る点」の表の点（番号と名）が全部 1 行ずつ在り、
     各行の値がその点に選べる値のどれか。選べる値は SKILL.md の「判定の形」の雛形の `## 点` の行
     （`- 1 依頼の充足: pass/fail`・`- 8 歯と口・注入の試験: pass/fail/N/A`・点 3 は `書いた窓 <id> ≠ この窓`）から点ごとに読む。
     欠け・重なり・表に無い点・その点に選べる値の外（例: 点 1〜7 の N/A）・同じ見出しの節が 2 つ在るのは誤り。
     点と選べる値の正本は SKILL.md の 1 か所（ここに写さない）。読めない時は止まる（点を見ずに通さない）。
  7. red（blocked を除く）は `## verdict` に `直し: 細目 §3「まず構造を疑う」` の行が在る
     （所見を直す行の一覧として返さず、根治の入口を指す。中身は細目が正本＝ここは指すだけ）。

  8. 所見の札（止める・台帳へ・直った）と段（設計・整地…）は、review-pr の SKILL.md の「判定の形」の節の
     「- 札は」の行から読む（ここに写さない＝札や段を足す PR がこの file の定数を触らない）。読めない時は止まる。

  10. 3 行目 `決まりの版: <SHA の先頭 12 文字>`＝この判定が従う土台の commit（その commit の review-pr の SKILL.md の
     見る点・選べる値・札で照らす）。--first（PR の初めの判定の決まりの版・無ければ `なし`）と照らす:
     SHA なら同じ版でなければ誤り（レビューは始めた時の決まりで見る＝途中で main の決まりが変わっても見直しで点を増やさない）。
     `なし`（初めの判定）なら、その版の SKILL.md が main の先端の物と同じでなければ誤り（古い決まりで始めない）。
     版の SKILL.md は決まりの git（環境変数 AF_RULES_GIT・無ければ土台の取り出し ~/.claude/plugins/marketplaces/agent-foundation）
     から読み、main の先端は origin を聞いて決める。読めない時は exit 2（版を照らさずに通さない）。
     ただし SKILL.md の「版によらず当てる点」の行に並ぶ点（安全の点）は、main の先端の名と値で必ず当てる（版が古くても外れない）。

使い方: python3 verdict_form.py <コメントのファイル> [<ファイル> …] --writer <書いた窓の session id>[,<id> …] --head <PR の先端の SHA>
          --first <PR の初めの判定の決まりの版 SHA12|なし> [--reviewer <判定を出す窓の session id>]
  --writer・--head は欠かせない（欠けたら別の目・先端を照らさずに通さない＝exit 2）。--first と 3 行目は、壊れる変更の
  1 段目の間は無くても通す（無い時は前の形＝main の先端の決まりで照らす。2 段目で欠かせなくする・CONTRIBUTING.md「配り方と「壊れる:」変更」）。
  --first の値は review_gate.py が「入ってよい」の時に出す（PR のコメントから first_rules で読む・手で決めない）。
  助手（Agent）の判定は立てた窓の session id で書く。書いた窓が立てた助手の判定は --writer と同じになり誤り。
  ファイルは全部照らす（2 つ以上の時は誤りの頭にファイルの名）。誤りを 1 行ずつ出し、どれかに誤りがあれば exit 1。
"""
import os
import re
import subprocess
import sys
from pathlib import Path

SKILL = Path(__file__).resolve().parent.parent / "skills" / "review-pr" / "SKILL.md"
SKILL_IN_REPO = "plugins/checker/skills/review-pr/SKILL.md"
RULES_GIT_ENV = "AF_RULES_GIT"   # 決まりの git（版ごとの SKILL.md を読む取り出し・origin が土台の repo）
MARKET = "agent-foundation"      # 既定の決まりの git: ~/.claude/plugins/marketplaces/<MARKET>
NO_FIRST = "なし"                # --first の値: この PR にまだ決まりの版を持つ判定が無い

LINE1 = re.compile(r"^レビューした窓: (session_[A-Za-z0-9]+) 判定: (green|red)$")
LINE2 = re.compile(r"^見た先端: ([0-9a-f]{12})$")
LINE3 = re.compile(r"^決まりの版: ([0-9a-f]{12})$")
ALWAYS = re.compile(r"^- 版によらず当てる点: (\d+(?:・\d+)*)(?:$|[ （(])")
VERDICT = re.compile(r"^(green|red)(?:（blocked: .+）)?$")
STOP_CARD = "止める"   # 1 つでも在れば red になる札（判定の決まりの軸。名は SKILL.md の札の並びに在ることを load_cards が確かめる）
POINT_ROW = re.compile(r"^\| (\d+) (\S[^|]*?) \|")
POINT_LINE = re.compile(r"^- (\d+) ([^:：]+)[:：] ?(.*)$")
VALUE = re.compile(r"^(pass|fail|N/A)(?:$|[ （(])")
OTHER_EYE = re.compile(r"^書いた窓 (session_[A-Za-z0-9]+) ≠ この窓$")
TEMPLATE_EYE = "書いた窓 <id> ≠ この窓"   # 雛形の点 3 の値の書き方（OTHER_EYE の雛形の形）
TEMPLATE_VALUES = re.compile(r"^((?:pass|fail|N/A)(?:/(?:pass|fail|N/A))*)(?:$|[ （(])")
ROOT_CAUSE = "直し: 細目 §3「まず構造を疑う」"
SESSION_ID = re.compile(r"^session_[A-Za-z0-9]+$")


def writer_set(writer):
    """--writer の値（`,` で並べた字か並び）を書いた窓の組にする。"""
    if not writer:
        return set()
    items = writer.split(",") if isinstance(writer, str) else list(writer)
    return {w.strip() for w in items if w and w.strip()}


def _text(path, text):
    return text if text is not None else Path(path).read_text(encoding="utf-8")


def load_points(path=SKILL, text=None):
    """review-pr の「見る点」の表から {番号: 名}。表が読めなければ例外（黙って空で進めない）。"""
    text = _text(path, text)
    points = {}
    for ln in section(text.splitlines(), "見る点") or []:
        m = POINT_ROW.match(ln)
        if m:
            points[int(m.group(1))] = m.group(2).strip()
    if not points:
        raise ValueError("見る点の表が読めない: %s" % path)
    return points


def load_values(path=SKILL, text=None):
    """review-pr の「判定の形」の雛形の `## 点` の行から {番号: 選べる値の組}。点 3 の別の目の形は {"eye"}。
    雛形が読めない・点の値が読めない行が在る時は例外（黙って pass／fail／N/A を全部許さない）。"""
    lines = [ln.strip() for ln in _text(path, text).splitlines()]
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


def load_cards(path=SKILL, text=None):
    """review-pr の「判定の形」の「札は」の行から (札の並び, 段の並び)。読めなければ例外（黙って既定で進めない）。"""
    text = _text(path, text)
    for ln in text.splitlines():
        if ln.startswith("- 札は") and "段は" in ln:
            cards = re.findall(r"`\[([^｜|\]`]+)[｜|]<段>\]`", ln)
            m = re.search(r"段は((?:\s*`[^`]+`\s*・?)+)", ln)
            steps = re.findall(r"`([^`]+)`", m.group(1)) if m else []
            if cards and steps and STOP_CARD in cards:
                return tuple(cards), tuple(steps)
    raise ValueError("判定の形の札と段が読めない: %s" % path)


def load_always(path=SKILL, text=None):
    """「見る点」の節の `- 版によらず当てる点: 5・…` の行から点の番号の組（安全の点＝決まりの版によらず main の先端で当てる）。
    行が無ければ例外（黙って空の組で進めない＝安全の点を版の古さで外さない）。"""
    for ln in section(_text(path, text).splitlines(), "見る点") or []:
        m = ALWAYS.match(ln.strip())
        if m:
            return frozenset(int(n) for n in m.group(1).split("・"))
    raise ValueError("見る点の節に `- 版によらず当てる点:` の行が無い: %s" % path)


def first_rules(bodies):
    """PR のコメントの本文の並び（古い順）から、初めの判定の `決まりの版` の SHA12。無ければ None。
    判定は 1 行目が名乗りの形・3 行目が決まりの版の形の物だけ（決まりの版を持たない古い形の判定は数えない）。
    review_gate.py（--first を出す）と guard の pr_text（判定を出す前に照らす）の両方がここを呼ぶ（写さない）。"""
    for body in bodies or []:
        lines = (body or "").splitlines()
        if len(lines) > 2 and LINE1.match(lines[0].strip()):
            m = LINE3.match(lines[2].strip())
            if m:
                return m.group(1)
    return None


def rules_git(env=None):
    env = os.environ if env is None else env
    if env.get(RULES_GIT_ENV):
        return Path(env[RULES_GIT_ENV])
    return Path(env.get("HOME") or Path.home()) / ".claude" / "plugins" / "marketplaces" / MARKET


def _git(repo, *args):
    r = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True, timeout=60)
    if r.returncode:
        raise RuntimeError("git %s: %s" % (args[0], (r.stderr or "").strip()[:200]))
    return r.stdout.strip()


def _commit(repo, sha):
    """短い SHA を決まりの git の commit に解く。手元に無ければ origin の main を取ってから解き直す。"""
    for attempt in (0, 1):
        r = subprocess.run(["git", "-C", str(repo), "rev-parse", "--verify", "-q", sha + "^{commit}"],
                           capture_output=True, text=True, timeout=60)
        if r.returncode == 0:
            return r.stdout.strip()
        if attempt == 0:
            _git(repo, "fetch", "-q", "origin", "main")
    raise RuntimeError("決まりの版 %s が決まりの git %s に無い" % (sha, repo))


class Rules:
    """決まりの版の SKILL.md の点・値・札に、main の先端の「版によらず当てる点」を重ねた物。"""

    def __init__(self, ver, tip, points, values, cards):
        self.ver, self.tip, self.points, self.values, self.cards = ver, tip, points, values, cards


def load_rules(ver, first, repo=None):
    """決まりの版 ver（判定の 3 行目）を --first と照らし、照らせたら Rules を返す。
    返り: (Rules か None, 誤りの並び)。決まりの git が読めない時は例外（呼ぶ側が exit 2 にする）。"""
    repo = rules_git() if repo is None else Path(repo)
    if not (repo / ".git").exists() and not (repo / "HEAD").exists():
        raise RuntimeError("決まりの git %s が無い（%s に path を置くか土台の取り出しを入れる）" % (repo, RULES_GIT_ENV))
    line = _git(repo, "ls-remote", "--quiet", "origin", "refs/heads/main")
    if not line:
        raise RuntimeError("決まりの git の origin に main が無い")
    tip = line.split()[0]
    _commit(repo, tip)
    tip_text = _git(repo, "show", "%s:%s" % (tip, SKILL_IN_REPO))
    if first != NO_FIRST and not first.startswith(ver) and not ver.startswith(first):
        return None, ["決まりの版 %s がこの PR の初めの判定の版 %s と違う（レビューは始めた時の決まりで見る＝"
                      "`決まりの版: %s` で書き、その版の見る点で見る）" % (ver, first[:12], first[:12])]
    full = _commit(repo, ver)
    if first == NO_FIRST and _git(repo, "rev-parse", "%s:%s" % (full, SKILL_IN_REPO)) != \
            _git(repo, "rev-parse", "%s:%s" % (tip, SKILL_IN_REPO)):
        return None, ["決まりの版 %s の見る点が main の先端 %s の物と違う（初めの判定は main の先端の決まりで書く＝"
                      "`決まりの版: %s`）" % (ver, tip[:12], tip[:12])]
    text = _git(repo, "show", "%s:%s" % (full, SKILL_IN_REPO))
    points, values, cards = dict(load_points(text=text)), dict(load_values(text=text)), load_cards(text=text)
    tip_points, tip_values = load_points(text=tip_text), load_values(text=tip_text)
    for no in load_always(text=tip_text):
        if no not in tip_points or no not in tip_values:
            raise ValueError("版によらず当てる点 %d が main の先端の見る点の表か雛形に無い" % no)
        points[no], values[no] = tip_points[no], tip_values[no]
    return Rules(full[:12], tip[:12], points, values, cards), []


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
    writers = writer_set(writer)
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
            if writers and eye.group(1) not in writers:
                errs.append("点 3: 書いた窓 %s が --writer %s のどれとも違う" % (eye.group(1), ",".join(sorted(writers))))
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


def check(text, writer=None, head=None, points=None, cards=None, values=None, poster=None, rules=None):
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
    m3 = LINE3.match(lines[2].strip()) if len(lines) > 2 else None
    if not m1:
        errs.append("1 行目が `レビューした窓: <session id> 判定: green|red` でない")
    if not m2:
        errs.append("2 行目が `見た先端: <SHA12>` でない")
    # 3 行目の無い判定は 1 段目の間は古い形として通す（main の先端の点で照らす・CONTRIBUTING.md「配り方と「壊れる:」変更」・古い形.json verdict-no-rules-line）
    if m3 and rules and rules != m3.group(1):
        errs.append("決まりの版 %s が照らした版 %s と違う" % (m3.group(1), rules))
    reviewer, judged = (m1.group(1), m1.group(2)) if m1 else (None, None)
    if poster:
        # 名乗りの字は写し。判定を出す窓の本物の id（記録）と照らし、別の目はその本物の id で見る
        if reviewer and reviewer != poster:
            errs.append("1 行目の `レビューした窓: %s` が判定を出す窓 %s と違う（名乗りは出す窓の id で書く。書いた窓の"
                        "中の助手は判定を出せない＝別の窓で当てる）" % (reviewer, poster))
        reviewer = poster
    for h in ("verdict", "点", "所見"):
        n = sum(1 for ln in lines if ln.strip() == "## " + h)
        if n > 1:
            errs.append("`## %s` の節が %d 個在る（1 つだけにする）" % (h, n))
    if m2 and head and not head.startswith(m2.group(1)):
        errs.append("見た先端 %s が PR の今の先端 %s と違う（見直して判定を足す）" % (m2.group(1), head[:12]))
    if reviewer and reviewer in writer_set(writer):
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


class Unreadable(Exception):
    """決まりの版の見る点を読めない（決まりの git が無い・版が無い・先端の安全の点の行が無い）。呼ぶ側は通さずに止める。"""


def check_posted(text, first, writer=None, head=None, poster=None, repo=None):
    """1 つの判定を、その 3 行目の決まりの版（first＝この PR の初めの判定の版か `なし`）の見る点で照らし、誤りの並びを返す。
    main と、判定を数える他の repo の関所（例: pixel-office の pr_review_gate）が呼ぶ 1 つの口（先端の点で照らす写しを持たせない）。
    3 行目が無い判定と first が None（--first の無い古い呼び方）は、1 段目の間は前の形として main の先端の点で照らす
    （CONTRIBUTING.md「配り方と「壊れる:」変更」・古い形.json の verdict-no-rules-line）。版を読めない時は Unreadable。"""
    lines = (text or "").splitlines()
    m3 = LINE3.match(lines[2].strip()) if len(lines) > 2 else None
    rules, rerrs = None, []
    if m3 and first is not None:
        try:
            rules, rerrs = load_rules(m3.group(1), first, repo)
        except (OSError, RuntimeError, ValueError, subprocess.SubprocessError) as e:
            raise Unreadable("決まりの版 %s の見る点を読めない（%s）" % (m3.group(1), e)) from e
    if rules:
        return check(text, writer=writer, head=head, poster=poster,
                     points=rules.points, values=rules.values, cards=rules.cards, rules=rules.ver)
    return rerrs + check(text, writer=writer, head=head, poster=poster)


def main(argv):
    args = argv[1:]
    if not args:
        sys.stderr.write(__doc__)
        return 2
    opts, paths, i = {"--writer": None, "--head": None, "--reviewer": None, "--first": None}, [], 0
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
    if not writer_set(opts["--writer"]) or not opts["--head"]:
        # 欠けた材料で通さない: 書いた窓が無いと別の目を、先端が無いと見た後の push を照らせない
        sys.stderr.write("--writer <書いた窓の session id>・--head <PR の先端の SHA> が"
                         "全部要る（欠けたまま形を通さない）\n")
        return 2
    if opts["--first"] is None:
        # 1 段目の間は --first の無い古い呼び方も通す（main の先端の決まりで照らす・CONTRIBUTING.md「配り方と「壊れる:」変更」）
        sys.stderr.write("--first が無い古い呼び方。決まりの版を照らさず main の先端の決まりで照らす"
                         "（review_gate.py が出す --first を渡す形へ移る）\n")
    elif opts["--first"] != NO_FIRST and not re.fullmatch(r"[0-9a-f]{12,40}", opts["--first"]):
        sys.stderr.write("--first の値が SHA（12 文字以上）か `%s` でない: %s\n" % (NO_FIRST, opts["--first"][:20]))
        return 2
    bad_ids = [w for w in writer_set(opts["--writer"]) | ({opts["--reviewer"]} if opts["--reviewer"] else set())
               if not SESSION_ID.match(w)]
    if bad_ids:
        sys.stderr.write("--writer・--reviewer の値が窓の id（session_…）の形でない: %s\n" % "・".join(sorted(bad_ids)))
        return 2
    bad = 0
    for path in paths:
        with open(path, encoding="utf-8") as f:
            text = f.read()
        try:
            errs = check_posted(text, opts["--first"], writer=opts["--writer"], head=opts["--head"], poster=opts["--reviewer"])
        except Unreadable as e:
            # 決まりの版を読めない時は照らさずに通さない（古い・知らない決まりで形を通さない）
            sys.stderr.write("%s。照らさずに通さない\n" % e)
            return 2
        bad += bool(errs)
        for e in errs:
            print(("%s: %s" % (path, e)) if len(paths) > 1 else e)
    if len(paths) > 1:
        print("照らしたファイル %d・誤りのあるファイル %d" % (len(paths), bad))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
