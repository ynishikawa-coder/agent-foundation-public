"""docs-kit の型の検査の Chrome の探し方と ?selftest の読み方は、共通の口 1 つが正本（型ごとに写さない）。"""
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SKILLS = ROOT / "plugins" / "docs-kit" / "skills"


def test_型の検査は_Chrome_の探し方と_selftest_の読み方を写さず共通の口を使う():
    """型ごとに Chrome の探し方を写す形（Blueprint と理論モックが同じ関数を別々に持った）に戻すと赤。"""
    shared = ROOT / "plugins" / "docs-kit" / "scripts" / "page_selftest.py"
    assert "def find_chrome" in shared.read_text(encoding="utf-8")
    for f in SKILLS.glob("*/scripts/*.py"):
        src = f.read_text(encoding="utf-8")
        for name in ("def find_chrome", "def dump_dom", "def chrome_cmd", "def open_dom", "def pre_text"):
            assert name not in src, f"{f.relative_to(ROOT)} が {name} を写して持つ（page_selftest を使う）"
