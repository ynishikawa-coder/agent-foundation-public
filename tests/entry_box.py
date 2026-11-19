"""検査の入口を小箱に写す 1 か所（小箱で check_all や pytest を回す試験はここを使う）。

入口は check_all.sh・pytest.sh・結果を構造で残す plugin（scripts/pytest_plugin/）の組。試験ごとに写す file を
手で並べると、入口に部品が足された時に写し忘れた小箱だけが別の形で回る。
"""
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ENTRY_FILES = ("scripts/check_all.sh", "scripts/pytest.sh")
ENTRY_DIRS = ("scripts/pytest_plugin",)


def copy_entry(root):
    """root に入口の組を写して root を返す。"""
    root = Path(root)
    for rel in ENTRY_FILES:
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / rel, root / rel)
    for rel in ENTRY_DIRS:
        shutil.copytree(ROOT / rel, root / rel, ignore=shutil.ignore_patterns("__pycache__"), dirs_exist_ok=True)
    return root
