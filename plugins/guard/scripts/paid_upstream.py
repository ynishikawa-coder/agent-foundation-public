"""PreToolUse — 試験から有料の上流（AI の API など）へ直接つながる線を書く手を止める。

なぜ在るか: 開発中の自動試験が、本物の AI の API を叩き続けて費用の大半を占めた実測がある。
データを壊す書き込みは全部塞いでいたのに、読み取り（AI に読ませる口）だけ本物を通していた。
費用も壊れ物として、試験の中で本物へつなぐ線を書く時に止める。

止める: 試験の file（is_test_file＝試験の道具が試験として集める物の決まり）へ書く中身に、
  有料の上流の鍵名か公式のエンドポイント・鍵の名の形（…_API_KEY 等）・AI の SDK の取り込みが現れた時（paid_hits）。
逃げ道: 中身に PAID_UPSTREAM_GUARD を書く（＝環境変数 1 本で本物へ切り替える共通の関所を通す宣言。既定は録画の再生か偽物）。

試験の file は path の形の列挙で見ず、試験の道具の集め方の決まりを 1 つの関数（is_test_file）で読む:
  pytest の設定（pytest.ini・pyproject.toml・tox.ini・setup.cfg）の python_files・testpaths（無ければ pytest と
  unittest の既定 test_*.py・*_test.py・test*.py）・conftest.py と conftest.py が取り込む物（fixtures の file）・
  試験の dir（testpaths・tests/ など）の下・JS の試験の道具の既定（__tests__/・*.test.*・*.spec.*）・Go の *_test.go。
見る口: 道具の名で見ず、入力の形で見る＝入力に path の欄と中身の欄が在る道具（Write・Edit・MultiEdit・NotebookEdit・
  MCP の file 書き込み）と Bash。Bash は読み手（cmd_read）の語で「どこへ書くか」を読む（bash_writes）:
  リダイレクトの的・-i／--in-place の段の file・of= の的と、読むだけ（cmd_read.inert）でない段が指す file 全部
  （知らない書き手が試験の file を指す段は書く物と見なす＝cp・dd・python -c の open も入る）。
  中身は命令の文全体（heredoc を含む）と、命令が指す試験でない file の中身（cp の元など）。
射程の外（正直に書く）: 自分のサーバを経た中継（例: 手元のサーバが本物の鍵で AI へ中継する）は見えない。
  別の script の file の中で試験の file の名を組んで書く形も見えない。
判定できない時は通す（1 つの不具合で書き込みを止めない）。
"""
from __future__ import annotations

import ast
import configparser
import fnmatch
import os
import re
import subprocess

import cmd_read as R

PAID_MARKERS = (
    "ANTHROPIC_API_KEY", "OPENAI_API_KEY", "GEMINI_API_KEY", "GOOGLE_GENAI_API_KEY",
    "MISTRAL_API_KEY", "COHERE_API_KEY", "GROQ_API_KEY", "FAL_KEY", "REPLICATE_API_TOKEN",
    "api.anthropic.com", "api.openai.com", "generativelanguage.googleapis.com",
    "api.mistral.ai", "api.cohere.ai", "api.groq.com",
)
# 鍵の名を 1 つずつ並べず類で見る: 環境から読む鍵の名の形（…_API_KEY 等）・AI の SDK の取り込み（引数なしの
# クライアントが環境から鍵を読む形もこれで拾う）。字を割って組む名（"ANTHROPIC_" + "API_KEY"）は、照らす前に
# 字の継ぎ（" + "・' '・f 文字列の継ぎ目）を外して寄せる。
KEY_NAME = re.compile(r"\b[A-Z][A-Z0-9]*_(?:API_?KEY|API_?TOKEN|SECRET_?KEY|ACCESS_?TOKEN|AUTH_?TOKEN)\b")
AI_SDK = re.compile(
    r"^\s*(?:from|import)\s+(?:anthropic|openai|google\.generativeai|google\.genai|mistralai|cohere|groq|replicate|"
    r"fal_client|together|voyageai|litellm|langchain_(?:openai|anthropic|google_genai))\b"
    r"|(?:require\s*\(|from\s+|import\s*\()\s*[\"'](?:@anthropic-ai/sdk|openai|@google/generative-ai|@google/genai|"
    r"@mistralai/mistralai|cohere-ai|groq-sdk|replicate|@fal-ai/[\w-]+|ai|@ai-sdk/[\w-]+)[\"']", re.M)
