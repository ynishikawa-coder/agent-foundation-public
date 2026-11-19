"""使う側に貼る setup script の塊（docs/核の届け方.md）は、クラウドの窓の道具 update_environment が運べる
1 行 200 バイト（改行を除く）・100 行に収まる。超えると AI の窓が環境に貼れない（2026-11-19 に 207・317 バイトの行で
貼れず、人の手で貼った）。照らすのは塊を読む 1 か所（scripts/plugin_smoke.py の setup_block）で、CI の plugin-smoke も
同じ口で塊を読むので、上限を超えた塊は合流の前に止まる。"""
import importlib.util
import re
import shutil
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
DOC = "docs/核の届け方.md"
spec = importlib.util.spec_from_file_location("plugin_smoke_limit", ROOT / "scripts" / "plugin_smoke.py")
smoke = importlib.util.module_from_spec(spec)
spec.loader.exec_module(smoke)


def _doc_with(tmp_path, extra: list[str]) -> Path:
    """正本の docs の塊の末尾に行を足した写し（注入）。"""
    dst = tmp_path / "repo"
    (dst / "docs").mkdir(parents=True)
    text = (ROOT / DOC).read_text(encoding="utf-8")
    m = re.search(r"(<!-- setup-script.*?-->\s*```bash\n.*?)(\n\s*```)", text, re.S)
    add = "".join("\n   " + s for s in extra)
    (dst / DOC).write_text(text[:m.end(1)] + add + text[m.end(1):], encoding="utf-8")
    return dst


def test_使う側に貼る塊は道具の上限に収まる():
    block = smoke.setup_block(ROOT)
    assert smoke.over_limits(block) == []
    assert all(len(s.encode("utf-8")) <= 200 for s in block.splitlines()) and len(block.splitlines()) <= 100


def test_注入_201_バイトの行を足すと赤(tmp_path):
    with pytest.raises(ValueError, match=r"行目が 201 バイト（上限 200）"):
        smoke.setup_block(_doc_with(tmp_path, ["echo " + "x" * 196]))


def test_200_バイトの行は収まる_日本語はバイトで数える(tmp_path):
    assert smoke.setup_block(_doc_with(tmp_path, ["echo " + "あ" * 65]))           # 5+195=200
    with pytest.raises(ValueError, match="201 バイト"):
        smoke.setup_block(_doc_with(tmp_path / "b", ["echo x" + "あ" * 65]))      # 6+195=201


def test_注入_101_行の塊は赤(tmp_path):
    n = len(smoke.setup_block(ROOT).splitlines())
    with pytest.raises(ValueError, match="101 行（上限 100）"):
        smoke.setup_block(_doc_with(tmp_path, ["true"] * (101 - n)))
