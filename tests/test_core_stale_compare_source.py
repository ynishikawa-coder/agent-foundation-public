"""古い土台の判定は、比べる正本を読む（手近な物を読まない）。

- 起動の時の古さ: 入った commit を、hook の時の main でなく setup の時に入れた main の先端（入口 scripts/setup_plugins.py が
  ~/.claude/af-foundation/setup.json の main_at_setup に書く記録）と比べる。setup の後に main が進んだだけの窓に
  「setup script を直せ」と言わず、起動の後に古くなった窓と同じ引き継ぎ（fresh）にする。記録が無ければ分からないと名指す。
- 古い形の照らし: 開いた repo の作業の枝の checkout でなく main の中身を読む（枝が main より古い時に、main で直った
  古い形を「この仕事で消す」と言い切らない）。
remote は作り物の git。
"""
import json
import subprocess

from test_core_plugin import Foundation, _commit, _git, kaku, run
from test_setup_plugins import foundation, run as run_entry
from uses import py_calls, py_code

SETUP_FIX = "update_environment"


# ── 起動の時の古さ: setup の時の main と比べる ──

def test_setup_が古い物を入れた窓には_setup_script_を直せと言う(tmp_path):
    """注入 (b): setup の時の main の先端は進んでいたのに、setup は 1 つ前を入れた → setup script を直す知らせ（窓は続ける）。"""
    f = Foundation(tmp_path)
    tip = _commit(f.work, {"plugins/guard/x.py": "x\n"}, "守りを変える")
    f.install(main_at_setup=tip)
    text = f.hook("inject")
    assert "土台が古いまま立った窓 — setup script を直し、窓はそのまま続ける" in text and SETUP_FIX in text and tip[:12] in text
    assert f.hook("fresh") == ""                            # 起動の知らせが扱う（二重に出さない）


def test_setup_の時の_main_の記録が無ければ分からないと名指す(tmp_path):
    """注入: 記録が無い（古い入口・印が無い）→ どちらとも言い切らず、分からない事と setup script の照らし方を出す。"""
    f = Foundation(tmp_path)
    _commit(f.work, {"plugins/guard/x.py": "x\n"}, "守りを変える")
    f.install()
    text = f.hook("inject")
    assert "分からない" in text and "main_at_setup" in text and "get_environment" in text
    assert "setup はそれと違う物を入れた" not in text
    assert f.hook("fresh") == ""
    assert "分からない" in f.hook("inject", source="resume")


def test_hook_の時の_main_と比べて起動の時から古いと立てる道が無い():
    """なくす物: start_cause は setup の時の記録だけで「起動の時から古い」を決める（hook の時の main の先端は使わない）。"""
    import inspect
    import textwrap
    src = textwrap.dedent(inspect.getsource(kaku.inject))
    assert 'bool(f and f["plugins"])' not in py_code(src)
    assert "start_cause" in py_calls(src)                                # docstring・注釈の字でなく、呼ぶ形


def test_入口は_setup_の時の_main_の先端を記録に書く(tmp_path):
    """入口が、出所の main の先端を setup.json の main_at_setup に書く（起動の hook の比べる正本）。"""
    root = foundation(tmp_path, ["core"])
    r, _, _, home = run_entry(tmp_path, root)
    assert r.returncode == 0, r.stdout
    tip = subprocess.run(["git", "-C", str(tmp_path / "upstream"), "rev-parse", "HEAD"], capture_output=True,
                         text=True).stdout.strip()
    state = json.loads((home / ".claude" / "af-foundation" / "setup.json").read_text(encoding="utf-8"))
    assert state["main_at_setup"] == tip


def test_入口は出所の_main_が読めなければ記録を空にする(tmp_path):
    """注入: 出所に出られない → 記録は None（起動の hook は「分からない」と名指す。違う物を書いて言い切らない）。"""
    root = foundation(tmp_path, ["core"])
    subprocess.run(["git", "-C", str(root), "remote", "set-url", "origin", str(tmp_path / "無い")], check=True)
    _, _, _, home = run_entry(tmp_path, root)
    state = json.loads((home / ".claude" / "af-foundation" / "setup.json").read_text(encoding="utf-8"))
    assert state["main_at_setup"] is None


