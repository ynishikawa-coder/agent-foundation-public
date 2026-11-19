"""job plugin-smoke の pytest が、印 real_claude の試験の飛ばし・xfail・外しを緑に数えないか（注入の試験）。

前の形: job plugin-smoke は `bash scripts/pytest.sh -q -m real_claude tests/` を回し、pytest の終わり方だけを見た。
印の試験が中で自分の条件で skip・xfail しても緑（本物の claude を要る試験が回らずに緑）で、試験の file が
自分で claude の有る無しを見て飛ばす形は字（正規表現 OWN_SKIP）で拾うだけで狭かった（原因の台帳 束 F1）。
今の形: 入口の plugin の --af-judge=real-claude が pytest の中で結果を判定し、印の試験が 1 本でも passed の外なら赤で終える。
"""
import shutil
import subprocess
from pathlib import Path

import pytest
from entry_box import box_env, copy_entry

ROOT = Path(__file__).resolve().parent.parent
HEAD = "import pytest\npytestmark = pytest.mark.real_claude\n\n"


def run(tmp_path, body):
    root = copy_entry(tmp_path / "box")
    (root / "tests").mkdir()
    shutil.copy2(ROOT / "tests" / "conftest.py", root / "tests" / "conftest.py")
    (root / "tests" / "test_plain.py").write_text("def test_plain():\n    pass\n", encoding="utf-8")
    (root / "tests" / "test_x_real_claude.py").write_text(HEAD + body, encoding="utf-8")
    fake = tmp_path / "bin"   # claude の命令が在る所（中身は作り物。印の試験を conftest が飛ばさない）
    fake.mkdir()
    (fake / "claude").write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    (fake / "claude").chmod(0o755)
    r = subprocess.run(["bash", "scripts/pytest.sh", "-q", "-p", "no:cacheprovider", "-m", "real_claude",
                        "--af-judge=real-claude", "tests/"], cwd=root, capture_output=True, text=True,
                       env=box_env(ci=True, PATH=f"{fake}:/usr/bin:/bin"), timeout=300)
    return r.returncode, r.stdout + r.stderr


def test_合格_印の試験が通れば緑(tmp_path):
    code, out = run(tmp_path, "def test_a():\n    pass\n")
    assert code == 0, out


@pytest.mark.parametrize("body", [
    "import shutil\n\ndef test_a():\n    if shutil.which('af-no-such-tool') is None:\n        pytest.skip('自前の飛ばし')\n",
    "from shutil import which\n\n" "@pytest.mark.skipif(which('nothing-here') is None, reason='x')\ndef test_a():\n    pass\n",
    "def test_a():\n    try:\n        import 無い部品  # noqa: F401\n    except ImportError:\n        pytest.skip('部品が無い')\n",
    "@pytest.mark.xfail(reason='作り物')\ndef test_a():\n    assert False\n",
], ids=["which is None", "from shutil import which", "try/except", "xfail"])
def test_注入_印の試験が自前の条件で飛ぶと赤(tmp_path, body):
    code, out = run(tmp_path, body)
    assert code != 0 and "af_judge 赤" in out, out
