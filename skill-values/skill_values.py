#!/usr/bin/env python3
"""値の表（使う側の repo の config/skill-values.json）を読む 1 本の口。探し方と鍵の一覧（同じ dir の schema.json）の正本。

土台の道具（guard・qa-html の check.mjs・codex の codex_pack.py・make-deck の scripts）は、これを直に読む。
各 plugin の lib/ には、この file と schema.json への symlink だけを置く（plugin を入れる時に実体が写る）。
探し方や鍵を変える時はここと schema.json だけを直す。

探し方（どの道具も同じ）:
  1. 道具に --values で渡した path
  2. 環境変数 SKILL_VALUES
  3. 道具が渡した起点の dir（例: 問いのページの dir）→ $CLAUDE_PROJECT_DIR → 今の dir の順に、
     それぞれ上へ config/skill-values.json を探す（.git の在る dir＝repo の根で止める）
  どれにも無ければ「表が無い」＝鍵は全部既定（表の無い repo でも動く）。

照らし（schema.json の鍵の一覧で）:
  - 土台の plugin の欄（schema の sections）の中の、知らない skill・知らない鍵・畳んだ鍵（retired）・型の違う値を、
    表の中の場所で名指しする。名が _ で始まる鍵は注として読まない。
  - 土台の plugin の名でも common でもない頂の欄（例: その repo 自身の skill の欄）は照らさない。
  - 鍵が無い・値が空（""・[]・{}・null）は「既定で動く」で、問題ではない。

使い方:
  import skill_values as SV
  sec = SV.section("dev-flow", "codex", explicit=path)        # 欄の dict。問題があれば SV.ValuesError（名指しの文）
  sec, problems = SV.section("guard", strict=False)           # 問題の鍵を落とした欄と、問題の文の並び
  python3 skill_values.py check [--values P] [--start D ...]           # 表全体を照らす（問題があれば exit 1）
  python3 skill_values.py section <plugin> [<skill>] [--values P] [--start D ...]
                                                                       # {"path": …, "values": …} を出す（問題があれば exit 2）
  python3 skill_values.py get <plugin> [<skill>] <鍵>                  # 値を 1 つ（無い・空なら空行。問題があれば exit 2）
"""
from __future__ import annotations

import json
import os
import re
import sys

sys.dont_write_bytecode = True

REL_PATH = os.path.join("config", "skill-values.json")
SCHEMA_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "schema.json")
TYPES = ("str", "int", "bool", "list", "dict", "text", "any", "repo_names", "patterns", "words", "globs")


class ValuesError(Exception):
    """値の表に問題がある（名指しの文を持つ）。"""

    def __init__(self, path, problems):
        self.path = path
        self.problems = list(problems)
        super().__init__(format_problems(path, self.problems))


def format_problems(path, problems):
    head = ("値の表 %s に直す所がある（鍵の一覧の正本は土台の skill-values/schema.json。鍵を 1 つずつ消して済ませず、"
            "細目 §3「まず構造を疑う」で、なぜ写しや古い鍵が残ったかから直す）:" % (path or "（不明）"))
    return "\n".join([head] + ["  - " + p for p in problems])


# ── 鍵の一覧 ──
_SCHEMA = None


def schema():
    global _SCHEMA
    if _SCHEMA is None:
        with open(SCHEMA_PATH, encoding="utf-8") as f:
            _SCHEMA = json.load(f)
    return _SCHEMA


def _spec(raw):
    """鍵の書き方（"str" か {"type": …}）を dict に揃える。"""
    return {"type": raw} if isinstance(raw, str) else dict(raw)


def keys_of(plugin, skill=None):
    """その欄の鍵の一覧 {鍵: spec}。欄が無ければ None。"""
    sec = schema()["sections"].get(plugin)
    if sec is None:
        return None
    if skill is None:
        if "keys" not in sec:
            return None
        return {k: _spec(v) for k, v in sec["keys"].items()}
    sk = (sec.get("skills") or {}).get(skill)
    if sk is None:
        return None
    return {k: _spec(v) for k, v in (sk.get("keys") or {}).items()}


