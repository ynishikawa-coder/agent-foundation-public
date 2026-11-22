"""決まりの文を 1 つ消しても試験が緑のままになる穴を、試験の側から照らす。

意図: 核と細目の決まりの文が、どれも消すと赤になる試験で照らされているようにする。
課題: 照らしていない文（PR #30 の細目 §4 並走の
「挙がった物を全部やる時の分け方は、窓を並べて同時に進めるのが既定。」など）を消しても緑だった。
原因: 決まりの試験が「語がどこかに在るか」の照らしだった。
ここでは核と細目の文を 1 つずつ消し、決まりの試験（引数を取らない試験の関数）を回して、どれかが赤になるかを見る。

- 赤にならない文は、tests/data/試験で守らない文/ に 1 件 1 file で載せた物だけ（知らない穴＝新しく足した文・書き換えた文は赤）。
  新しい決まりの文を足したら、その文を照らす試験を同じ PR で足す（文をそのまま照らすのが一番強い）。
- 表の文が試験で守られるようになった・文が無くなった時は、表から消す（古い穴の行を残さない）。
"""
import collections
import contextlib
import functools
import hashlib
import io
import importlib.util
import inspect
import pathlib
import re

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
# 細目は節ごとの file（plugins/core/細目/）。文は file ごとに消して回す。
RULE_FILES = ["plugins/core/核.md", "plugins/core/振る舞い.md",
              *sorted(p.relative_to(ROOT).as_posix() for p in (ROOT / "plugins" / "core" / "細目").glob("*.md"))]
# 1 件 1 file（名は中身の sha1 の頭 12 字）。全部の PR が 1 枚の末尾へ足すと互いに衝突するので、行を 1 file に集めない。
TABLE = ROOT / "tests" / "data" / "試験で守らない文"
_read = pathlib.Path.read_text
_rglob_real = pathlib.Path.rglob
_rglob_cache = {}


def _rglob(self, pattern, *a, **k):
    """文を消して回す間は file の並びが変わらない＝repo を歩くのは 1 度だけ（.git も歩く試験が多く、回すたびに歩くと遅い）。"""
    key = (str(self), pattern)
    if key not in _rglob_cache:
        _rglob_cache[key] = [q for q in _rglob_real(self, pattern, *a, **k) if ".git" not in q.parts]  # どの試験も .git は飛ばす
    return iter(_rglob_cache[key])


def 文の並び(text):
    """(行の番号, 文) の並び。文は「。」までの切れ目（「。」の無い行は行の全部）。空の行は数えない。"""
    out = []
    for i, ln in enumerate(text.splitlines()):
        for s in re.findall(r"[^。]*。|[^。]+$", ln):
            if s.strip():
                out.append((i, s))
    return out


def _消す(text, i, s):
    lines = text.splitlines(keepends=True)
    lines[i] = lines[i].replace(s, "", 1)
    return "".join(lines)


# 飛んだ・xfail は「赤になった」に数えない（試験が回っていない）。pytest.fail と普通の例外だけが赤。
_NOT_RUN = (pytest.skip.Exception, pytest.xfail.Exception)
_RED = (Exception, pytest.fail.Exception)
外れた = {}   # 決まりの試験の照らしから外れた試験 → 訳（tests/test_rule_holes_witness.py が名指しで照らす）


def _呼び方(f):
    """f を回す呼び方の並び（引数の組）。tmp_path・monkeypatch・capsys と parametrize の値だけを用意できる。用意できなければ None。"""
    names = list(inspect.signature(f).parameters)
    if not names:
        return [{}]
    params = [{}]
    for m in getattr(f, "pytestmark", []):
        if m.name != "parametrize":
            continue
        argnames = [x.strip() for x in m.args[0].split(",")] if isinstance(m.args[0], str) else list(m.args[0])
        rows = [v.values if hasattr(v, "values") else v for v in m.args[1]]
        rows = [dict(zip(argnames, r if len(argnames) > 1 else (r,))) for r in rows]
        params = [{**p, **r} for p in params for r in rows]
    left = [n for n in names if n not in params[0]]
    if any(n not in FIXTURES for n in left):
        return None
    return params


