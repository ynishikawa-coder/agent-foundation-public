"""入れて起動する試験（scripts/plugin_smoke.py）の歯: 届かない物をわざと入れた土台の写しで赤になるか。

土台は main の先端をそのまま配るので、合流の前の CI の job `plugin-smoke` が、使う側と同じ入れ方で入れて起動する。
ここはその試験自身が「壊すと赤・戻すと緑」かを、作り物の写しで見る（注入の試験）。
本物の claude を要る印 real_claude を付ける（飛ばす条件と CI で拾う所は tests/conftest.py の 1 か所）。
"""
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

import smoke_breaks

ROOT = Path(__file__).resolve().parent.parent
SMOKE = ROOT / "scripts" / "plugin_smoke.py"

pytestmark = pytest.mark.real_claude


def _git(cwd, *a):
    return subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@example.invalid", *a], cwd=cwd,
                          capture_output=True, text=True, check=True).stdout.strip()


def copy_of_foundation(tmp_path, breaks=None):
    """git の追跡する file だけを写した土台の作り物（窓の作業の跡を混ぜない）に、壊す手を当てて commit する。"""
    dst = tmp_path / "foundation"
    for rel in _git(ROOT, "ls-files", "-z").split("\0"):
        if not rel or not (ROOT / rel).is_file():
            continue
        (dst / rel).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / rel, dst / rel)
    if breaks:
        breaks(dst)
    _git(dst, "init", "-q", "-b", "main")
    _git(dst, "add", "-A")
    _git(dst, "commit", "-q", "-m", "作り物")
    return dst, _git(dst, "rev-parse", "HEAD")


def smoke(src, sha):
    p = subprocess.run([sys.executable, str(SMOKE), "--source", str(src), "--expect-sha", sha, "--repo", str(ROOT)],
                       capture_output=True, text=True, timeout=600)
    return p.returncode, p.stdout + p.stderr


def test_そのままの土台は緑(tmp_path):
    src, sha = copy_of_foundation(tmp_path)
    code, out = smoke(src, sha)
    assert code == 0 and out.strip().endswith("plugin-smoke: 緑"), out


# 注入（壊す手と、赤の文に出るはずの字）は tests/smoke_breaks/ に 1 注入 1 file で置く（ここに並べない＝
# 並ぶ PR が同じ並びの末尾へ足して衝突しない）。足す時は tests/smoke_breaks/__init__.py の形で file を 1 つ足す。
BREAKS = smoke_breaks.load()


@pytest.mark.parametrize("breaks,want", [(b, w) for _, w, b in BREAKS], ids=[i for i, _, _ in BREAKS])
def test_届かない物を入れた土台は赤(tmp_path, breaks, want):
    src, sha = copy_of_foundation(tmp_path, breaks)
    code, out = smoke(src, sha)
    assert code == 1 and want in out, out


def test_試したい先端と違う物が入れば赤(tmp_path):
    src, _ = copy_of_foundation(tmp_path)
    code, out = smoke(src, "0" * 40)
    assert code == 1 and "試したい先端" in out, out