def defaults(plugin, skill=None):
    """schema に既定が書いてある鍵の既定 {鍵: 値}。"""
    return {k: s["default"] for k, s in (keys_of(plugin, skill) or {}).items() if "default" in s}


# ── 探し方 ──
def _walk_up(start):
    d = os.path.abspath(os.path.expanduser(start))
    if os.path.isfile(d):
        d = os.path.dirname(d)
    while True:
        p = os.path.join(d, REL_PATH)
        if os.path.isfile(p):
            return p
        if os.path.exists(os.path.join(d, ".git")):
            return None
        up = os.path.dirname(d)
        if up == d:
            return None
        d = up


def find(explicit=None, starts=(), env=None):
    """表の path か None（無い）。explicit／SKILL_VALUES が無い file を指す時はその path を返す（読む所で名指しする）。"""
    env = os.environ if env is None else env
    if explicit:
        return os.path.abspath(explicit)
    if env.get("SKILL_VALUES"):
        return os.path.abspath(env["SKILL_VALUES"])
    for s in [*starts, env.get("CLAUDE_PROJECT_DIR"), os.getcwd()]:
        if s and os.path.isdir(s if not os.path.isfile(s) else os.path.dirname(s)):
            p = _walk_up(s)
            if p:
                return p
    return None


def load(path):
    """(表, 問題の並び)。path が None なら ({}, [])＝表が無い。"""
    if not path:
        return {}, []
    if not os.path.isfile(path):
        return {}, ["表の file が無い（--values か SKILL_VALUES が指す先を直す）"]
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:  # noqa: BLE001
        return {}, ["JSON として読めない: %s" % e]
    if not isinstance(data, dict):
        return {}, ["頂が {…} でない"]
    return data, []


# ── 照らし ──
try:  # 正規表現の解析の口（字の頭と尻を見ず、解いた形で全体の一致かを決める）
    from re import _constants as _RC, _parser as _RP
except ImportError:  # 3.10 まで
    import sre_constants as _RC  # noqa: N812
    import sre_parse as _RP  # noqa: N812

_HEADS = {_RC.AT_BEGINNING, _RC.AT_BEGINNING_STRING}
_TAILS = {_RC.AT_END, _RC.AT_END_STRING}


def _edge(seq, at, heads):
    """解いた並び seq の at 番（0 か -1）が、全体の頭（heads が _HEADS）か尻（_TAILS）の錨か。囲み（group）と
    分かれ（|）の中は、全部の道がそうなら錨と見る。"""
    items = list(seq)
    if not items:
        return False
    op, av = items[at]
    if op == _RC.AT:
        return av in heads
    if op == _RC.SUBPATTERN:
        return _edge(av[-1], at, heads)
    if op == _RC.BRANCH:
        return all(_edge(b, at, heads) for b in av[1])
    return False


def _anchored(x):
    """^ で始まり、エスケープしない $ で終わる（字の形。型 patterns の全体の鍵の前の形と今の形の見分けに使う）。"""
    return isinstance(x, str) and x.startswith("^") and x.endswith("$") and not re.search(r"(?<!\\)(?:\\\\)*\\\$$", x)


def _whole_regex(x):
    """全体に当てる形と読める（正規表現として読め、解いた形の全部の道が頭の錨 ^・\\A で始まり尻の錨 $・\\Z で終わる）。
    字の頭の ^ と尻の $ だけでは決めない（(?i)^o/r$ のように頭にフラグを置いた形・^a$|^b$ の分かれも全体の形。
    \\$ で終わる形・^a|b$ は全体の形でない）。"""
    if not isinstance(x, str):
        return False
    try:
        seq = _RP.parse(x)
    except (re.error, RecursionError, OverflowError):
        return False
    return _edge(seq, 0, _HEADS) and _edge(seq, -1, _TAILS)


