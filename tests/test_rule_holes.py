"""決まりの文を 1 つ消しても試験が緑のままになる穴を、試験の側から照らす。

なぜ在るか: 決まりの試験が「語がどこかに在るか」の照らしで、照らしていない文（PR #30 の細目 §4 並走の
「挙がった物を全部やる時の分け方は、窓を並べて同時に進めるのが既定。」など）を消しても緑だった。
ここでは核と細目の文を 1 つずつ消し、決まりの file を読む試験を回して、どれかが赤になるかを見る。

- 赤にならない文は、tests/data/試験で守らない文.txt に訳つきで載せた物だけ（知らない穴＝新しく足した文・書き換えた文は赤）。
  新しい決まりの文を足したら、その文を照らす試験を同じ PR で足す（文をそのまま照らすか、道具の値と文の値を突き合わせる）。
- 表の文が試験で守られるようになった・文が無くなった時は、表から消す（古い穴の行を残さない）。表の文を消す・書き換えると
  表の行が古くなって赤＝表そのものが文の控えで、表の文の書き換えも PR の差分で人の関所（review-pr の点 12）に出る。

決まりの file を読む試験の見分け（PR #59 のレビューの所見 3）: 読み方に依らないよう、Path.read_text でなく open の口
（builtins.open・io.open。Path.read_text・read_bytes・open() は全部ここを通る）で読みを拾い、消した中身もそこで渡す。
module の頭で読む試験（定数に読み込む形）は、消した中身で module を読み直して回す。回すのは引数の無い試験と、
引数が parametrize の値・tmp_path・monkeypatch・capsys だけの試験。subprocess の中の読みと、他の fixture を使う試験は
数えない（穴を多めに出す側に倒れる＝守られている文が表に残るだけで、黙って緑にはならない）。
"""
import builtins
import contextlib
import functools
import importlib.util
import inspect
import io
import itertools
import os
import pathlib
import re
import shutil
import signal
import sys
import tempfile
import time
from collections import namedtuple

import pytest
from _pytest.mark.structures import ParameterSet

ROOT = pathlib.Path(__file__).resolve().parent.parent
RULE_FILES = ["plugins/core/核.md", "plugins/core/振る舞い.md", "plugins/core/細目.md"]
TABLE = ROOT / "tests" / "data" / "試験で守らない文.txt"
# 表に残す訳（行の 3 列目）。訳の無い行・知らない訳の行は赤。
訳 = {
    "形": "見出し・表の見出しと罫・コードの囲みの行で、文でない（照らす値が無い）",
    "判断": "AI と人の判断に任せる既定で、機械が照らせる値が無い（消す・書き換えると表の行が古くなり赤。弱めは review-pr の点 12 が読む）",
}
形の行 = re.compile(r"^(#{1,6} |\|.*\|$|`{1,3}$)")

_open_real = builtins.open
_TARGETS = {str((ROOT / r).resolve()): r for r in RULE_FILES}
_NAMES = {pathlib.Path(r).name for r in RULE_FILES}
_state = {"log": None, "swap": {}}
_rglob_real = pathlib.Path.rglob
_rglob_cache = {}


def _target(file):
    if isinstance(file, int):
        return None
    try:
        name = os.fsdecode(file)
    except TypeError:
        return None
    if os.path.basename(name) not in _NAMES:
        return None
    return _TARGETS.get(os.path.realpath(name))


def _open(file, mode="r", *a, **k):
    rel = _target(file)
    if rel is not None:
        if _state["log"] is not None:
            _state["log"].add(rel)
        if rel in _state["swap"] and not set(mode) & set("wax+"):
            body = _state["swap"][rel]
            return io.BytesIO(body.encode("utf-8")) if "b" in mode else io.StringIO(body)
    return _open_real(file, mode, *a, **k)