_JOIN = re.compile(r"""[\"']\s*\+\s*[\"']|[\"']\s+[\"']""")
GUARD_MARKER = "PAID_UPSTREAM_GUARD"
SOURCE_BYTES = 256_000     # 命令が指す file（cp の元など）の中身を読む上限

# この見張りが回る出来事と関数（guard.py がこの宣言を読んで回す＝入口の一覧に足さない）
HOOKS = {"pre": "check"}


# ── 試験の file（試験の道具が試験として集める物の決まりを 1 か所で読む）──
PY_FILES = ("test_*.py", "*_test.py", "test*.py")       # pytest の既定（python_files）と unittest・Django の既定（test*.py）
TEST_DIRS = ("tests", "test", "testing", "__tests__", "e2e", "spec", "specs")   # 試験の道具が既定で集める dir の名
JS_FILES = ("*.test.*", "*.spec.*", "*.e2e.*", "*_test.go")                 # jest・vitest・playwright・go test の既定
_CONFIGS = ("pytest.ini", "pyproject.toml", "tox.ini", "setup.cfg")


def _ini_opts(path):
    """pytest の設定 file 1 つから {python_files, testpaths}（pytest の設定でなければ None）。"""
    name = os.path.basename(path)
    try:
        if name == "pyproject.toml":
            import tomllib
            with open(path, "rb") as f:
                opts = ((tomllib.load(f).get("tool") or {}).get("pytest") or {}).get("ini_options")
            if not isinstance(opts, dict):
                return None
            got = {k: opts.get(k) for k in ("python_files", "testpaths")}
            return {k: (v.split() if isinstance(v, str) else list(v or [])) for k, v in got.items()}
        cp = configparser.ConfigParser(interpolation=None)
        cp.read(path, encoding="utf-8")
        sec = {"pytest.ini": "pytest", "tox.ini": "pytest", "setup.cfg": "tool:pytest"}[name]
        if not cp.has_section(sec):
            return None
        return {k: cp.get(sec, k, fallback="").split() for k in ("python_files", "testpaths")}
    except Exception:  # noqa: BLE001  読めない設定は既定の決まりで見る
        return None


def test_rules(start):
    """start から上へ、pytest の rootdir（設定の在る dir）か repo の根を探し (根, python_files, testpaths) を返す。"""
    d = os.path.abspath(start)
    while True:
        for c in _CONFIGS:
            p = os.path.join(d, c)
            opts = _ini_opts(p) if os.path.isfile(p) else None
            if opts is not None:
                return d, tuple(opts["python_files"]) or PY_FILES, tuple(opts["testpaths"])
        up = os.path.dirname(d)
        if os.path.exists(os.path.join(d, ".git")) or up == d:
            return d, PY_FILES, ()
        d = up


def _conftests(root):
    try:
        out = subprocess.run(["git", "-C", root, "ls-files", "-co", "--exclude-standard", "--", "conftest.py",
                              "*/conftest.py"], capture_output=True, text=True, timeout=10)
        names = out.stdout.split() if out.returncode == 0 else []
    except Exception:  # noqa: BLE001
        names = []
    return [os.path.join(root, n) for n in names]


