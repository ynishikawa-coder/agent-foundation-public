#!/usr/bin/env python3
"""部品（plugin）どうしの呼び出しの流れを、コードと手順の文から機械で拾い、全体の絵に全部在るかを照らす。

なぜ在るか: 全体の絵を写す・描く時に、ある plugin の script・skill の手順が別の plugin の道具を呼ぶ流れを、
人の目で 2 回続けて拾い漏らした（合意した絵に無い流れが実物に在り、合流の前の照らしで red）。
流れは目で探さず、ここで拾った一覧を正にする。

  python3 scripts/call_flows.py list  [--repo DIR]            # 流れを 1 行ずつ「呼ぶ側 → 呼ばれる側  証拠」で出す
  python3 scripts/call_flows.py check <絵.json> [--repo DIR]  # 拾った流れが全部、絵の仕組みの構成（arch）の矢印に在るか

拾う物（道具＝plugins/<名>/ の下の .py .mjs .js .sh の file）: 実際に呼ぶ・import する・実行する形だけ。
  道具の指し方は、別の plugin の道具の path（plugins/<名>/…/<file 名>・手順の文で plugin の根を置いた `<名>/…`）か、
  file 名（その名の file が plugin の外にも・2 つの plugin にも在る時は path ごと書いた物だけ）か、
  plugin の外の土台の部品（repo の根の dir のうち OUTSIDE_SKIP に無い物・例 public-guard）の道具の path（<dir>/…/<file 名>）。
  部品の名は dir の名。plugin が土台の file を借りる流れも、plugin どうしと同じく絵に要る（拾わないと人の目で漏れる）。
  使う側の repo を読む流れも拾う（使う側の repo の在り処を引くか・形は using_items の上の注釈）。読む物の名が絵の
  個別の箱の題の頭。前は読む物を字の形で 1 つずつ挙げて拾い、決まった path・引数の path を読む流れが絵から漏れた。
  呼ぶ形:
  - .py: 字の値そのものが道具を指す（docstring と式だけの字は除く）・os.path.join／Path の字を繋いだ値・
    隣の plugin の名と並べた path（sibling_plugin_file("docs-kit", "…/check.mjs")）・import の名・interpreter で始まる命令の字。
  - .mjs .js: 注釈を除いた字の値（同じ決まり）。.sh: 注釈を除いた命令の語。.json: 字の値（同じ決まり）。
  - .md（手順の文）: コードの中の命令の形だけ（`python3 <名>/…/x.py …`・`x.py olds` のように引数を付けた直の実行・コードの塊の行）。
  拾わない物: 説明の文（docstring・注釈・人への文・`x.py` と名や path を挙げるだけの手順の文）＝呼んでいない。
    skill の名・文書（.md）の path（道具を呼ぶ流れでない）・.html・.txt（道具を呼ばない）・
    plugin の外の実体を指す symlink（例: lib/skill_values.py → skill-values/）の中身（実体の部品の文で、置いた plugin の物でない）。
    ただし plugin がその symlink を import して実体の部品のコードを借りる形は、実体の部品（例 skill-values）への流れに数える。
  前の形は行の字に名が在れば数え、説明の文で名を挙げるだけで「絵に無い流れ」の赤になり、絵に偽の流れを足すか
  注釈の言い方を替えて逃げる圧になった。読めない file（読めない・utf-8 でない・.py・.json の形が崩れた）は黙って飛ばさず照らせない（exit 2）。
絵との対応: 絵の箱のうち tab が arch で、題の頭（「（」の前）が plugin（部品）の名と同じ箱をその箱とみる。
  箱が無い plugin・2 つ在る plugin は照らせない＝赤（黙って通さない）。箱が無い部品は「絵に無い箱」＝赤。矢印の向きは 呼ぶ側 → 呼ばれる側。
exit: list は 0（読めない file は 2）。check は 0=全部在る／1=絵に無い流れが在る／2=照らせない（絵が読めない・箱が無い・重なる）。
"""
from __future__ import annotations

