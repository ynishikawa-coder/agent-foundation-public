"""次の版の印の決め方（scripts/release/next_tag.py）。"""
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "scripts" / "release" / "next_tag.py"
spec = importlib.util.spec_from_file_location("next_tag", SCRIPT)
nt = importlib.util.module_from_spec(spec)
sys.dont_write_bytecode = True
spec.loader.exec_module(nt)


def test_合流のたびに小の位を1上げる():
    assert nt.plan(["v0.3.1", "v0.4.0", "v0.2.0", "印でない"], []) == "v0.4.1"
    assert nt.plan(["v0.4.9"], []) == "v0.4.10"


def test_印の無い_repo_は_v0_0_1():
    assert nt.plan([], []) == "v0.0.1"


def test_既に印のある_commit_には打たない():
    assert nt.plan(["v0.4.0"], ["v0.4.0"]) is None


def test_手で回す口は今より新しい版だけを通す():
    assert nt.plan(["v0.4.3"], [], "v0.5.0") == "v0.5.0"
    for bad in ("v0.4.3", "v0.4.1", "0.5.0", "v0.5"):
        with pytest.raises(ValueError):
            nt.plan(["v0.4.3"], [], bad)


def test_作り物の_repo_で_版_SHA_の1行を出す(tmp_path):
    run = lambda *a: subprocess.run(["git", *a], cwd=tmp_path, capture_output=True, text=True, check=True)
    run("init", "-q")
    run("-c", "user.name=t", "-c", "user.email=t@example.invalid", "commit", "-q", "--allow-empty", "-m", "作り物")
    run("tag", "v0.1.0")
    run("-c", "user.name=t", "-c", "user.email=t@example.invalid", "commit", "-q", "--allow-empty", "-m", "作り物 2")
    out = subprocess.run([sys.executable, str(SCRIPT), "--repo", str(tmp_path)], capture_output=True, text=True)
    sha = run("rev-parse", "HEAD").stdout.strip()
    assert out.returncode == 0 and out.stdout.strip() == "v0.1.1 " + sha


def test_plugin_は版の番号を持たない():
    """番号は印 1 つだけ。plugin.json に版を書くと、合流のたびにそろえる手が要る（それを畳んだ）。"""
    for f in sorted(ROOT.glob("plugins/*/.claude-plugin/plugin.json")):
        assert "version" not in json.loads(f.read_text(encoding="utf-8")), f
