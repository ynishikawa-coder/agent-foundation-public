"""古い形 no-stale-catalog-remove を字の並びでなく命令の読み手で読む約束の注入の試験:
コメント・echo の中の「marketplace remove」は外す命令に数えず、引用符で割った命令は外す命令に数える。"""
import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("kaku_rm82", ROOT / "plugins" / "core" / "scripts" / "kaku.py")
kaku = importlib.util.module_from_spec(spec)
spec.loader.exec_module(kaku)

ADD = "claude plugin marketplace add o/agent-foundation-public --scope user || true\n" \
      "claude plugin marketplace update agent-foundation || true\npython3 \"$af/scripts/setup_plugins.py\" || true\n"


def _row():
    return next(r for r in kaku.olds_table() if r["id"] == "no-stale-catalog-remove")


@pytest.mark.parametrize("extra", [
    "# claude plugin marketplace remove agent-foundation\n",          # コメントは命令でない
    "echo 'claude plugin marketplace remove agent-foundation'\n",     # echo の中の字は命令でない
    "claude plugin marketplace remove other-market || true\n",        # 別の目録を外しても土台の目録は残る
])
def test_外す命令でない字は数えず名指す(extra):
    assert kaku.olds_hit(_row(), extra + ADD, "setup.sh")


@pytest.mark.parametrize("extra", [
    "claude plugin marketplace remove agent-foundation >/dev/null 2>&1 || true\n",
    "claude plugin marketplace \"remove\" 'agent-foundation' || true\n",   # 引用符で割っても同じ命令
])
def test_外す命令が在れば当たらない(extra):
    assert not kaku.olds_hit(_row(), extra + ADD, "setup.sh")
