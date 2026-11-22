#!/usr/bin/env python3
"""核を窓の起動時に差し込む口と、常に読まれる量の上限を照らす口（plugin core の道具はこの 1 本）。

使い方:
  python3 kaku.py inject              SessionStart の hook が呼ぶ。核（同じ plugin の 核.md）と振る舞いの既定
                                      （振る舞い.md）を窓の文脈へいつも差し込み、形の細目（細目/ の節ごとの file）の在り処を知らせる。使う側に残った写し・古い形は名指しで知らせる:
                                      開いた repo の古い形（古い形.json の一覧・核の写しの枠など）／CLAUDE.md の量の上限越え／
                                      古い形の setup script（土台の入口 scripts/setup_plugins.py を通っていない）／入っていない plugin。
                                      あわせて、窓の最初の 1 回だけ、入った土台が main の先端と同じかを見て窓ごとに覚える。古ければ、
                                      setup の時の main の先端の記録（setup.json の main_at_setup）と比べて、setup が古い物を入れた
                                      （setup script を直す）か setup の後に main が進んだ（作り置きの箱・setup script は直さない）かを分ける
                                      （記録が無ければ分からないと名指す）。古ければ先端の核と振る舞いの既定も差し込む。
  python3 kaku.py fresh               UserPromptSubmit の hook が呼ぶ。窓が立った時の main の先端から plugin が変わったら、
                                      先端の核と振る舞いの既定をこの窓に差し込む（窓は引き継がず閉じず、そのまま続ける）。
  python3 kaku.py refresh TIP ENTRY    inject・fresh が古さを見つけた時に裏で回す。目録の clone の入口 ENTRY（setup_plugins.py）で
                                      先端の版を入れ直し、結果を ~/.claude/af-foundation/refresh.json に書く（hook の入口 hook_run.py が
                                      次の呼び出しから入れ直した版を回す・失敗は fresh が 1 行で名指す）。
  python3 kaku.py check [--claude P]  核と振る舞いの既定が在り、上限の内かを照らす。--claude を渡すと、その CLAUDE.md が各社固有の上限の内で
                                      核の写しの枠を持たないかも照らす。
  python3 kaku.py grow --base REF     増やさない物（guarded() の一覧＝毎回差し込む物と形の細目）が git の REF の時より
                                      増えていないかを照らす。足すなら同じ変更で同じだけ畳む（上限の内で足し続けて満杯にしない）。
  python3 kaku.py olds DIR...         使う側の repo の main（origin の既定の枝）の中身に古い形.json の古い形が残っていないかを照らす
                                      （main を持たない dir は checkout を読む）
                                      （「壊れる（2 段目）」の前に、使う側が移ったのを記録で確かめる口）。
exit: inject と fresh は何が起きても 0（窓の起動も人の作業も止めない）。check・grow・olds は 0=緑 / 1=外れ・増えた / 2=読めない。
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

PLUGIN = Path(__file__).resolve().parent.parent
KAKU = PLUGIN / "核.md"
FURUMAI = PLUGIN / "振る舞い.md"
# 形の細目は節ごとの file（細目/<番号>-<名>.md）。並ぶ PR が 1 枚の大きな file を取り合って衝突しないよう、節を別の file に割る。
# 名の順に "\n" でつないだ物が細目の全文（saimoku_text・量を照らす grow・refs の約束が同じこれを読む）。
SAIMOKU = PLUGIN / "細目"
# 割る前の 1 枚の名。比べる元（main）がまだ割る前の形の時だけ読む（土台の中の移り目・割った形が main に入れば読まれない）。
SAIMOKU_ONE_FILE = "細目.md"
OLDS = PLUGIN / "古い形.json"
FRAME_BEGIN = "<!-- AF-CORE:BEGIN"
# 越えた時の最後の行（中身は細目 §3 が正本＝ここは指すだけ）
ROOT_CAUSE = "直し: 文を移して量を合わせるだけで済ませず、意図（常に読まれる決まりが少なく保たれる）とのずれから入り、決まりが増えた原因を細目 §3「まず構造を疑う」で探して畳む"
# 常に読まれる量の上限（バイト・UTF-8）。数はここの 1 か所だけに置く。
LIMITS = {"核": 4800, "振る舞い": 2400, "各社固有": 3000}
MARKET = "agent-foundation"
# 土台の出所（GitHub の repo）。目録 agent-foundation がこの repo から入った時だけ、main の先端と比べ入れ方を照らす
# （同じ名で fork が登録された箱で、fork の main を正と取り違えない）。docs/核の届け方.md の setup script の
# `marketplace add` と同じ（試験が照らす）。
UPSTREAM = "ynishikawa-coder/agent-foundation-public"
# 土台の振る舞いを運ぶ path。ここが変わった時だけ「古い土台」と見る（文書・試験・CI だけの変更では窓を替えない）。
CARRIERS = ("plugins", ".claude-plugin")
FRESH_INTERVAL = 900  # 起動の後に main の先端を見に行く間（秒）。毎回の問いごとに外へ出ない。
# 起動の時の古い形の見張りに使ってよい時間（秒）。越えたら打ち切って名指しする（hook の上限に当たって核の差し込みごと落ちない）。
WATCH_BUDGET = 5


# 読めない時の類（無い・権限・UTF-8 でない中身）を 1 か所で受ける。どの読みもこれで受け、欠けを名指しする。
UNREADABLE = (OSError, UnicodeDecodeError)


def size(text: str) -> int:
    return len(text.encode("utf-8"))


# ── 使う側に残った古い形（写し）を名指しする ──

def olds_table(path: Path = OLDS) -> list[dict]:
    """古い形の一覧。形が違えば ValueError（黙って一部だけ見ない）。"""
    data = json.loads(path.read_text(encoding="utf-8"))
    rows = data.get("olds") if isinstance(data, dict) else None
    if not isinstance(rows, list):
        raise ValueError(f"{path.name} に olds の並びが無い")
    keys = {"id", "what", "files", "pattern", "fix", "example"}
    for r in rows:
        if not isinstance(r, dict) or set(r) - {"reads"} != keys or not isinstance(r["files"], list) or not r["files"]:
            raise ValueError(f"{path.name} の行の欄が {sorted(keys)}（と reads）でない: {r!r}")
        if r.get("reads", "all") not in READS:
            raise ValueError(f"{path.name} の行 {r['id']} の reads が {sorted(READS)} のどれでもない: {r['reads']!r}")
        r["re"] = re.compile(r["pattern"])
    return rows


# 古い形の行が file のどこを読むか（reads）。名が在るかでなく、使う形の所だけに当てる（説明の文で名を挙げるだけは古い形でない）。
#   all      … 中身の全部（既定）
#   commands … 動く命令の所（code）: .md はコードの所（md_code）だけ。.sh .py .yml .yaml などは注釈と Python の docstring を除く。
#              入口の名が注釈に在るだけでは入口を呼ぶことにならない
#   prose    … 書いた欄・札の所: .md の自分の文（md_own＝閉じの在る囲み・注記・引用の外。# で始まる引用は書く行として残す）
READS = {"all", "commands", "prose"}


# ── 使う形の読み口（正本） ──
# 構造（コードの囲み・字下げのコード・<pre>・注記・引用・注釈）の読み方は、ここの 1 か所に置く。古い形の行（old_view）・写しの照らし
# （copies.py）・指しの照らし（refs.py）・試験（tests/uses.py と、それを通す試験）はここを呼び、読み方を写さない（写すと所ごとに
# 読み方がずれる）。読めない・判断できない形（閉じの無い囲み・字下げ・<pre>・構文の読めない .py）は、読む側（名指す側）に倒す。
# guard の plugin の読み方（pr_text の囲み・session_watch の strip_code など）は別の plugin で、plugin を跨いで import しない
# 作りのため、ここの対象の外。

_FENCE_OPEN = re.compile(r"^[ \t]*(?P<mark>`{3,}|~{3,})(?P<info>[^\n]*)$")
_INDENTED = re.compile(r"^(?: {4}|[ \t]*\t)[ \t]*\S")
_PRE_OPEN = re.compile(r"<pre\b", re.I)
_PRE_CLOSE = re.compile(r"</pre\s*>", re.I)
_NOTE = re.compile(r"<!--.*?-->", re.S)
_QUOTES = re.compile(r"「[^「」\n]*」|『[^『』\n]*』|“[^“”\n]*”")
_SPAN = re.compile(r"`[^`\n]+`")
_BLOCKQUOTE = re.compile(r"^[ \t]{0,3}>")
_CODE_KINDS = ("fence", "open", "indented", "pre")


def md_blocks(text: str) -> list[tuple[str, str, str]]:
    """.md の行ごとの (種類, 行, 囲みの言語)。種類:
      text     … 地の文
      mark     … コードの囲みの開き・閉じの行
      fence    … コードの囲みの中（CommonMark の形: ` か ~ を 3 字以上で開き、同じ字を開きと同じ数以上だけ並べた行で閉じる。
                 ` の囲みの開きの情報の欄に ` は入らない）
      open     … 閉じの無い囲みの開きから終わりまで（読めない形＝コードとしても地の文としても読む）
      indented … 4 字下げ・tab の行（字下げのコードか、リストの続きか、構文だけでは分けられない＝コードとしても読む）
      pre      … <pre> から </pre> までの行（同じく、コードとしても読む）
    """
    lines = text.split("\n")
    out: list[tuple[str, str, str]] = []
    i, n = 0, len(lines)
    while i < n:
        ln = lines[i]
        m = _FENCE_OPEN.match(ln)
        if m and not (m.group("mark")[0] == "`" and "`" in m.group("info")):
            mark = m.group("mark")
            close = re.compile(r"^[ \t]*" + re.escape(mark[0]) + "{%d,}[ \t\r]*$" % len(mark))
            j = next((k for k in range(i + 1, n) if close.match(lines[k])), None)
            lang = (m.group("info").strip().split() or [""])[0].lower()
            if j is None:
                out += [("open", x, lang) for x in lines[i:]]
                break
            out.append(("mark", ln, lang))
            out += [("fence", x, lang) for x in lines[i + 1:j]]
            out.append(("mark", lines[j], lang))
            i = j + 1
            continue
        if _PRE_OPEN.search(ln):
            j = next((k for k in range(i, n) if _PRE_CLOSE.search(lines[k])), n - 1)
            out += [("pre", x, "") for x in lines[i:j + 1]]
            i = j + 1
            continue
        out.append(("indented" if _INDENTED.match(ln) else "text", ln, ""))
        i += 1
    return out


def md_code(text: str) -> str:
    """.md のコードの所（囲みの中・閉じの無い囲み・字下げ・<pre>）の字から注釈を除いた物。他の行は空（行の番号は保つ）。
    地の文の `…` の中は、説明か指示かを構文で分けられないので読まない（残る穴）。"""
    out, run, key = [], [], None
    for kind, ln, lang in md_blocks(text) + [("end", "", "")]:
        k = (kind, lang) if kind in _CODE_KINDS else None
        if k != key and run:
            body = "\n".join(run)
            out.append(py_code(body) if key[1] in ("py", "python", "python3") else sh_code(body))
            run = []
        key = k
        if k is not None:
            run.append(ln)
        elif kind != "end":
            out.append("")
    return "\n".join(out)


def _keep_heading(m: re.Match) -> str:
    """引用の中身が見出しの印 # で始まる物（「## 欄の名」＝書く行そのもの）は残し、他は空にする。"""
    s = m.group(0)
    return s if s[1:].lstrip(" \t").startswith("#") else " "


def note_code(text: str) -> str:
    """注記 <!-- --> を空にした字（.html・.md の注記。行の番号は保つ）。"""
    return _NOTE.sub(lambda m: re.sub(r"[^\n]", " ", m.group(0)), text)


def md_own(text: str, notes: bool = False, spans: bool = False) -> str:
    """.md の自分の文: コードの囲み（閉じの在る物）・注記 <!-- -->・> の引用の行・地の文の引用（「」『』“”`…`）を空にした字
    （行の番号は保つ）。引用の中身が見出しの印 # で始まる物は書く行そのものとして残す。閉じの無い囲み・字下げ・<pre> は、
    囲みと決められないので地の文として読む。notes=True は注記の中を、spans=True は地の文の `…` の中を自分の文として読む
    （写しの照らし＝注記も AI が読む文で、決まりの文を `…` で囲むだけで写しの照らしを迂回させない）。"""
    body = "\n".join("" if kind in ("mark", "fence") else ln for kind, ln, _ in md_blocks(text))
    body = body if notes else note_code(body)
    out = []
    for ln in body.split("\n"):
        if _BLOCKQUOTE.match(ln):
            ln = ln if re.sub(r"^[ \t>]*", "", ln).startswith("#") else ""
        ln = _QUOTES.sub(_keep_heading, ln)
        out.append(ln if spans else _SPAN.sub(_keep_heading, ln))
    return "\n".join(out)


def sh_code(text: str) -> str:
    """shell（と yml）の字から注釈（引用の外で語の頭に在る #）を除いた物。' の中は \\ も字のまま・" の中と引用の外は
    \\ が次の 1 字を守る。"""
    out, q, i, n = [], "", 0, len(text)
    while i < n:
        c = text[i]
        if c == "\\" and q != "'" and i + 1 < n:
            out.append(text[i:i + 2])
            i += 2
            continue
        if q:
            q = "" if c == q else q
        elif c in "'\"":
            q = c
        elif c == "#" and (i == 0 or text[i - 1] in " \t\n;&|("):
            j = text.find("\n", i)
            i = n if j < 0 else j
            continue
        out.append(c)
        i += 1
    return "".join(out)


def py_code(text: str) -> str:
    """Python の源から注釈と docstring を空にした字（字の値・名・演算子は元の字のまま・行の番号は保つ）。構文の読めない
    源は全部を読む（読む側に倒す）。"""
    import ast
    import io
    import tokenize
    try:
        tree = ast.parse(text)
        toks = list(tokenize.generate_tokens(io.StringIO(text).readline))
    except (SyntaxError, ValueError, tokenize.TokenError):
        return text
    doc = set()
    for node in ast.walk(tree):
        body = getattr(node, "body", None)
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) and body \
                and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant) \
                and isinstance(body[0].value.value, str):
            doc.add((body[0].value.lineno, body[0].value.col_offset))
    starts = [0]
    for ln in text.split("\n"):
        starts.append(starts[-1] + len(ln) + 1)
    chars = list(text)
    for t in toks:
        if t.type == tokenize.COMMENT or (t.type == tokenize.STRING and t.start in doc):
            (r0, c0), (r1, c1) = t.start, t.end
            for k in range(starts[r0 - 1] + c0, starts[r1 - 1] + c1):
                if chars[k] != "\n":
                    chars[k] = " "
    return "".join(chars)


def js_code(text: str) -> str:
    """JavaScript（.mjs .js）の字から注釈（字の値の外の // と /* */）を除いた物。' " ` の字の値の中の // は残す。"""
    out, q, i, n = [], "", 0, len(text)
    while i < n:
        c = text[i]
        if q:
            if c == "\\" and i + 1 < n:
                out.append(text[i:i + 2])
                i += 2
                continue
            q = "" if c == q else q
        elif c in "'\"`":
            q = c
        elif text.startswith("//", i):
            j = text.find("\n", i)
            i = n if j < 0 else j
            continue
        elif text.startswith("/*", i):
            j = text.find("*/", i + 2)
            out.append(re.sub(r"[^\n]", " ", text[i:n if j < 0 else j + 2]))
            i = n if j < 0 else j + 2
            continue
        out.append(c)
        i += 1
    return "".join(out)


