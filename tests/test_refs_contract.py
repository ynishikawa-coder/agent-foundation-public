"""plugin core の refs.py: 土台の文書の節・名・見張りの出来事を約束として出し、使う側の指しを名で照らすか（注入の試験）。

原因（原因の台帳の束 F6）: 土台が節・箇条・見張りの出来事を約束として出さず、使う側は番号（細目 §3）や字形で指していた。
土台が節を足す・並べ替えると、番号の指しは黙って別の節を指し、字形を読む口は読めずに止まった。
"""
import json
import shutil
import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
TOOL = ROOT / "plugins" / "core" / "scripts" / "refs.py"
def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


R = _load("af_refs", TOOL)


def run(*args):
    return subprocess.run([sys.executable, "-B", str(TOOL), *map(str, args)], capture_output=True, text=True)


def consumer(tmp_path, text):
    f = tmp_path / "使う側の決まり.md"
    f.write_text(text, encoding="utf-8")
    return f


def renumbered(tmp_path):
    """作り物の土台: 細目の頭に節を 1 つ足し、後ろの番号を全部 1 つずつずらす（土台が節を足した時の形）。"""
    root = tmp_path / "土台"
    for rel in R.ALIASES.values():
        src = ROOT / rel
        if src.is_file():
            (root / rel).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy(src, root / rel)
    p = root / "plugins/core/細目.md"
    text = p.read_text(encoding="utf-8")
    for n in range(8, 0, -1):
        text = text.replace(f"\n## {n}. ", f"\n## {n + 1}. ")
    p.write_text(text.replace("\n## 2. 安全", "\n## 1. 作り物の新しい節\n\n- 作り物。\n\n## 2. 安全", 1), encoding="utf-8")
    return root


def test_約束は節と名と見張りの出来事を出す():
    res = run("list")
    assert res.returncode == 0, res.stdout
    c = json.loads(res.stdout)
    sai = c["docs"]["plugins/core/細目.md"]
    assert {"no": 3, "title": "直すは根治"} in [{k: s[k] for k in ("no", "title")} for s in sai["sections"]]
    assert any(n["name"] == "まず構造を疑う" and n["section"] == "直すは根治" for n in sai["names"])
    assert c["hooks"]["plugins/guard/scripts/values_keys.py"] == {"pre": "check", "start": "resurface"}


def test_見張りの出来事は_guard_が回す物と同じ():
    guard = _load("af_guard_for_refs", ROOT / "plugins" / "guard" / "scripts" / "guard.py")
    events = {e for h in R.contract(ROOT)["hooks"].values() for e in h}
    for e in events:
        want = {f"plugins/guard/scripts/{m}.py": f for m, f in guard.watchers(e)}
        got = {p: h[e] for p, h in R.contract(ROOT)["hooks"].items() if e in h}
        assert got == want, e


def test_名で引くと今の番号が出る():
    res = run("find", "細目", "まず構造を疑う")
    assert res.returncode == 0 and "§3「直すは根治」" in res.stdout, res.stdout
    assert run("find", "細目", "作り物の無い名").returncode == 1


@pytest.mark.parametrize("text,ok", [
    ("原因は細目「まず構造を疑う」で探す。", True),
    ("原因は細目 §3「まず構造を疑う」で探す。", True),
    ("聞き方は核「聞き方」に従う。", True),
    ("核 §2「物は本当の名で呼ぶ」。", True),                            # 文の引き（その節に在る字）
    ("原因は細目 §3 で探す。", False),                                  # 番号だけ
    ("原因は細目 §4「まず構造を疑う」で探す。", False),                  # 番号と名が合わない
    ("原因は細目「作り物の消えた名」で探す。", False),                    # 名が無い
    ("核 §3「物は本当の名で呼ぶ」。", False),                            # 引いた文がその節に無い
    ("細目 §99 を見る。", False),                                       # 無い番号
])
def test_使う側の指しを名で照らす(tmp_path, text, ok):
    res = run("check", consumer(tmp_path, text + "\n"))
    assert (res.returncode == 0) is ok, res.stdout
    if not ok:
        assert res.returncode == 1 and "✗" in res.stdout


def test_番号だけの指しは名の直し方を出す(tmp_path):
    res = run("check", consumer(tmp_path, "細目 §3 を読む。\n"))
    assert "名で指す: 細目「直すは根治」" in res.stdout


def test_土台が節を足すと_番号の指しは赤になり_名の指しは合ったまま(tmp_path):
    """注入: 作り物の土台で細目の番号を 1 つずつずらす。前は番号の指しが黙って別の節を指した。"""
    root = renumbered(tmp_path)
    by_name = consumer(tmp_path, "原因は細目「まず構造を疑う」で探す。\n")
    assert run("--root", root, "check", by_name).returncode == 0
    both = consumer(tmp_path, "原因は細目 §3「まず構造を疑う」で探す。\n")
    res = run("--root", root, "check", both)
    assert res.returncode == 1 and "今は §4「直すは根治」" in res.stdout, res.stdout
    assert "§4「直すは根治」" in run("--root", root, "find", "細目", "まず構造を疑う").stdout


def test_土台が読めない時と照らす_file_が読めない時は_2(tmp_path):
    empty = tmp_path / "空"
    empty.mkdir()
    assert run("--root", empty, "list").returncode == 2
    assert run("check", tmp_path / "無い.md").returncode == 2


def test_土台の中の番号の指しは全部今の節に合う():
    """土台の中は同じ PR で番号を直せるので番号だけも許す（--numbers）。在る番号か・名と合うかは照らす。"""
    files = subprocess.run(["git", "-C", str(ROOT), "-c", "core.quotepath=off", "ls-files", "-z", "--",
                            "plugins/*.md", "plugins/*.py", "CONTRIBUTING.md", "docs/*.md", ".github/*.md",
                            "scripts/*.py"], capture_output=True, text=True, check=True).stdout.split("\0")
    res = run("check", "--numbers", *[ROOT / f for f in files if f])
    assert res.returncode == 0, res.stdout