def _rglob(self, pattern, *a, **k):
    """文を消して回す間は file の並びが変わらない＝repo を歩くのは 1 度だけ（.git も歩く試験が多く、回すたびに歩くと遅い）。"""
    key = (str(self), pattern)
    if key not in _rglob_cache:
        _rglob_cache[key] = [q for q in _rglob_real(self, pattern, *a, **k) if ".git" not in q.parts]  # どの試験も .git は飛ばす
    return iter(_rglob_cache[key])


@contextlib.contextmanager
def _口(log=None, swap=None):
    """open の口を差し替える間（log: 読んだ決まりの file を足す集まり・swap: {rel: 消した中身}）。"""
    before = (_state["log"], _state["swap"], builtins.open, io.open, pathlib.Path.rglob)
    _state["log"], _state["swap"] = log, swap or {}
    builtins.open = io.open = _open
    pathlib.Path.rglob = _rglob
    try:
        yield
    finally:                                   # 入れ子でも外の差し替えへ戻す
        _state["log"], _state["swap"], builtins.open, io.open, pathlib.Path.rglob = before


def 文の並び(text):
    """(行の番号, 文) の並び。文は「。」までの切れ目（「。」の無い行は行の全部）。空の行は数えない。"""
    out = []
    for i, ln in enumerate(text.splitlines()):
        for s in re.findall(r"[^。]*。|[^。]+$", ln):
            if s.strip():
                out.append((i, s))
    return out


def _消す(text, cut):
    """cut: [(行の番号, 文)] を消した中身。"""
    lines = text.splitlines(keepends=True)
    for i, s in cut:
        lines[i] = lines[i].replace(s, "", 1)
    return "".join(lines)


class _Capsys:
    """capsys の代わり（readouterr だけ）。"""
    Out = namedtuple("Out", "out err")

    def __init__(self):
        self._o, self._e = io.StringIO(), io.StringIO()
        self._stack = contextlib.ExitStack()
        self._stack.enter_context(contextlib.redirect_stdout(self._o))
        self._stack.enter_context(contextlib.redirect_stderr(self._e))

    def readouterr(self):
        r = self.Out(self._o.getvalue(), self._e.getvalue())
        self._o.seek(0), self._o.truncate(), self._e.seek(0), self._e.truncate()
        return r

    def close(self):
        self._stack.close()


_FIXTURES = {"tmp_path", "monkeypatch", "capsys"}
# 引数を取る試験を回すのは、決まりの file の名か core の dir を名指す module だけ（引数を取る試験は重い統合の試験が多い。
# 名指さずに決まりを読む試験〔repo の md を全部歩く形〕は引数の無い形が多く、そちらは全部の module で回す）。
_名指す = re.compile(r'核\.md|細目\.md|振る舞い\.md|"core"')
_見分けの上限 = 20.0   # 秒。止まったままの試験で見分けが終わらないのを防ぐだけ（越えた試験は数えない）
# 回さない module: 理由。時間で切ると数えるかが回ごとに揺れるので、重い module は名で外す（揺れない）。
_窓を起動 = "窓（claude）を起動する試験で重く、決まりの file を読むのは起動した窓（subprocess）の中＝ここでは数えられない"
_回さない = {"test_plugin_smoke.py": _窓を起動, "test_setup_plugins_real_claude.py": _窓を起動}


def _組(f):
    """parametrize の印から、引数の値の組（dict）の並び。印と _FIXTURES の外の引数が在れば None（回さない）。"""
    axes, given = [], set()
    for m in getattr(f, "pytestmark", []):
        if m.name != "parametrize":
            continue
        names = m.args[0]
        names = [n.strip() for n in names.split(",")] if isinstance(names, str) else list(names)
        given |= set(names)
        rows = []
        for v in m.args[1]:
            if isinstance(v, ParameterSet):
                rows.append(dict(zip(names, v.values)))
            else:
                rows.append(dict(zip(names, v)) if len(names) > 1 else {names[0]: v})
        axes.append(rows)
    if set(inspect.signature(f).parameters) - given - _FIXTURES:
        return None
    return [functools.reduce(lambda a, b: {**a, **b}, combo, {}) for combo in itertools.product(*axes)]


class _時間切れ(BaseException):
    pass