import argparse
import ast
import json
import re
import shlex
import subprocess
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TOOL_SUFFIX = (".py", ".mjs", ".js", ".sh")
CODE_SUFFIX = (".py", ".mjs", ".js", ".sh", ".md", ".json")   # 呼ぶ形を読める file（.html・.txt は道具を呼ばない）
OUTSIDE_SKIP = {"plugins", "tests", "scripts", "docs", "CHANGELOG.d"}  # 配らない・道具でない dir（. で始まる dir も外す）
ROOT_CAUSE = ("直し: 絵に無い流れを 1 本ずつ足して済ませず、流れが絵から漏れた原因を細目 §3「まず構造を疑う」で探して直す"
              "（絵は合意の版＝足すならオーナーに差を見せて決めてもらう）")


def tracked(repo: Path) -> list[str]:
    r = subprocess.run(["git", "-c", "core.quotepath=off", "ls-files"], cwd=repo, capture_output=True, text=True)
    if r.returncode != 0:
        raise OSError(f"git の一覧が取れない: {r.stderr.strip()}")
    return [ln for ln in r.stdout.splitlines() if ln]


def borrowed_link(repo: Path, f: str) -> bool:
    """plugins/<名>/ の下の symlink で、実体がその plugin の外（例: 土台の skill-values/）に在る物。
    中身は実体の部品の物で、symlink を置いた plugin が書いた文でも持つ道具でもない（plugin を入れる時に写るだけ）。"""
    parts = f.split("/")
    p = repo / f
    if parts[0] != "plugins" or len(parts) < 3 or not p.is_symlink():
        return False
    home = (repo / "plugins" / parts[1]).resolve()
    real = p.resolve()
    return home != real and home not in real.parents


def flows(repo: Path) -> dict[tuple[str, str], list[str]]:
    """{(呼ぶ側, 呼ばれる側): [証拠 "path:行 字"]}。"""
    files = tracked(repo)
    plugins = sorted({f.split("/")[1] for f in files if f.startswith("plugins/") and f.count("/") >= 2
                      and (repo / "plugins" / f.split("/")[1] / ".claude-plugin" / "plugin.json").is_file()})
    borrowed: dict[str, dict[str, str]] = defaultdict(dict)   # plugin → {借りた file 名: 実体の部品}
    for f in files:
        if borrowed_link(repo, f) and f.endswith(TOOL_SUFFIX):
            real = (repo / f).resolve().relative_to(repo.resolve()).parts
            borrowed[f.split("/")[1]][f.rsplit("/", 1)[-1]] = real[0]
    files = [f for f in files if not borrowed_link(repo, f)]
    owner: dict[str, set[str]] = defaultdict(set)      # 道具の file 名 → 持つ plugin
    outside: set[str] = set()                          # plugin の外にも同じ名の file が在る名
    for f in files:
        name = f.rsplit("/", 1)[-1]
        parts = f.split("/")
        if parts[0] == "plugins" and len(parts) >= 3 and parts[1] in plugins and f.endswith(TOOL_SUFFIX):
            owner[name].add(parts[1])
        elif not (parts[0] == "plugins"):
            outside.add(name)
    outside_units: dict[str, set[str]] = defaultdict(set)   # plugin の外の土台の部品 → その道具の file 名
    for f in files:
        parts = f.split("/")
        if (len(parts) >= 2 and parts[0] not in OUTSIDE_SKIP and not parts[0].startswith(".")
                and f.endswith(TOOL_SUFFIX)):
            outside_units[parts[0]].add(parts[-1])
    pats = []
    for unit, names in outside_units.items():
        for name in names:
            path_pat = re.compile(r"(?:\S*/)?%s/(?:\S*/)?%s" % (re.escape(unit), re.escape(name)))
            pats.append((unit, name, path_pat, None))
    for name, ys in owner.items():
        for y in ys:
            path_pat = re.compile(r"(?:\S*/)?(?:plugins/%s|<%s>)/(?:\S*/)?%s"
                                  % (re.escape(y), re.escape(y), re.escape(name)))
            bare = None if (name in outside or len(ys) > 1) else re.compile(r"(?:\S*/)?%s" % re.escape(name))
            pats.append((y, name, path_pat, bare))
    units = set(plugins) | set(outside_units)
    out: dict[tuple[str, str], list[str]] = defaultdict(list)
    for f in files:
        parts = f.split("/")
        if parts[0] != "plugins" or len(parts) < 3 or parts[1] not in plugins or not f.endswith(CODE_SUFFIX):
            continue
        x = parts[1]
        try:
            text = (repo / f).read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as e:   # 黙って飛ばすと、その file の流れを照らさず緑を返す
            raise ValueError(f"{f} が読めず、呼ぶ形を拾えない（{type(e).__name__}: {e}）") from None
        seen = set()
        for no in locate_calls(f, text):
            if (no, USING_REPO) not in seen:
                seen.add((no, USING_REPO))
                out[(x, USING_REPO)].append(f"{f}:{no} 今の dir を引く")
        for no in relative_reads(f, text):
            if (no, USING_REPO) not in seen:
                seen.add((no, USING_REPO))
                out[(x, USING_REPO)].append(f"{f}:{no} 相対の path で開く（今の dir に頼る）")
        for no, piece, kind in pieces(f, text, units):
            if kind == "value":
                y = borrowed[x].get(piece.strip()) if f.endswith(".py") else None
                if y and y != x and (no, y, "lib") not in seen:   # lib/ の symlink（土台の部品の実体）を import して借りる
                    seen.add((no, y, "lib"))
                    out[(x, y)].append(f"{f}:{no} {piece.strip()}")
                for item in using_items(f, piece):
                    if (no, item) not in seen:
                        seen.add((no, item))
                        out[(x, item)].append(f"{f}:{no} {piece.strip()}")
            for y, name, path_pat, bare in pats:
                if y == x or (no, y, name) in seen:
                    continue
                if refers(piece, kind, path_pat, bare):
                    seen.add((no, y, name))
                    out[(x, y)].append(f"{f}:{no} {name}")
    return dict(out)


