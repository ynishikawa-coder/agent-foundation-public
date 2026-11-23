"""作り置きの箱で立つ窓の起動の判定（原因の台帳の束 F-setup）。

setup は箱を作る時に走り、窓は何時間も後にその箱を使う（2026-11-20 実測 7 時間）。
- setup の後に main が進んだだけの窓に setup script を直させない（先端の核を差し込むだけ・窓は引き継がない）。
  問いの時は窓が立った後に急ぎの安全の直し（題の頭が「急ぎの安全:」）が入った時だけ、先端の核をもう 1 度差し込む。
- 起動の時に使う側の hook が入口を回し直し、setup.json と台帳が新しい版を指しても、今動いている版の記録で決める。
"""
import json
from pathlib import Path

from test_core_plugin import Foundation, _commit, kaku
from test_stale_compare_rest import _home

SETUP_FIX = "update_environment"


def test_setup_の後に_main_が進んだだけの窓に_setup_script_を直せと言わず先端の核だけ差し込む(tmp_path):
    """注入 (a): setup は main の先端を入れた（記録＝入った commit）→ 窓が立つ前に main で plugin が変わる（作り置きの箱）
    → 起動の知らせは「setup script を直せ」を出さず、先端の核を差し込む。立った後に main が plugin を変えた時は、
    その plugin の名で先端の核をもう 1 度差し込む（どちらも窓は引き継がず続ける）。"""
    f = Foundation(tmp_path)
    f.install(main_at_setup=f.installed)
    _commit(f.work, {"plugins/guard/x.py": "x\n"}, "setup の後・窓が立つ前に守りを変える")
    text = f.hook("inject")
    assert "土台が古いまま立った窓" not in text and SETUP_FIX not in text, text
    assert text.startswith("核 1") and "# 振る舞いの核" not in text   # 先端の核を 1 枚だけ（入っている古い核と並べない）
    assert "setup の後に main が進んでいた" in text
    assert f.hook("fresh") == ""                            # 起動の時に差し込んだ先端は繰り返さない
    assert "土台が古いまま立った窓" not in f.hook("inject", source="compact")
    _commit(f.work, {"plugins/checker/y.py": "y\n"}, "窓が立った後に checker を変える")
    assert f.hook("fresh") == ""                            # 核の本文が同じなら送り直さない
    _commit(f.work, {"plugins/checker/y.py": "y2\n", "plugins/core/核.md": "核 2\n"}, "急ぎの安全: checker と核を変える")
    told = f.hook("fresh")
    assert "新しい核をここで読み" in told and "核 2" in told and "checker" in told and SETUP_FIX not in told
    assert "create_session で" not in told and "引き継いで閉じる" not in told
    assert "guard" not in told                              # 立つ前の進みは数えない
    assert f.hook("fresh") == ""                            # 1 回だけ


def test_注入_作り置きの箱から立つ窓は次の窓も引き継がず輪にならない(tmp_path):
    """注入: 同じ作り置きの箱（同じ setup の記録と入った版）から次々に窓が立つ → どの窓も引き継げと言われない
    （前の形は立つたびに引き継がせ、引き継いだ窓もまた古いので輪になった）。"""
    f = Foundation(tmp_path)
    f.install(main_at_setup=f.installed)
    _commit(f.work, {"plugins/guard/x.py": "x\n"}, "setup の後に守りを変える")
    for sid in ("窓1", "引き継いだ窓2", "引き継いだ窓3"):
        assert "土台が古いまま立った窓" not in f.hook("inject", sid=sid)
        assert f.hook("fresh", sid=sid) == "", sid


def test_注入_起動の口が並んで入口を回し直しても今動いている版の記録で訳を決める(tmp_path, monkeypatch):
    """注入: 窓の起動の時に使う側の hook が入口を回し直し、setup.json を新しい版の記録に書き換えた（並んで走る）
    → 今動いている版の記録（setup-<版>.json）で決める。前の形は「前の setup の記録が残っている＝setup script が古い形」
    と誤って知らせ、訳も「分からない」にした。"""
    home = _home(tmp_path, rec_sha="c" * 40, main_at="c" * 40)    # setup.json は別の版（回し直した後）の記録
    monkeypatch.setenv("HOME", str(home))
    sha = kaku.installed_sha()                                      # 今動いている版
    assert kaku.setup_record()[0] is None                           # 前の形（setup.json だけ）では読めない
    d = home / ".claude" / "af-foundation"
    (d / f"setup-{sha}.json").write_text(json.dumps(
        {"entry": "scripts/setup_plugins.py", "catalog_sha": sha, "main_at_setup": sha, "at": "2026-11-19T20:57:09+0900",
         "refreshed": True, "stale": []}), encoding="utf-8")
    assert kaku.setup_record()[0]["catalog_sha"] == sha
    assert kaku.start_cause({"plugins": ["guard"], "installed": sha}) == "after"
    assert "setup script が古い形" not in (kaku.setup_text() or "")


