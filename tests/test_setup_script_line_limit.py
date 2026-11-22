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


def _over(n: int) -> str:
    """ちょうど n バイトの 1 行（ASCII で埋める）。"""
    return "echo " + "x" * (n - 5)


def _ja(n: int) -> str:
    """日本語（3 バイトの字）を入れて、ちょうど n バイトにする 1 行。"""
    k, r = divmod(n - 5, 3)
    return "echo " + "x" * r + "あ" * k


def test_使う側に貼る塊は道具の上限に収まる():
    block = smoke.setup_block(ROOT)
    assert smoke.over_limits(block) == []
    lines = block.splitlines()
    assert all(len(s.encode("utf-8")) <= smoke.LINE_BYTES for s in lines) and len(lines) <= smoke.MAX_LINES


def test_注入_上限より1バイト長い行を足すと赤(tmp_path):
    b = smoke.LINE_BYTES
    with pytest.raises(ValueError, match=r"行目が %d バイト（上限 %d）" % (b + 1, b)):
        smoke.setup_block(_doc_with(tmp_path, [_over(b + 1)]))


def test_上限ちょうどの行は収まる_日本語はバイトで数える(tmp_path):
    b = smoke.LINE_BYTES
    assert "あ" in _ja(b) and len(_ja(b).encode("utf-8")) == b
    assert smoke.setup_block(_doc_with(tmp_path, [_ja(b)]))
    with pytest.raises(ValueError, match="%d バイト" % (b + 1)):
        smoke.setup_block(_doc_with(tmp_path / "b", [_ja(b + 1)]))


def test_注入_上限より1行多い塊は赤(tmp_path):
    n, m = len(smoke.setup_block(ROOT).splitlines()), smoke.MAX_LINES
    with pytest.raises(ValueError, match="%d 行（上限 %d）" % (m + 1, m)):
        smoke.setup_block(_doc_with(tmp_path, ["true"] * (m + 1 - n)))
