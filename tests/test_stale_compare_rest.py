"""古い土台の判定は手近な物でなく正本と比べる（残りの 6 か所・原因の台帳の同じ原因の行）。

- kaku.py の main: 手元の refs/remotes/origin/*（fetch しない・origin/HEAD は既定の枝と限らない）でなく出所の今の main。
  取れなければ「確かめられない」と名指し、消す・直ったと言い切らない。
- kaku.py の入れ方の照らし: setup.json が在るかでなく、今の土台を入れた setup の記録か（名簿の版・時）で見る。
  入っていない plugin は user scope で enabled かで見る（入口の enabled() と同じ）。
- kaku.py の目録の出所: GitHub かだけでなく、土台の repo か（同じ名の fork の main を正と見ない）。
remote は作り物の git。
"""
import json
import re
import subprocess
from pathlib import Path

import pytest

from test_core_plugin import PLUGIN, Foundation, _commit, _git, catalog_commit, kaku, run

ROOT = Path(__file__).resolve().parent.parent
OLD = 'for p in core guard; do claude plugin install "$p@agent-foundation"; done\n'
NEW = 'python3 "$af" || true\n'


def _ctx(r):
    return json.loads(r.stdout)["hookSpecificOutput"]["additionalContext"] if r.stdout else ""


def _stale_clone(tmp_path):
    """出所の main は古い形を直したが、使う側の手元の origin/main は直す前のまま（fetch していない）の repo。"""
    remote, writer, work = tmp_path / "remote.git", tmp_path / "書く側", tmp_path / "使う側"
    subprocess.run(["git", "init", "-q", "--bare", "-b", "main", str(remote)], check=True)
    subprocess.run(["git", "clone", "-q", str(remote), str(writer)], check=True, capture_output=True)
    _commit(writer, {"setup.sh": OLD, "README.md": "ふつう\n"}, "始め")
    subprocess.run(["git", "clone", "-q", str(remote), str(work)], check=True, capture_output=True)
    _commit(writer, {"setup.sh": NEW}, "main で直す")                       # 使う側は fetch しない
    assert "plugin install" in _git(work, "show", "origin/main:setup.sh")  # 手元の origin/main は古い
    return remote, writer, work


# ── main は出所の今の main ──

def test_手元の_origin_main_が古くても_main_で直った古い形を消せと言い切らない(tmp_path):
    """注入: 手元の origin/main を古く置く → 出所の今の main を読み、「この仕事で消す」と言わない。"""
    _, writer, work = _stale_clone(tmp_path)
    text = _ctx(run("inject", project=work))
    assert "この仕事で消す" not in text, text
    assert "main では直っている" in text and "setup.sh" in text
    r = run("olds", work)
    tip = _git(writer, "rev-parse", "HEAD")
    assert r.returncode == 0 and tip[:12] in r.stdout, r.stdout


def test_origin_HEAD_が別の枝を指しても出所の既定の枝を読む(tmp_path):
    """注入: 手元の origin/HEAD を古い形の残る別の枝へ向ける → 出所の既定の枝（main）を読む。"""
    _, writer, work = _stale_clone(tmp_path)
    _git(writer, "push", "-q", "origin", "HEAD~1:refs/heads/古い枝")
    _git(work, "fetch", "-q", "origin")
    _git(work, "remote", "set-head", "origin", "古い枝")
    _git(work, "checkout", "-q", "-B", "作業", "origin/main")
    assert "この仕事で消す" not in _ctx(run("inject", project=work))


def test_出所に出られなければ確かめられないと名指し_消すとも_0_とも言わない(tmp_path):
    """注入: 出所が無くなる（オフライン）→ 手元の origin/main を読んだ事と、同じか分からない事を名指す。"""
    remote, _, work = _stale_clone(tmp_path)
    remote.rename(tmp_path / "移した.git")
    text = _ctx(run("inject", project=work))
    assert "この仕事で消す" not in text and "確かめられない" in text and "setup.sh" in text, text
    r = run("olds", work)
    assert r.returncode == 2 and "照らせない" in r.stdout and "古い形 0" not in r.stdout, r.stdout


# ── 入れ方は今回の setup の記録で見る ──

def _home(tmp_path, *, rec_sha=None, rec_at="2026-11-19T20:57:09+0900", updated="2026-11-19T11:57:05.000Z",
          enabled=("core", "guard"), repo=None, main_at=None):
    home = tmp_path / "home"
    loc = home / ".claude" / "plugins" / "marketplaces" / "agent-foundation"
    (loc / ".claude-plugin").mkdir(parents=True)
    (loc / ".claude-plugin" / "marketplace.json").write_text(json.dumps(
        {"name": "agent-foundation", "plugins": [{"name": "core"}, {"name": "guard"}]}), encoding="utf-8")
    (home / ".claude" / "plugins" / "known_marketplaces.json").write_text(json.dumps({"agent-foundation": {
        "source": {"source": "github", "repo": repo or kaku.UPSTREAM}, "installLocation": str(loc)}}), encoding="utf-8")
    sha = catalog_commit(loc)
    (home / ".claude" / "plugins" / "installed_plugins.json").write_text(json.dumps({"version": 2, "plugins": {
        f"{n}@agent-foundation": [{"scope": "user", "installPath": str(PLUGIN), "gitCommitSha": sha, "lastUpdated": updated}]
        for n in ("core", "guard")}}), encoding="utf-8")
    (home / ".claude" / "settings.json").write_text(json.dumps(
        {"enabledPlugins": {f"{n}@agent-foundation": n in enabled for n in ("core", "guard")}}), encoding="utf-8")
    (home / ".claude" / "af-foundation").mkdir(parents=True)
    (home / ".claude" / "af-foundation" / "setup.json").write_text(json.dumps(
        {"entry": "scripts/setup_plugins.py", "catalog_sha": rec_sha or sha, "at": rec_at, "refreshed": True,
         "stale": [], **({"main_at_setup": main_at} if main_at else {})}), encoding="utf-8")
    return home


