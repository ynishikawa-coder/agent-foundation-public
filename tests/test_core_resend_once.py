"""核と振る舞いの既定は、窓が読んだ本文から変わった物だけを 1 回送る（2026-11-22 のトークンの食い過ぎの誤りの類）。

plugin のどこかが main で動くたびに同じ核の全文を送り直すと、窓の文脈に同じ核が何枚も積もる。
"""
from test_core_plugin import PLUGIN, Foundation, _commit, _git


def test_核の本文が変わらない土台の変更では核を送り直さない(tmp_path):
    """注入（2026-11-22 の誤りの類）: 窓が読んだ核と同じ本文の先端を、plugin が動くたびに送り直す形を戻すと赤。
    守りだけの変更が何本 main へ入っても、核と振る舞いの既定の全文は文脈に 1 枚だけ。"""
    f = Foundation(tmp_path)
    _commit(f.work, {"plugins/core/核.md": (PLUGIN / "核.md").read_text(encoding="utf-8"),
                     "plugins/core/振る舞い.md": (PLUGIN / "振る舞い.md").read_text(encoding="utf-8")}, "本物の核")
    f.installed = _git(f.work, "rev-parse", "HEAD")
    f.install()
    f.hook("inject")
    for i in range(5):
        _commit(f.work, {f"plugins/guard/x{i}.py": "x\n"}, f"守りを変える {i}")
        assert f.hook("fresh") == "", i
    again = f.hook("inject", source="compact")
    assert again.count("# 振る舞いの核") == 1 and again.count("# 振る舞いの既定") == 1
