"""検査の入口を小箱に写す 1 か所と、小箱を回す環境の 1 か所（小箱で check_all や pytest を回す試験はここを使う）。

入口は check_all.sh。試験ごとに写す file を手で並べると、入口に部品が足された時に写し忘れた小箱だけが別の形で回る。
環境も同じ: 試験ごとに消す変数を手で選ぶと、CI（GITHUB_*）と手元で小箱が違う形で回るのに名指されない（原因の台帳 束 F1）。
小箱で入口を回す試験は box_env() の環境で回す（tests/test_box_env_one_place.py が照らす）。
"""
import os
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ENTRY_FILES = ("scripts/check_all.sh",)
# 小箱へ受け継がない変数: CI の印（GITHUB_*）・PR の値・入口の結果の置き場と照らしていない訳の置き場・pytest の設定。
SCRUB = ("GITHUB_", "PR_BODY", "PR_HEAD_SHA", "AF_PYTEST_", "AF_CHECK_UNCHECKED", "AF_REQUIRE_CLAUDE",
         "PYTEST_ADDOPTS", "PYTEST_PLUGINS")


def box_env(ci=False, **over):
    """小箱を回す環境: 外の CI の印や入口の値を受け継がず、ci=True の時だけ CI の印を立て、over で足す。"""
    e = {k: v for k, v in os.environ.items() if not k.startswith(SCRUB)}
    if ci:
        e["GITHUB_ACTIONS"] = "true"
    e.update(over)
    return e


def copy_entry(root):
    """root に入口の組を写して root を返す。"""
    root = Path(root)
    for rel in ENTRY_FILES:
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / rel, root / rel)
    return root