def bad_repo_names(v):
    """型 repo_names（owner/repo の名の全体に当てる正規表現の並び）に合わない行の並び。
    各行は正規表現として読め、解いた形が ^ で始まり $ で終わる（_whole_regex。頭にフラグを置いた (?i)^o/r$ も全体の形）。頭だけ（^owner/）・錨なし（owner/repo）の
    前の形は、名の一部に当てる読み方と取り違えるので書けない（使う側は ^owner/repo$・owner ごとなら ^owner/.*$）。"""
    out = []
    for x in v if isinstance(v, list) else [v]:
        ok = _whole_regex(x)
        if ok:
            try:
                re.compile(x)
            except re.error:
                ok = False
        if not ok:
            out.append(x)
    return out


# ── 正規表現・字・glob の鍵の当て方（1 本の口） ──
# 値の表の字や正規表現を「何に・全体か一部か」で当てるかは、型の正本 schema.json の鍵の spec が持つ:
#   型 patterns: {"match": "whole"|"part", "against": 当てる相手}。whole は相手の全体に当てる（各行を ^ で始め $ で終える）。
#                part は相手の文の一部に当てる（re.search）。行は字か {"pattern": 字, …}。
#   型 words:    字のまま相手の一部に当てる（正規表現でない。\ を含む行は正規表現のつもりの書き違いとして名指す）。
#   型 globs:    path（repo の根から・/ 区切り）の全体に当てる glob。* と ? は / をまたがない。** は dir をまたぐ。
# 道具はこの口（compile_patterns・hit・words_in・glob_match）だけで当てる＝鍵ごとに re.search・fullmatch・
# 部分文字列・fnmatch を書き分けない。
def _row_pattern(x):
    if isinstance(x, dict):
        x = x.get("pattern")
    return x if isinstance(x, str) and x else None


def bad_pattern_rows(v):
    """型 patterns の並びの、字でない・正規表現として読めない行（照らし check が名指す・型の違いにはしない）。"""
    out = []
    for x in v if isinstance(v, list) else [v]:
        p = _row_pattern(x)
        try:
            ok = p is not None and re.compile(p) is not None
        except re.error:
            ok = False
        if not ok:
            out.append(x)
    return out


def old_pattern_rows(spec, v):
    """全体に当てる鍵（match whole）の、^…$ でない行（前の形＝一部に当てる読み方。1 段目は前の読み方で効かせて名指す）。"""
    if (spec or {}).get("type") != "patterns" or spec.get("match") != "whole" or not isinstance(v, list):
        return []
    return [x for x in v if _row_pattern(x) is not None and not _anchored(_row_pattern(x))]


def bad_words(v):
    """型 words（字のまま一部に当てる）の、字でない・正規表現のつもりの行（\\ を含む）。"""
    return [x for x in (v if isinstance(v, list) else [v]) if not isinstance(x, str) or not x or "\\" in x]


def key_spec(plugin, skill, key):
    """鍵の spec（{"type": …, "match": …, "against": …}）。無ければ {}。"""
    return (keys_of(plugin, skill) or {}).get(key) or {}


def compile_patterns(spec, rows, flags=0):
    """値の表の正規表現の並びを [(正規表現, 全体か, 元の行)] にする。読めない行は捨てる（照らし check が名指す）。
    全体に当てる鍵（match whole）の ^…$ の行は全体に、前の形の行（^…$ でない）と一部に当てる鍵（match part）は一部に当てる。"""
    whole = (spec or {}).get("match") == "whole"
    out = []
    for x in rows if isinstance(rows, list) else []:
        p = _row_pattern(x)
        if p is None:
            continue
        try:
            rx = re.compile(p, flags)
        except re.error:
            continue
        out.append((rx, whole and _anchored(p), x))
    return out


def patterns_of(plugin, skill, key, values, flags=0):
    """値の表の欄 values（dict）の鍵 key を、型の正本の spec の当て方で読んだ形（hit に渡す）。"""
    return compile_patterns(key_spec(plugin, skill, key), (values or {}).get(key) or [], flags)


