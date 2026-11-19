"""土台の入口（scripts/setup_plugins.py）の約束: 作り置きの容器に前の setup の古い版が残っても、目録の写しを main の先端へ進め、
入った commit を先端と照らして入れ直す（入れ直しても揃わなければ名指し）。作り物の claude は test_setup_plugins.py の物を使う。
"""
import importlib.util
import json
import os
import subprocess
from pathlib import Path

spec = importlib.util.spec_from_file_location("tsp", Path(__file__).with_name("test_setup_plugins.py"))
tsp = importlib.util.module_from_spec(spec)
spec.loader.exec_module(tsp)
foundation, run = tsp.foundation, tsp.run


def git_foundation(tmp_path, names):
    """git の checkout の作り物の目録（先端の commit が引ける）。(root, 先端の commit)。"""
    root = foundation(tmp_path, names)
    env = dict(os.environ, GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@t", GIT_COMMITTER_NAME="t", GIT_COMMITTER_EMAIL="t@t")
    for c in (["init", "-q"], ["add", "-A"], ["commit", "-q", "-m", "c"]):
        subprocess.run(["git", "-C", str(root), *c], check=True, env=env, capture_output=True)
    head = subprocess.run(["git", "-C", str(root), "rev-parse", "HEAD"], check=True, capture_output=True,
                          text=True).stdout.strip()
    return root, head


def old_container(tmp_path, names, old="0" * 40):
    """作り置きの容器: 前の setup で古い commit が入った台帳を置いた HOME。"""
    pj = tmp_path / "home" / ".claude" / "plugins" / "installed_plugins.json"
    pj.parent.mkdir(parents=True)
    pj.write_text(json.dumps({"plugins": {f"{n}@agent-foundation": [{"scope": "user", "gitCommitSha": old}]
                                          for n in names}}), encoding="utf-8")
    return pj


def test_合格_古い版が残った容器でも目録を進め_入った_commit_を先端に入れ直す(tmp_path):
    """注入: 前の setup の古い commit が入り、update が動かない（作り置きの容器）→ 入口が先端に入れ替える。"""
    root, head = git_foundation(tmp_path, ["core", "guard"])
    pj = old_container(tmp_path, ["core", "guard"])
    r, log, note, home = run(tmp_path, root, source="github", FAKE_HEAD=head, FAKE_STUCK="1", FAKE_OLD="0" * 40)
    assert r.returncode == 0, r.stdout
    lines = log.splitlines()
    assert lines[0] == "plugin marketplace update agent-foundation"   # 何より先に目録の写しを進める
    assert "plugin uninstall core@agent-foundation --scope user" in lines
    got = json.loads(pj.read_text(encoding="utf-8"))["plugins"]
    assert {k: v[0]["gitCommitSha"] for k, v in got.items()} == {"core@agent-foundation": head, "guard@agent-foundation": head}
    state = json.loads((home / ".claude" / "af-foundation" / "setup.json").read_text(encoding="utf-8"))
    assert state["commit"] == head and state["stale"] == [] and "af-plugin-missing" not in note


def test_入れ直しても先端に揃わない_plugin_は名指しで知らせる(tmp_path):
    root, head = git_foundation(tmp_path, ["core", "guard"])
    old_container(tmp_path, ["core", "guard"])
    r, _, note, _ = run(tmp_path, root, source="github", FAKE_HEAD=head, FAKE_STUCK="1", FAKE_OLD="0" * 40, FAKE_PIN="guard")
    assert r.returncode == 1
    assert f"目録の先端（{head[:12]}）に揃わない: guard" in note and "core" not in note.split("揃わない:")[1]


def test_入った_commit_を照らす段を外すと古い版のまま緑になる(tmp_path):
    """誤りの類の注入: 入っているかだけを見る前の形（照らしの段を外した入口）は古い版のまま 0 で抜ける＝上の試験が拾う故障。"""
    root, head = git_foundation(tmp_path, ["core"])
    src = (root / "scripts" / "setup_plugins.py").read_text(encoding="utf-8")
    cut = src.replace("    return [n for n in names if f\"{n}@{market}\" in got and got[f\"{n}@{market}\"] != head]\n",
                      "    return []\n")
    assert cut != src, "照らしの段の形が変わった（注入の置き換えを合わせる）"
    (root / "scripts" / "setup_plugins.py").write_text(cut, encoding="utf-8")
    pj = old_container(tmp_path, ["core"])
    r, _, _, _ = run(tmp_path, root, source="github", FAKE_HEAD=head, FAKE_STUCK="1", FAKE_OLD="0" * 40)
    assert r.returncode == 0
    assert json.loads(pj.read_text(encoding="utf-8"))["plugins"]["core@agent-foundation"][0]["gitCommitSha"] == "0" * 40