def _imported_by_conftest(path, root):
    """conftest.py が取り込む（import・pytest_plugins）module の file か（fixtures の置き場）。"""
    for cf in _conftests(root):
        try:
            tree = ast.parse(open(cf, encoding="utf-8").read())
        except Exception:  # noqa: BLE001
            continue
        mods = []
        for n in ast.walk(tree):
            if isinstance(n, ast.Import):
                mods += [a.name for a in n.names]
            elif isinstance(n, ast.ImportFrom) and n.module:
                mods += [n.module] + ["%s.%s" % (n.module, a.name) for a in n.names]
            elif isinstance(n, ast.Constant) and isinstance(n.value, str) and re.fullmatch(r"[\w.]+", n.value):
                mods.append(n.value)                     # pytest_plugins = ["fixtures.llm_client"]
        for base in {root, os.path.dirname(cf)}:
            for m in mods:
                rel = m.replace(".", os.sep)
                if path in (os.path.join(base, rel + ".py"), os.path.join(base, rel, "__init__.py")):
                    return True
    return False


def is_test_file(path, cwd=""):
    """path が試験の道具に試験（か試験の支え）として集められる file か。dir は file でない。"""
    if not isinstance(path, str) or not path.strip() or path.endswith(("/", os.sep)):
        return False
    p = os.path.normpath(os.path.join(cwd or os.getcwd(), os.path.expanduser(path)))
    if os.path.isdir(p):
        return False
    base = os.path.basename(p)
    root, py_files, testpaths = test_rules(os.path.dirname(p))
    if base == "conftest.py" or any(fnmatch.fnmatch(base, pat) for pat in py_files + JS_FILES):
        return True
    rel = os.path.relpath(p, root)
    if not rel.startswith(".."):
        if any(rel == t or rel.startswith(t.rstrip("/") + os.sep) for t in testpaths):
            return True
    if any(part in TEST_DIRS for part in p.split(os.sep)[:-1]):
        return True
    return base.endswith(".py") and _imported_by_conftest(p, root)


# ── Bash が書く先（読み手 cmd_read の語で読む）──
def _redirects(cmd, depth=0):
    """[(演算子, 的の Word)]。bash -c の中も読む。heredoc の中身は命令でないので見ない。"""
    toks = R._tokens(R._strip_heredocs(cmd)) if depth <= R.DEPTH else None
    if toks is None:
        return []
    out, subs = [], []
    for i, (kind, val) in enumerate(toks):
        if kind == "redir" and ">" in val and not val.endswith("&") and i + 1 < len(toks) and toks[i + 1][0] == "word":
            out.append((val, R._cook(toks[i + 1][1], {}, subs)))
    for seg in R.read(cmd).segments:
        if R.prog_name(seg) in R.SHELLS:
            for j, w in enumerate(seg[1:], 1):
                if w.text.startswith("-") and "c" in w.text.lstrip("-") and j + 1 < len(seg):
                    out += _redirects(seg[j + 1].text, depth + 1)
    for sub in subs:
        out += _redirects(sub, depth + 1)
    return out


def _parts(word):
    """語とその中を割った語（python -c の中の字・of=… の的も 1 語として出す）。"""
    return [word] + [t for t in R._SPLIT.split(R._flat(word)) if t and t != word]


def bash_writes(cmd):
    """(確かに書く的, 書くかもしれない的)。確か＝リダイレクト（> >> &>）の的・-i／--in-place の段の語・of= の的。
    かも＝読むだけ（cmd_read.inert）でない段が指す語の全部（知らない書き手は、指す file に書く物と見なす）。"""
    sure, maybe = [], []
    for op, w in _redirects(cmd):
        if not w.text.startswith("/dev/"):
            sure.append(w.text)
    for seg in R.read(cmd).segments:
        if R._seg_inert(seg):
            continue
        words = [w.text for w in seg[1:]]
        inplace = any(t.startswith("-i") or t == "--in-place" for t in words)
        for t in words:
            if t.startswith("of="):
                sure.append(t[3:])
            elif inplace and not t.startswith("-"):
                sure.append(t)
            maybe += _parts(t)
    return sure, maybe


def _sources(tokens, cwd):
    """命令が指す、試験でない在る file の中身（cp の元などの中身を照らす）。"""
    out = []
    for t in dict.fromkeys(tokens):
        p = os.path.join(cwd or os.getcwd(), os.path.expanduser(t))
        try:
            if os.path.isfile(p) and os.path.getsize(p) <= SOURCE_BYTES and not is_test_file(p):
                with open(p, encoding="utf-8", errors="replace") as f:
                    out.append(f.read())
        except Exception:  # noqa: BLE001
            continue
    return "\n".join(out)