def _setup(tmp_path, **kw):
    return _ctx(run("inject", project=tmp_path / "proj", home=_home(tmp_path, **kw)))


def test_今回の_setup_の記録なら入れ方を知らせない(tmp_path):
    assert "入れ方が古い" not in _setup(tmp_path)


def test_前の_setup_の記録が残った箱で古い形の_setup_を名指す_名簿の版が違う(tmp_path):
    """注入: 前回の setup.json を残し（名簿の版が今入った物と違う）、古い形の setup で入れ直した箱 → 古い形を名指す。"""
    text = _setup(tmp_path, rec_sha="c" * 40)
    assert "setup script が古い形" in text and "前の setup の記録" in text, text


def test_前の_setup_の記録が残った箱で古い形の_setup_を名指す_記録の後に入れ直した(tmp_path):
    """注入: 記録の版は同じでも、記録の後に入口を通らずに入れ直した（台帳の lastUpdated が記録の時より後）→ 名指す。"""
    text = _setup(tmp_path, updated="2026-11-19T13:00:00.000Z")
    assert "setup script が古い形" in text and "入れ直した" in text, text


def test_入っていても_enabled_でない_plugin_を名指す(tmp_path):
    """注入: 台帳に鍵は在るが enabled でない plugin → 入っていない物として名指す（入口の enabled() と同じ見方）。"""
    text = _setup(tmp_path, enabled=("core",))
    assert "enabled になっていない: guard" in text, text


@pytest.mark.parametrize("kw", [{"rec_sha": "c" * 40}, {"updated": "2026-11-19T13:00:00.000Z"}])
def test_前の_setup_の記録の_main_で起動の古さの訳を決めない(tmp_path, monkeypatch, kw):
    """注入: 前の setup の記録（main_at_setup が今入った版と同じ）が残る箱で、入口を通らずに入れ直した
    → その記録で「setup の後に main が進んだ」と決めず、記録が無い時と同じく見分けられないとする。"""
    sha = "b" * 40
    monkeypatch.setenv("HOME", str(_home(tmp_path, main_at=sha, **kw)))
    f = {"plugins": ["guard"], "installed": sha, "main": "e" * 40}
    assert kaku.setup_record()[0] is None
    assert kaku.start_cause(f) == "unknown"
    assert f"setup の時の main の先端は {sha[:12]}" not in kaku.stale_at_start_text(f)


def test_今回の_setup_の記録の_main_で起動の古さの訳を決める(tmp_path, monkeypatch):
    sha = "b" * 40
    monkeypatch.setenv("HOME", str(_home(tmp_path, main_at=sha)))
    assert kaku.start_cause({"plugins": ["guard"], "installed": sha}) == "after"
    assert kaku.start_cause({"plugins": ["guard"], "installed": "d" * 40}) == "setup"


# ── 目録の出所は土台の repo ──

def test_同じ名の_fork_から入った目録を名指し_fork_の_main_と比べない(tmp_path):
    """注入: 目録 agent-foundation が fork から入る → 出所が違うと名指し、fork の main で古さを決めない。"""
    text = _setup(tmp_path, repo="someone/agent-foundation-public")
    assert "土台の repo" in text and "someone/agent-foundation-public" in text, text
    f = Foundation(tmp_path / "fork")
    f.install()
    known = f.home / ".claude" / "plugins" / "known_marketplaces.json"
    data = json.loads(known.read_text(encoding="utf-8"))
    data["agent-foundation"]["source"]["repo"] = "someone/agent-foundation-public"
    known.write_text(json.dumps(data), encoding="utf-8")
    _commit(f.work, {"plugins/guard/x.py": "x\n"}, "fork で守りを変える")
    assert "土台が古いまま立った窓" not in f.hook("inject")
    assert f.hook("fresh") == ""                       # fork の main を正として引き継ぎを出さない


def test_土台の_repo_の名は_setup_script_の手本と同じ():
    """UPSTREAM は docs/核の届け方.md の setup script が足す目録の出所と同じ（2 つに分かれない）。"""
    doc = (ROOT / "docs" / "核の届け方.md").read_text(encoding="utf-8")
    block = re.search(r"<!-- setup-script.*?-->\s*```bash\n(.*?)\n\s*```", doc, re.S).group(1)
    assert set(re.findall(r"marketplace add (\S+)", block)) == {kaku.UPSTREAM}