FIXTURES = ("tmp_path", "monkeypatch", "capsys")


class _Capsys:
    """capsys の代わり（readouterr() が前に読んだ後の出力を返す）。"""
    def __init__(self):
        self.out, self.err = io.StringIO(), io.StringIO()

    def readouterr(self):
        o, e = self.out.getvalue(), self.err.getvalue()
        self.out.seek(0), self.out.truncate(), self.err.seek(0), self.err.truncate()
        return collections.namedtuple("CaptureResult", "out err")(o, e)


def _回す(f, args):
    """f を args と、要る fixture（tmp_path・monkeypatch・capsys）で 1 回回す。"""
    import tempfile
    names = inspect.signature(f).parameters
    cap = _Capsys()
    with tempfile.TemporaryDirectory() as d, pytest.MonkeyPatch.context() as mp, \
            contextlib.redirect_stdout(cap.out), contextlib.redirect_stderr(cap.err):
        kw = dict(args)
        if "tmp_path" in names:
            kw["tmp_path"] = pathlib.Path(d)
        if "monkeypatch" in names:
            kw["monkeypatch"] = mp
        if "capsys" in names:
            kw["capsys"] = cap
        f(**kw)


@functools.lru_cache(maxsize=1)
def _決まりの試験():
    """{決まりの file: その file を読む試験の (関数, 引数) の並び}。読むかは 1 回回して見る。
    元の文で通らない試験（元から赤・飛んだ・xfail）は、文を消した回の赤と区別できないので照らしに使わず 外れた に名を残す。"""
    targets = {(ROOT / r).resolve(): r for r in RULE_FILES}
    readers = {r: [] for r in RULE_FILES}
    current = []

    def spy(self, *a, **k):
        r = targets.get(pathlib.Path(self).resolve())
        if r and current and current[-1] not in readers[r]:
            readers[r].append(current[-1])
        return _read(self, *a, **k)

    for p in sorted((ROOT / "tests").glob("test_*.py")):
        if p.name == pathlib.Path(__file__).name:
            continue
        spec = importlib.util.spec_from_file_location("_rule_holes_" + p.stem, p)
        m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(m)
        for name, f in sorted(vars(m).items()):
            if not (name.startswith("test_") and inspect.isfunction(f)):
                continue
            calls = _呼び方(f)
            if calls is None:
                外れた[f"{p.name}::{name}"] = "用意できない fixture を取る"
                continue
            for args in calls:
                current.append((f, args))
                pathlib.Path.read_text = spy
                try:
                    _回す(f, args)
                except _NOT_RUN:
                    外れた[f"{p.name}::{name}"] = "元の文で飛んだ・xfail"
                except _RED:
                    外れた[f"{p.name}::{name}"] = "元の文で赤"
                finally:
                    pathlib.Path.read_text = _read
    return {r: [x for x in fs if f"{x[0].__module__[len('_rule_holes_'):]}.py::{x[0].__name__}" not in 外れた]
            for r, fs in readers.items()}


def 穴(rel, text=None, only=None):
    """rel の文のうち、消しても決まりの試験がどれも赤にならない文の並び。text を渡せばその中身で見る（only は見る文を絞る）。
    文を消した回で決まりの試験が飛んだ・xfail になった時は、赤に数えず止める（回っていない試験を赤と言わない）。"""
    path = (ROOT / rel).resolve()
    text = _read(path, encoding="utf-8") if text is None else text
    funcs = _決まりの試験()[rel]
    _中身 = {}
    holes = []
    for i, s in 文の並び(text):
        if only is not None and s.strip() not in only:
            continue
        mutated = _消す(text, i, s)

        def fake(self, *a, **k):
            key = str(self)
            if key not in _中身:                      # 他の file は回の間で変わらない＝1 度だけ読む
                _中身[key] = (pathlib.Path(self).resolve() == path, _read(self, *a, **k))
            same, body = _中身[key]
            return mutated if same else body

        caught = False
        pathlib.Path.read_text = fake
        pathlib.Path.rglob = _rglob
        try:
            for f, args in funcs:
                try:
                    _回す(f, args)
                except _NOT_RUN as e:
                    raise AssertionError(f"{f.__name__} が文「{s.strip()}」を消した回で飛んだ（赤と数えない）: {e}") from None
                except _RED:
                    caught = True
                    break
        finally:
            pathlib.Path.read_text = _read
            pathlib.Path.rglob = _rglob_real
        if not caught:
            holes.append(s.strip())
    return holes