def paid_hits(text, vals):
    """有料の上流へつなぐ印の並び（表の字・鍵の名の形・AI の SDK の取り込み）。"""
    joined = _JOIN.sub("", text)
    markers = list(PAID_MARKERS) + [m for m in vals.get("paid_markers_extra") or [] if isinstance(m, str) and m]
    hits = [m for m in markers if m in text or m in joined]
    hits += sorted({m.group(0) for m in KEY_NAME.finditer(joined)} - set(hits))
    hits += ["AI の SDK の取り込み（%s）" % m.group(0).strip()[:40] for m in AI_SDK.finditer(joined)][:1]
    return hits


def reason(path, hits):
    return (
        "試験から有料の上流（AI の API など）へ直接つながる線なので止めました。\n"
        "  書こうとしている file: {}\n"
        "  当たった印: {}\n"
        "開発中の自動試験が本物の API を叩き続けると、費用の大半がそこに消えます（実測がある）。\n"
        "進め方:\n"
        "  ① 既定は録画の再生か偽物にする（本物が無い時は赤で止める。『無ければ本物で』の逃げは黙って課金する）\n"
        "  ② 本物を通す線が本当に要るなら、環境変数 1 本で切り替える共通の関所を通し、この file に `{}` を書く\n"
        "  ③ 手元のサーバが本物の鍵で中継していないかも、その行を引用して確かめる（この見張りからは見えない）"
    ).format(path, " / ".join(hits), GUARD_MARKER)


def check_bash(data, vals):
    ti = data.get("tool_input")
    cmd = ti.get("command") if isinstance(ti, dict) else None
    if not isinstance(cmd, str) or GUARD_MARKER in cmd:
        return ""
    cwd = data.get("cwd") if isinstance(data.get("cwd"), str) else ""
    sure, maybe = bash_writes(cmd)
    body = cmd + "\n" + _sources(maybe, cwd)
    hits = paid_hits(body, vals) if GUARD_MARKER not in body else []
    if not hits:
        return ""                                        # 印が無ければ書く先を見るまでもない（安い方を先に）
    tests = [t for t in dict.fromkeys(sure + maybe) if is_test_file(t, cwd)]
    return reason(", ".join(tests), hits) if tests else ""


def _strings(node, key=""):
    """入力の入れ子を歩いた (鍵, 字) の並び。"""
    if isinstance(node, dict):
        for k, v in node.items():
            yield from _strings(v, str(k))
    elif isinstance(node, list):
        for v in node:
            yield from _strings(v, key)
    elif isinstance(node, str):
        yield key, node


def _key_words(key):
    return set(re.split(r"[^a-z]+", key.lower()))


def _is_path_key(key):
    return bool(_key_words(key) & {"path", "file", "filename"})


def _is_body_key(key):
    """書く中身の欄（content・new_string・new_source・text・body・data）。古い字（old_string）と探す字（pattern）は中身でない。"""
    w = _key_words(key)
    return bool(w & {"content", "new", "source", "text", "body", "data"}) and "old" not in w


def check(data, vals):
    """止めるなら理由、通すなら ""。道具の名で見ず、入力に試験の file を指す path の欄が在るかで見る。"""
    if str(data.get("tool_name") or "") == "Bash":
        return check_bash(data, vals)
    tool_input = data.get("tool_input")
    if not isinstance(tool_input, dict):
        return ""
    pairs = list(_strings(tool_input))
    cwd = data.get("cwd") if isinstance(data.get("cwd"), str) else ""
    body = "\n".join(v for k, v in pairs if _is_body_key(k))
    hits = paid_hits(body, vals) if body and GUARD_MARKER not in body else []
    if not hits:
        return ""
    paths = [v for k, v in pairs if _is_path_key(k) and "\n" not in v and is_test_file(v, cwd)]
    return reason(paths[0], hits) if paths else ""