def hit(compiled, text, old_text=None):
    """当たった最初の行（元の行）か None。全体の行は text の全体に当てる。前の形の行（全体の鍵の ^…$ でない行）は
    old_text（前の当てる相手。渡さなければ text）の一部に当てる。一部の鍵の行は text の一部に当てる。"""
    for rx, whole, row in compiled:
        if whole:
            if rx.fullmatch(text):
                return row
        elif rx.search(text if old_text is None else old_text):
            return row
    return None


def words_in(words, text):
    """型 words の字のうち text の一部に在る物の並び（字のまま）。"""
    return [w for w in (words or []) if isinstance(w, str) and w and "\\" not in w and w in text]


def _glob_rx(pat):
    out, i = [], 0
    while i < len(pat):
        c = pat[i]
        if pat.startswith("**/", i):
            out.append("(?:[^/]*/)*")
            i += 3
        elif pat.startswith("**", i):
            out.append(".*")
            i += 2
        elif c == "*":
            out.append("[^/]*")
            i += 1
        elif c == "?":
            out.append("[^/]")
            i += 1
        else:
            out.append(re.escape(c))
            i += 1
    return re.compile("".join(out))


def glob_match(pat, path):
    """型 globs: path（repo の根から・/ 区切り）の全体に glob を当てる。* と ? は / をまたがず、** は dir をまたぐ。"""
    return isinstance(pat, str) and bool(pat) and bool(_glob_rx(pat).fullmatch(str(path).replace(os.sep, "/")))


def _type_ok(t, v):
    if v is None or t == "any":
        return True
    if t == "str":
        return isinstance(v, str)
    if t == "int":
        return isinstance(v, int) and not isinstance(v, bool)
    if t == "bool":
        return isinstance(v, bool)
    if t == "list":
        return isinstance(v, list)
    if t == "dict":
        return isinstance(v, dict)
    if t == "text":
        return isinstance(v, str) or (isinstance(v, list) and all(isinstance(x, str) for x in v))
    if t == "repo_names":
        return isinstance(v, list) and not bad_repo_names(v)
    if t == "patterns":
        # 読めない行は型の違いにしない（鍵ごと落とすと、止める側の鍵〔irreversible_*_extra〕が黙って効かなくなる）。
        # 読めない行は道具が捨てるか照らせないと止め、照らし check は名指す（_check_keys）。
        return isinstance(v, list) and all(_row_pattern(x) is not None for x in v)
    if t == "words":
        # 書き違いの行（\ を含む）は型の違いにしない（鍵ごと落とすと、止める側の鍵 paid_markers_extra の正しい行まで
        # 黙って効かなくなる）。その行だけ words_in が捨て、照らし check が名指す（_check_keys）。型 patterns と同じ扱い。
        return isinstance(v, list) and all(isinstance(x, str) and x for x in v)
    if t == "globs":
        return isinstance(v, list) and all(isinstance(x, str) and x for x in v)
    return False


TYPE_WORD = {"str": "文字列", "int": "整数", "bool": "真偽", "list": "並び [...]", "dict": "{...}",
             "text": "文字列か文字列の並び", "any": "何でも",
             "repo_names": "owner/repo の名の全体に当てる正規表現の並び（各行を ^ で始め $ で終える・"
                           "repo 1 つなら ^owner/repo$・owner ごとなら ^owner/.*$）",
             "patterns": "正規表現の並び（読める形で書く）",
             "words": "字の並び（字のまま一部に当てる・正規表現でない＝\\ を書かない）",
             "globs": "glob の並び（repo の根からの path の全体に当てる・* は / をまたがない・dir をまたぐのは **）"}


def _against(spec):
    m = {"whole": "全体", "part": "一部"}.get(spec.get("match"), "")
    return "（%sの%sに当てる）" % (spec.get("against") or "相手", m) if m else ""


