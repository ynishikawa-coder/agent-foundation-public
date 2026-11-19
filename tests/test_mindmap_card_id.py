"""mindmap のカードの id の決まりは 1 つ（SKILL の schema と型の自己検査が同じ決まりで見る）: id を省く・空のカードは
engine の自動の番号の後で見るので通り、書いた id の重複と「c+数字」の形の崩れは検査が NG にする。型の自己検査
（page_selftest.py）を Chrome で直に回す。入力は型の template を作り物に書き替えた物。"""
import sys

import pytest

from test_guard import ROOT  # noqa: F401
from test_guard_page_ledger import needs_chrome, page


def _selftest(path):
    import subprocess
    ps = ROOT / "plugins" / "docs-kit" / "scripts" / "page_selftest.py"
    return subprocess.run([sys.executable, str(ps), str(path)], capture_output=True, text=True, timeout=120)


@needs_chrome
@pytest.mark.parametrize("edit", [
    lambda s: s.replace('"id": "c13",', "", 1),            # id を省く（SKILL の schema: engine が自動採番）
    lambda s: s.replace('"id": "c13"', '"id": ""', 1),     # id を空にする
], ids=["省く", "空"])
def test_mindmap_id_を省いたカードは自動採番で検査を通る(tmp_path, edit):
    """schema と selftest は 1 つの決まり: id が空・無いカードは prep の採番の後で見るので通る。"""
    r = _selftest(page(tmp_path, "mindmap", edit))
    assert r.returncode == 0 and "SELFTEST OK" in r.stdout, r.stdout + r.stderr


@needs_chrome
@pytest.mark.parametrize("edit,why", [
    (lambda s: s.replace('"id": "c13"', '"id": "c12"', 1), "id が重複"),
    (lambda s: s.replace('"id": "c13"', '"id": "x 13"', 1), "c+数字の形でない"),
], ids=["重複", "形"])
def test_mindmap_書いた_id_の重複と形の崩れは検査が_NG(tmp_path, edit, why):
    r = _selftest(page(tmp_path, "mindmap", edit))
    assert r.returncode == 1 and why in r.stdout, r.stdout + r.stderr