def code(rel: str, text: str) -> str:
    """file の動く所（使う形）: 拡張子で読み方を選ぶ。知らない拡張子は全部を読む（読む側に倒す）。"""
    ext = Path(rel).suffix.lower()
    if ext in (".md", ".markdown"):
        return md_code(text)
    if ext == ".py":
        return py_code(text)
    if ext in (".sh", ".bash", ".yml", ".yaml"):
        return sh_code(text)
    if ext in (".mjs", ".js", ".cjs"):
        return js_code(text)
    if ext in (".html", ".htm"):
        return note_code(text)
    return text


def own(rel: str, text: str) -> str:
    """file の自分の文と使う形: .md は自分の文（md_own）、他は動く所（code）。"""
    return md_own(text) if Path(rel).suffix.lower() in (".md", ".markdown") else code(rel, text)


def old_view(row: dict, rel: str, text: str) -> str:
    """古い形の行が読む所（reads の決まり）。"""
    reads = row.get("reads", "all")
    if reads == "commands":
        return code(rel, text)
    if reads == "prose" and Path(rel).suffix.lower() in (".md", ".markdown"):
        return md_own(text)
    return text


def old_hit(row: dict, rel: str, text: str) -> bool:
    """古い形の行が (相対 path, 中身) に当たるか（照らし方はこの 1 か所）。"""
    return bool(row["re"].search(old_view(row, rel, text)))


def _tracked(project: Path, specs: list[str]) -> list[Path]:
    """照らす file の全部。数で切らない（切ると残りを照らさず緑を返す）。時間の上限は find_olds_bounded が
    process の外から掛け、越えたら打ち切ったと名指す。"""
    try:
        out = _git_run(str(project), "ls-files", "-z", "--", *specs, timeout=10)
    except GitFailed as e:
        if (project / ".git").exists() or _git(str(project), "rev-parse", "--git-dir", timeout=5) is not None:
            # git の repo なのに一覧を読めない: 名で書いた file だけに縮めて「0」と言わない（照らせないと名指す）
            raise OSError(f"照らす file の一覧（git ls-files）を読めない: {e}") from None
        out = None
    if out is not None:
        return [project / n for n in out.split("\0") if n]
    return [project / s for s in specs if "*" not in s]  # git でない dir は、名で書いた file だけ見る


def _local_main(project: Path) -> str | None:
    for ref in ("refs/remotes/origin/HEAD", "refs/remotes/origin/main", "refs/remotes/origin/master"):
        sha = _git(str(project), "rev-parse", "--verify", "-q", f"{ref}^{{commit}}", timeout=10)
        if sha:
            return sha
    return None


def main_ref(project: Path) -> tuple[str | None, str | None]:
    """開いた repo の main（出所 origin の既定の枝）の今の commit と、それを確かめられなかった時の名指し。
    正本は出所の今の main（手元の refs/remotes/origin/* は fetch しなければ古い・origin/HEAD は既定の枝と限らない）:
    出所へ既定の枝と先端を聞き（ls-remote --symref）、手元に無ければその枝だけを取って来る。
    (sha, None)＝出所の今の main を読んだ / (sha, 名指し)＝出所に出られない・取れず手元の origin の main を読んだ
    （同じかは分からない）/ (None, None)＝git でない・origin が無い（checkout を読む）。"""
    if _git(str(project), "remote", "get-url", "origin", timeout=5) is None:
        return None, None
    local = _local_main(project)
    out = _git(str(project), "ls-remote", "--symref", "origin", "HEAD", timeout=3)
    branch = tip = None
    for line in (out or "").splitlines():
        m = re.fullmatch(r"ref: refs/heads/(\S+)\tHEAD", line)
        if m:
            branch = m.group(1)
        elif line.endswith("\tHEAD") and re.fullmatch(r"[0-9a-f]{40}|[0-9a-f]{64}", line.split("\t")[0]):
            tip = line.split("\t")[0]
    if not tip:
        note = "出所（origin）に出られず、出所の今の main を確かめられない"
        return local, (f"{note}。読んだのは手元の origin の main {local[:12]}（出所の今の main と同じかは分からない）"
                       if local else note)
    have = lambda: _git(str(project), "cat-file", "-e", f"{tip}^{{commit}}", timeout=5) is not None  # noqa: E731
    if not have() and branch:
        _git(str(project), "fetch", "--quiet", "--no-tags", "origin",
             f"+refs/heads/{branch}:refs/remotes/origin/{branch}", timeout=3)
    if have():
        return tip, None
    note = f"出所の今の main {tip[:12]} を取って来られなかった"
    return local, (f"{note}。読んだのは手元の origin の main {local[:12]}（出所より古い）" if local else note)


def _hits(rows: list[dict], texts) -> list[tuple[dict, str]]:
    """(相対 path, 中身) の並びに古い形の行を当てる（照らし方はこの 1 か所）。"""
    found = []
    for r in rows:
        for rel, text in texts(r):
            if old_hit(r, rel, text):
                found.append((r, rel))
    return found


TEXT_LIMIT = 1_000_000  # 照らす 1 つの file の上限（バイト）。越えた file は読まず、照らせないと名指す（黙って飛ばさない）。


def _checkout_texts(project: Path, unread: dict[str, str] | None = None):
    """checkout の中身。読めない file（上限越え・普通の file でない・開けない）は unread（{相対 path: 訳}）へ名指す。
    無い file（git でない dir で名で書いた物が無い）だけが「無い」。"""
    note = (lambda rel, why: unread.setdefault(rel, why)) if unread is not None else (lambda rel, why: None)

    def texts(r):
        for f in _tracked(project, r["files"]):
            rel = str(f.relative_to(project))
            try:
                if not f.exists() and not f.is_symlink():
                    continue
                if not f.is_file():
                    note(rel, "checkout で普通の file でない（dir・壊れた link など）")
                    continue
                n = f.stat().st_size
                if n > TEXT_LIMIT:
                    note(rel, f"checkout で {n} バイト＝照らす上限 {TEXT_LIMIT} を越える")
                    continue
                text = f.read_text(encoding="utf-8", errors="replace")
            except OSError as e:
                note(rel, f"checkout で開けない: {type(e).__name__}: {e}")
                continue
            yield rel, text
    return texts