# ── 使う側の repo を読む形 ───────────────────────────────────────
# plugin は土台の道具だけでなく、開いた（使う側の）repo も読む（読むだけ・オーナーの決定 2026-11-22 で土台の道具の全体に許す）。
# 読む物を字の形で 1 つずつ挙げて拾うと、決まった path・引数で渡された path を読む形を漏らす（漏れが 3 回続いた）。
# なので「使う側の repo の在り処を引くか」で拾う。在り処を引く道は 2 つ: 在り処を名指して引く形と、相対の path で開いて
# 今の dir に暗に頼る形（hook・道具は使う側の repo を今の dir にして動くので、相対の path は使う側の repo を指す）。
#   在り処を引く形（コードの値と呼び出し。説明の文は除く）: 環境変数 CLAUDE_PROJECT_DIR・`git rev-parse --show-toplevel`・
#   今の dir（Path.cwd()・os.getcwd()・process.cwd()・sh の $PWD／$(pwd)）・hook の入力の "cwd"・
#   plugin の .json の表に置いた git の pathspec の glob（例 古い形.json の files。表を読む道具が使う側の repo に当てる）。
#   相対の path で開く形（コードの呼び出し）: .py の open()・Path()・PurePath()・os.path／os の stat・exists・isfile・isdir・
#   listdir・scandir・walk・glob／iglob（関数か module の呼び出し。物の method の root.glob() は物から辿るので数えない）に、
#   / と ~ で始まらない字の値を直に渡す。.mjs／.js の fs の読む呼び出し
#   （readFileSync・readFile・existsSync・statSync・readdirSync・openSync・createReadStream など）に同じ字の値を渡す。
#   → 絵の箱「使う側の repo」（題の頭）への流れ。
# 使う側の repo の中の名前付きの物（値の表・CLAUDE.md）は、その物を指す値でそれぞれの箱への流れにも数える:
#   - 値の表: 値が config/skill-values.json・値の表の口 skill_values の import（plugin の lib/ の symlink を通して読む）
#   - CLAUDE.md: 値が CLAUDE.md（開いた repo の根の CLAUDE.md を読む）
# 残る穴: 在り処を呼ぶ側（人・別の道具）から引数だけで受け取り、自分では在り処を引かない道具は拾わない
#   （その道具を呼ぶ側が在り処を引く。手で path を渡して読ませる使い方は絵の上では呼ぶ側の流れ）。
#   相対の path を字の値でなく組み立てた値（変数・f-string・+ でつないだ値）で開く形と、.sh の命令に相対の path を
#   渡す形（cat docs/x など）は拾わない（.sh は命令の引数が path か字の値かを形で分けられない）。
USING_TABLE = "repo ごとの値の表"
USING_CLAUDE = "repo 固有の CLAUDE.md"
USING_REPO = "使う側の repo"
USING = (USING_TABLE, USING_CLAUDE, USING_REPO)
_LOCATE_VALUES = {"CLAUDE_PROJECT_DIR", "--show-toplevel", "cwd"}
_LOCATE_SH = re.compile(r"CLAUDE_PROJECT_DIR|--show-toplevel|\$PWD\b|\$\{PWD\}|\$\(\s*pwd\s*\)")
_PATHSPEC_GLOB = re.compile(r"(?::\(exclude\))?[\w./-]*\*[\w./*-]*")


