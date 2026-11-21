"""PreToolUse — 試験から有料の上流（AI の API など）へ直接つながる線を書く手を止める。

なぜ在るか: 開発中の自動試験が、本物の AI の API を叩き続けて費用の大半を占めた実測がある。
データを壊す書き込みは全部塞いでいたのに、読み取り（AI に読ませる口）だけ本物を通していた。
費用も壊れ物として、試験の中で本物へつなぐ線を書く時に止める。

止める: 試験らしい path（tests/・e2e/・spec/・__tests__/・test_*.py・*.test.js …）へ書く中身に、
  有料の上流の鍵名か公式のエンドポイントが現れた時。
逃げ道: PAID_UPSTREAM_GUARD を書く（＝環境変数 1 本で本物へ切り替える共通の関所を通す。既定は録画の再生か偽物。
  例 `os.environ.get("PAID_UPSTREAM_GUARD")`・`process.env.PAID_UPSTREAM_GUARD`）。コードに書けば黙って通す。
  関所が共通の補助に在り、この file には注釈で印を名指すだけの時も止めない（関所の置き場は pytest_plugins・jest の setupFiles・
  TS の別名・shell の source など限りなく在り、探し方の一覧の外の正しい置き方を止めないため）。その時は手元で見つかる補助
  （上の dir の conftest.py・コードが import する手元の module）のコードが印を読むかを見て、見つかれば黙って通し、
  見つからなければ書いた後に「関所を見つけられなかった」と知らせる（notice・止めない）。
  止めるのは印がどこにも無い形だけ（前から止めていた形）。
見るのはコードの所だけ（guard_common.code_only: 注釈〔# か // と /* */〕と Python の docstring を除く）。Edit・MultiEdit は
  手元の file に置き換えを当てた全体を読み、置き換えの後にだけ在るコードの行（前との行の差）に在る印だけを数える。全体を組めない時は断片を
  字のまま見る。注釈・docstring で鍵の名や host を挙げるだけでは止めない。拡張子で注釈の形が決まらない file は字のまま見る。

見る口: Write / Edit / MultiEdit / NotebookEdit と、Bash で試験らしい path へ書く形（`>`・`>>` のリダイレクト・
  `tee`・`sed -i`／`perl -i` の的）。Bash は命令の字（shell の注釈を除く）と、heredoc の中身（書く先の試験の file の拡張子で
  注釈を除いた字）に印があるかを見る。命令が読み切れない形なら命令の字全体で見る。
射程の外（正直に書く）: 自分のサーバを経た中継（例: 手元のサーバが本物の鍵で AI へ中継する）は見えない。
  Bash でも、書く中身が命令の外にある形（cp・mv・別の script の中で書く・python -c の中の open）は見えない。
判定できない時は通す（1 つの不具合で書き込みを止めない）。
"""
from __future__ import annotations

import os
import re
import sys
from collections import Counter

sys.dont_write_bytecode = True
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "lib"))
import skill_values as SV  # noqa: E402  値の表の当て方の 1 本の口（土台の skill-values/ への symlink）
import guard_common as G  # noqa: E402  命令の字の読み方・コードの所の取り方の 1 本の口

TEST_PATH_RE = re.compile(
    r"(^|/)(tests?|e2e|__tests__|spec|specs|testing)(/|$)"
    r"|(^|/)test_[^/]*\.py$"
    r"|[._-](test|spec|e2e)\.[cm]?[jt]sx?$"
    r"|_test\.(py|go)$",
    re.I)

PAID_MARKERS = (
    "ANTHROPIC_API_KEY", "OPENAI_API_KEY", "GEMINI_API_KEY", "GOOGLE_GENAI_API_KEY",
    "MISTRAL_API_KEY", "COHERE_API_KEY", "GROQ_API_KEY", "FAL_KEY", "REPLICATE_API_TOKEN",
    "api.anthropic.com", "api.openai.com", "generativelanguage.googleapis.com",
    "api.mistral.ai", "api.cohere.ai", "api.groq.com",
)
GUARD_MARKER = "PAID_UPSTREAM_GUARD"
WRITE_TOOLS = {"Write", "Edit", "MultiEdit", "NotebookEdit"}
CONTENT_KEYS = ("content", "new_string", "new_source")



# この見張りが回る出来事と関数（guard.py がこの宣言を読んで回す＝入口の一覧に足さない）
HOOKS = {"pre": "check", "post": "notice"}

def _path_of(tool_input):
    for k in ("file_path", "notebook_path"):
        v = tool_input.get(k)
        if v:
            return str(v)
    return ""


def _payload(tool_input):
    """書こうとしている中身を全部つなげる（MultiEdit の edits も含む）。"""
    parts = [tool_input[k] for k in CONTENT_KEYS if isinstance(tool_input.get(k), str)]
    for e in tool_input.get("edits") or []:
        if isinstance(e, dict):
            parts += [e[k] for k in CONTENT_KEYS if isinstance(e.get(k), str)]
    return "\n".join(parts)