def _tree_texts(project: Path, ref: str, only: set[tuple[str, str]] | None = None, unread: dict[str, str] | None = None):
    """ref の木の中身（checkout でなく git の物を読む）。path の選び方は checkout と同じ pathspec（git が解く）。
    only を渡すと、その (行の id, path) だけを読む。木に在るのに読めない物（中身が無い・blob でない・上限越え）は
    unread（{相対 path: 訳}）へ名指す（黙って飛ばして「古い形 0」にしない）。"""
    note = (lambda rel, why: unread.setdefault(rel, why)) if unread is not None else (lambda rel, why: None)
    try:
        empty = _git_run(str(project), "hash-object", "-t", "tree", "/dev/null", timeout=10)
    except GitFailed as e:
        empty, why = None, e

    def texts(r):
        try:
            if empty is None:
                raise why
            out = _git_run(str(project), "diff", "--name-only", "-z", "--no-renames", "--diff-filter=A", empty, ref,
                           "--", *r["files"], timeout=10)
        except GitFailed as e:
            raise OSError(f"main（{ref[:12]}）の木を読めない: {e}") from None
        names = [n for n in out.split("\0") if n and (only is None or (r["id"], n) in only)]
        for n in [n for n in names if "\n" in n]:  # cat-file --batch に 1 行で渡せない名＝読めないと名指す
            note(n, "名に改行を含み、git から中身を引けない")
        names = [n for n in names if "\n" not in n]
        if not names:
            return
        try:
            p = subprocess.run(["git", "-C", str(project), "cat-file", "--batch"], capture_output=True, timeout=20,
                               input="".join(f"{ref}:{n}\n" for n in names).encode("utf-8"))
        except (OSError, subprocess.SubprocessError) as e:
            raise OSError(f"main（{ref[:12]}）の中身を読めない: {e}") from None
        buf, i = p.stdout, 0
        for n in names:
            head_end = buf.find(b"\n", i)
            if p.returncode != 0 or head_end < 0:
                raise OSError(f"main（{ref[:12]}）の中身を読めない（{n}）")
            head = buf[i:head_end].split()
            i = head_end + 1
            if len(head) != 3 or not head[2].isdigit():  # missing など（中身が続かない）
                note(n, f"{ref[:12]} の木に在るのに中身を読めない（{b' '.join(head[1:]).decode('utf-8', 'replace') or '答えが空'}）")
                continue
            n_bytes = int(head[2])
            body = buf[i:i + n_bytes]
            i += n_bytes + 1
            if head[1] != b"blob":
                note(n, f"{ref[:12]} の木で普通の file でない（{head[1].decode('utf-8', 'replace')}）")
            elif n_bytes > TEXT_LIMIT:
                note(n, f"{ref[:12]} の木で {n_bytes} バイト＝照らす上限 {TEXT_LIMIT} を越える")
            else:
                yield n, body.decode("utf-8", errors="replace")
    return texts


SCAN_KEYS = ("found", "fixed_here", "behind", "added", "unknown")


def olds_scan(project: Path, rows: list[dict] | None = None) -> dict:
    """古い形を照らす。正本は main の中身（窓の作業の枝の checkout は main より古いことがある＝main で直った形を
    「この仕事で消す」と言い切らない）。main を持たない repo（git でない・origin の main が無い）は checkout を読む。
    checkout にだけ残る物は、枝と main の分かれ目の中身で分ける（中身で決める）: 分かれ目に在った＝main で直った
    （behind・枝が main より古い）／無かった＝この枝で足した（added・この仕事で消す）。
    {"ref": main の commit か None, "found": main に残る (行, path), "behind": [...], "added": [...],
     "unread": 照らす file のうち読めなかった [(相対 path, 訳)]（在れば古い形 0 と言い切らない）}。"""
    rows = rows if rows is not None else olds_table()
    unread: dict[str, str] = {}
    scan = _olds_scan(project, rows, unread)
    return dict(scan, unread=sorted(unread.items()))


def _olds_scan(project: Path, rows: list[dict], unread: dict[str, str]) -> dict:
    ref, note = main_ref(project)
    checkout = _hits(rows, _checkout_texts(project, unread))
    if note:  # 読んだ main が出所の今の main と確かめられない: どれも消す・直ったと言い切らない（分からないと名指す）
        found = _hits(rows, _tree_texts(project, ref, unread=unread)) if ref else []
        seen = {(r["id"], f) for r, f in found}
        return {"ref": ref, "note": note, "found": [], "fixed_here": [], "behind": [], "added": [],
                "unknown": found + [(r, f) for r, f in checkout if (r["id"], f) not in seen]}
    if not ref:
        return {"ref": None, "note": None, "found": checkout, "fixed_here": [], "behind": [], "added": [], "unknown": []}
    found = _hits(rows, _tree_texts(project, ref, unread=unread))
    seen = {(r["id"], f) for r, f in found}
    only = {(r["id"], f) for r, f in checkout} - seen
    base = _git(str(project), "merge-base", "HEAD", ref, timeout=10) if only else None
    was = {(r["id"], f) for r, f in _hits(rows, _tree_texts(project, base, only, unread))} if base else set()
    rest = [(r, f) for r, f in checkout if (r["id"], f) in only]
    if not base:  # 分かれ目が読めない（浅い clone 等）: main で直ったともこの枝で足したとも言い切らない
        return {"ref": ref, "note": None, "found": found, "fixed_here": [(r, f) for r, f in found if (r["id"], f) not in
                                                                         {(x["id"], y) for x, y in checkout}],
                "behind": [], "added": [], "unknown": rest}
    return {"ref": ref, "note": None, "found": found, "fixed_here": [(r, f) for r, f in found if (r["id"], f) not in
                                                       {(x["id"], y) for x, y in checkout}],
            "behind": [x for x in rest if (x[0]["id"], x[1]) in was],
            "added": [x for x in rest if (x[0]["id"], x[1]) not in was], "unknown": []}


def find_olds(project: Path, rows: list[dict] | None = None) -> list[tuple[dict, str]]:
    """開いた repo に残る古い形の (行, 当たった file の相対 path)。読むのは main の中身（無ければ checkout）。"""
    return olds_scan(project, rows)["found"]


def find_olds_bounded(project: Path, budget: float = WATCH_BUDGET, table: Path = OLDS) -> dict:
    """olds_scan を別の process で走らせ、budget 秒で殺す。1 つの file の正規表現の照らしは途中で止められないので、
    時間の上限は file の合間でなく process の外から掛ける。越えたら TimeoutError（黙って一部だけにしない）。"""
    cmd = [sys.executable, str(Path(__file__).resolve()), "olds", "--json", "--table", str(table), str(project)]
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=budget)
    except subprocess.TimeoutExpired:
        raise TimeoutError(f"{budget} 秒で見終わらず打ち切った（古い形の照らしの途中）") from None
    if p.returncode not in (0, 1):
        raise ValueError((p.stdout + p.stderr).strip() or f"olds が {p.returncode} で抜けた")
    rows = {r["id"]: r for r in olds_table(table)}
    got = json.loads(p.stdout)
    return {"ref": got["ref"], "note": got.get("note"), **{k: [(rows[i], f) for i, f in got.get(k) or []] for k in SCAN_KEYS},
            "unread": [(f, why) for f, why in got.get("unread") or []]}


def olds_text(scan: dict, project: Path) -> str | None:
    ref = scan["ref"]
    fixed = {(r["id"], f) for r, f in scan.get("fixed_here") or []}
    remove = [(r, f, "（この枝では消えている＝枝を main へ入れれば済む）" if (r["id"], f) in fixed else "")
              for r, f in scan["found"]] + [(r, f, "（この枝で足した）") for r, f in scan.get("added") or []]
    lines = []
    if remove:
        src = f"main（{ref[:12]}）の中身" if ref else "checkout"
        lines += [f"## この repo（{project.name}）に土台の古い形（写し）が残っている — この仕事で消す\n",
                  f"読んだ物: {src}。写しは土台が変わっても古いまま残り、誰も止めない。土台を直した同じ仕事で使う側も直す決まり（オーナー決定 2026-11-19）なので、"
                  "この repo の手順（CONTRIBUTING・CLAUDE.md）で 1 枝 1 PR を出して消す。頼みの仕事が別なら、その仕事を止めずに並べて出す:\n"]
        lines += [f"- {f}: {r['what']} → {r['fix']}{note}\n" for r, f, note in remove]
    if scan.get("behind"):
        lines += [f"## この repo（{project.name}）の作業の枝は main より古い — 古い形は main では直っている\n",
                  f"次は checkout には残るが main（{ref[:12]}）で直った（消す仕事は要らない。枝を main に追いつかせれば消える）: "
                  + "・".join(f"{f}（{r['id']}）" for r, f in scan["behind"]) + "\n"]
    if scan.get("note") and scan.get("unknown"):
        lines += [f"## この repo（{project.name}）の古い形が今の main に残るかが分からない — 照らした main を出所の今の main と確かめられない\n",
                  f"{scan['note']}。次は手元の main か checkout に在る。消すか（main に残る）・直った（main で消えた）かを言い切れないので、"
                  "`git fetch origin` の後に土台の kaku.py olds でこの repo を照らし直して決める: "
                  + "・".join(f"{f}（{r['id']}）" for r, f in scan["unknown"]) + "\n"]
    elif scan.get("unknown"):
        lines += [f"## この repo（{project.name}）の作業の枝にだけ古い形が在る — main で直ったか、この枝で足したかが分からない\n",
                  f"次は checkout には在るが main（{ref[:12]}）には無い。枝と main の分かれ目が読めない（浅い clone など）ので、"
                  "main で直った物（枝を main に追いつかせれば消える）か、この枝で足した物（この仕事で消す）かを言い切れない。"
                  "`git fetch --unshallow`（または `--deepen`）で分かれ目を取ってから見分ける: "
                  + "・".join(f"{f}（{r['id']}）" for r, f in scan["unknown"]) + "\n"]
    if scan.get("unread"):
        lines += [f"## この repo（{project.name}）に照らせない file が在る — 古い形 0 と言い切れない\n",
                  "次は照らす file なのに読めなかった（無いのではない）。中に古い形が残るかは分からない。中身・大きさ・権限を見て、"
                  "読める形にしてから土台の kaku.py olds でこの repo を照らし直す: "
                  + "・".join(f"{f}（{why}）" for f, why in scan["unread"]) + "\n"]
    return "".join(lines) or None


