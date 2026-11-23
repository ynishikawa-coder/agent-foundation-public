"""seal が設計書の在る repo の値の表と型で照らし、窓が立つ所の repo の物では照らさないか（注入の試験）。"""
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_dev_flow_spec_seal import DONE_TABLE, HEAD, env, put15, seal, write_values  # noqa: E402,F401


def _loose_repo(tmp_path):
    """窓が立つ所の作り物の repo: いつも通す gate と、照合を外す値を持つ（設計書の repo の決まりより緩い）。"""
    loose = tmp_path / "loose"
    (loose / "型").mkdir(parents=True)
    (loose / "型" / "check_spec_doc.py").write_text(
        "import sys, pathlib\npathlib.Path(sys.argv[1], 'loose_gate_called').write_text('x')\nsys.exit(0)\n", encoding="utf-8")
    (loose / "config").mkdir()
    write_values(loose, {"template_dir": "型", "decision_match_allow": ["作り物の書き方で済み"]})
    subprocess.run(["git", "init", "-q"], cwd=loose, check=True)
    return loose


def test_窓が立つ所の_repo_の緩い値と型では照らさない(env, tmp_path):
    repo, spec = env
    loose = _loose_repo(tmp_path)
    put15(spec, HEAD + "## §6 決定照合\n\n- 作り物の決定 A: 作り物の書き方で済み\n")
    assert seal(loose, spec).returncode == 1                       # 設計書の repo の表に外す行は無い
    assert not (spec / "loose_gate_called").exists()
    write_values(repo, {})                                         # 設計書の repo に型が無い
    put15(spec, DONE_TABLE)
    res = seal(loose, spec)
    assert res.returncode == 3 and "LOCK しない" in res.stdout
    assert not (spec / "loose_gate_called").exists()


def test_設計書が_repo_の外なら止める(env, tmp_path):
    repo, _ = env
    out = tmp_path / "外の設計書"
    out.mkdir()
    put15(out, DONE_TABLE)
    res = seal(repo, out)
    assert res.returncode == 1 and "repo の中に無い" in res.stderr
    assert not (out / "gate_called").exists()
