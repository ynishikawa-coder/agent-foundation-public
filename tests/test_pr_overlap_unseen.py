"""scripts/pr_overlap.py: 見ていない時（材料が無い・他の PR を読めない）を、見て重なりが無い時と同じ緑（exit 0）にしないか。

止めない知らせの job なので赤にはしないが、見ていない時は exit 3 と GitHub の注記 ::warning:: で名指し、
ci.yml の job overlap はその step を continue-on-error で回す（step に外れの印が残る）。わざと見ない形を入れて確かめる注入の試験。
"""
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
TOOL = ROOT / "scripts" / "pr_overlap.py"
spec = importlib.util.spec_from_file_location("af_pr_overlap_unseen", TOOL)
po = importlib.util.module_from_spec(spec)
sys.dont_write_bytecode = True
spec.loader.exec_module(po)


def _run(args, env):
    return subprocess.run([sys.executable, "-B", str(TOOL), *args], capture_output=True, text=True,
                          env={"PATH": "/usr/bin:/bin", **env})


@pytest.mark.parametrize("args,env", [
    ([], {}),                                                   # 材料が何も無い
    (["--repo", "o/r", "--pr", "1"], {}),                       # 鍵が無い
    (["--repo", "o/r"], {"GITHUB_TOKEN": "x"}),                 # PR の番号が無い
])
def test_材料が無ければ_exit_3_で見ていないと言い_重なりが無いとは言わない(args, env):
    res = _run(args, env)
    assert res.returncode == 3, res.stdout + res.stderr
    assert "見ていない" in res.stdout and "重なる PR は無い" not in res.stdout


def test_他の_PR_を読めなければ_exit_3(monkeypatch, capsys):
    def boom(*_a, **_k):
        raise OSError("読めない作り物")
    monkeypatch.setattr(po, "_get", boom)
    monkeypatch.setenv("GITHUB_TOKEN", "x")
    monkeypatch.delenv("GITHUB_ACTIONS", raising=False)
    assert po.main(["--repo", "o/r", "--pr", "1"]) == 3
    out = capsys.readouterr().out
    assert "見ていない" in out and "読めない作り物" in out and "重なる PR は無い" not in out


def test_試験の口の材料が読めなくても_exit_3(tmp_path):
    res = _run(["--self", str(tmp_path / "無い.json"), "--others", str(tmp_path / "無い2.json")], {})
    assert res.returncode == 3 and "見ていない" in res.stdout


def test_GitHub_の上では見ていない事を注記_warning_で出す():
    res = _run([], {"GITHUB_ACTIONS": "true"})
    assert res.returncode == 3
    assert any(line.startswith("::warning") and "見ていない" in line for line in res.stdout.splitlines()), res.stdout


def test_見て重なりが無い時だけ_exit_0(tmp_path):
    a, b = tmp_path / "a.json", tmp_path / "b.json"
    a.write_text(json.dumps({"x.md": "@@ -1,1 +1,1 @@\n"}), encoding="utf-8")
    b.write_text(json.dumps({"#2": {"y.md": "@@ -1,1 +1,1 @@\n"}}), encoding="utf-8")
    res = _run(["--self", str(a), "--others", str(b)], {})
    assert res.returncode == 0 and "重なる PR は無い" in res.stdout


def test_ci_の_job_overlap_は止めずに見ていない印を残す形():
    yml = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    job = yml.split("\n  overlap:\n", 1)[1].split("\n  public-guard:", 1)[0]
    step = job.split("- name: 重なる PR を知らせる", 1)[1]
    assert "continue-on-error: true" in step
    # 終わり方を 0 に潰す形（|| true・; exit 0）を置かない＝見ていない 3 が step の外れの印に残る
    assert "|| true" not in step and "exit 0" not in step