def claude_md_text(project: Path) -> str | None:
    """開いた repo の根の CLAUDE.md が各社固有の上限を越えていれば知らせる文。無ければ照らす物が無い（None）。
    在るのに読めない時は「上限の内」と読まず、量を照らしていないと名指す。"""
    path = project / "CLAUDE.md"
    try:
        n = size(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None
    except UNREADABLE as e:
        return (f"## この repo の CLAUDE.md が読めず、常に読まれる量の上限を照らしていない\n"
                f"{path}: {type(e).__name__}: {e}。上限の内と決まったのではない。中身（UTF-8 か）と権限を見て直す。\n")
    if n <= LIMITS["各社固有"]:
        return None
    return (f"## この repo の CLAUDE.md が常に読まれる量の上限を越えている\n"
            f"{n} > {LIMITS['各社固有']} バイト（数は土台の plugin core の LIMITS の 1 か所・写さない）。"
            "その repo に固有の決まりだけを残し、細かい手順はその repo の文書へ移して指す 1 行にする。\n")


LOCAL_SOURCES = ("directory", "file")  # 手元の dir・file から入れた試し・CI（使う側の setup script を持たず main と比べない）


def source_ref(m: dict) -> str:
    """目録が追う出所の枝（known_marketplaces の source の ref＝`marketplace add <repo>#<枝>`。無ければ main）。
    枝で入れた窓（plugin-smoke の試し）は、その枝の先端と比べる（いつも main と比べて「setup が古い物を入れた」と取り違えない）。"""
    src = m.get("source") if isinstance(m.get("source"), dict) else {}
    ref = str(src.get("ref") or "").strip()
    return ref or "main"


def source_tip(loc: str, ref: str) -> str | None:
    """出所（origin）の枝 ref の今の先端を出所へ直に聞く（共用の FETCH_HEAD や手元の ref を読まない）。
    枝が無い（版の tag で止めた目録など）時は出所の main と比べる（止めた版を「古くない」と見ない）。
    出所に聞けない・どの枝の先端も読めない時は Incomparable（「古くない」と読ませない）。"""
    whys = []
    for name in dict.fromkeys((ref, "main")):
        try:
            out = _git_run(loc, "ls-remote", "--quiet", "origin", f"refs/heads/{name}")
        except GitFailed as e:
            whys.append(f"{name}: {e}")
            continue
        sha = out.split()[0] if out.split() else ""
        if re.fullmatch(r"[0-9a-f]{40}|[0-9a-f]{64}", sha):
            return sha
        whys.append(f"{name}: 出所に枝が無い" if not out else f"{name}: 先端の答えを読めない（{out[:40]}）")
    raise Incomparable("出所（origin）の先端を聞けない — " + "／".join(whys))


def catalog_source() -> tuple[dict, str | None]:
    """目録 agent-foundation の登録（known_marketplaces.json の行）と、土台の出所でない時の名指し。
    ({}, None)＝目録が無い・手元から入れた（照らさない）/ (行, None)＝土台の repo の GitHub から入った /
    ({}, 名指し)＝別の出所（fork・別の git）から入った＝その main を正と見ない。"""
    path = _home() / "plugins" / "known_marketplaces.json"
    m = (_read_json(path, dict) or {}).get(MARKET)
    if m is None:
        return {}, None
    # 行が在るのに形が違う時は「目録が無い」と読まない（新しさ・入れ方を黙って照らさなくなる）
    if not isinstance(m, dict):
        raise Unreadable(path, f"目録 {MARKET} の行の形が dict でない（{type(m).__name__}）")
    src = m.get("source")
    if not isinstance(src, dict) or not src.get("source"):
        raise Unreadable(path, f"目録 {MARKET} の行に出所（source）が無い・形が違う")
    if src.get("source") in LOCAL_SOURCES:
        return {}, None
    if not m.get("installLocation"):
        raise Unreadable(path, f"目録 {MARKET} の行に入れた所（installLocation）が無い")
    where = src.get("repo") or src.get("url") or src.get("source")
    if src.get("source") != "github" or str(src.get("repo") or "").lower() != UPSTREAM.lower():
        return {}, (f"- 土台の目録 {MARKET} が土台の repo {UPSTREAM} でない出所（{where}）から入っている（同じ名の fork・別の git）。"
                    "その出所の main を正として古さ・入れ損ねを照らさない＝この窓の核と守りが土台の今の物か分からない。"
                    "最初にオーナーへ知らせ、setup script を土台の docs/核の届け方.md の形（土台の repo を足す）に直す。\n")
    return m, None


def _when(text) -> float | None:
    """ISO 8601 の時（Z・+0900 の形）を秒に。読めなければ None。"""
    from datetime import datetime
    try:
        return datetime.fromisoformat(str(text).replace("Z", "+00:00")).timestamp()
    except ValueError:
        return None


def user_rows(table: dict | None = None, market: str = MARKET) -> dict[str, list[dict]]:
    """{plugin の名: 入った台帳の user scope の行の並び}（目録 market の物だけ）。scope の欄が user と書かれた行だけを
    数える（欄の無い行を user と見ない）。台帳を読む所（新しさ・入れ方・写しの見張り・plugin-smoke）はこの 1 つを通す。"""
    if table is None:
        table = _ledger()
    plugins = table.get("plugins") if isinstance(table, dict) else None
    out = {}
    for key, rows in plugins.items() if isinstance(plugins, dict) else []:
        name, at, m = str(key).rpartition("@")
        user = [r for r in rows if isinstance(r, dict) and r.get("scope") == "user"] if isinstance(rows, list) else []
        if at and m == market and user:
            out[name] = user
    return out


LEDGER = ("plugins", "installed_plugins.json")


def _ledger() -> dict:
    """入った台帳（~/.claude/plugins/installed_plugins.json）を読む 1 本の口。無い＝{}。在るのに読めない・
    形が違う（plugins が dict でない・行の並びが list でない・行が dict でない）＝Unreadable（黙って行を落とさない）。"""
    path = _home().joinpath(*LEDGER)
    table = _read_json(path, dict) or {}
    plugins = table.get("plugins", {})
    if not isinstance(plugins, dict):
        raise Unreadable(path, f"plugins の形が dict でない（{type(plugins).__name__}）")
    for key, rows in plugins.items():
        if not isinstance(rows, list):
            raise Unreadable(path, f"{key} の行の並びが list でない（{type(rows).__name__}）")
        if not all(isinstance(r, dict) for r in rows):
            raise Unreadable(path, f"{key} の行に dict でない物が在る")
    return table


def current_row(rows: list[dict]) -> dict | None:
    """user scope の行が複数の時に、今読まれる 1 つ: dir が在る行のうち最後に入れた（lastUpdated の新しい）行。
    最初の行・dir の無い行（消えた前の版）を取らない。在る行が無ければ None（＝分からない）。"""
    live = [r for r in rows if r.get("installPath") and Path(str(r["installPath"])).is_dir()]
    return max(live, key=lambda r: _when(r.get("lastUpdated")) or 0.0, default=None)


def _foundation_rows() -> dict[str, dict]:
    """{plugin の名: 入った台帳の今読まれる user scope の行}（土台の目録の物だけ・current_row で 1 つに決めた物）。"""
    out = {}
    for name, rows in user_rows().items():
        row = current_row(rows)
        if row is not None:
            out[name] = row
    return out


def setup_record() -> tuple[dict | None, str | None]:
    """今の土台を入れた setup が入口 scripts/setup_plugins.py で書いた記録（setup.json）と、そう確かめられない訳。
    file が在るだけでは今回の記録と見ない: 記録の名簿の版（catalog_sha）が入った plugin core の commit と同じで、
    記録の時（at）が土台の plugin を入れ直した時（台帳の lastUpdated）より前でない時だけ今回の物（前の setup の記録が
    残った容器で、入口を通らない古い形の setup script が入れ直したのを見逃さない）。
    記録が在るのに読めない（開けない・壊れた JSON）時は「無い」と言わず Unreadable を上げる。"""
    have = installed_sha()
    # 版ごとの記録（入口が setup-<入れた版>.json にも書く）が今動いている版の物なら、それが今回の記録。setup.json は
    # 起動の時に別の口（使う側の起動の hook）が入口を回し直すと、並んで走るこの hook が読む前に新しい版の記録へ
    # 書き換わる＝今動いている版の記録を版の名で引けば取り違えない。同じ版を後で入れ直しても動く物は同じ。
    # 在るのに読めない記録は Unreadable のまま上げる（「記録が無い」と言って setup の走らせ直しへ導かない・setup_text が名指す）
    own = _read_json(_home() / "af-foundation" / f"setup-{have}.json", dict) if have else None
    if own is not None and own.get("catalog_sha") == have:
        # 版ごとの記録にも記録の時の照らしを当てる（入口を通らない古い形が同じ版を記録の後に入れ直したのを見逃さない）。
        # 見るのは今動いている版の行だけ: 並んだ入れ直しが書いた別の版の行は、今動いている物を変えていない。
        at = _when(own.get("at"))
        same = [t for rows in user_rows().values() for r in rows if r.get("gitCommitSha") == have
                for t in [_when(r.get("lastUpdated"))] if t is not None]
        if at is None or (same and max(same) > at + 2):
            return None, "入口の記録の時が土台の plugin を入れ直した時より前（記録の後に入口を通らずに入れ直した）"
        return own, None
    state = _read_json(_home() / "af-foundation" / "setup.json", dict)
    if state is None:
        return None, "入口の記録（~/.claude/af-foundation/setup.json）が無い"
    if not have or state.get("catalog_sha") != have:
        return None, (f"入口の記録の名簿の版 {str(state.get('catalog_sha'))[:12]} が入った土台 {str(have)[:12]} と違う"
                      "（前の setup の記録が残っている）")
    at = _when(state.get("at"))
    # 入れ直した時は user scope の全部の行で見る（古い行の lastUpdated で、記録の後の入れ直しを見逃さない）
    later = [t for rows in user_rows().values() for t in (_when(r.get("lastUpdated")) for r in rows) if t is not None]
    if at is None or (later and max(later) > at + 2):
        return None, "入口の記録の時が土台の plugin を入れ直した時より前（記録の後に入口を通らずに入れ直した）"
    return state, None


def _enabled() -> set[str]:
    """user scope で enabled の plugin（~/.claude/settings.json の enabledPlugins。入口の listed() と同じ見方）。"""
    path = _home() / "settings.json"
    on = (_read_json(path, dict) or {}).get("enabledPlugins") or {}
    if not isinstance(on, dict):  # 形の違う欄を「どれも enabled でない」と読まない
        raise Unreadable(path, f"enabledPlugins の形が dict でない（{type(on).__name__}）")
    return {k for k, v in on.items() if v is True}


def setup_text() -> str | None:
    """GitHub から土台を入れた窓で、古い形の setup script（入口を通っていない）・入っていない plugin・土台でない出所を知らせる文。
    照らす元の file（目録の一覧・入った台帳・settings.json・入った版の名簿）が在るのに読めない時は、
    「入れ方に欠けが無い」と読ませず、どの file がなぜ読めないかを名指す。"""
    try:
        return _setup_text()
    except Unreadable as e:
        return ("## 土台の入れ方を照らせない — 欠けが無いと決まったのではない\n"
                f"- {e}。入っていない plugin・古い形の setup script・土台の古さを照らしていない。"
                "その file の中身と権限を見て直す。直せない時は親の窓・オーナーへ 1 行知らせる。\n")


def _setup_text() -> str | None:
    m, other = catalog_source()
    if other:
        return "## 土台の入れ方が古い・欠けている\n" + other
    if not m:
        return None
    parts = []
    if installed_sha() is None:  # 別の dir の行の版で古さを決めない＝分からない事をそのまま名指す
        parts.append(f"- この窓に入った plugin core の版が分からない（入った台帳 installed_plugins.json に installPath が"
                     f"この plugin の dir {PLUGIN} と同じ行が無い）。土台の古さを照らしていない＝核と守りが土台の今の物か分からない。"
                     "最初にオーナーへ知らせ、setup script を土台の docs/核の届け方.md の形に直す。\n")
    try:
        state, why = setup_record()
    except Unreadable as e:
        state, why = None, None
        parts.append(f"- 入口の記録が読めない: {e}。記録が無いのでも、setup script が古い形と決まったのでもない（在るのに開けない・壊れている）。"
                     "setup を走らせ直す前に、その file の中身と権限を見る。直せない時は親の窓・オーナーへ 1 行知らせる。\n")
    if state is None and why:
        parts.append(f"- 環境の setup script が古い形（今の土台を入れた setup が土台の入口 scripts/setup_plugins.py を通っていない: {why}）。"
                     "土台が plugin を足しても入らず、入れ損ねの見張りにも入らない。土台の docs/核の届け方.md の形に貼り替える"
                     "（Javis の環境は get_environment → update_environment。直せない環境は親の窓・連絡板へ頼み、オーナーへ 1 行知らせる）。\n")
    # 名簿は setup が入れた版（入った core の commit）の物を読む（目録の clone の今の作業の木は setup の後に進みうる）
    try:
        want = catalog_at(m["installLocation"], installed_sha())
    except Unreadable as e:  # 1 つ読めない物で、ほかに見つけた欠け（上の入口の記録など）を消さない＝並べて名指す
        want = None
        parts.append(f"- 入った版の土台の名簿が読めない: {e}。入っていない plugin を照らしていない（入っていないと決まったのでも、"
                     "全部入ったと決まったのでもない）。目録の clone（git）の中身を見て直す。直せない時は親の窓・オーナーへ 1 行知らせる。\n")
    have, on = set(_foundation_rows()), _enabled()
    lack = [p.get("name") for p in (want or {}).get("plugins") or []
            if isinstance(p, dict) and (p.get("name") not in have or f"{p.get('name')}@{MARKET}" not in on)]
    if want is None and not any("名簿が読めない" in x for x in parts):
        parts.append("- 入った版の土台の名簿（.claude-plugin/marketplace.json）が目録の clone から読めず、入っていない plugin を照らしていない。"
                     "最初にオーナーへ知らせ、setup script を土台の docs/核の届け方.md の形に直す。\n")
    if lack:
        parts.append(f"- 土台の plugin が user scope で入って enabled になっていない: {' '.join(map(str, lack))}。その plugin の決まりと守りの hook がこの窓で効いていない。"
                     "最初にオーナーへ知らせ、setup script を土台の docs/核の届け方.md の形に直す。\n")
    state = state or {}
    if state.get("refreshed") is False or state.get("stale"):
        parts.append(f"- 土台の目録を先端へ取り直せず、または名簿の版に揃わずに入った（揃わない plugin: {' '.join(map(str, state.get('stale') or [])) or 'なし'}）。"
                     "古い決まりと守りの hook で動いている。最初にオーナーへ知らせ、setup script を土台の docs/核の届け方.md の形に直す。\n")
    return ("## 土台の入れ方が古い・欠けている\n" + "".join(parts)) if parts else None


def catalog_at(loc: str, sha: str | None) -> dict | None:
    """目録の clone の、commit sha の時の名簿（.claude-plugin/marketplace.json）。版が分からなければ None。
    在るはずの名簿を読めない（git が引けない・壊れた JSON・形が違う）時は Unreadable（訳つき）。"""
    if not sha:
        return None
    path = Path(loc) / ".claude-plugin" / f"marketplace.json（{sha[:12]} の時）"
    try:
        text = _git_run(loc, "show", f"{sha}:.claude-plugin/marketplace.json")
    except GitFailed as e:
        raise Unreadable(path, str(e)) from None
    try:
        data = json.loads(text)
    except ValueError as e:
        raise Unreadable(path, f"JSON として壊れている: {e}") from None
    if not isinstance(data, dict):
        raise Unreadable(path, f"中身の形が dict でない（{type(data).__name__}）")
    return data


def injected() -> tuple[Path, ...]:
    """毎回差し込む物の一覧（差し込む inject と増え方を照らす grow が同じこの 1 つを読む）。頭の核は欠けたら差し込まない。"""
    return (KAKU, FURUMAI)


def guarded() -> tuple[Path, ...]:
    """増やさない物の一覧＝毎回差し込む物と、核から押し出した物の行き先の細目（細目だけ照らさないと押し出した物がそこで膨らむ）。"""
    return (*injected(), SAIMOKU)


def saimoku_files(d: Path | None = None) -> list[Path]:
    """形の細目の節ごとの file（名の順）。"""
    return sorted((d or SAIMOKU).glob("*.md"))


def saimoku_text(d: Path | None = None) -> str:
    """形の細目の全文（節ごとの file を名の順に空の行 1 つでつなぐ＝割る前の 1 枚と一字違わず同じ）。"""
    return "\n".join(f.read_text(encoding="utf-8") for f in saimoku_files(d))


def read_guarded(path: Path) -> str:
    """増やさない物の 1 つの今の中身（dir なら中の file をつないだ全文）。"""
    return saimoku_text(path) if path.is_dir() else path.read_text(encoding="utf-8")


def inject_text(texts: dict[str, str | None] | None = None) -> str:
    """毎回差し込む物の本文。texts（名→本文）を渡すと、在る名はその本文で差し込む（起動の時から古い窓に先端の本文を
    1 枚だけ差し込む＝入っている古い本文と先端の本文の 2 枚を並べない）。"""
    texts = texts or {}

    def read(path: Path) -> str:
        return texts.get(path.name) or path.read_text(encoding="utf-8")

    head, *rest = injected()
    parts = [read(head).rstrip("\n")]
    for path in rest:
        try:
            parts.append(read(path).rstrip("\n"))
        except UNREADABLE as e:
            # 欠けたまま黙って核だけにしない: 窓の起動は止めず、欠けた事を文脈に名指しで出す
            print(f"plugin core: {path.name} が読めない（{e}）", file=sys.stderr)
            parts.append(f"（毎回差し込む {path} が読めず、差し込まれていない。最初にオーナーへ知らせる）")
    return ("\n\n".join(parts) + "\n\n"
            + "（この核と振る舞いの既定は土台の plugin core が起動時に差し込んだ。"
            + f"返事・問い・手の窓などの形の細目は {SAIMOKU} の中の、核の節と同じ番号で始まる file（例: 03-直すは根治.md）。"
            + "その形を書く時に Read する）\n")


# ── 土台の新しさ（入っている物と main の先端を比べる） ──

def _home() -> Path:
    return Path(os.environ.get("HOME") or "~").expanduser() / ".claude"


class Unreadable(Exception):
    """在るのに読めない記録（開けない・UTF-8 でない・JSON でない・形が違う）。名（path）と訳（why）を持つ。
    「無い」（None）と分ける＝読めない記録を「無い」と読んで書き直す・別の直しへ導く道を作らない。"""

    def __init__(self, path: Path, why: str):
        super().__init__(f"{path} が読めない（{why}）")
        self.path, self.why = path, why


def _read_json(path: Path, kind: type | None = None):
    """記録の JSON を読む 1 本の口。無い＝None。在るのに読めない（開けない・壊れた JSON・kind の形でない）＝Unreadable を上げる。
    黙って None にしない（呼ぶ側が「無い」と「読めない」を分けて名指すため）。"""
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return None
    except UNREADABLE as e:
        raise Unreadable(path, f"{type(e).__name__}: {e}") from e
    try:
        data = json.loads(text)
    except ValueError as e:
        raise Unreadable(path, f"JSON として壊れている: {e}") from e
    if kind is not None and not isinstance(data, kind):
        raise Unreadable(path, f"中身の形が {kind.__name__} でない（{type(data).__name__}）")
    return data


def _broken_text(name: str, e: Exception) -> str:
    """見張りが動かなかった・入力が読めなかった事を窓の文脈へ名指す文（止めずに知らせる）。"""
    return (f"## 土台の見張り（{name}）が動かなかった\n{type(e).__name__}: {e}。"
            "土台の plugin core の不具合か壊れた記録として親の窓へ知らせる（止めずに頼みは続ける）。\n")


def _incomparable_text(e: Exception) -> str:
    """入った土台と先端をその時は比べられなかった事の知らせ（「古くない」と読ませない）。"""
    return ("## 土台の新しさを比べられなかった — 古くないと決まったのではない\n"
            f"{str(e).rstrip('。.')}。この窓の核と守りが土台の今の物かは分からない。次の問いの時にもう一度見る"
            "（続けて比べられない時は、目録の clone と出所へ出られるかを見て、親の窓へ知らせる）。\n")


def _state_broken_text(e: "Unreadable", where: str) -> str:
    """窓の記録（~/.claude/af-foundation/<session>.json）が在るのに読めない時の知らせ。記録は書き直さない。"""
    return ("## この窓の土台の記録が読めない — 記録は書き直していない\n"
            f"{e}。{where}（無い記録として今の値で上書きすると、起動の時の main の先端と前に差し込んだ核の比べが黙って変わる）。"
            "起動の後に土台が新しくなったかの見張りは、この記録が読めるまでこの窓で動かない。"
            "この記録は plugin core が書いた物: 中身と権限を見て、壊れていれば消す（次の起動の hook が今の値で書き直す）。"
            "直せない時は親の窓へ知らせる。\n")


class GitFailed(OSError):
    """git を呼べなかった・git が失敗した（訳を持つ）。「何も無い」（空の出力）と分ける。"""


class Incomparable(Exception):
    """入った土台と先端を、その時は比べられなかった（出所に出られない・取って来られない・差分を読めない）。
    「古くない」と分ける＝比べられなかった事を名指し、次の問いの時にもう一度見る。"""


def _git_run(loc: str, *args: str, timeout: int = 20) -> str:
    """git を走らせ出力を返す。呼べない・失敗した時は GitFailed（訳つき）。失敗を「空」と読ませない 1 本の口。"""
    try:
        p = subprocess.run(["git", "-c", "core.quotepath=off", "-C", loc, *args], capture_output=True, text=True, timeout=timeout,
                           env=dict(os.environ, GIT_TERMINAL_PROMPT="0"))  # 鍵を問う画面で止まらない
    except (OSError, subprocess.SubprocessError) as e:
        raise GitFailed(f"git {args[0] if args else ''} を呼べない: {type(e).__name__}: {e}") from None
    if p.returncode != 0:
        why = (p.stderr or "").strip().splitlines()
        raise GitFailed(f"git {args[0] if args else ''} が {p.returncode} で失敗した" + (f": {why[-1]}" if why else ""))
    return p.stdout.strip()


def _git(loc: str, *args: str, timeout: int = 20) -> str | None:
    """失敗を None で返す口。在るかを問う（cat-file -e など、失敗が「無い」という答えそのもの）時だけ使う。
    読んだ物を照らす時は _git_run（失敗を「無い」と読まない）。"""
    try:
        return _git_run(loc, *args, timeout=timeout)
    except GitFailed:
        return None


def installed_sha() -> str | None:
    """この窓に入った plugin core の commit（入れた時に Claude Code が書く台帳から）。

    読むのは installPath がこの plugin の dir（今動いている kaku.py の在り処）と同じ行だけ。合う行が無ければ None
    （＝分からない）。行が 1 つでも別の dir（project scope で入った・前に別の所へ入った）の行の版で古さを決めない。"""
    rows = (_ledger().get("plugins") or {}).get(f"core@{MARKET}") or []
    for row in rows:
        if row.get("installPath") and Path(row["installPath"]).resolve() == PLUGIN:
            return row.get("gitCommitSha") or None
    return _running_from_record()


def _running_from_record() -> str | None:
    """台帳の行が無い時（起動の時に別の口が入れ直し、台帳が新しい版の dir を指した）、今動いている dir の名
    （Claude Code の cache は <目録>/<plugin>/<commit の頭 12 字>）と入口の版ごとの記録から入った commit を引く。
    名が commit の頭でない・記録が 1 つに決まらない時は None（分からない）。"""
    if not re.fullmatch(r"[0-9a-f]{12}", PLUGIN.name):
        return None
    hits = set()
    for f in (_home() / "af-foundation").glob(f"setup-{PLUGIN.name}*.json"):
        rec = _read_json(f)
        sha = rec.get("catalog_sha") if isinstance(rec, dict) else None
        if isinstance(sha, str) and f.name == f"setup-{sha}.json":
            hits.add(sha)
    return hits.pop() if len(hits) == 1 else None


def _carrier_names(names: str) -> set[str]:
    return {n.split("/")[1] if n.startswith("plugins/") and n.count("/") >= 2 else n.split("/")[0]
            for n in names.splitlines() if n}


def freshness() -> dict | None:
    """{installed, main, ref, shas, plugins}（plugins が空でなければ古い）。比べる物が無い（GitHub から入れていない・
    入った版が分からない）時は None。比べる物は在るのにその時は比べられない（出所に出られない・先端を取って来られない）
    時は Incomparable（「古くない」と読ませず、次の問いの時にもう一度見る）。

    GitHub から入れた時だけ見る（手元の dir から入れた試し・CI は main の先端と比べる物が無い）。
    先端は、目録が追う枝（source_ref・ふつうは main）の今の先端を出所へ直に聞き（共用の FETCH_HEAD を読まない）、
    その commit を入れた時の marketplace の clone へ取って来て比べる（鍵は要らない・public）。
    古さは plugin ごとに、その plugin の入った版と先端を比べる（core の版 1 つで全部の plugin の古さを決めない
    ＝core だけ先端に揃い guard の入れ直しが失敗した窓を「古くない」と見ない）。core の版からは
    plugins/・.claude-plugin/ の全部を見る（足された・消えた plugin も拾う）。"""
    m, _ = catalog_source()  # 土台の repo の GitHub から入った時だけ（fork の main を正と見ない）
    loc = m.get("installLocation")
    if not loc:
        return None
    have = installed_sha()
    ref = source_ref(m)
    if not have:
        return None
    tip = source_tip(loc, ref)
    if _git(loc, "cat-file", "-e", f"{tip}^{{commit}}") is None:
        try:
            _git_run(loc, "fetch", "--quiet", "--depth=1", "origin", tip)
        except GitFailed as e:
            raise Incomparable(f"先端 {tip[:12]} を目録の clone へ取って来られない — {e}") from None
        if _git(loc, "cat-file", "-e", f"{tip}^{{commit}}") is None:
            raise Incomparable(f"先端 {tip[:12]} を取って来たのに目録の clone に無い")
    shas = {name: str(row.get("gitCommitSha") or "") or None for name, row in _foundation_rows().items()}
    shas["core"] = have  # core は今動いている dir の行（installed_sha）の版
    plugins: set[str] = set()
    for name, sha in sorted(shas.items()):
        if sha == tip:
            continue
        if not sha:
            plugins.add(name)  # 版が分からない plugin は古い側に数える（既定で知らせる側）
            continue
        paths = CARRIERS if name == "core" else (f"plugins/{name}", ".claude-plugin")
        names = _git(loc, "diff", "--name-only", sha, tip, "--", *paths)
        if names is None:  # 入った commit が clone に無い＝比べられないが先端とは違う。古いと見る（既定で知らせる側）
            plugins.add("（どれか分からない）" if name == "core" else name)
        elif name == "core":
            plugins |= _carrier_names(names)
        elif names:
            plugins.add(name)
    return {"installed": have, "main": tip, "ref": ref, "shas": shas, "plugins": sorted(plugins)}


def moved_since(base: str, tip: str) -> list[str]:
    """base（窓が立った時の先端）から tip（今の先端）までに変わった plugin の名。空＝本当に変わっていない時だけ。
    目録の clone が浅く取り直されて base が無ければ base だけを取って来る。取って来られない・差分を読めない時は
    Incomparable（「変わっていない」と読ませない・人の作業は止めず、比べられなかった事を名指す）。"""
    if base == tip:
        return []
    loc = catalog_source()[0].get("installLocation")
    if not loc:
        return []
    if _git(loc, "cat-file", "-e", f"{base}^{{commit}}") is None:
        try:
            _git_run(loc, "fetch", "--quiet", "--depth=1", "origin", base)
        except GitFailed as e:
            raise Incomparable(f"窓が立った時の先端 {base[:12]} を取って来られない — {e}") from None
    try:
        names = _git_run(loc, "diff", "--name-only", base, tip, "--", *CARRIERS)
    except GitFailed as e:
        raise Incomparable(f"{base[:12]} から {tip[:12]} の差分を読めない — {e}") from None
    return sorted(_carrier_names(names))


REFRESH_TIMEOUT = 600  # 裏の入れ直し（入口 setup_plugins.py）を待つ上限（秒）


def _refresh_file(name: str) -> Path:
    return _home() / "af-foundation" / name


def start_refresh(tip: str) -> bool:
    """入った土台が先端より古い時、目録の clone の入口 scripts/setup_plugins.py を裏で回して先端の版を入れ直す
    （窓の起動を待たせない）。入れ直した版は、hook の入口 hook_run.py が次の呼び出しから回す。
    同じ先端へ入れ直し済み・入れ直し中なら何もしない。回し始めた＝True。"""
    loc = catalog_source()[0].get("installLocation")
    entry = Path(loc) / "scripts" / "setup_plugins.py" if loc else None
    if not entry or not entry.is_file():
        return False
    try:
        done = _read_json(_refresh_file("refresh.json"), dict) or {}
    except Unreadable:
        done = {}  # 壊れた前の結果は入れ直しの結果で書き直す（入れ直しを止めない）
    if done.get("main") == tip and done.get("code") == 0:
        return False
    lock = _refresh_file("refresh.lock")
    lock.parent.mkdir(parents=True, exist_ok=True)
    try:
        if lock.exists() and time.time() - lock.stat().st_mtime > REFRESH_TIMEOUT + 60:
            lock.unlink()  # 前の入れ直しが落ちて残した錠
        fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        os.close(fd)
    except FileExistsError:
        return False
    subprocess.Popen([sys.executable, str(Path(__file__).resolve()), "refresh", tip, str(entry)],
                     stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                     start_new_session=True, cwd=str(_home()))
    return True


def refresh(tip: str, entry: Path) -> int:
    """裏で回る入れ直しの本体（start_refresh が別の process で呼ぶ）。結果を refresh.json に書き、錠を外す。"""
    try:
        p = subprocess.run([sys.executable, str(entry)], capture_output=True, text=True, timeout=REFRESH_TIMEOUT,
                           stdin=subprocess.DEVNULL)
        code, out = p.returncode, (p.stdout + p.stderr).strip()
    except (OSError, subprocess.SubprocessError) as e:
        code, out = -1, f"{type(e).__name__}: {e}"
    line = (out.splitlines() or [""])[-1][:300]
    try:
        _refresh_file("refresh.json").write_text(json.dumps(
            {"main": tip, "code": code, "line": line, "at": time.time()}, ensure_ascii=False), encoding="utf-8")
    except OSError:
        pass
    try:
        _refresh_file("refresh.lock").unlink()
    except OSError:
        pass
    return 0


def refresh_failed_text(state: dict) -> str | None:
    """裏の入れ直しが失敗していれば、1 度だけ 1 行で名指す（前の版の hook で続ける）。"""
    try:
        r = _read_json(_refresh_file("refresh.json"), dict)
    except Unreadable as e:
        if state.get("refresh_told") == "unreadable":
            return None
        state["refresh_told"] = "unreadable"
        return _broken_text("裏の入れ直しの記録", e)
    if r is None or r.get("code") == 0 or r.get("at") == state.get("refresh_told"):
        return None
    state["refresh_told"] = r.get("at")
    return (f"## 土台の hook を先端へ入れ直せなかった\n入口 scripts/setup_plugins.py が {r.get('code')} で抜けた"
            f"（{r.get('line') or '訳は出ていない'}）。守りの hook は前の版のまま動く（止めない）。最初にオーナーへ 1 行知らせる。\n")


def _state_path(session: str) -> Path:
    safe = "".join(c for c in session if c.isalnum() or c in "-_") or "unknown"
    return _home() / "af-foundation" / f"{safe}.json"


def _save_state(session: str, state: dict) -> None:
    try:
        path = _state_path(session)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")
    except OSError:
        pass


def _hook_input() -> tuple[dict, Exception | None]:
    """hook の入力（stdin の JSON）と、読めなかった時の訳。空は {}（無い）。壊れた入力を黙って {} にしない。"""
    try:
        data = json.loads(sys.stdin.read() or "{}")
    except (ValueError, OSError) as e:
        return {}, e
    if not isinstance(data, dict):
        return {}, ValueError(f"hook の入力の形が dict でない（{type(data).__name__}）")
    return data, None


def _short(f: dict) -> str:
    ref = f.get("ref") or "main"
    return f"入った土台 {f['installed'][:12]}・{ref} の先端 {f['main'][:12]}・変わった plugin: {'・'.join(f['plugins'])}"


def start_cause(f: dict | None) -> str | None:
    """起動の時に入った土台が古い訳。比べる正本は setup の時の main の先端（入口 scripts/setup_plugins.py が
    setup.json の main_at_setup に書く記録）で、hook の時の main ではない（setup の後に main が進んだだけの窓を
    「setup script を直せ」と取り違えない）。
    None＝古くない・比べられない / "setup"＝setup が main の先端と違う物を入れた / "after"＝setup は main の先端を
    入れ、その後に main が進んだ / "unknown"＝setup の時の main の記録が無く見分けられない。"""
    if not f or not f["plugins"]:
        return None
    rec = (setup_record()[0] or {}).get("main_at_setup")  # 今回の setup の記録だけを読む（前の記録の残りを読まない）
    if not isinstance(rec, str) or not re.fullmatch(r"[0-9a-f]{40}|[0-9a-f]{64}", rec):
        return "unknown"
    # 全部の plugin が setup の時の先端で入っていれば、その後に先端が進んだだけ（1 つでも違えば setup が古い物を入れた）
    shas = f.get("shas") or {"core": f["installed"]}
    return "after" if all(sha == rec for sha in shas.values()) else "setup"


CONTINUE = ("窓は立て直さず・引き継がず・閉じず、そのまま頼みを続ける（create_session・archive_session をしない）。"
            "下の main の先端の核と振る舞いの既定が、起動の時に差し込まれた物に代わって効く。"
            "守りの hook は裏で先端の版を入れ直し、済んだ後の呼び出しから先端の版で動く（hook の足し・外しと skill は次に立つ窓から）。\n")


def tip_texts(main: str) -> dict[str, str | None]:
    """main の先端の核と振る舞いの既定の本文（名→本文・読めない物は None）。入れた時の目録の clone から読む。"""
    loc = catalog_source()[0].get("installLocation")
    return {path.name: (_git(loc, "show", f"{main}:plugins/core/{path.name}") if loc else None) for path in injected()}


def installed_texts() -> dict[str, str | None]:
    """この窓に入っている核と振る舞いの既定の本文（名→本文・読めない物は None）。"""
    out = {}
    for path in injected():
        try:
            out[path.name] = path.read_text(encoding="utf-8")
        except UNREADABLE:
            out[path.name] = None
    return out


def core_digests(texts: dict[str, str | None]) -> dict[str, str | None]:
    """差し込んだ本文の印（名→印）。窓が今読んでいる核と同じかを、送った本文そのもので比べる（版の印や plugin の動きでは比べない）。"""
    return {name: (hashlib.sha256(text.strip().encode("utf-8")).hexdigest() if text is not None else None)
            for name, text in texts.items()}


def effective_texts(texts: dict[str, str | None] | None) -> dict[str, str | None]:
    """差し込む本文（名→本文）。先端の本文が在ればそれ、読めない物は入っている版の本文（inject_text と同じ選び方）。"""
    texts = texts or {}
    return {name: texts.get(name) or text for name, text in installed_texts().items()}


TIP_UNREADABLE = "先端で読めなかった"


def changed_core_text(main: str, new: dict[str, str | None], had: dict[str, str | None]) -> str:
    """窓が今読んでいる本文の印（had）から変わった物だけの全文。同じ物は送らない（同じ核を何枚も文脈に積まない）。"""
    parts = []
    now = core_digests(new)
    for name, text in new.items():
        if text is None and had.get(name) != TIP_UNREADABLE:  # 読めない事は 1 回だけ名指す
            parts.append(f"（main の先端の {name} を読めなかった。今読んでいる物で続ける）")
        elif text is not None and had.get(name) != now[name]:
            parts.append(f"### main の先端の {name}（{main[:12]}）\n" + text.rstrip("\n"))
    return "\n\n".join(parts) + "\n" if parts else ""


def stale_at_start_text(f: dict) -> str:
    try:  # 2 回目の起動（told の差し直し）の間に記録が壊れても、核の差し込みごと落とさず名指す
        rec = ((setup_record()[0] or {}).get("main_at_setup") or "")[:12]
    except Unreadable as e:
        rec = f"（入口の記録が読めない: {e}）"
    return ("## 土台が古いまま立った窓 — setup script を直し、窓はそのまま続ける\n"
            f"この窓は main の先端より古い土台で立った（{_short(f)}）。setup の時の main の先端は {rec} で、setup はそれと違う物を入れた。"
            "setup script が版（tag）を指している・目録を取り直さない古い形（marketplace update の行が無い）・入れ損ねている"
            "ので、次に立つ窓にも同じ物が入る。頼みの合間に次をする:\n"
            "1. 環境の setup script を土台の docs/核の届け方.md の形（main の先端を入れる）に直す: "
            "claude-code-remote の get_environment → update_environment（直せる環境の時）。\n"
            "2. 直せない時（他のアカウントの環境・道具が無い）は、UTC の環境なら連絡板の issue で setup script の直しを頼み、"
            "オーナーへ「守りが古い形で動いている」と 1 行知らせる。\n"
            + START_CONTINUE)


def unknown_at_start_text(f: dict) -> str:
    return ("## 土台が古いまま立った窓 — 起動の時から古いか、setup の後に main が進んだかが分からない\n"
            f"この窓は main の先端より古い土台で立った（{_short(f)}）。setup の時に入れた main の先端の記録"
            "（土台の入口 scripts/setup_plugins.py が ~/.claude/af-foundation/setup.json の main_at_setup に書く）が無いので、"
            "setup script が古い物を入れたのか、setup の後に main が進んだだけなのかを見分けられない"
            "（記録が無いのは、setup script が入口を通らない古い形か、入口が記録を書く前の版で入れた時）。頼みの合間に次をする:\n"
            "1. claude-code-remote の get_environment で setup script を読み、土台の docs/核の届け方.md の形（目録の取り直しと入口）と照らす。"
            "違えば update_environment で直す（直せない環境は親の窓・連絡板へ頼み、オーナーへ 1 行知らせる）。\n"
            + START_CONTINUE)


def update_text(f: dict, core: str) -> str:
    """起動の後に核か振る舞いの既定の文が変わった時の知らせ。core＝変わった物だけの全文（changed_core_text）。"""
    return ("## 土台が新しくなった — 新しい核をここで読み、窓はそのまま続ける\n"
            f"土台の main の先端で、窓が読んでいる核か振る舞いの既定の文が変わった（{_short(f)}）。"
            + CONTINUE + core)


# 起動の時の知らせの締め（核は上に先端の本文で 1 枚だけ差し込んでいるので、ここでは本文を重ねない）
START_CONTINUE = ("窓は立て直さず・引き継がず・閉じず、そのまま頼みを続ける（create_session・archive_session をしない）。"
                  "上の核と振る舞いの既定は main の先端の本文（読めなかった物だけ入っている版の本文）。"
                  "守りの hook は裏で先端の版を入れ直し、済んだ後の呼び出しから先端の版で動く（hook の足し・外しと skill は次に立つ窓から）。\n")


def after_setup_text(f: dict) -> str:
    """setup の後に main が進んだだけの窓（作り置きの箱）の起動の知らせ。直す物は無い。"""
    return f"（土台は setup の後に main が進んでいた（{_short(f)}）。{START_CONTINUE}"


# 先端の核を差し込む時の文（起動の時の古さの訳ごと。無い訳＝setup の後に main が進んだ・起動の後に新しくなった）
TOLD_TEXT = {"setup": stale_at_start_text, "unknown": unknown_at_start_text}
# 起動の後に新しくなった窓の圧縮・resume の後の知らせ（本文は上に 1 枚だけ差し込む）
RESTART_TEXT = ("## 土台は起動の後に新しくなっている — 上の核と振る舞いの既定は main の先端の本文\n" + START_CONTINUE)


def inject() -> int:
    data, bad_input = _hook_input()
    project = Path(os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd())
    parts = []
    for name, make in (("古い形", lambda: olds_text(find_olds_bounded(project), project)),
                       ("CLAUDE.md の量", lambda: claude_md_text(project)), ("入れ方", setup_text)):
        try:
            t = make()
        except Exception as e:  # noqa: BLE001  見張りが壊れても核の差し込みは止めない。壊れた事は名指しする
            t = _broken_text(name, e)
        if t:
            parts.append(t)
    if bad_input:
        parts.append(_broken_text("hook の入力", bad_input))
    session = data.get("session_id")
    broken = None
    try:
        state = _read_json(_state_path(session), dict) if session else None
    except Unreadable as e:  # 読めない記録を「無い」と読んで起動の時の記録を書き直さない
        state, broken = None, e
    if state is not None:
        # 同じ窓の 2 回目（文脈の圧縮・/clear・resume）: 起動の時の記録を書き直さず、外へも見に行かない。
        # 前に差し込んだ main の先端の核（told）を、もう一度差し込む（圧縮で起動の時の古い核だけが残らない）。
        told, kind = state.get("told"), state.get("told_kind")
    else:
        comparable = True
        try:
            f = freshness()
            cause = start_cause(f)
            comparable = f is not None
        except Incomparable as e:  # その時だけ比べられない＝古くないと読まず、問いの時の見張り（fresh）が比べ直す
            f, cause = None, None
            parts.append(_incomparable_text(e))
        except Exception as e:  # noqa: BLE001  新しさの見張りが壊れても核の差し込みは止めない。壊れた事は名指しする
            f, cause = None, None
            parts.append(_broken_text("新しさ", e))
        # 入った土台が先端より古ければ、先端の核をここで差し込む。setup が古い物を入れた・分からない時だけ setup script を
        # 直させる（setup の後に main が進んだだけ＝作り置きの箱は直す物が無い）。
        told, kind = (f, cause) if f and f["plugins"] else (None, None)
        if told:
            try:  # 守りの hook も先端の版で動くよう、裏で入れ直す（起動は待たせない・失敗は fresh が 1 行で名指す）
                start_refresh(f["main"])
            except Exception as e:  # noqa: BLE001  入れ直しが壊れても核の差し込みは止めない。壊れた事は名指しする
                parts.append(_broken_text("裏の入れ直し", e))
        if broken is not None:
            parts.append(_state_broken_text(broken, "起動の時の記録（start_main・told）を今の値で書き直していない"))
        elif session:
            state = {"checked": time.time(), "cause": cause, "comparable": comparable, "start": f,
                     "start_main": f["main"] if f else None, "told": told, "told_kind": kind}
    # 核はいつも正本を 1 枚だけ差し込む（使う側の写しの枠が在っても、写しでなく正本が効く）。土台が入った版より新しい窓は
    # 先端の本文で差し込み、入っている古い本文と先端の本文の 2 枚を並べない。
    texts = None
    if told:
        try:
            texts = tip_texts(told["main"])
        except Exception as e:  # noqa: BLE001  先端が読めなくても入っている版の核は差し込む。壊れた事は名指しする
            parts.append(_broken_text("先端の核の読み", e))
    try:
        parts.insert(0, inject_text(texts))
    except UNREADABLE as e:
        print(f"plugin core: 核.md が読めない（{e}）＝核は差し込まれていない", file=sys.stderr)
    if state is not None and broken is None and session and "core" not in state:
        try:  # この窓が読んだ本文の印（fresh が、本文の変わらない先端を送り直さないために比べる）
            state["core"] = core_digests(effective_texts(texts))
        except UNREADABLE:
            pass
        _save_state(session, state)
    if told:
        parts.append(TOLD_TEXT[kind](told) if kind in TOLD_TEXT else RESTART_TEXT if kind == "update"
                     else after_setup_text(told))
    if parts:
        out = {"hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": "\n".join(parts)}}
        sys.stdout.write(json.dumps(out, ensure_ascii=False))
    return 0