# ── 古い形の照らし: main の中身を読む ──

OLD = 'for p in core guard; do claude plugin install "$p@agent-foundation"; done\n'
NEW = 'python3 "$af" || true\n'


def _repo_with_main(tmp_path, main_body, branch_body):
    """origin の main に main_body、作業の枝の checkout に branch_body を持つ使う側の repo。"""
    remote, work = tmp_path / "remote.git", tmp_path / "使う側"
    subprocess.run(["git", "init", "-q", "--bare", "-b", "main", str(remote)], check=True)
    subprocess.run(["git", "clone", "-q", str(remote), str(work)], check=True, capture_output=True)
    base = _commit(work, {"setup.sh": branch_body, "README.md": "ふつう\n"}, "始め")
    if main_body != branch_body:
        _commit(work, {"setup.sh": main_body}, "main で直す")
        _git(work, "checkout", "-q", "-b", "古い枝", base)  # 枝は main より古い
    else:
        _git(work, "checkout", "-q", "-b", "作業の枝")
    return work


def test_枝が_main_より古い時に_main_で直った古い形を消せと言い切らない(tmp_path):
    """注入 (c): main では直った古い形が、main より古い作業の枝の checkout に残る → 「この仕事で消す」と言わず、
    枝が main より古い事を出す。olds も main を読んで古い形 0。"""
    work = _repo_with_main(tmp_path, NEW, OLD)
    assert "plugin install" in (work / "setup.sh").read_text(encoding="utf-8")   # checkout には残っている
    text = json.loads(run("inject", project=work).stdout)["hookSpecificOutput"]["additionalContext"]
    assert "この仕事で消す" not in text, text
    assert "main より古い" in text and "setup.sh" in text
    r = run("olds", work)
    assert r.returncode == 0 and "古い形 0" in r.stdout and "main" in r.stdout, r.stdout


def test_main_に残る古い形は今までどおり消せと名指す(tmp_path):
    """main にも枝にも残る → 名指す（読む物を main に替えても見つける力は落ちない）。"""
    work = _repo_with_main(tmp_path, OLD, OLD)
    text = json.loads(run("inject", project=work).stdout)["hookSpecificOutput"]["additionalContext"]
    assert "この仕事で消す" in text and "setup.sh: 土台の目録を足して plugin を入れるのに" in text
    assert run("olds", work).returncode == 1


def test_枝で消した古い形は_main_へ入れれば済むと添える(tmp_path):
    """main に残り、この枝では消えている → main の物として名指し、枝を main へ入れれば済むと添える。"""
    remote, work = tmp_path / "remote.git", tmp_path / "使う側"
    subprocess.run(["git", "init", "-q", "--bare", "-b", "main", str(remote)], check=True)
    subprocess.run(["git", "clone", "-q", str(remote), str(work)], check=True, capture_output=True)
    _commit(work, {"setup.sh": OLD}, "始め")
    _git(work, "checkout", "-q", "-b", "直す枝")
    (work / "setup.sh").write_text(NEW, encoding="utf-8")
    text = json.loads(run("inject", project=work).stdout)["hookSpecificOutput"]["additionalContext"]
    assert "setup.sh" in text and "この枝では消えている" in text


def test_この枝で足した古い形は_main_に無くても消せと名指す(tmp_path):
    """注入: main にも分かれ目にも無く、この枝で足した古い形 → 「main で直った」と取り違えず、この仕事で消す。"""
    work = _repo_with_main(tmp_path, NEW, NEW)
    (work / "setup.sh").write_text(OLD, encoding="utf-8")
    text = json.loads(run("inject", project=work).stdout)["hookSpecificOutput"]["additionalContext"]
    assert "この仕事で消す" in text and "この枝で足した" in text and "main より古い" not in text, text