def _check_keys(where, node, specs, retired):
    """node（dict）を specs で照らし、(問題の並び, 問題の鍵の集合)。"""
    out, bad = [], set()
    if not isinstance(node, dict):
        return ["%s が {…} でない" % where], {None}
    for k, v in node.items():
        if str(k).startswith("_"):
            continue
        at = "%s.%s" % (where, k)
        if at in retired:
            out.append("%s は畳んだ鍵: %s" % (at, retired[at]))
            bad.add(k)
            continue
        spec = specs.get(k)
        if spec is None:
            known = "・".join(sorted(specs)) or "（鍵を持たない）"
            out.append("%s は知らない鍵（効かない）。この欄の鍵: %s" % (at, known))
            bad.add(k)
            continue
        if empty(v):
            continue   # 空（""・[]・{}・null）は型を問わず「既定で動く」＝問題ではない
        if not _type_ok(spec["type"], v):
            rows = {"repo_names": bad_repo_names}.get(spec["type"])
            if rows and isinstance(v, list):
                out.append("%s の行 %s が型に合わない（%s で書く%s）" % (
                    at, "・".join(json.dumps(x, ensure_ascii=False) for x in rows(v)), TYPE_WORD[spec["type"]], _against(spec)))
            else:
                out.append("%s の型が違う（%s で書く・今は %s）" % (at, TYPE_WORD[spec["type"]], type(v).__name__))
            bad.add(k)
            continue
        # 読めない行・書き違いの行は鍵を落とさず、その行だけが効かないと名指す（型ごとの「行の扱い」はここ 1 か所）
        unread = {"patterns": bad_pattern_rows, "words": bad_words}.get(spec["type"], lambda _v: [])(v)
        if unread:
            out.append("%s の行 %s が型に合わない（その行だけ効かない・%s で書く%s）" % (
                at, "・".join(json.dumps(x, ensure_ascii=False) for x in unread), TYPE_WORD[spec["type"]], _against(spec)))
        old = old_pattern_rows(spec, v)
        if old:
            # 1 段目: 前の形の行は前の読み方（一部に当てる）で効かせたまま名指す（鍵は落とさない）
            out.append("%s の行 %s は前の形（一部に当てる読み方）。この鍵は%s。^…$ で全体の形に書き直す" % (
                at, "・".join(json.dumps(x, ensure_ascii=False) for x in old), _against(spec)))
        if isinstance(v, dict) and "keys" in spec:
            sub, subbad = _check_keys(at, v, {kk: _spec(vv) for kk, vv in spec["keys"].items()}, retired)
            out += sub
            if subbad:
                bad.add(k)
    return out, bad


def check_section(table, plugin, skill=None):
    """(その欄の問題の並び, 問題の鍵の集合)。欄が無ければ ([], set())。"""
    retired = schema().get("retired") or {}
    node = table.get(plugin)
    if skill is not None:
        if node is not None and not isinstance(node, dict):
            # 上の欄が {…} でない時は、その下の欄が無いと黙って見なさない（表全体の照らし check と同じ線）
            return ["%s が {…} でない" % plugin], {None}
        node = node.get(skill) if isinstance(node, dict) else None
    if node is None:
        return [], set()
    specs = keys_of(plugin, skill)
    where = plugin if skill is None else "%s.%s" % (plugin, skill)
    if specs is None:
        return ["%s は知らない欄（効かない）" % where], {None}
    return _check_keys(where, node, specs, retired)


def check(table):
    """表全体を照らした問題の並び（土台の欄だけ）。"""
    sections = schema()["sections"]
    retired = schema().get("retired") or {}
    out = []
    for plugin, node in table.items():
        if str(plugin).startswith("_") or plugin not in sections:
            continue
        sec = sections[plugin]
        if "keys" in sec:
            out += check_section(table, plugin)[0]
            continue
        if not isinstance(node, dict):
            out.append("%s が {…} でない" % plugin)
            continue
        skills = sec.get("skills") or {}
        for skill, sub in node.items():
            if str(skill).startswith("_"):
                continue
            at = "%s.%s" % (plugin, skill)
            if at in retired:
                out.append("%s は畳んだ欄: %s" % (at, retired[at]))
            elif skill not in skills:
                known = "・".join(sorted(skills)) or "（skill を持たない）"
                out.append("%s は知らない skill の欄（効かない）。%s の skill: %s" % (at, plugin, known))
            else:
                out += check_section(table, plugin, skill)[0]
    return out