def fresh() -> int:
    """起動の後に土台が新しくなったかを見る。新しくなっていれば、main の先端の核と振る舞いの既定をこの窓に差し込み、
    窓はそのまま頼みを続ける（引き継がせない・閉じさせない）。同じ先端は 1 回だけ見る（問いのたびに繰り返さない）。
    核と振る舞いの既定は、この窓が読んだ本文から変わった物だけを送る（本文が同じなら守りの入れ直しだけで黙る）。"""
    data, bad_input = _hook_input()
    session = data.get("session_id")
    if bad_input:
        return _say(_broken_text("hook の入力", bad_input))
    if not session:
        return 0
    path = _state_path(session)
    try:
        state = _read_json(path, dict)
    except Unreadable as e:  # 読めない記録で黙って 0 を返さない（新しくなった土台を差し込めない事を名指す）
        return _say(_state_broken_text(e, "記録を書き直していない"))
    if state is None or not state.get("comparable"):
        return 0
    failed = refresh_failed_text(state)
    if failed:
        _save_state(session, state)
        return _say(failed)
    interval = float(os.environ.get("AF_FRESH_INTERVAL") or FRESH_INTERVAL)
    if time.time() - float(state.get("checked") or 0) < interval:
        return 0
    text = None
    try:
        got = freshness()
        if got and got["plugins"] and state.get("start_main"):
            # 入った版でなく、この窓が立った時の先端と比べる（作り置きの箱で立った窓を、立つ前の main の進みで数えない）
            moved = moved_since(state["start_main"], got["main"])
            got = dict(got, plugins=moved) if moved else None
    except Incomparable as e:  # 比べられない時は「新しくなっていない」と読まず名指す（間を置いて 1 回）
        got, text = None, _incomparable_text(e)
    except Exception as e:  # noqa: BLE001  見張りが壊れても問いは止めない。壊れた事は名指しする（間を置いて 1 回）
        got, text = None, _broken_text("新しさ", e)
    state["checked"] = time.time()
    if got and got["plugins"] and got["main"] != (state.get("told") or {}).get("main"):
        # 守りの hook は先端の版へ入れ直す。核と振る舞いの既定は、この窓が読んだ本文から変わった物だけを 1 回送る
        # （plugin のどこかが動くたびに同じ核を送り直さない＝同じ核を文脈に何枚も積まない）。
        had = state.get("core")
        if had is None:  # 本文の印を持たない前の版の記録: 前に送った先端か、入っている版の本文を読んだと読む
            told_main = (state.get("told") or {}).get("main")
            had = core_digests(effective_texts(tip_texts(told_main) if told_main else None))
        new = tip_texts(got["main"])
        core = changed_core_text(got["main"], new, had)
        state["told"], state["told_kind"] = got, "update"
        state["core"] = {**had, **{k: v or TIP_UNREADABLE for k, v in core_digests(new).items()}}
        text = update_text(got, core) if core else None
        try:
            start_refresh(got["main"])
        except Exception as e:  # noqa: BLE001  入れ直しが壊れても問いは止めない。壊れた事は名指しする
            text += _broken_text("裏の入れ直し", e)
    _save_state(session, state)
    return _say(text)


