"""GitHub の手は AI が打つ（オーナーの指摘 2026-11-19: 合流や守りの設定がオーナーの手に回っていた）。"""
import importlib.util
import json
import pathlib
import subprocess

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]


def _read(rel):
    return (ROOT / rel).read_text(encoding="utf-8")


def test_付いていないrepoはpushで付けて打ち_拒まれた時だけ原文を添えて人へ回す():
    t = _read("plugins/core/細目.md")
    assert "repo が付いていなければ `add_repo`（push）で付けて打ち" in t
    assert "打って拒まれた時だけ拒みの原文を添えて人へ回す。" in t


def test_守りの設定は正本のfileをPRで直しCIが書き戻す():
    t = _read("CONTRIBUTING.md")
    assert "正本は `.github/rulesets/main.json`。直す時は AI がこの file を PR で直し" in t
    assert "鍵 `RULESET_TOKEN` が無い時は書き戻しが赤で止まる" in t


def test_守りの正本の必須の検査は重複なく今の3つ():
    d = json.loads(_read(".github/rulesets/main.json"))
    checks = [c["context"] for r in d["rules"] if r["type"] == "required_status_checks"
              for c in r["parameters"]["required_status_checks"]]
    assert len(checks) == len(set(checks)), f"必須の検査が重なっている: {checks}"
    assert set(checks) == {"check", "public-guard", "plugin-smoke"}


def test_書き戻しは鍵が無いと止まりPRでは回らない(monkeypatch):
    monkeypatch.delenv("GH_TOKEN", raising=False)
    assert _apply().main() == 1
    t = _read(".github/workflows/rulesets.yml")
    assert "python3 scripts/ruleset_apply.py" in t
    assert "pull_request" not in t


def test_AIの道具で打てる手は自分で打ち_人にしか打てない手だけ手の窓で頼む():
    t = _read("plugins/core/細目.md")
    assert "push・PR・合流・調べる・見張る・Notion や Drive への書き込み）は自分で打つ。" in t
    assert "人にしか打てない手（許し・アカウントと支払い・PC やスマホにしか無い物・社外への go・他社のオーナーへの連絡）だけ" in t


def test_鍵はmainだけのenvironmentから読み_手動でも回らない():
    t = _read(".github/workflows/rulesets.yml")
    assert "environment: rulesets" in t
    assert "workflow_dispatch" not in t
    c = _read("CONTRIBUTING.md")
    assert "鍵は environment `rulesets` の秘密に置く" in c
    assert "Deployment branches を「Selected branches and tags」にして `main` だけを足し" in c


def _apply():
    spec = importlib.util.spec_from_file_location("ruleset_apply", ROOT / "scripts/ruleset_apply.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


MAIN_ONLY = ({"deployment_branch_policy": {"protected_branches": False, "custom_branch_policies": True}},
             {"branch_policies": [{"name": "main", "type": "branch"}]})


def test_枝の制限がmainだけなら通る():
    assert _apply().env_problem(*MAIN_ONLY) is None


@pytest.mark.parametrize("env,pol", [
    ({"deployment_branch_policy": None}, None),                                            # 名を指して自動で作られた（制限なし）
    ({"deployment_branch_policy": {"protected_branches": True, "custom_branch_policies": False}}, None),
    (MAIN_ONLY[0], {"branch_policies": []}),
    (MAIN_ONLY[0], {"branch_policies": [{"name": "main", "type": "branch"}, {"name": "claude/*", "type": "branch"}]}),
    (MAIN_ONLY[0], {"branch_policies": [{"name": "*", "type": "branch"}]}),
    (MAIN_ONLY[0], {"branch_policies": [{"name": "main", "type": "tag"}]}),
])
def test_枝の制限がmainだけでなければ書かずに止まる(env, pol):
    assert _apply().env_problem(env, pol)


def _fake_gh(env, pol, calls):
    def gh(*args, stdin=None):
        calls.append(args)
        if args[-1].endswith("/environments/rulesets"):
            return env
        if args[-1].endswith("/deployment-branch-policies"):
            return pol
        raise AssertionError(f"書いてはいけない所で書いた: {args}")
    return gh


def test_制限の無い返りでは守りへ書かずに赤(monkeypatch):
    m = _apply()
    calls = []
    monkeypatch.setenv("GH_TOKEN", "x")
    monkeypatch.setenv("GITHUB_REPOSITORY", "o/r")
    monkeypatch.setenv("RULESET_ID", "1")
    monkeypatch.setattr(m, "gh", _fake_gh({"deployment_branch_policy": None}, {"branch_policies": []}, calls))
    assert m.main() == 1
    assert not any("PUT" in a for a in calls)


def test_枝の制限が読めない時も書かずに赤(monkeypatch):
    m = _apply()
    monkeypatch.setenv("GH_TOKEN", "x")
    monkeypatch.setenv("GITHUB_REPOSITORY", "o/r")
    monkeypatch.setenv("RULESET_ID", "1")

    def boom(*a, **k):
        raise subprocess.CalledProcessError(1, "gh", stderr="Not Found")
    monkeypatch.setattr(m, "gh", boom)
    assert m.main() == 1


def test_書き戻した後に正本と違えば赤():
    m = _apply()
    want = {"name": "main", "rules": [1]}
    assert m.diff(want, {"name": "main", "rules": [1], "id": 9}) == []
    assert m.diff(want, {"name": "main", "rules": []}) == ["rules"]


def _check_all_の最後の行(tmp_path, dirty):
    """check_all.sh を tmp の repo に写し、検査の中身は空にして最後の行だけを見る。"""
    (tmp_path / "scripts").mkdir()
    (tmp_path / "tests").mkdir()
    (tmp_path / "scripts/check_all.sh").write_text(_read("scripts/check_all.sh"), encoding="utf-8")
    (tmp_path / "tests/test_ok.py").write_text("def test_ok():\n    pass\n", encoding="utf-8")
    g = lambda *a: subprocess.run(["git", *a], cwd=tmp_path, check=True, capture_output=True)
    g("init", "-q")
    g("add", "-A")
    g("-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "t")
    if dirty:
        (tmp_path / "tests/test_new.py").write_text("def test_new():\n    pass\n", encoding="utf-8")
    out = subprocess.run(["bash", "scripts/check_all.sh"], cwd=tmp_path, capture_output=True, text=True)
    head = subprocess.run(["git", "rev-parse", "--short=12", "HEAD"], cwd=tmp_path, capture_output=True, text=True).stdout.strip()
    return out.stdout.strip().splitlines()[-1], head


def test_check_allの結果は回した先端を添える(tmp_path):
    last, head = _check_all_の最後の行(tmp_path, dirty=False)
    assert last.startswith("check_all: 緑") and last.endswith(f"@{head}")


def test_git_に無いfileがあると未commitの印が付く(tmp_path):
    last, head = _check_all_の最後の行(tmp_path, dirty=True)
    assert f"@{head}+未 commit" in last