def using_items(f: str, piece: str) -> list[str]:
    """値 piece が使う側の repo の物を指すなら、その物の名（絵の箱の題の頭）。"""
    w = piece.strip()
    if w == "config/skill-values.json" or (f.endswith(".py") and w == "skill_values.py"):
        return [USING_TABLE]
    if w == "CLAUDE.md":
        return [USING_CLAUDE]
    if f.endswith(".json") and _PATHSPEC_GLOB.fullmatch(w):
        return [USING_REPO]
    if f.endswith((".py", ".mjs", ".js")) and w in _LOCATE_VALUES:
        return [USING_REPO]
    if f.endswith(".sh") and _LOCATE_SH.search(w):
        return [USING_REPO]
    return []


def locate_calls(f: str, text: str) -> list[int]:
    """今の dir を引く呼び出し（Path.cwd()・os.getcwd()・process.cwd()）の行。値でなく呼び出しなので using_items と別に拾う。"""
    if f.endswith(".py"):
        try:
            tree = ast.parse(text)
        except SyntaxError:
            return []                      # 形の崩れは pieces が照らせないで止める
        return [n.lineno for n in ast.walk(tree) if isinstance(n, ast.Call)
                and (n.func.attr if isinstance(n.func, ast.Attribute) else getattr(n.func, "id", "")) in ("cwd", "getcwd")
                and not n.args]
    if f.endswith((".mjs", ".js")):
        code = re.sub(r"/\*.*?\*/", lambda m: "\n" * m.group(0).count("\n"), text, flags=re.S)
        return [no for no, ln in enumerate(code.splitlines(), 1)
                if re.search(r"\bprocess\.cwd\(\s*\)", ln.split("//", 1)[0])]
    return []


_REL_PY_FUNCS = {"open", "Path", "PurePath", "exists", "isfile", "isdir", "listdir", "scandir", "walk", "stat",
                 "glob", "iglob"}
_REL_PY_MODULES = {"os", "os.path", "glob", "io", "pathlib", "shutil"}
_REL_JS = re.compile(r"\b(?:readFileSync|readFile|existsSync|statSync|lstatSync|readdirSync|readdir|openSync|"
                     r"createReadStream|accessSync)\(\s*(['\"`])(?![/~])([^'\"`$]+)\1")


def _relative(v) -> bool:
    return isinstance(v, str) and bool(v.strip()) and v not in ("-", ".") and not v.startswith(("/", "~"))


def relative_reads(f: str, text: str) -> list[int]:
    """相対の path（字の値）で開く・調べる呼び出しの行。今の dir に暗に頼る＝使う側の repo を読む。"""
    if f.endswith(".py"):
        try:
            tree = ast.parse(text)
        except SyntaxError:
            return []                      # 形の崩れは pieces が照らせないで止める
        out = []
        for n in ast.walk(tree):
            if not isinstance(n, ast.Call) or not n.args:
                continue
            if isinstance(n.func, ast.Attribute):   # 物の method（root.glob・p.open）はその物から辿るので数えない
                fn = n.func.attr if ast.unparse(n.func.value) in _REL_PY_MODULES else ""
            else:
                fn = getattr(n.func, "id", "")
            a = n.args[0]
            if fn in _REL_PY_FUNCS and isinstance(a, ast.Constant) and _relative(a.value):
                out.append(n.lineno)
        return out
    if f.endswith((".mjs", ".js")):
        code = re.sub(r"/\*.*?\*/", lambda m: "\n" * m.group(0).count("\n"), text, flags=re.S)
        return [no for no, ln in enumerate(code.splitlines(), 1)
                if any(_relative(m.group(2)) for m in _REL_JS.finditer(ln.split("//", 1)[0]))]
    return []