def _say(text: str | None) -> int:
    """問いの時の hook（fresh）が窓の文脈へ足す口。"""
    if text:
        out = {"hookSpecificOutput": {"hookEventName": "UserPromptSubmit", "additionalContext": text}}
        sys.stdout.write(json.dumps(out, ensure_ascii=False))
    return 0


def check(claude: Path | None) -> int:
    bad = []
    try:
        n = size(KAKU.read_text(encoding="utf-8"))
    except UNREADABLE as e:
        print(f"✗ 核.md が読めない: {e}")
        return 2
    if n > LIMITS["核"]:
        bad.append(f"核（{KAKU.name}）が上限を越えた: {n} > {LIMITS['核']} バイト（細目へ移す）")
    try:
        f = size(FURUMAI.read_text(encoding="utf-8"))
    except UNREADABLE as e:
        print(f"✗ 振る舞い.md が読めない: {e}")
        return 2
    if f > LIMITS["振る舞い"]:
        bad.append(f"振る舞いの既定（{FURUMAI.name}）が上限を越えた: {f} > {LIMITS['振る舞い']} バイト（癖と逆を求めない物を細目へ移す）")
    if claude is not None:
        try:
            text = claude.read_text(encoding="utf-8")
        except UNREADABLE as e:
            print(f"✗ {claude} が読めない: {e}")
            return 2
        m = size(text)
        if FRAME_BEGIN in text:
            bad.append(f"{claude} に核の写しの枠が残っている（枠を中身ごと消す・核は plugin core が差し込む）")
        if m > LIMITS["各社固有"]:
            bad.append(f"各社固有（{claude}）が上限を越えた: {m} > {LIMITS['各社固有']} バイト（その repo の文書へ移す）")
    for b in bad:
        print(f"✗ {b}")
    if bad:
        print(ROOT_CAUSE)
        return 1
    print("✅ 量の上限 緑")
    return 0


