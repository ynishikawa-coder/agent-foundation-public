"""scripts/checks/public_guard.sh の CI の exit 3（照らしていない・job public-guard が照らす）は、その job が ci.yml に
在る事を workflow の読み手で照らしてから言う（注入の試験）。

前の形: GITHUB_ACTIONS=true だけで exit 3 を返し、ci.yml から job public-guard の呼び口を消しても「job が照らす」と言った。
"""
import os
import shutil
import subprocess
from pathlib import Path

import pytest
from entry_box import box_env

ROOT = Path(__file__).resolve().parent.parent
CI = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")


def _box(tmp_path, ci_text):
    for rel in ("scripts/checks/public_guard.sh", "public-guard/workflow_reader.py", "scripts/af_unchecked.sh"):
        (tmp_path / rel).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(ROOT / rel, tmp_path / rel)
    (tmp_path / "public-guard" / "guard.py").write_text("import sys\nprint('GUARD RAN')\nsys.exit(0)\n", encoding="utf-8")
    (tmp_path / ".github" / "workflows").mkdir(parents=True)
    (tmp_path / ".github" / "workflows" / "ci.yml").write_text(ci_text, encoding="utf-8")
    env = box_env(ci=True)
    return subprocess.run(["bash", str(tmp_path / "scripts" / "checks" / "public_guard.sh")], capture_output=True,
                          text=True, env=env, timeout=60)


def test_CI_で_job_public_guard_が在れば照らしていないの_3(tmp_path):
    r = _box(tmp_path, CI)
    assert r.returncode == 3 and "照らしていない" in r.stdout and "GUARD RAN" not in r.stdout, r.stdout + r.stderr


@pytest.mark.parametrize("old, new", [
    ("      - uses: ./public-guard\n", "      # - uses: ./public-guard\n"),     # 呼び口を消した
    ("    name: public-guard\n", "    name: public-guard-old\n"),             # job の名を変えた
])
def test_注入_CI_で_job_public_guard_が無ければ赤(tmp_path, old, new):
    broken = CI.replace(old, new, 1)
    assert broken != CI
    r = _box(tmp_path, broken)
    assert r.returncode == 1 and "照らしていない" not in r.stdout, r.stdout + r.stderr