# ── 呼ぶ形だけを取り出す ─────────────────────────────────────────
# 説明の文（docstring・注釈・人への文）に道具の名が在っても呼んでいない。呼ぶ形は、コードの値そのものが道具の
# path（か名）である所・命令の形（interpreter の後に道具・道具の path を直に実行）だけ。文の中に名が混ざるだけの物は数えない。
INTERP = {"python", "python3", "node", "bash", "sh", "zsh"}
_SEG = re.compile(r"&&|\|\||;|\||\$\(|`")


def _words(seg: str) -> list[str]:
    try:
        return shlex.split(seg, comments=False)
    except ValueError:
        return seg.split()


def is_command(piece: str, match, direct: bool) -> bool:
    """piece が命令の形で、道具（match が真になる語）を実行するか。命令の形＝interpreter の後に道具、
    か（手順のコードの中だけ・direct）道具に引数。コードの字の値は人への文でもありうるので、名で始まる文を命令とみない。"""
    for seg in _SEG.split(piece):
        ws = [w for w in _words(seg) if w not in ("(", ")")]
        while ws and re.fullmatch(r"\w+=\S*", ws[0]):
            ws = ws[1:]
        if not ws:
            continue
        head = ws[0].rsplit("/", 1)[-1]
        if head in INTERP and any(match(w) for w in ws[1:] if not w.startswith("-")):
            return True
        if direct and len(ws) > 1 and match(ws[0]):          # 道具を直に実行（`kaku.py olds`）。引数の無い名・path だけは挙げただけ
            return True
    return False


def refers(piece: str, kind: str, path_pat, bare) -> bool:
    def match(w: str) -> bool:
        w = w.strip()
        return bool(path_pat.fullmatch(w) or (bare and bare.fullmatch(w)))
    if kind == "value" and match(piece):
        return True
    return is_command(piece, match, direct=(kind == "command"))


def pieces(f: str, text: str, units) -> list[tuple[int, str, str]]:
    """file の中の呼ぶ形の候補 [(行, 字, 種類)]。種類 value＝値そのものが道具を指せば呼ぶ／command＝命令の形の時だけ呼ぶ。"""
    if f.endswith(".py"):
        return _py_pieces(f, text, units)
    if f.endswith((".mjs", ".js")):
        return _js_pieces(text)
    if f.endswith(".sh"):
        return _sh_pieces(text)
    if f.endswith(".json"):
        return _json_pieces(f, text)
    if f.endswith(".md"):
        return _md_pieces(text)
    return []