# 増やさない物（guarded＝毎回差し込む物と細目）。足す時は同じ変更で同じだけ畳む（上限の内でも純増は赤）。
GROW_FIX = "直し: 足すなら同じ変更で同じだけ畳む（重複を細目・skill の正本へ寄せる）。量を合わせるだけで済ませず、意図（決まりの量を増やさない）とのずれから入り、細目 §3「まず構造を疑う」で増えた原因を探して畳む"


def base_text(ref: str, path: Path) -> str:
    """git の ref の時の中身（dir なら中の .md を名の順につないだ全文＝read_guarded と同じ読み方）。
    細目の dir が ref に無く、割る前の 1 枚（細目.md）が在れば、その 1 枚を読む（同じ量を比べる）。
    読めない（ref が無い・その時に file が無い）時は OSError で止める。"""
    top = subprocess.run(["git", "rev-parse", "--show-toplevel"], cwd=path.parent, capture_output=True, text=True)
    if top.returncode != 0:
        raise OSError(f"git の外: {top.stderr.strip()}")
    rel = path.resolve().relative_to(Path(top.stdout.strip()).resolve()).as_posix()

    def show(r_: str) -> str:
        r = subprocess.run(["git", "show", f"{ref}:{r_}"], cwd=path.parent, capture_output=True)
        if r.returncode != 0:
            raise OSError(f"{ref}:{r_} が読めない: {r.stderr.decode('utf-8', 'replace').strip()}")
        return r.stdout.decode("utf-8")

    if not path.is_dir():
        return show(rel)
    ls = subprocess.run(["git", "-c", "core.quotepath=off", "ls-tree", "--full-tree", "--name-only", f"{ref}:{rel}"],
                        cwd=path.parent, capture_output=True)
    names = sorted(n for n in ls.stdout.decode("utf-8").splitlines() if n.endswith(".md")) if ls.returncode == 0 else []
    if names:
        return "\n".join(show(f"{rel}/{n}") for n in names)
    if path == SAIMOKU:
        parent = rel.rpartition("/")[0]
        return show(f"{parent}/{SAIMOKU_ONE_FILE}" if parent else SAIMOKU_ONE_FILE)
    raise OSError(f"{ref}:{rel} に .md が無い")


