"""土台の入口（scripts/setup_plugins.py）の約束: 照らせない時（欠けた材料）は黙って緑にせず、名指しして止める。

照らせない形は 3 つ: 目録の写しを main の先端へ進められない（marketplace update の失敗）・目録の写しの先端の commit が
引けない・入った commit の台帳（installed_plugins.json）が読めない。どれも古い版のまま「揃った」と見えるので、
~/.claude/CLAUDE.md に名指しして exit 1。手元の dir から足した試し（目録の台帳の source が directory）だけは照らさない。
"""
import importlib.util
import json
from pathlib import Path

spec = importlib.util.spec_from_file_location("tsp", Path(__file__).with_name("test_setup_plugins.py"))
tsp = importlib.util.module_from_spec(spec)
spec.loader.exec_module(tsp)


def test_目録の写しを進められなければ名指しして止める(tmp_path):
    root, head = tsp.git_foundation(tmp_path, ["core"])
    r, _, note, home = tsp.run(tmp_path, root, source="github", FAKE_HEAD=head, FAKE_UPDATE_FAIL="1")
    assert r.returncode == 1, r.stdout
    assert "照らせない: 目録の写しを main の先端へ進められなかった" in note
    assert json.loads((home / ".claude" / "af-foundation" / "setup.json").read_text(encoding="utf-8"))["blind"]


def test_目録の写しの先端が引けなければ名指しして止める(tmp_path):
    root = tsp.foundation(tmp_path, ["core"])   # git でない写し
    r, _, note, _ = tsp.run(tmp_path, root, source="github")
    assert r.returncode == 1 and "先端の commit が引けない" in note, r.stdout


def test_目録の台帳が無ければ試しと見ず照らす側に倒す(tmp_path):
    root = tsp.foundation(tmp_path, ["core"])
    r, _, note, _ = tsp.run(tmp_path, root, source=None)
    assert r.returncode == 1 and "先端の commit が引けない" in note, r.stdout


def test_入った_commit_の台帳が読めなければ名指しして止める(tmp_path):
    root, head = tsp.git_foundation(tmp_path, ["core"])
    pj = tmp_path / "home" / ".claude" / "plugins" / "installed_plugins.json"
    pj.parent.mkdir(parents=True)
    pj.write_text("{", encoding="utf-8")   # 作り物の claude は FAKE_HEAD が無いと台帳に触れない
    r, _, note, _ = tsp.run(tmp_path, root, source="github")
    assert r.returncode == 1 and "installed_plugins.json）が読めない" in note, r.stdout


def test_手元の_dir_から足した試しは照らさず緑(tmp_path):
    root = tsp.foundation(tmp_path, ["core"])
    r, _, note, _ = tsp.run(tmp_path, root, source="directory")
    assert r.returncode == 0 and "照らせない" not in note, r.stdout
