"""古い形 no-stale-catalog-remove の約束: 前の目録を外さない setup（古い 3 行の形）は名指しされ、docs の新しい塊は当たらない。"""
import importlib.util
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("kaku_stale", ROOT / "plugins" / "core" / "scripts" / "kaku.py")
kaku = importlib.util.module_from_spec(spec)
spec.loader.exec_module(kaku)


def _row():
    return next(r for r in kaku.olds_table() if r["id"] == "no-stale-catalog-remove")


def _block():
    doc = (ROOT / "docs" / "核の届け方.md").read_text(encoding="utf-8")
    return re.search(r"<!-- setup-script.*?-->\s*```bash\n(.*?)\n\s*```", doc, re.S).group(1)


def test_docs_の塊は前の目録を外すので当たらない():
    assert "marketplace remove agent-foundation" in _block() and not _row()["re"].search(_block())


def test_注入_外す行を抜いた塊は当たる():
    block = re.sub(r"(?m)^.*marketplace remove.*\n", "", _block())
    assert _row()["re"].search(block)


def test_例の行は当たる():
    assert _row()["re"].search(_row()["example"])