def grow(ref: str) -> int:
    bad = []
    for path in guarded():
        try:
            now = size(read_guarded(path))
            before = size(base_text(ref, path))
        except UNREADABLE as e:
            # 比べる元が無い時に黙って緑にしない（既定で止める）
            print(f"✗ {path.name} の増え方を照らせない: {e}")
            return 2
        if now > before:
            bad.append(f"{path.name} が {ref} より増えた: {before} → {now} バイト（+{now - before}）")
        else:
            print(f"・{path.name}: {before} → {now} バイト")
    for b in bad:
        print(f"✗ {b}")
    if bad:
        print(GROW_FIX)
        return 1
    print("✅ 毎回差し込む物と細目は増えていない")
    return 0


def olds(dirs: list[Path], table: Path = OLDS, as_json: bool = False) -> int:
    try:
        rows = olds_table(table)
    except (OSError, ValueError) as e:
        print(f"✗ {table.name} が読めない: {e}")
        return 2
    bad = 0
    for d in (x.resolve() for x in dirs):
        if not d.is_dir():
            print(f"✗ {d} が無い")
            return 2
        try:
            scan = olds_scan(d, rows)
        except OSError as e:
            print(f"✗ {d.name}: {e}")
            return 2
        found = scan["found"]
        if as_json:
            print(json.dumps({"ref": scan["ref"], "note": scan.get("note"), **{k: [[r["id"], f] for r, f in scan[k]] for k in SCAN_KEYS},
                              "unread": [[f, why] for f, why in scan["unread"]]}, ensure_ascii=False))
            bad += len(found)
            continue
        src = f"main {scan['ref'][:12]} の中身" if scan["ref"] else "checkout"
        if scan.get("note"):  # 出所の今の main を読めていない: 0 とも言い切らない（照らせない）
            held = "・".join(f"{f}（{r['id']}）" for r, f in scan["unknown"])
            print(f"✗ {d.name}: 照らせない — {scan['note']}（手元の main か checkout に在る形: "
                  f"{held or 'なし'}）")
            return 2
        for r, f in found:
            print(f"✗ {d.name}/{f}: {r['id']}（{r['what']}・読んだ物: {src}）")
        if scan["unread"]:  # 照らす file を読めなかった: 古い形 0 とも言い切らない（照らせない）
            for f, why in scan["unread"]:
                print(f"✗ {d.name}/{f}: 照らせない — {why}")
            return 2
        if not found:
            print(f"✅ {d.name}: 古い形 0（読んだ物: {src}・見た形: {'・'.join(r['id'] for r in rows)}）")
        bad += len(found)
    return 1 if bad else 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="核の差し込みと量の上限の照らし")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("inject", help="SessionStart の hook から呼ぶ")
    sub.add_parser("fresh", help="UserPromptSubmit の hook から呼ぶ")
    c = sub.add_parser("check", help="量の上限を照らす")
    c.add_argument("--claude", type=Path, help="照らす repo の根の CLAUDE.md")
    g = sub.add_parser("grow", help="毎回差し込む物と細目が REF より増えていないかを照らす")
    g.add_argument("--base", required=True, help="比べる元の git の ref（例: main との分かれ目）")
    o = sub.add_parser("olds", help="使う側の checkout に古い形が残っていないかを照らす")
    o.add_argument("dirs", type=Path, nargs="+")
    o.add_argument("--table", type=Path, default=OLDS, help="古い形の一覧（既定は plugin の 古い形.json）")
    o.add_argument("--json", action="store_true", help="当たりを [[id, path], …] で出す（起動の hook が別の process で呼ぶ）")
    r = sub.add_parser("refresh", help="裏で入口を回して先端の版を入れ直す（inject・fresh が別の process で呼ぶ）")
    r.add_argument("tip")
    r.add_argument("entry", type=Path)
    a = ap.parse_args(argv)
    if a.cmd == "refresh":
        return refresh(a.tip, a.entry)
    if a.cmd == "inject":
        return inject()
    if a.cmd == "grow":
        return grow(a.base)
    if a.cmd == "fresh":
        return fresh()
    if a.cmd == "olds":
        return olds(a.dirs, a.table, a.json)
    return check(a.claude)


if __name__ == "__main__":
    sys.exit(main())
