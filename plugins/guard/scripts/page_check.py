"""PreToolUse — docs-kit の型で作ったページ（Blueprint・理論モック等）を Artifact で出す前に、その型の検査をかけ、赤なら止める。

なぜ在るか: blueprint・theory-mock は「検査を通してから渡す」を SKILL の文で求めるだけで、AI が検査を回さずに
  publish しても何も止めなかった（原因の台帳: 出す口・渡す口で照らさない）。問いのページは qa_page が出す口で
  検査を回す。同じ形を、検査を持つ docs-kit の型の全部へ広げる。

正本（写さない）:
  - どの型か: ページの頭の <meta name="af-page" content="<skill の名>">（型の template.html が持つ印）。
  - その型の検査: docs-kit の skills/<名>/SKILL.md の頭（frontmatter）の `page-check: <skill の dir からの path>`。
    検査は `python3 <path> <page>` で回り、exit 0 が緑・1 が赤・2 が回せない（Chrome が無い等）。
  見張りの側は型の名も検査の名も持たない＝型を足す PR は template に印を、SKILL に page-check を書くだけ。
既定で止める:
  - 印が名指す型が無い・その型が page-check を宣言していない・検査の file が無い・検査が回せない／壊れた時。
  - docs-kit の枠の印（`?selftest` の見張り）を持つのに af-page の印が無いページ（印を外して検査を逃れる道を塞ぐ）。
止まるのは AI の道具の呼び出しだけ（人の操作は止めない）。問いのページは qa_page の受け持ち（ここは見ない）。
"""
from __future__ import annotations

import os
import re
import subprocess
import sys

import guard_common as G
import qa_page

PAGE_EXT = (".html", ".htm")
TIMEOUT = 50
RED_SHOWN = 12
AF_PAGE = re.compile(r"""<meta\b[^>]*\bname\s*=\s*["']af-page["'][^>]*\bcontent\s*=\s*["']([^"']*)["']""", re.I)
# docs-kit の枠が持つ selftest の見張り（型の印を外したページもこれで拾う）
FRAME = re.compile(r"""\[\?&\]selftest\\b""")
FRONT = re.compile(r"\A---\s*\n(.*?)\n---\s*\n", re.S)


# この見張りが回る出来事と関数（guard.py がこの宣言を読んで回す＝入口の一覧に足さない）
HOOKS = {"pre": "check"}


def skill_dir(name, guard_root=None):
    """docs-kit の skill の dir か ""（隣の plugin の正本を直に読む）。AF_DOCS_KIT で docs-kit の根を渡せる。"""
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]*", name or ""):
        return ""
    env = os.environ.get("AF_DOCS_KIT") or ""
    if env:
        cand = os.path.join(env, "skills", name, "SKILL.md")
        return os.path.dirname(cand) if os.path.isfile(cand) else ""
    md = G.sibling_plugin_file("docs-kit", os.path.join("skills", name, "SKILL.md"), guard_root)
    return os.path.dirname(md) if md else ""


def declared_check(sdir):
    """SKILL.md の頭の page-check の path（skill の dir からの相対）か ""。"""
    try:
        with open(os.path.join(sdir, "SKILL.md"), encoding="utf-8") as f:
            m = FRONT.match(f.read())
    except OSError:
        return ""
    if not m:
        return ""
    for ln in m.group(1).splitlines():
        k, _, v = ln.partition(":")
        if k.strip() == "page-check":
            return v.strip().strip("'\"")
    return ""


def reason(path, kind, lines, cmd=""):
    return (
        "docs-kit の型のページ（{}）が型の検査を通っていないので、Artifact に出すのを止めました。\n"
        "  出そうとした file: {}\n"
        "{}\n"
        "直し方（skill guard:guard-rules の page_check・docs-kit:{}）:\n"
        "  ① 型（template.html）の枠は変えずに中身だけを直す\n"
        "  ② {} が緑（exit 0）になってから出し直す"
    ).format(kind or "型の名が無い", path, "\n".join(lines), kind or "<型の名>", cmd or "<型の検査> <file>")


def check(data, vals):
    """止めるなら理由、通すなら ""。"""
    if str(data.get("tool_name") or "") != "Artifact":
        return ""
    ti = data.get("tool_input")
    if not isinstance(ti, dict) or ti.get("asset"):
        return ""
    if str(ti.get("action") or "publish") != "publish":
        return ""
    for path in qa_page._sources(ti, data):        # file_path と files（出る file の読み方は qa_page と 1 つ）
        why = check_page(path)
        if why:
            return why
    return ""


def check_page(path, guard_root=None):
    if not path.lower().endswith(PAGE_EXT):
        return ""
    try:
        with open(path, encoding="utf-8") as f:
            raw = f.read()
    except OSError:
        return ""          # 読めない file は Artifact の道具の側が断る
    m = AF_PAGE.search(raw)
    if not m:
        if FRAME.search(raw):
            return reason(path, "", ["  docs-kit の枠（?selftest の見張り）を持つのに、型の印 <meta name=\"af-page\" content=\"<型の名>\"> が無い。"
                                     "型の template.html から作り直し、印を残す"])
        return ""
    kind = m.group(1).strip()
    sdir = skill_dir(kind, guard_root)
    if not sdir:
        return reason(path, kind, ["  印が名指す型「%s」が docs-kit に無い（知らない型）。plugin docs-kit を入れ直すか、印を型の名に直す" % kind])
    rel = declared_check(sdir)
    if not rel:
        return reason(path, kind, ["  型「%s」の SKILL.md が page-check（型の検査）を宣言していない。検査を持たない型は印を付けない" % kind])
    chk = os.path.normpath(os.path.join(sdir, rel))
    if not os.path.isfile(chk):
        return reason(path, kind, ["  型の検査 %s が無い。plugin docs-kit を入れ直す" % chk])
    cmd = "python3 %s %s" % (chk, path)
    try:
        p = subprocess.run([sys.executable, chk, path], capture_output=True, text=True, timeout=TIMEOUT,
                           cwd=os.path.dirname(path) or None)
    except (OSError, subprocess.SubprocessError) as e:
        return reason(path, kind, ["  検査が走らなかった: %s" % e], cmd)
    if p.returncode == 0:
        return ""
    out = [ln for ln in (p.stdout + "\n" + p.stderr).splitlines() if ln.strip()]
    if p.returncode == 2:
        return reason(path, kind, ["  検査を回せない（exit 2）: " + " / ".join(out[-3:]),
                                   "  Chrome（Playwright の chromium）を入れるか、環境変数 CHROME に path を渡す"], cmd)
    if p.returncode != 1:
        return reason(path, kind, ["  検査が壊れた（exit %d）: %s" % (p.returncode, " / ".join(out[-3:]))], cmd)
    lines = ["  検査の赤:"] + ["    " + ln for ln in out[:RED_SHOWN]]
    if len(out) > RED_SHOWN:
        lines.append("    …ほか %d 行（全部は %s で出る）" % (len(out) - RED_SHOWN, cmd))
    return reason(path, kind, lines, cmd)