def test_注入_台帳が新しい版の_dir_を指しても動いている_dir_の名と記録で入った版を引く(tmp_path, monkeypatch):
    """注入: 起動の口の入れ直しで台帳の core の行が新しい版の dir を指した → 今動いている dir の名（commit の頭 12 字）と
    版ごとの記録で入った版を引く（前の形は「入った版が分からない・setup script を直す」と誤って知らせた）。"""
    sha = "b" * 40
    home = _home(tmp_path, main_at=sha)
    d = home / ".claude" / "af-foundation"
    (d / f"setup-{sha}.json").write_text(json.dumps({"catalog_sha": sha, "main_at_setup": sha}), encoding="utf-8")
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setattr(kaku, "PLUGIN", tmp_path / "cache" / "agent-foundation" / "core" / sha[:12])
    assert kaku.installed_sha() == sha
    (d / f"setup-{sha[:12]}{'e' * 28}.json").write_text(json.dumps({"catalog_sha": sha[:12] + "e" * 28}), encoding="utf-8")
    assert kaku.installed_sha() is None                             # 1 つに決まらなければ分からない
    monkeypatch.setattr(kaku, "PLUGIN", tmp_path / "plugins" / "core")
    assert kaku.installed_sha() is None                             # dir の名が commit の頭でなければ引かない


def test_入口は版ごとの記録も残す(tmp_path, monkeypatch):
    import importlib.util
    spec = importlib.util.spec_from_file_location("setup_plugins_t", Path(__file__).resolve().parent.parent / "scripts" / "setup_plugins.py")
    sp = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(sp)
    monkeypatch.setenv("HOME", str(tmp_path))
    sp.save_state({"catalog_sha": "a" * 40, "main_at_setup": "a" * 40})
    d = tmp_path / ".claude" / "af-foundation"
    assert json.loads((d / ("setup-" + "a" * 40 + ".json")).read_text())["catalog_sha"] == "a" * 40
    assert (d / "setup.json").is_file()


def _own_record(home, sha, at="2026-11-19T20:57:09+0900"):
    (home / ".claude" / "af-foundation" / f"setup-{sha}.json").write_text(json.dumps(
        {"entry": "scripts/setup_plugins.py", "catalog_sha": sha, "main_at_setup": sha, "at": at,
         "refreshed": True, "stale": []}), encoding="utf-8")


def _rows(home, update):
    pj = home / ".claude" / "plugins" / "installed_plugins.json"
    table = json.loads(pj.read_text(encoding="utf-8"))
    for name, rows in table["plugins"].items():
        for r in rows:
            update(name, r)
    pj.write_text(json.dumps(table), encoding="utf-8")


def test_注入_版ごとの記録の後に入口を通らず同じ版を入れ直した箱は記録を読まない(tmp_path, monkeypatch):
    """注入: 版ごとの記録が在っても、今動いている版の行が記録の時より後に入れ直されていれば（入口を通らない古い形の
    setup script）、その記録で after と決めず、分からない・setup script が古い形と名指す（setup.json と同じ照らし）。"""
    home = _home(tmp_path, rec_sha="c" * 40, main_at="c" * 40)
    monkeypatch.setenv("HOME", str(home))
    sha = kaku.installed_sha()
    _own_record(home, sha)
    _rows(home, lambda n, r: r.update(lastUpdated="2026-11-19T13:00:00.000Z"))   # 記録（11:57Z）の後に入れ直した
    rec, why = kaku.setup_record()
    assert rec is None and "入れ直した" in why
    assert kaku.start_cause({"plugins": ["guard"], "installed": sha}) == "unknown"
    assert "setup script が古い形" in (kaku.setup_text() or "")


def test_並んだ入れ直しが別の版の行を後で書いても今動いている版の記録を読む(tmp_path, monkeypatch):
    """起動の口の入れ直しは別の版（新しい先端）の行を記録の後に書く。今動いている版の行は変わっていないので記録を読む。"""
    home = _home(tmp_path, rec_sha="c" * 40, main_at="c" * 40)
    monkeypatch.setenv("HOME", str(home))
    sha = kaku.installed_sha()
    _own_record(home, sha)
    _rows(home, lambda n, r: n != "core@agent-foundation" and r.update(gitCommitSha="c" * 40,
                                                                    lastUpdated="2026-11-19T13:00:00.000Z"))
    assert kaku.setup_record()[0]["catalog_sha"] == sha


def test_立った後に古くなった窓は圧縮の後も先端の核をもう一度差し込む(tmp_path):
    f = Foundation(tmp_path)
    f.install(main_at_setup=f.installed)
    f.hook("inject")
    _commit(f.work, {"plugins/guard/x.py": "x\n", "plugins/core/核.md": "核 2\n"}, "急ぎの安全: 立った後に守りと核を変える")
    assert "新しい核をここで読み" in f.hook("fresh")
    again = f.hook("inject", source="compact")
    assert "土台が古いまま立った窓" not in again and "起動の後に新しくなっている" in again
    assert again.startswith("核 2") and "# 振る舞いの核" not in again
    assert f.hook("fresh") == ""                            # 同じ先端は繰り返さない