def test_入口は入れ終わる前の_main_を記録し_入れている間の_push_で記録が新しくならない(tmp_path):
    """注入: plugin を入れている間に出所の main へ push が入る → 記録は入れた物（取り直した名簿の版）と同じ。
    入れ終わった後に読むと記録が新しくなり、正しい setup を「古い物を入れた」と取り違える。"""
    import os
    root = foundation(tmp_path, ["core"])
    up = tmp_path / "upstream"
    hook = tmp_path / "push_on_install.sh"
    hook.write_text(f'git -C "{up}" -c user.name=t -c user.email=t@example.invalid commit -q --allow-empty -m 間\n')
    # 作り物の claude の install の時に出所へ push を入れる
    fake_extra = {"FAKE_ON_INSTALL": str(hook)}
    from test_setup_plugins import FAKE
    patched = FAKE.replace('elif a[:2] in (["plugin", "install"], ["plugin", "update"]):',
                           'elif a[:2] in (["plugin", "install"], ["plugin", "update"]):\n'
                           '    os.environ.get("FAKE_ON_INSTALL") and a[1] == "install" and subprocess.run(["sh", os.environ["FAKE_ON_INSTALL"]])')
    assert patched != FAKE
    fake = tmp_path / "claude"
    home = tmp_path / "home"
    home.mkdir()
    fake.write_text(patched, encoding="utf-8")
    fake.chmod(0o755)
    env = dict(os.environ, HOME=str(home), CLAUDE_BIN=str(fake), FAKE_LOG=str(tmp_path / "log"), FAKE_BROKEN="",
               FAKE_ROOT=str(root), **fake_extra)
    import sys
    r = subprocess.run([sys.executable, str(root / "scripts" / "setup_plugins.py")], capture_output=True, text=True,
                       env=env, timeout=60)
    state = json.loads((home / ".claude" / "af-foundation" / "setup.json").read_text(encoding="utf-8"))
    up_tip = subprocess.run(["git", "-C", str(up), "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
    assert state["main_at_setup"] == state["catalog_sha"] != up_tip, (r.stdout, state)


def test_分かれ目が読めない浅い_clone_では直ったとも足したとも言い切らない(tmp_path):
    """注入（レビューの止める）: main で古い形を直し 5 本進めた remote を浅く clone し、古い枝を checkout → 分かれ目が
    読めない → 「この枝で足した・消す」とも「main で直った」とも言わず、分からないと名指す。olds は main を読んで 0。"""
    remote, work = tmp_path / "remote.git", tmp_path / "work"
    subprocess.run(["git", "init", "-q", "--bare", "-b", "main", str(remote)], check=True)
    subprocess.run(["git", "clone", "-q", str(remote), str(work)], check=True, capture_output=True)
    base = _commit(work, {"setup.sh": OLD}, "始め")
    _git(work, "push", "-q", "origin", f"{base}:refs/heads/古い枝")
    _commit(work, {"setup.sh": NEW}, "main で直す")
    for i in range(5):
        _commit(work, {f"docs/{i}.md": "x\n"}, f"進める {i}")
    shallow = tmp_path / "浅い"
    subprocess.run(["git", "clone", "-q", "--depth", "2", "--no-single-branch", f"file://{remote}", str(shallow)],
                   check=True, capture_output=True)
    _git(shallow, "checkout", "-q", "古い枝")
    assert subprocess.run(["git", "-C", str(shallow), "merge-base", "HEAD", "origin/main"],
                          capture_output=True).returncode != 0
    text = json.loads(run("inject", project=shallow).stdout)["hookSpecificOutput"]["additionalContext"]
    assert "残っている — この仕事で消す" not in text and "（この枝で足した）" not in text, text
    assert "古い形は main では直っている" not in text
    assert "分からない" in text and "setup.sh" in text
    assert run("olds", shallow).returncode == 0


def test_記録が_SHA_の形でなければ分からないと名指す(tmp_path):
    f = Foundation(tmp_path)
    _commit(f.work, {"plugins/guard/x.py": "x\n"}, "守りを変える")
    f.install(main_at_setup="壊れた記録")
    text = f.hook("inject")
    assert "分からない" in text and "setup はそれと違う物を入れた" not in text
