"""決まりの文を 1 つ消しても試験が緑のままになる穴を、試験の側から照らす。

なぜ在るか: 決まりの試験が「語がどこかに在るか」の照らしで、照らしていない文（PR #30 の細目 §4 並走の
「挙がった物を全部やる時の分け方は、窓を並べて同時に進めるのが既定。」など）を消しても緑だった。
ここでは核と細目の文を 1 つずつ消し、決まりの試験（引数を取らない試験の関数）を回して、どれかが赤になるかを見る。

- 赤にならない文は、tests/data/試験で守らない文.txt に載せた物だけ（知らない穴＝新しく足した文・書き換えた文は赤）。
  新しい決まりの文を足したら、その文を照らす試験を同じ PR で足す（文をそのまま照らすのが一番強い）。
- 表の文が試験で守られるようになった・文が無くなった時は、表から消す（古い穴の行を残さない）。
"""
import functools
import importlib.util
import inspect
import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parent.parent
RULE_FILES = ["plugins/core/核.md", "plugins/core/振る舞い.md", "plugins/core/細目.md"]
TABLE = ROOT / "tests" / "data" / "試験で守らない文.txt"
_read = pathlib.Path.read_text


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


@functools.lru_cache(maxsize=1)
def _決まりの試験():
    """{決まりの file: その file を読む試験の関数の並び}。読むかは 1 回回して見る。"""
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
            if not (name.startswith("test_") and inspect.isfunction(f)) or inspect.signature(f).parameters:
                continue
            current.append(f)
            pathlib.Path.read_text = spy
            try:
                f()
            except BaseException:      # noqa: BLE001 — 元から赤の試験は他の所で赤になる。ここは読むかだけを見る
                pass
            finally:
                pathlib.Path.read_text = _read
    return readers


def 穴(rel, text=None, only=None):
    """rel の文のうち、消しても決まりの試験がどれも赤にならない文の並び。text を渡せばその中身で見る（only は見る文を絞る）。"""
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
        try:
            for f in funcs:
                try:
                    f()
                except BaseException:  # noqa: BLE001
                    caught = True
                    break
        finally:
            pathlib.Path.read_text = _read
        if not caught:
            holes.append(s.strip())
    return holes


def 表():
    out = set()
    for ln in _read(TABLE, encoding="utf-8").splitlines():
        if ln.strip() and not ln.startswith("#"):
            rel, s = ln.split("\t", 1)
            out.add((rel, s))
    return out


@functools.lru_cache(maxsize=1)
def 今の穴():
    return {(rel, s) for rel in RULE_FILES for s in 穴(rel)}


def test_核と細目の文は消すと試験が赤になるか_守らない文の表に在る():
    new = sorted(今の穴() - 表())
    assert not new, ("この文を消しても試験が赤にならない（文を照らす試験を足す。足せない訳がある時だけ "
                     "tests/data/試験で守らない文.txt に載せる）:\n" + "\n".join(f"{r}\t{s}" for r, s in new))


def test_守らない文の表に古い行を残さない():
    stale = sorted(表() - 今の穴())
    assert not stale, ("表の文が無くなったか、試験で守られるようになった（表から消す）:\n"
                       + "\n".join(f"{r}\t{s}" for r, s in stale))


def test_文を足しても照らす試験が無ければ穴に出て_照らした文を消せば赤():
    """注入の試験: 新しい決まりの文を足すと穴に出る。並走の文（PR #30 の穴の場所）は消すと試験が拒む。"""
    rel = "plugins/core/細目.md"
    text = _read(ROOT / rel, encoding="utf-8")
    added = text.replace("## 4. ", "- 作り物の新しい決まり。誰も照らしていない。\n\n## 4. ", 1)
    new = {"- 作り物の新しい決まり。", "誰も照らしていない。"}
    assert set(穴(rel, added, only=new)) == new
    # PR #30 の穴の並走は振る舞いの既定へ移った（PR #44）。今の並走の文は消すと赤になる
    walk = "- **並走** — 着手と言われたら確認させずに進め、5 分を超える作業は窓・助手を並べて同時に進める。"
    assert walk in _read(ROOT / "plugins/core/振る舞い.md", encoding="utf-8")
    assert 穴("plugins/core/振る舞い.md", only={walk}) == []
