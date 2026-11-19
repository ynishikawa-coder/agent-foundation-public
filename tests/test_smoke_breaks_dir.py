"""入れて起動する試験の注入は 1 注入 1 file の dir から読むか（並ぶ PR が試験の並びの末尾へ足して衝突する形が戻らないか）。

本物の起動（tests/test_plugin_smoke.py）は claude の命令の在る所だけで回るので、注入の読み方はここで claude 無しに照らす。
"""
import shutil
from pathlib import Path

import pytest

import smoke_breaks

ROOT = Path(__file__).resolve().parent.parent


def test_今の注入は全部読める():
    got = smoke_breaks.load()
    assert len(got) >= 7 and all(w for _, w, _ in got)


def test_試験の_file_は注入を並べずに_dir_から読む():
    text = (ROOT / "tests" / "test_plugin_smoke.py").read_text(encoding="utf-8")
    assert "smoke_breaks.load()" in text
    assert "def _" not in text.split("BREAKS =", 1)[0].split("def smoke(", 1)[1], "注入の関数を試験の file に戻した"


@pytest.fixture
def copy(tmp_path):
    d = tmp_path / "smoke_breaks"
    shutil.copytree(smoke_breaks.HERE, d, ignore=shutil.ignore_patterns("__pycache__"))
    return d


@pytest.mark.parametrize("bad,want", [
    ('ID = "x"\n\n\ndef breaks(d):\n    pass\n', "揃わない"),
    ('ID = "x"\nWANT = ""\n\n\ndef breaks(d):\n    pass\n', "揃わない"),
    ('ID = "skill が欠ける"\nWANT = "y"\n\n\ndef breaks(d):\n    pass\n', "重なる"),
    ("これは python でない\n", "読めない"),
], ids=["WANT が無い", "WANT が空", "ID の重なり", "読めない"])
def test_崩れた注入の_file_は黙って飛ばさず止める(copy, bad, want):
    (copy / "zz_bad.py").write_text(bad, encoding="utf-8")
    with pytest.raises(ValueError, match=want):
        smoke_breaks.load(copy)


def test_注入が_1_つも無い_dir_は止める(tmp_path):
    with pytest.raises(ValueError, match="1 つも無い"):
        smoke_breaks.load(tmp_path)


def test_注入を足すのは_file_を_1_つ足すだけ(copy):
    n = len(smoke_breaks.load(copy))
    (copy / "zz_new.py").write_text('ID = "作り物"\nWANT = "作り物の赤"\n\n\ndef breaks(d):\n    pass\n', encoding="utf-8")
    assert len(smoke_breaks.load(copy)) == n + 1
