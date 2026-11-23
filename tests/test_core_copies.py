"""plugin core の copies.py: 使う側の文に、土台の決まりのそのままの写しも言い換えた写しも拾うか（注入の試験）。"""
import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest

from test_kimari_okiba import 戻せない操作の文

ROOT = Path(__file__).resolve().parent.parent
TOOL = ROOT / "plugins" / "core" / "scripts" / "copies.py"
def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


REFS = _load("af_refs_for_copies", ROOT / "plugins" / "core" / "scripts" / "refs.py")

KAKU = (ROOT / "plugins" / "core" / "核.md").read_text(encoding="utf-8")
ORIGINAL = 戻せない操作の文(KAKU) or ""   # 核 §1 の箇条から読む（写さない・読めなければ下の試験が赤）


def run(tmp_path, text, *args):
    f = tmp_path / "使う側の決まり.md"
    f.write_text(text, encoding="utf-8")
    return subprocess.run([sys.executable, "-B", str(TOOL), str(f), *args], capture_output=True, text=True)


def test_試験の元の文が今の核に在る():
    assert 戻せない操作の文((ROOT / "plugins" / "core" / "核.md").read_text(encoding="utf-8")), "核 §1 に「戻せない操作」の箇条が 1 つでない"


@pytest.mark.parametrize("label,text", [
    ("そのままの写し", ORIGINAL),
    ("語順と語尾を変えた言い換え", "強制 push や DB の削除、人の手が入った物・git に無い一点物の削除のような戻せない操作の前には、人に聞くこと。"),
    ("括弧と語を替えた言い換え", "取り消せない操作（強制 push、DB 削除、人が手を入れた物や git に無い一点物を消す）の前は人に確認する。"),
])
def test_土台の決まりの写しは言い換えても拾い_根治の入口を指す(tmp_path, label, text):
    res = run(tmp_path, "# 作り物の repo の決まり\n\n- " + text + "\n")
    assert res.returncode == 1, (label, res.stdout)
    assert "使う側の決まり.md:3 が土台の 核.md:" in res.stdout, label
    last = res.stdout.strip().splitlines()[-1]
    assert "まず構造を疑う" in last and not REFS.check_text(REFS.contract(ROOT), last), last  # 根治の入口を名で指し、指しが合う


def test_関係の無い決まりは拾わない(tmp_path):
    res = run(tmp_path, "# 作り物\n\n- 作り物の帳票の合計は税込みで出し、端数は切り捨てて表の一番下に置く。\n")
    assert res.returncode == 0, res.stdout


def test_土台の文が読めない時は黙って緑にしない(tmp_path):
    empty = tmp_path / "空"
    empty.mkdir()
    res = run(tmp_path, ORIGINAL + "\n", "--foundation", str(empty))
    assert res.returncode == 2
