"""spec-doc の封の入口 seal.py が、15 §6 の決定照合が済んでいない設計書を gate へ渡さず止めるかを、作り物の設計書で見る。"""
import json
import subprocess
import sys
from pathlib import Path

import pytest

SEAL = (Path(__file__).resolve().parent.parent
        / "plugins" / "dev-flow" / "skills" / "spec-doc" / "seal.py")

HEAD = "# 15 台帳\n\n## §5 未確定\n\n- 作り物の未確定 1\n\n"
DONE_TABLE = (HEAD + "## §6 決定照合\n\n"
              "| 決定 | 照合 | 扱い |\n|---|---|---|\n"
              "| 作り物の決定 A | ぶつかる | 直した |\n"
              "| 作り物の決定 B | ぶつかる | 覆す＝墓標へ |\n"
              "| 作り物の決定 C | Claude が読む | 関係なし |\n"
              "\n## §7 更新ログ\n\n- 作り物の更新\n")


@pytest.fixture
def env(tmp_path):
    """作り物の repo（値の表と型の gate）と設計書の dir。gate は呼ばれたら印を書く。"""
    repo = tmp_path / "repo"
    tmpl = repo / "型"
    tmpl.mkdir(parents=True)
    (tmpl / "check_spec_doc.py").write_text(
        "import sys, pathlib\n"
        "pathlib.Path(sys.argv[1], 'gate_called').write_text(' '.join(sys.argv[2:]))\n"
        "sys.exit(0)\n", encoding="utf-8")
    (repo / "config").mkdir()
    write_values(repo, {"template_dir": "型"})
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    spec = tmp_path / "設計書"
    spec.mkdir()
    return repo, spec


def write_values(repo, vals):
    (repo / "config" / "skill-values.json").write_text(
        json.dumps({"dev-flow": {"spec-doc": vals}}), encoding="utf-8")


def seal(repo, spec, *args):
    return subprocess.run([sys.executable, "-B", str(SEAL), str(spec), *args],
                          cwd=repo, capture_output=True, text=True)


def put15(spec, text):
    (spec / "15_台帳.md").write_text(text, encoding="utf-8")


def test_照合が済んだ設計書は_gate_を_lock_で直に呼ぶ(env):
    repo, spec = env
    put15(spec, DONE_TABLE)
    res = seal(repo, spec)
    assert res.returncode == 0, res.stderr
    assert (spec / "gate_called").read_text() == "--lock"


def test_箇条で書いた照合も扱いがあれば通す(env):
    repo, spec = env
    put15(spec, HEAD + "### 6. 決定照合\n\n- 作り物の決定 A: ぶつかる → 直した\n- 作り物の決定 B: 関係なし\n")
    assert seal(repo, spec).returncode == 0


@pytest.mark.parametrize("label,text,why", [
    ("扱いの無い食い違い", DONE_TABLE.replace("| 直した |", "|  |"), "扱いが無い"),
    ("ぶつかるのまま（箇条）", HEAD + "## §6 決定照合\n\n- 作り物の決定 A: ぶつかる\n", "扱いが無い"),
    ("§6 が空", HEAD + "## §6 決定照合\n\n（まだ）\n\n## §7 更新ログ\n", "行が 1 つも無い"),
    ("§6 が無い", HEAD, "§6（決定照合）の節が無い"),
])
def test_照合が済んでいないと_gate_を呼ばずに止め直し方と外し方を出す(env, label, text, why):
    repo, spec = env
    put15(spec, text)
    res = seal(repo, spec)
    assert res.returncode == 1, label
    assert why in res.stderr, (label, res.stderr)
    assert "直し方" in res.stderr and "decision_match_allow" in res.stderr
    assert not (spec / "gate_called").exists(), label


def test_15_の台帳が無いと止める(env):
    repo, spec = env
    res = seal(repo, spec)
    assert res.returncode == 1 and "15 の台帳" in res.stderr


UNMATCHED = HEAD + "## §6 決定照合\n\n- 未照合（照合の口なし）\n"


def test_未照合は照合の口が無い_repo_では知らせて通す(env):
    repo, spec = env
    put15(spec, UNMATCHED)
    res = seal(repo, spec)
    assert res.returncode == 0, res.stderr
    assert "未照合" in res.stdout


def test_未照合は照合の口が在る_repo_では止める(env):
    repo, spec = env
    write_values(repo, {"template_dir": "型", "decision_match": ["作り物の照合の口を回す"]})
    put15(spec, UNMATCHED)
    res = seal(repo, spec)
    assert res.returncode == 1 and "未照合のまま" in res.stderr
    assert not (spec / "gate_called").exists()


def test_誤って止まる行は値の表で外せる(env):
    repo, spec = env
    put15(spec, HEAD + "## §6 決定照合\n\n- 作り物の決定 A: 作り物の書き方で済み\n")
    assert seal(repo, spec).returncode == 1
    write_values(repo, {"template_dir": "型", "decision_match_allow": ["作り物の書き方で済み"]})
    assert seal(repo, spec).returncode == 0


def test_型が無い_repo_では照合が済んでも_LOCK_しない(env):
    repo, spec = env
    write_values(repo, {})
    put15(spec, DONE_TABLE)
    res = seal(repo, spec)
    assert res.returncode == 3 and "LOCK しない" in res.stdout


def test_gate_の赤はそのまま返す(env):
    repo, spec = env
    (repo / "型" / "check_spec_doc.py").write_text("import sys\nsys.exit(2)\n", encoding="utf-8")
    put15(spec, DONE_TABLE)
    assert seal(repo, spec).returncode == 2