def _py_pieces(f, text, units):
    try:
        tree = ast.parse(text)
    except SyntaxError as e:
        raise ValueError(f"{f} が Python として読めず、呼ぶ形を拾えない（{e.msg}・{e.lineno} 行）")
    prose = {id(n.value) for n in ast.walk(tree) if isinstance(n, ast.Expr) and isinstance(n.value, ast.Constant)}

    def const(n):
        return n.value if isinstance(n, ast.Constant) and isinstance(n.value, str) and id(n) not in prose else None

    def joined(n):
        """os.path.join("a", "b")・Path("a", "b") の全部が字の時は "a/b"。"""
        if not isinstance(n, ast.Call) or n.keywords or not n.args:
            return None
        fn = n.func.attr if isinstance(n.func, ast.Attribute) else getattr(n.func, "id", "")
        if fn not in ("join", "Path", "PurePath"):
            return None
        xs = [const(a) for a in n.args]
        return "/".join(xs) if all(x is not None for x in xs) else None

    out = []
    for n in ast.walk(tree):
        s = const(n)
        if s is not None:
            out.append((n.lineno, s, "value"))
        j = joined(n)
        if j is not None:
            out.append((n.lineno, j, "value"))
        if isinstance(n, (ast.Call, ast.Tuple, ast.List)):
            items = n.args if isinstance(n, ast.Call) else n.elts
            names = [c for c in (const(a) for a in items) if c in units]
            paths = [p for p in (const(a) or joined(a) for a in items) if p and p not in units]
            for u in names:                         # sibling_plugin_file("docs-kit", "skills/…/check.mjs") の形
                for q in paths:
                    out.append((n.lineno, f"plugins/{u}/{q}", "value"))
                    out.append((n.lineno, f"{u}/{q}", "value"))
        if isinstance(n, ast.Import):
            out += [(n.lineno, a.name.replace(".", "/") + ".py", "value") for a in n.names]
        if isinstance(n, ast.ImportFrom) and n.module and not n.level:
            out.append((n.lineno, n.module.replace(".", "/") + ".py", "value"))
    return out


def _js_pieces(text):
    """注釈を除き、字の値（'…' "…" `…`）だけを取り出す。正規表現の値は字に数えない。"""
    out, i, n, line, prev = [], 0, len(text), 1, ""
    while i < n:
        c = text[i]
        if c == "\n":
            line += 1
            i += 1
            continue
        if text.startswith("//", i):
            j = text.find("\n", i)
            i = n if j < 0 else j
            continue
        if text.startswith("/*", i):
            j = text.find("*/", i + 2)
            j = n if j < 0 else j + 2
            line += text.count("\n", i, j)
            i = j
            continue
        if c in "'\"`":
            j, start, buf = i + 1, line, []
            while j < n and text[j] != c:
                if text[j] == "\\":
                    buf.append(text[j:j + 2])
                    j += 2
                    continue
                if text[j] == "\n":
                    line += 1
                buf.append(text[j])
                j += 1
            out.append((start, "".join(buf), "value"))
            i, prev = j + 1, c
            continue
        if c == "/" and (prev == "" or prev in "(,=:[!&|?{};+-*%<>~^" or re.search(r"\b(return|typeof|case|in|of)\s*$", text[max(0, i - 8):i])):
            j, cls = i + 1, False
            while j < n and text[j] != "\n":
                if text[j] == "\\":
                    j += 2
                    continue
                if text[j] == "[":
                    cls = True
                elif text[j] == "]":
                    cls = False
                elif text[j] == "/" and not cls:
                    break
                j += 1
            i, prev = j + 1, "/"
            continue
        if not c.isspace():
            prev = c
        i += 1
    return out


def _sh_pieces(text):
    out = []
    for no, ln in enumerate(text.splitlines(), 1):
        try:
            lex = shlex.shlex(ln, posix=True, punctuation_chars=True)
            lex.whitespace_split = True
            ws = list(lex)
        except ValueError:
            ws = ln.split("#", 1)[0].split()
        out += [(no, w, "value") for w in ws]
    return out


def _json_pieces(f, text):
    try:
        data = json.loads(text)
    except ValueError as e:
        raise ValueError(f"{f} が JSON として読めず、呼ぶ形を拾えない（{e}）")
    lines = text.splitlines()
    out = []

    def walk(v):
        if isinstance(v, dict):
            for x in v.values():
                walk(x)
        elif isinstance(v, list):
            for x in v:
                walk(x)
        elif isinstance(v, str):
            enc = json.dumps(v, ensure_ascii=False)[1:-1]
            no = next((k for k, ln in enumerate(lines, 1) if enc in ln), 1)
            out.append((no, v, "value"))
    walk(data)
    return out


_FENCE = re.compile(r"^\s*(```|~~~)")
_SPAN = re.compile(r"(`+)(.+?)\1")


def _md_pieces(text):
    """手順の文は、命令の形のコード（`python3 …/x.py`・コードの塊の行）だけを呼ぶ形とみる。名を `x.py` と挙げるだけは数えない。"""
    out, fence = [], False
    for no, ln in enumerate(text.splitlines(), 1):
        if _FENCE.match(ln):
            fence = not fence
            continue
        if fence:
            out.append((no, ln, "command"))
            continue
        out += [(no, m.group(2), "command") for m in _SPAN.finditer(ln)]
    return out


