"""開いている窓に届くのは急ぎの安全の直しだけ（区切って配る・2026-11-23 のオーナーの決定「窓では変えず急ぎだけ」）。

窓は立った時の版で続け、次に立つ窓が先端を取る。題の頭が「急ぎの安全:」の直しだけ、開いている窓へ先端の核を差し込み
守りの入れ直しを始める。印の無い直しを入れても開いている窓に届く形へ戻すと赤。
"""
from test_core_plugin import Foundation, _commit


def test_起動の後に急ぎの安全の直しが入ったら先端の核を差し込み窓はそのまま続ける(tmp_path):
    """注入: 窓が立った後に main へ急ぎの安全の直しを入れる → 次の問いで先端の核が差し込まれ、引き継ぎ・閉じは求めない。"""
    f = Foundation(tmp_path)
    f.install()
    assert "土台が古い" not in f.hook("inject")
    assert f.hook("fresh") == ""                         # まだ先端と同じ
    _commit(f.work, {"plugins/guard/x.py": "x\n", "plugins/core/核.md": "核 3\n"}, "急ぎの安全: 守りと核を変える")
    text = f.hook("fresh")
    assert "新しい核をここで読み" in text and "そのまま頼みを続ける" in text and "guard" in text
    assert "### main の先端の 核.md" in text and "核 3" in text and "- 急ぎの安全: 守りと核を変える" in text
    for old in ("create_session", "archive_session", "引き継いで閉じる"):
        assert old not in text, old
    assert f.hook("fresh") == ""                         # 同じ先端は 1 回だけ（問いのたびに繰り返さない）
    _commit(f.work, {"plugins/checker/y.py": "y\n"}, "急ぎの安全: また変える")
    assert f.hook("fresh") == ""                         # 核の本文が同じなら、plugin が動いても送り直さない
    _commit(f.work, {"plugins/core/核.md": "核 5\n"}, "急ぎの安全: 核をまた変える")
    again = f.hook("fresh")
    assert "核 5" in again and "核 3" not in again        # 核が変われば、変わった物だけをもう 1 度


def _with_entry(f):
    """目録の clone に入口 scripts/setup_plugins.py を置く（裏の入れ直しが始められる形）。"""
    f.installed = _commit(f.work, {"scripts/setup_plugins.py": "print('入れ直した')\n"}, "入口")


def _refreshed(f):
    """裏の入れ直しを始めた跡（錠か結果の記録）。"""
    d = f.home / ".claude" / "af-foundation"
    return (d / "refresh.lock").exists() or (d / "refresh.json").exists()


def test_急ぎの印の無い直しは開いている窓に届けず_核も守りも立った時の版のまま(tmp_path):
    """注入（2026-11-23 の誤りの類: main へ入るたびに全部の窓へ配る）: 印の無い直しを何本入れても、開いている窓には
    核を差し込まず、守りの入れ直しも始めない。次に立つ窓は先端の版で立つ。"""
    f = Foundation(tmp_path)
    _with_entry(f)
    f.install()
    f.hook("inject")
    for i in range(3):
        _commit(f.work, {"plugins/core/核.md": f"核 {i + 10}\n", f"plugins/guard/x{i}.py": "x\n"}, f"守りと核を変える {i}")
        assert f.hook("fresh") == "", i
    assert not _refreshed(f)
    again = f.hook("inject", source="compact")           # 圧縮の後も立った時の版の核のまま
    assert again.startswith("# 振る舞いの核") and "核 12" not in again
    g = Foundation.__new__(Foundation)                    # 次に立つ窓は、作り置きの箱でも起動の時に先端の版を取る
    g.tmp, g.remote, g.work, g.home, g.installed = f.tmp, f.remote, f.work, tmp_path / "home2", f.installed
    g.install(main_at_setup=f.installed)
    assert g.hook("inject", sid="s2").startswith("核 12") and _refreshed(g)


def test_急ぎの直しの後に印の無い直しが続いても届け_届けた後の印の無い直しは届けない(tmp_path):
    """注入: 先端の題だけを見る形（急ぎの直しの後に別の直しが入ると見落とす）・届けた急ぎを何度も届け直す形を戻すと赤。"""
    f = Foundation(tmp_path)
    _with_entry(f)
    f.install()
    f.hook("inject")
    _commit(f.work, {"plugins/guard/a.py": "a\n"}, "急ぎの安全: 秘密の見張りの穴を塞ぐ")
    _commit(f.work, {"plugins/checker/b.py": "b\n"}, "レビューの文を直す")
    _commit(f.work, {"docs/a.md": "3\n"}, "文書だけ")
    text = f.hook("fresh")
    assert "- 急ぎの安全: 秘密の見張りの穴を塞ぐ" in text and "レビューの文を直す" not in text
    assert _refreshed(f)
    _commit(f.work, {"plugins/core/核.md": "核 9\n"}, "核を変える")
    assert f.hook("fresh") == ""                         # 届けた後の印の無い直しは、次に立つ窓から


def test_急ぎの印は題の頭だけで_本文や途中の語では届けない(tmp_path):
    f = Foundation(tmp_path)
    f.install()
    f.hook("inject")
    _commit(f.work, {"plugins/guard/a.py": "a\n"}, "見張りを直す（急ぎの安全: ではない）")
    assert f.hook("fresh") == ""


def test_急ぎの印は全角のコロンでも届ける(tmp_path):
    """注入: 印を半角の「急ぎの安全:」だけにする形を戻すと赤（全角の「急ぎの安全：」も同じ印）。"""
    f = Foundation(tmp_path)
    _with_entry(f)
    f.install()
    f.hook("inject")
    _commit(f.work, {"plugins/guard/a.py": "a\n"}, "急ぎの安全：お金の守りの穴を塞ぐ")
    text = f.hook("fresh")
    assert "- 急ぎの安全：お金の守りの穴を塞ぐ" in text and _refreshed(f)


def _plugins_line(text):
    return next(line for line in text.splitlines() if "変わった plugin:" in line)


def test_2_回目の知らせは届けた後に変わった_plugin_だけを挙げる(tmp_path):
    """注入: 1 回目に guard の急ぎを届けた後、checker と核の急ぎを入れる → 2 回目の「変わった plugin」に guard を挙げない
    （変わった plugin を立った時の先端から数え、急ぎだけ最後に取った先端から数えると、届けた guard をまた挙げた）。"""
    f = Foundation(tmp_path)
    _with_entry(f)
    f.install()
    f.hook("inject")
    _commit(f.work, {"plugins/guard/a.py": "a\n", "plugins/core/核.md": "核 3\n"}, "急ぎの安全: 守りを塞ぐ")
    assert "guard" in _plugins_line(f.hook("fresh"))
    _commit(f.work, {"plugins/checker/b.py": "b\n", "plugins/core/核.md": "核 4\n"}, "急ぎの安全: 照らしを塞ぐ")
    line = _plugins_line(f.hook("fresh"))
    assert "checker" in line and "core" in line and "guard" not in line, line