def section(plugin, skill=None, *, explicit=None, starts=(), strict=True, env=None):
    """その欄の dict。strict なら問題（表が読めない・この欄の問題）で ValuesError。
    strict=False なら (問題の鍵を落とした欄, 問題の並び) を返す。"""
    path = find(explicit, starts, env)
    table, problems = load(path)
    node = table.get(plugin) if isinstance(table, dict) else None
    if skill is not None:
        node = node.get(skill) if isinstance(node, dict) else None
    sec_problems, bad = check_section(table, plugin, skill)
    problems = problems + sec_problems
    if strict:
        if problems:
            raise ValuesError(path, problems)
        return _usable(node, set())
    if None in bad or not isinstance(node, dict):
        return {}, problems
    return _usable(node, bad), problems


def _usable(node, bad):
    """道具に渡す欄: 注（_）・問題の鍵・空の値（＝既定で動く）を落とす。"""
    if not isinstance(node, dict):
        return {}
    return {k: v for k, v in node.items() if k not in bad and not str(k).startswith("_") and not empty(v)}


def empty(v):
    return v is None or (isinstance(v, (str, list, dict)) and len(v) == 0) or (isinstance(v, str) and not v.strip())


def get(plugin, skill, key, default=None, **kw):
    """1 つの値。鍵が無い・空なら default。問題があれば ValuesError。"""
    v = section(plugin, skill, **kw).get(key)
    return default if empty(v) else v


# ── 命令 ──
def _opts(argv):
    pos, explicit, starts = [], None, []
    it = iter(argv)
    for a in it:
        if a == "--values":
            explicit = next(it, None)
        elif a == "--start":
            starts.append(next(it, ""))
        else:
            pos.append(a)
    return pos, explicit, starts


def main(argv):
    if not argv or argv[0] not in ("check", "section", "get"):
        sys.stderr.write(__doc__.split("使い方:")[1])
        return 2
    cmd, (pos, explicit, starts) = argv[0], _opts(argv[1:])
    path = find(explicit, starts)
    if cmd == "check":
        table, problems = load(path)
        problems += check(table)
        if problems:
            sys.stderr.write(format_problems(path, problems) + "\n")
            return 1
        print("値の表: 直す所なし（%s）" % (path or "表が無い"))
        return 0
    if cmd == "section":
        if len(pos) not in (1, 2):
            sys.stderr.write("使い方: skill_values.py section <plugin> [<skill>]\n")
            return 2
        try:
            vals = section(pos[0], pos[1] if len(pos) > 1 else None, explicit=path)
        except ValuesError as e:
            sys.stderr.write(str(e) + "\n")
            return 2
        print(json.dumps({"path": path, "values": vals}, ensure_ascii=False))
        return 0
    if len(pos) not in (2, 3):
        sys.stderr.write("使い方: skill_values.py get <plugin> [<skill>] <鍵>\n")
        return 2
    try:
        v = get(pos[0], pos[1] if len(pos) == 3 else None, pos[-1], default="", explicit=path)
    except ValuesError as e:
        sys.stderr.write(str(e) + "\n")
        return 2
    print(json.dumps(v, ensure_ascii=False) if isinstance(v, (dict, list)) else v)
    return 0


if __name__ == "__main__":
    import af_place  # noqa: E402  古い版の窓から呼ばれても、入った中でいちばん新しい版で回す（入口の 1 行）
    af_place.run_newest(__file__)
    sys.exit(main(sys.argv[1:]))
