"""土台の入口は、前の setup の目録の clone が残る箱でも、打てば必ず名簿の先端（出所の HEAD）に揃える。

前の setup の clone が残ると `claude plugin marketplace add` は「already on disk」で何もせず、`plugin update` も目録を
進めない（実機の claude 2.1 で確かめた）。入口が `marketplace update` を打たないと、古い名簿と古い入口のまま入る。
claude の命令は作り物（tests/test_setup_plugins.py の FAKE: marketplace update で clone を出所から pull し、
install/update で入った台帳に clone の HEAD を書く）で置き換える。
"""
import importlib.util
import json
import re
import subprocess
from pathlib import Path

from test_setup_plugins import ENTRY, foundation, git, run, write_manifest

ROOT = Path(__file__).resolve().parent.parent
DOC = ROOT / "docs" / "核の届け方.md"


def head(path):
    return subprocess.run(["git", "-C", str(path), "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()


def shas(tmp_path):
    t = json.loads((tmp_path / "home" / ".claude" / "plugins" / "installed_plugins.json").read_text(encoding="utf-8"))
    return {k.split("@")[0]: v[0]["gitCommitSha"] for k, v in t["plugins"].items()}


def advance(tmp_path, names, entry_text=None):
    """出所が先へ進む（plugin を足す・入口を替える）。clone（market）は前の setup の古いまま残る。"""
    up = tmp_path / "upstream"
    write_manifest(up, names)
    if entry_text is not None:
        (up / "scripts" / "setup_plugins.py").write_text(entry_text, encoding="utf-8")
    git(up, "add", "-A")
    git(up, "commit", "-q", "--allow-empty", "-m", "v2")
    return head(up)


def stale_box(tmp_path):
    """前の窓の setup で v1 が入り、出所が v2 へ進んだ箱。"""
    root = foundation(tmp_path, ["core", "guard"])
    r, _, _, _ = run(tmp_path, root)
    assert r.returncode == 0, r.stdout
    return root, head(root)


def test_古い目録が残った箱で入口を打つと名簿の先端に揃い_足された_plugin_も入る(tmp_path):
    root, old = stale_box(tmp_path)
    tip = advance(tmp_path, ["core", "guard", "足した物"])
    r, log, note, home = run(tmp_path, root)
    assert r.returncode == 0, r.stdout
    assert shas(tmp_path) == {"core": tip, "guard": tip, "足した物": tip} and tip != old
    assert log.index("plugin marketplace update agent-foundation") < log.rindex("plugin install core@")
    state = json.loads((home / ".claude" / "af-foundation" / "setup.json").read_text(encoding="utf-8"))
    assert state["catalog_sha"] == tip and state["refreshed"] is True and state["stale"] == []


def test_注入_入口が目録を取り直さないと古い名簿のまま入る(tmp_path):
    """注入: 入口の marketplace update を「打ったふり」に替えた写し → 足された plugin が入らず版も古い（上の試験が赤になる証明）。"""
    root, old = stale_box(tmp_path)
    src = ENTRY.read_text(encoding="utf-8")
    call = 'r = claude("plugin", "marketplace", "update", market)'
    assert call in src
    (root / "scripts" / "setup_plugins.py").write_text(src.replace(call, "r = subprocess.CompletedProcess([], 0)"),
                                                       encoding="utf-8")
    tip = advance(tmp_path, ["core", "guard", "足した物"])
    run(tmp_path, root)
    got = shas(tmp_path)
    assert "足した物" not in got and got["core"] == old != tip


def test_目録を取り直せなければ名指して_0_で抜けない(tmp_path):
    root, _ = stale_box(tmp_path)
    advance(tmp_path, ["core", "guard"])
    r, _, note, _ = run(tmp_path, root, FAKE_UPDATE_FAIL="1")
    assert r.returncode == 1 and "取り直せなかった" in note and "<!-- af-plugin-missing -->" in note


def test_名簿の版に揃わない_plugin_を名指す(tmp_path):
    """plugin update が黙って動かなかった plugin は、入った台帳の commit と名簿の版を照らして名指す。"""
    root, _ = stale_box(tmp_path)
    advance(tmp_path, ["core", "guard"])
    r, _, note, _ = run(tmp_path, root, FAKE_UPDATE_STUCK="guard")
    assert r.returncode == 1 and re.search(r"名簿の版 \w+ に揃っていない: guard", note)


def test_取り直して入口が変わっていれば新しい入口で入れる(tmp_path):
    root, _ = stale_box(tmp_path)
    new = ENTRY.read_text(encoding="utf-8").replace("def main() -> int:\n", "def main() -> int:\n    print('新しい入口')\n")
    advance(tmp_path, ["core", "guard"], entry_text=new)
    r, _, _, _ = run(tmp_path, root)
    assert r.returncode == 0 and r.stdout.count("新しい入口") == 1, r.stdout


def _row(i):
    spec = importlib.util.spec_from_file_location("kaku_tip", ROOT / "plugins" / "core" / "scripts" / "kaku.py")
    kaku = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(kaku)
    return next(r for r in kaku.olds_table() if r["id"] == i)


def test_使う側に貼る塊は古い入口でも先に目録を取り直す():
    """docs の塊の 1 行目が marketplace update を打つ（clone が入口の直しより古い箱でも、古い入口の前に先端へ進む）。
    注入: update を外した塊は古い形 no-marketplace-update に当たる（使う側に残れば起動の hook が名指す）。"""
    block = re.search(r"<!-- setup-script.*?-->\s*```bash\n(.*?)\n\s*```", DOC.read_text(encoding="utf-8"), re.S).group(1)
    first = block.splitlines()[0]
    assert first.index("marketplace add") < first.index("marketplace update agent-foundation")
    row = _row("no-marketplace-update")
    assert not row["re"].search(block)
    assert row["re"].search(block.replace("; claude plugin marketplace update agent-foundation || true", ""))


def test_取り直した出所で入口が消えても名簿で入れて照らす(tmp_path):
    """出所で入口の file が消えた・名が変わった時も例外で落ちず、取り直した名簿で入れ、揃いを照らして印を書く。"""
    root, _ = stale_box(tmp_path)
    up = tmp_path / "upstream"
    write_manifest(up, ["core", "guard", "足した物"])
    (up / "scripts" / "setup_plugins.py").rename(up / "scripts" / "入れる.py")
    git(up, "add", "-A")
    git(up, "commit", "-qm", "v2")
    r, _, _, home = run_from(tmp_path, root)
    assert r.returncode == 0, r.stdout + r.stderr
    assert set(shas(tmp_path).values()) == {head(up)} and "足した物" in shas(tmp_path)
    assert json.loads((home / ".claude" / "af-foundation" / "setup.json").read_text(encoding="utf-8"))["refreshed"] is True


def run_from(tmp_path, root):
    """入口を clone の外の写しから走らせる（取り直しで clone の入口が消える箱を作るため）。名簿と HEAD は clone を読む。"""
    import os
    import sys
    entry = tmp_path / "entry" / "scripts" / "setup_plugins.py"
    entry.parent.mkdir(parents=True)
    src = ENTRY.read_text(encoding="utf-8").replace(
        "ROOT = Path(__file__).resolve().parent.parent", f"ROOT = Path({str(root)!r})")
    entry.write_text(src, encoding="utf-8")
    probe = root / "scripts" / "setup_plugins.py"
    src = src.replace("Path(__file__).read_bytes()", f"Path({str(probe)!r}).read_bytes()")
    entry.write_text(src, encoding="utf-8")
    fake = tmp_path / "claude"
    from test_setup_plugins import FAKE
    fake.write_text(FAKE, encoding="utf-8")
    fake.chmod(0o755)
    home = tmp_path / "home"
    env = dict(os.environ, HOME=str(home), CLAUDE_BIN=str(fake), FAKE_LOG=str(tmp_path / "log"), FAKE_BROKEN="",
               FAKE_ROOT=str(root))
    r = subprocess.run([sys.executable, str(entry)], capture_output=True, text=True, env=env, timeout=60)
    return r, None, None, home