def reason(path, hits):
    return (
        "試験から有料の上流（AI の API など）へ直接つながる線なので止めました。\n"
        "  書こうとしている file: {}\n"
        "  当たった印: {}\n"
        "開発中の自動試験が本物の API を叩き続けると、費用の大半がそこに消えます（実測がある）。\n"
        "進め方:\n"
        "  ① 既定は録画の再生か偽物にする（本物が無い時は赤で止める。『無ければ本物で』の逃げは黙って課金する）\n"
        "  ② 本物を通す線が本当に要るなら、環境変数 1 本で切り替える共通の関所を通し、この file のコードで `{}` を読む（関所が別の file に在るなら、この file に注釈で名指す）\n"
        "  ③ 手元のサーバが本物の鍵で中継していないかも、その行を引用して確かめる（この見張りからは見えない）"
    ).format(path, " / ".join(hits), GUARD_MARKER)


# Bash で file へ書く的: リダイレクト（> と >>・2> などの数字つきや >& は除く）・tee・sed -i／perl -i の最後の語
_REDIRECT = re.compile(r"(?<![0-9&>])>>?\s*(?!&)([^\s;&|<>()]+)")
_TEE = re.compile(r"\btee\b((?:\s+-[a-zA-Z]+)*)((?:\s+[^\s;&|<>()-][^\s;&|<>()]*)+)")
_INPLACE = re.compile(r"\b(?:sed|perl)\s+[^;&|]*?-i\S*[^;&|]*?\s([^\s;&|<>()]+)\s*(?:$|[;&|])", re.M)


def bash_targets(cmd):
    """Bash の命令が書く file の path の並び（推し量り）。"""
    out = [m.group(1) for m in _REDIRECT.finditer(cmd)]
    for m in _TEE.finditer(cmd):
        out += m.group(2).split()
    out += [m.group(1) for m in _INPLACE.finditer(cmd)]
    return [t.strip("'\"") for t in out if t.strip("'\"") not in ("/dev/null", "-")]


def bash_code(cmd, target):
    """命令のうち見る字: shell の注釈を除いた命令と、heredoc の中身から書く先の拡張子の注釈を除いた字。読み切れなければ全体。"""
    sh = G.shell_and_heredocs(cmd)
    if sh is None:
        return cmd
    flat, bodies = sh
    return "\n".join([flat] + [G.code_only(b, target) for b in bodies])


_PY_IMPORT = re.compile(r"^\s*(?:from\s+(\.*[\w.]*)\s+import|import\s+([\w.]+))", re.M)
_JS_IMPORT = re.compile(r"(?:\bfrom\s+|\brequire\s*\(\s*|\bimport\s*\(?\s*)['\"](\.{1,2}/[^'\"]+)['\"]")
_JS_TRY = ("", ".js", ".mjs", ".cjs", ".ts", ".mts", ".tsx", ".jsx", "/index.js", "/index.ts")


def _read(path):
    try:
        with open(path, encoding="utf-8") as f:
            return f.read()
    except (OSError, UnicodeDecodeError):
        return None


def _helpers(path, code):
    """試験の file が使う共通の補助: 上の dir の conftest.py（pytest が自動で読む）と、コードが import する手元の module。"""
    d = os.path.dirname(os.path.abspath(path))
    out, up = [], d
    for _ in range(8):
        out.append(os.path.join(up, "conftest.py"))
        if os.path.isdir(os.path.join(up, ".git")) or os.path.dirname(up) == up:
            break
        up = os.path.dirname(up)
    for m in _PY_IMPORT.finditer(code):
        name = m.group(1) or m.group(2) or ""
        rel = name.lstrip(".").replace(".", os.sep)
        if not rel:
            continue
        base = d
        for _ in range(max(0, len(name) - len(name.lstrip(".")) - 1)):
            base = os.path.dirname(base)
        roots = [base] if name.startswith(".") else [os.path.dirname(c) for c in out if c.endswith("conftest.py")]
        for r in roots:
            out += [os.path.join(r, rel + ".py"), os.path.join(r, rel, "__init__.py")]
    for m in _JS_IMPORT.finditer(code):
        out += [os.path.normpath(os.path.join(d, m.group(1))) + t for t in _JS_TRY]
    return out


def gate_read(path, raw, code):
    """本物へ切り替える共通の関所の印の読み方: "code"（この file のコードが印を読む）・"helper"（注釈で印を名指し、
    手元で見つかる共通の補助〔conftest.py・import する手元の module〕のコードが印を読む）・"named"（注釈で名指すだけで、
    関所を見つけられない＝止めずに知らせる）・""（印がどこにも無い＝止める）。"""
    if GUARD_MARKER in code:
        return "code"
    if GUARD_MARKER not in raw:
        return ""
    for h in _helpers(path, code):
        t = _read(h) if os.path.isfile(h) else None
        if t and GUARD_MARKER in G.code_only(t, h):
            return "helper"
    return "named"