def _切る(*_):
    raise _時間切れ()


def _回す(f, args, limit=None):
    """1 つの組で試験を回す。赤なら True。limit 秒を越えたら _時間切れ（見分けの時だけ）。"""
    params = inspect.signature(f).parameters
    kw = {k: v for k, v in args.items() if k in params}
    tmp, mp, cap = None, None, None
    stdin, sys.stdin = sys.stdin, io.StringIO("")          # pytest と同じく標準入力は空（読む試験が待たない）
    if limit:
        signal.signal(signal.SIGALRM, _切る)
        signal.setitimer(signal.ITIMER_REAL, limit)
    try:
        if "tmp_path" in params:
            tmp = tempfile.mkdtemp(prefix="rule_holes_")
            kw["tmp_path"] = pathlib.Path(tmp)
        if "monkeypatch" in params:
            mp = kw["monkeypatch"] = pytest.MonkeyPatch()
        if "capsys" in params:
            cap = kw["capsys"] = _Capsys()
        f(**kw)
        return False
    except _時間切れ:
        raise
    except BaseException:      # noqa: BLE001 — 赤（例外・assert）。skip は赤と数えない
        return not isinstance(sys.exc_info()[1], pytest.skip.Exception)
    finally:
        sys.stdin = stdin
        if limit:
            signal.setitimer(signal.ITIMER_REAL, 0)
        if cap:
            cap.close()
        if mp:
            mp.undo()
        if tmp:
            shutil.rmtree(tmp, ignore_errors=True)


class _試験:
    """1 つの試験の 1 つの組。module の頭で決まりを読む試験は、回す時に消した中身で module を読み直す。"""

    def __init__(self, mod, name, args, reload_mod):
        self.mod, self.name, self.args, self.reload = mod, name, args, reload_mod

    def 赤か(self):
        if self.reload:
            src = pathlib.Path(self.mod.__file__)
            code = compile(_open_real(src, encoding="utf-8").read(), str(src), "exec")
            saved = dict(vars(self.mod))
            try:
                exec(code, vars(self.mod))       # noqa: S102 — 消した中身で module の頭の定数を読み直す
                return _回す(vars(self.mod)[self.name], self.args)
            finally:
                vars(self.mod).clear()
                vars(self.mod).update(saved)
        return _回す(getattr(self.mod, self.name), self.args)


@functools.lru_cache(maxsize=1)
def _決まりの試験():
    """{決まりの file: その file を読む試験の並び}。読むかは 1 回回して見る。module の頭で読んだ file は、その module の
    回せる試験を全部、読み直す形で数える（どの試験が定数を使うかを字で見分けない）。"""
    readers = {r: [] for r in RULE_FILES}
    for p in sorted((ROOT / "tests").glob("test_*.py")):
        if p.name.startswith("test_rule_holes") or p.name in _回さない:   # 自分と、自分を読む試験は回さない
            continue
        spec = importlib.util.spec_from_file_location("_rule_holes_" + p.stem, p)
        m = importlib.util.module_from_spec(spec)
        src = _open_real(p, encoding="utf-8").read()
        head = set()
        with _口(log=head):
            spec.loader.exec_module(m)
        for name, f in sorted(vars(m).items()):
            if not (name.startswith("test_") and inspect.isfunction(f)) or f.__module__ != m.__name__:
                continue
            if not inspect.signature(f).parameters:
                cases = [{}]
            elif _名指す.search(src):
                cases = _組(f) or []
            else:
                cases = []
            for args in cases:
                read = set()
                t0 = time.monotonic()
                try:
                    with _口(log=read):
                        _回す(f, args, limit=_見分けの上限)   # 元から赤の試験は他の所で赤になる。ここは読むかだけを見る
                except _時間切れ:
                    continue                             # 重い試験は数えない（穴を多めに出す側）
                for r in RULE_FILES:
                    if r in read or r in head:
                        readers[r].append((time.monotonic() - t0, len(readers[r]), _試験(m, name, args, r in head)))
    return {r: [t for *_, t in sorted(v)] for r, v in readers.items()}   # 速い試験から回す＝守られた文は早く赤になる