def plugin_names(repo: Path) -> list[str]:
    return sorted(d.name for d in (repo / "plugins").iterdir() if (d / ".claude-plugin" / "plugin.json").is_file()) \
        if (repo / "plugins").is_dir() else []


def plugin_boxes(pic: dict, names) -> tuple[dict[str, str], list[str]]:
    boxes = [b for b in pic.get("boxes") or [] if isinstance(b, dict) and b.get("tab") == "arch"]
    found: dict[str, list[str]] = defaultdict(list)
    for b in boxes:
        head = str(b.get("t") or "").split("（", 1)[0].strip()
        if head in names:
            found[head].append(str(b.get("id")))
    errs = [f"plugin {n} の箱が絵の仕組みの構成（arch）に無い" for n in names if not found.get(n)]
    errs += [f"plugin {n} の箱が 2 つ以上在る（{'・'.join(ids)}）" for n, ids in found.items() if len(ids) > 1]
    return {n: ids[0] for n, ids in found.items() if len(ids) == 1}, errs


def check(pic_path: Path, repo: Path) -> int:
    try:
        pic = json.loads(pic_path.read_text(encoding="utf-8"))
        if not isinstance(pic, dict):
            raise ValueError("絵が JSON の object でない")
        got = flows(repo)
    except (OSError, ValueError) as e:
        print(f"call_flows: 照らせない — {e}")
        return 2
    units = {y for (_, y) in got} - {x for (x, _) in got} - set(plugin_names(repo))
    names = sorted({n for pair in got for n in pair} - units)
    box, errs = plugin_boxes(pic, names)
    ubox, _ = plugin_boxes(pic, units)
    no_box = sorted(u for u in units if u not in ubox)
    box.update(ubox)
    if errs:
        for e in errs:
            print(f"✗ {e}")
        print("call_flows: 照らせない（plugin の箱と流れを結べない）")
        return 2
    arrows = {(a.get("from"), a.get("to")) for a in pic.get("arrows") or [] if isinstance(a, dict)}
    for u in no_box:
        ev = [e for (_, y), es in sorted(got.items()) if y == u for e in es]
        what = "使う側の repo の物" if u in USING else "plugin の外の土台の部品"
        print(f"✗ 絵に無い箱: {u}（{what}）証拠: {ev[0]}" + (f" ほか {len(ev) - 1}" if len(ev) > 1 else ""))
    missing = [(x, y, ev) for (x, y), ev in sorted(got.items()) if y not in no_box and (box[x], box[y]) not in arrows]
    missing += [(x, y, ev) for (x, y), ev in sorted(got.items()) if y in no_box]
    for x, y, ev in missing:
        print(f"✗ 絵に無い流れ: {x} → {y}（{box[x]} → {box.get(y, '箱なし')}）証拠: {ev[0]}" + (f" ほか {len(ev) - 1}" if len(ev) > 1 else ""))
    if missing:
        print(f"call_flows: 赤 絵に無い流れ {len(missing)} 本" + (f"・絵に無い箱 {len(no_box)} つ" if no_box else ""))
        print(ROOT_CAUSE)
        return 1
    print(f"call_flows: 緑 流れ {len(got)} 本が全部絵に在る")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    ls = sub.add_parser("list")
    ls.add_argument("--repo", type=Path, default=ROOT)
    ck = sub.add_parser("check")
    ck.add_argument("picture", type=Path)
    ck.add_argument("--repo", type=Path, default=ROOT)
    a = ap.parse_args(argv)
    if a.cmd == "list":
        try:
            got = flows(a.repo)
        except (OSError, ValueError) as e:
            print(f"call_flows: 拾えない — {e}")
            return 2
        for (x, y), ev in sorted(got.items()):
            print(f"{x} → {y}  {ev[0]}" + (f" ほか {len(ev) - 1}" if len(ev) > 1 else ""))
        return 0
    return check(a.picture, a.repo)


if __name__ == "__main__":
    sys.exit(main())