def note(path, hits):
    return (
        "試験の file に有料の上流（AI の API など）への線が在り、本物へ切り替える関所の印 `{}` は注釈で名指すだけでした（止めていません）。\n"
        "  書いた file: {}\n"
        "  当たった印: {}\n"
        "手元で見つかる共通の補助（上の dir の conftest.py・import する手元の module）には、印を読むコードが見つかりませんでした。\n"
        "関所を別の置き方（pytest_plugins・jest の setupFiles・TS の別名・shell の source など）で通しているなら、そのままで構いません。\n"
        "関所がどこにも無いなら、既定を録画の再生か偽物にし、本物へは環境変数 1 本で切り替える関所を通してください。"
    ).format(GUARD_MARKER, path, " / ".join(hits))


def written_body(tool_name, tool_input, path):
    """書いた後の file の中身（全体）。Write はその中身、Edit・MultiEdit は手元の file に置き換えを当てた中身。
    組めない（file が無い・old_string が無い）時は None＝断片を字のまま見る。"""
    if tool_name == "Write":
        v = tool_input.get("content")
        return v if isinstance(v, str) else None
    if tool_name == "NotebookEdit":
        v = tool_input.get("new_source")
        return v if isinstance(v, str) else None      # 1 つの cell は丸ごと
    edits = tool_input.get("edits") if tool_name == "MultiEdit" else [tool_input]
    text = _read(path)
    if text is None or not isinstance(edits, list):
        return None
    for e in edits:
        if not isinstance(e, dict):
            return None
        old, new = e.get("old_string"), e.get("new_string")
        if not isinstance(old, str) or not isinstance(new, str) or (old and old not in text):
            return None
        text = text.replace(old, new) if e.get("replace_all") else text.replace(old, new, 1)
    return text


def added_lines(before, after, path):
    """置き換えの後のコードの行のうち、前に無かった行（行の多重集合の差）をつないだ字。前から在る行に触れない
    Edit を止めず、同じ数のまま偽物を本物へ書き換える行（fake('鍵') → os.environ['鍵']）は足した行として数える。"""
    old = Counter(G.code_only(before, path).splitlines())
    new = Counter(G.code_only(after, path).splitlines())
    return "\n".join((new - old).elements())


def _bash_judge(data, vals):
    ti = data.get("tool_input")
    cmd = ti.get("command") if isinstance(ti, dict) else None
    if not isinstance(cmd, str):
        return None
    tests = [t for t in bash_targets(cmd) if TEST_PATH_RE.search(t.replace(os.sep, "/"))]
    if not tests:
        return None
    code = bash_code(cmd, tests[0])
    cwd = str(data.get("cwd") or "")
    target = tests[0] if os.path.isabs(tests[0]) or not cwd else os.path.join(cwd, tests[0])
    gate = gate_read(target, cmd, code)
    if gate in ("code", "helper"):
        return None
    hits = SV.words_in(list(PAID_MARKERS) + list(vals.get("paid_markers_extra") or []), code)
    return (gate, ", ".join(tests), hits) if hits else None


def _write_judge(data, vals, post):
    tool_name = str(data.get("tool_name") or "")
    tool_input = data.get("tool_input")
    if not isinstance(tool_input, dict):
        return None
    path = _path_of(tool_input)
    if not path or not TEST_PATH_RE.search(path.replace(os.sep, "/")):
        return None
    if post and tool_name in ("Edit", "MultiEdit"):
        full = _read(path)                                   # 書いた後の手元の file
        frag = _payload(tool_input)                          # 知らせるのは new_string の字に在る印だけ
    else:
        full = written_body(tool_name, tool_input, path)
        frag = None
    raw = full if full is not None else _payload(tool_input)
    body = G.code_only(full, path) if full is not None else raw   # 断片は字のまま（どこから始まるか分からない）
    if not body:
        return None
    gate = gate_read(path, raw, body)
    if gate in ("code", "helper"):
        return None
    hits = SV.words_in(list(PAID_MARKERS) + list(vals.get("paid_markers_extra") or []), body)
    if hits and not post and full is not None and tool_name in ("Edit", "MultiEdit"):
        hits = [h for h in hits if h in added_lines(_read(path) or "", full, path)]
    if hits and frag is not None:
        hits = [h for h in hits if h in frag]
    return (gate, path, hits) if hits else None


def _judge(data, vals, post=False):
    """(印の読み方, 書く先, 当たった印) か None。"""
    tool_name = str(data.get("tool_name") or "")
    if tool_name == "Bash":
        return _bash_judge(data, vals)
    if tool_name not in WRITE_TOOLS:
        return None
    return _write_judge(data, vals, post)


def check(data, vals):
    """PreToolUse: 止めるなら理由、通すなら ""。止めるのは関所の印がどこにも無い形だけ。"""
    j = _judge(data, vals)
    return reason(j[1], j[2]) if j and j[0] == "" else ""


def notice(data, vals):
    """PostToolUse: 印を注釈で名指すだけで関所を見つけられなかった時に知らせる（止めない）。"""
    j = _judge(data, vals, post=True)
    return note(j[1], j[2]) if j and j[0] == "named" else ""