def _赤(rel, text, cut):
    """cut の文を消した中身で、rel を読む試験のどれかが赤になるか。"""
    tests = _決まりの試験()[rel]          # 見分けは差し替えの外で先に済ませる（見分けの中で中身を差し替えない）
    with _口(swap={rel: _消す(text, cut)}):
        return any(t.赤か() for t in tests)


def 穴(rel, text=None, only=None, expect=frozenset()):
    """rel の文のうち、消しても決まりの試験がどれも赤にならない文の並び。text を渡せばその中身で見る（only は見る文を絞る）。
    expect（穴と見込む文）はまとめて消して 1 回で確かめ、赤なら半分ずつに割る（守られる文は 1 つずつ見る）。"""
    text = _open_real(ROOT / rel, encoding="utf-8").read() if text is None else text
    sents = [(i, s) for i, s in 文の並び(text) if only is None or s.strip() in only]
    holes = []

    def bisect(group):
        if not group:
            return
        if not _赤(rel, text, group):
            holes.extend(s.strip() for _, s in group)
        elif len(group) > 1:
            bisect(group[:len(group) // 2])
            bisect(group[len(group) // 2:])

    bisect([x for x in sents if x[1].strip() in expect])
    for x in sents:
        if x[1].strip() not in expect and not _赤(rel, text, [x]):
            holes.append(x[1].strip())
    return holes


def 表():
    """{(path, 文): 訳}。"""
    out = {}
    for ln in _open_real(TABLE, encoding="utf-8").read().splitlines():
        if ln.strip() and not ln.startswith("#"):
            rel, s, why = (ln.split("\t") + ["", ""])[:3]
            out[(rel, s)] = why
    return out


@functools.lru_cache(maxsize=1)
def 今の穴():
    t = 表()
    return {(rel, s) for rel in RULE_FILES for s in 穴(rel, expect=frozenset(s for r, s in t if r == rel))}


def test_核と細目の文は消すと試験が赤になるか_守らない文の表に在る():
    new = sorted(今の穴() - set(表()))
    assert not new, ("この文を消しても試験が赤にならない（文を照らす試験を足す。足せない訳がある時だけ "
                     "tests/data/試験で守らない文.txt に訳つきで載せる）:\n" + "\n".join(f"{r}\t{s}" for r, s in new))


def test_守らない文の表に古い行を残さない():
    stale = sorted(set(表()) - 今の穴())
    assert not stale, ("表の文が無くなったか、試験で守られるようになった（表から消す）:\n"
                       + "\n".join(f"{r}\t{s}" for r, s in stale))


def test_文を足しても照らす試験が無ければ穴に出て_照らした文を消せば赤():
    """注入の試験: 新しい決まりの文を足すと穴に出る。並走の文（PR #30 の穴の場所）は消すと試験が拒む。"""
    rel = "plugins/core/細目.md"
    text = _open_real(ROOT / rel, encoding="utf-8").read()
    added = text.replace("## 4. ", "- 作り物の新しい決まり。誰も照らしていない。\n\n## 4. ", 1)
    new = {"- 作り物の新しい決まり。", "誰も照らしていない。"}
    assert set(穴(rel, added, only=new)) == new
    assert set(穴(rel, added, only=new, expect=frozenset(new))) == new      # まとめて消す見方でも同じ
    # PR #30 の穴の並走は振る舞いの既定へ移った（PR #44）。今の並走の文は消すと赤になる
    walk = "- **並走** — 着手と言われたら確認させずに進め、5 分を超える作業は窓・助手を並べて同時に進める。"
    assert walk in _open_real(ROOT / "plugins/core/振る舞い.md", encoding="utf-8").read()
    assert 穴("plugins/core/振る舞い.md", only={walk}) == []
    assert 穴("plugins/core/振る舞い.md", only={walk}, expect=frozenset({walk})) == []   # 見込みが外れても割って確かめる
