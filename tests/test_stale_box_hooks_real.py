"""古い土台で立った窓でも先端の守りの hook が動くか（本物の claude で入れて起動する・注入の試験）。

作り物の箱: 土台の写しを使う側と同じ setup script の塊で入れ（GitHub の土台の repo を手元の git へ差し替える）、
入れた後に main を進める（先端の guard の script だけが印の file を書く）。窓を起動すると plugin core が裏で入口
setup_plugins.py を回して先端を入れ直す。その後、窓が起動の時に読んだ古い版の dir の hooks.json の命令を
Claude Code と同じく回し、先端の guard が回る（印が在る・止めるべき入力は止めたまま）かを見る。
hooks.json の命令を古い形（版の dir の script を直に指す）に戻した箱では先端の guard が回らない＝赤を出す事も照らす。
窓の環境（鍵なし・API の行き先は閉じた口）は plugin_smoke.box_env の 1 か所を使う。
"""
import json
import sys
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import plugin_smoke as S  # noqa: E402
from test_plugin_smoke import copy_of_foundation, _git  # noqa: E402

pytestmark = pytest.mark.real_claude

MARK = "tip-guard-ran"


def _old_form(d: Path):
    """注入: 土台の hooks.json の命令を、版の dir の script を直に指す古い形に戻す。"""
    for hj in d.glob("plugins/*/hooks/hooks.json"):
        hooks = json.loads(hj.read_text(encoding="utf-8"))
        for groups in hooks["hooks"].values():
            for g in groups:
                for h in g["hooks"]:
                    h["command"] = 'python3 "${CLAUDE_PLUGIN_ROOT}/' + h["command"].split("${CLAUDE_PLUGIN_ROOT}/", 1)[1]
        hj.write_text(json.dumps(hooks, ensure_ascii=False, indent=2), encoding="utf-8")


def _tip_guard(d: Path):
    """先端の印: guard の入口が回ったら HOME に印の file を書く。"""
    f = d / "plugins" / "guard" / "scripts" / "guard.py"
    t = f.read_text(encoding="utf-8")
    probe = f'open(os.path.join(os.environ["HOME"], "{MARK}"), "a").write("x")\n\n\n'
    assert 'if __name__ == "__main__":' in t and "\nimport os\n" in t
    f.write_text(t.replace('if __name__ == "__main__":', probe + 'if __name__ == "__main__":', 1), encoding="utf-8")


def stale_box_tip_guard(tmp_path: Path, breaks=None) -> tuple[bool, list[str]]:
    """作り物の箱で起動し、(古い版の dir の guard の命令で先端の guard が回ったか, 途中の外れ)。"""
    src, v1 = copy_of_foundation(tmp_path, breaks)
    gh = tmp_path / "gh"
    gh.mkdir()
    bare = gh / (S.FOUNDATION.split("/")[1] + ".git")
    _git(tmp_path, "clone", "-q", "--bare", str(src), str(bare))
    _git(bare, "symbolic-ref", "HEAD", "refs/heads/main")
    home, proj = tmp_path / "home", tmp_path / "proj"
    home.mkdir()
    proj.mkdir()
    owner = S.FOUNDATION.split("/")[0]
    (home / ".gitconfig").write_text(f'[url "file://{gh}/"]\n\tinsteadOf = https://github.com/{owner}/\n'
                                     '[protocol "file"]\n\tallow = always\n', encoding="utf-8")
    env = S.box_env(home, proj)
    bad = []
    # 1. 使う側の setup script の塊そのもので v1 を入れる（土台の repo の名のまま・取りに行く先だけ手元の git）
    r = S.sh(["bash", "-ec", S.script_for(S.setup_block(ROOT), S.FOUNDATION)], env, timeout=900)
    if r.returncode != 0:
        bad.append(f"setup script が非 0: {(r.stdout + r.stderr)[-300:]}")
    table = home / ".claude" / "plugins" / "installed_plugins.json"
    rows = S.installed_rows(json.loads(table.read_text(encoding="utf-8")) if table.is_file() else {})
    old = Path(str((rows.get("guard") or {}).get("installPath") or "/nonexistent"))
    if (rows.get("guard") or {}).get("gitCommitSha") != v1 or not old.is_dir():
        return False, bad + [f"v1 が入っていない: {rows.get('guard')}"]
    # 2. 箱を作った後に main が進む（先端の guard だけが印を書く）
    _tip_guard(src)
    _git(src, "commit", "-qam", "先端")
    _git(src, "push", "-q", str(bare), "HEAD:main")
    # 3. 窓を起動する → plugin core が裏で先端を入れ直す
    S.start_session(env, proj)
    done = home / ".claude" / "af-foundation" / "refresh.json"
    end = time.time() + 600
    while time.time() < end and not done.is_file():
        time.sleep(2)
    res = json.loads(done.read_text(encoding="utf-8")) if done.is_file() else None
    if res is not None and res.get("code") != 0:
        bad.append(f"裏の入れ直しが失敗した: {res}")
    # 4. 窓が起動の時に読んだ古い版の dir の命令を、Claude Code と同じく回す
    hooks = json.loads((old / "hooks" / "hooks.json").read_text(encoding="utf-8"))
    cmd = hooks["hooks"]["PreToolUse"][0]["hooks"][0]["command"]
    p = S.run_hook(cmd, old, S.GUARD_PROBE, env)
    if '"deny"' not in p.stdout and p.returncode != 2:
        bad.append(f"止めるべき入力を止めない: {p.returncode} {p.stdout[-200:]} {p.stderr[-200:]}")
    return (home / MARK).exists(), bad + ([] if res else ["裏の入れ直しが始まらない・済まない（refresh.json が無い）"])


def test_古い版で立った窓でも先端の守りの_hook_が回る(tmp_path):
    ran, bad = stale_box_tip_guard(tmp_path)
    assert bad == [] and ran, bad


def test_注入_命令が版の_dir_を直に指す古い形なら先端の_hook_は回らない(tmp_path):
    ran, bad = stale_box_tip_guard(tmp_path, _old_form)
    assert bad == [], bad
    assert not ran, "古い形の命令で先端の guard が回った＝照らしが効いていない"