def 表の名(rel, s):
    """表の 1 件の file の名（中身 `<path><TAB><文>` の sha1 の頭 12 字）。"""
    return hashlib.sha1(f"{rel}\t{s}".encode("utf-8")).hexdigest()[:12] + ".txt"


def 表(table=None):
    out = set()
    for p in sorted((table or TABLE).glob("*.txt")):
        rel, s = _read(p, encoding="utf-8").rstrip("\n").split("\t", 1)
        out.add((rel, s))
    return out



# 決まりの file ごとに 1 本（1 本が長い＝check_all が組へ 1 本ずつ散らす。重さは他の試験 1 本の何本分か）
AF_SHARD_WEIGHT = 200


@pytest.mark.parametrize("rel", RULE_FILES)
def test_核と細目の文は消すと試験が赤になるか_守らない文の表に在る(rel):
    """rel の文を 1 つずつ消して、赤にならない文が表に在るか。表の rel の行が古くないか（守られた・無くなった文は表から消す）も同じ回で見る。"""
    now = set(穴(rel))
    listed = {s for r, s in 表() if r == rel}
    new, stale = sorted(now - listed), sorted(listed - now)
    assert not new, ("この文を消しても試験が赤にならない（文を照らす試験を足す。足せない訳がある時だけ "
                     "tests/data/試験で守らない文/ に 1 件 1 file で載せる・名は 表の名）:\n" + "\n".join(f"{rel}\t{s}" for s in new)
                     + "\n照らしから外れた試験（元の文で通らない・用意できない fixture）:\n"
                     + "\n".join(f"{k}: {v}" for k, v in sorted(外れた.items())))
    assert not stale, ("表の文が無くなったか、試験で守られるようになった（表から消す）:\n"
                       + "\n".join(f"{rel}\t{s}" for s in stale))


def test_守らない文の表に決まりの_file_の外の行を残さない():
    stale = sorted((r, s) for r, s in 表() if r not in RULE_FILES)
    assert not stale, ("表の行の file が決まりの file に無い（file が無くなった・名が変わった。表から消す）:\n"
                       + "\n".join(f"{r}\t{s}" for r, s in stale))


def test_文を足しても照らす試験が無ければ穴に出て_照らした文を消せば赤():
    """注入の試験: 新しい決まりの文を足すと穴に出る。並走の文（PR #30 の穴の場所）は消すと試験が拒む。"""
    rel = "plugins/core/細目/04-聞き方.md"
    text = _read(ROOT / rel, encoding="utf-8")
    added = text.replace("## 4. ", "- 作り物の新しい決まり。誰も照らしていない。\n\n## 4. ", 1)
    new = {"- 作り物の新しい決まり。", "誰も照らしていない。"}
    assert set(穴(rel, added, only=new)) == new
    # PR #30 の穴の並走は振る舞いの既定へ移った（PR #44）。今の並走の文は消すと赤になる
    walk = "- **並走** — 着手と言われたら確認させずに進め、5 分を超える作業は窓・助手を並べて同時に進める。"
    assert walk in _read(ROOT / "plugins/core/振る舞い.md", encoding="utf-8")
    assert 穴("plugins/core/振る舞い.md", only={walk}) == []
