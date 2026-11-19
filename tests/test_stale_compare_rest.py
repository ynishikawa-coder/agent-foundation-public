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
    assert kaku.find_olds(work) == []
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


# ── checks（kaku_growth・pr_shape）は出所の今の main と比べる ──

def _checks_repo(tmp_path):
    """土台の checks の入口と道具を持つ作り物の repo。main で断片を足した後、手元の origin/main は fetch していない。"""
    import shutil
    remote, writer, work = tmp_path / "remote.git", tmp_path / "書く側", tmp_path / "枝"
    subprocess.run(["git", "init", "-q", "--bare", "-b", "main", str(remote)], check=True)
    subprocess.run(["git", "clone", "-q", str(remote), str(writer)], check=True, capture_output=True)
    for rel in ("scripts/pr_shape.py", "scripts/checks/pr_shape.sh"):
        (writer / rel).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(ROOT / rel, writer / rel)
    _commit(writer, {"CHANGELOG.d/20261118-mae.txt": "- 足した: 前\n", "tests/test_old.py": "def test_a():\n    pass\n"}, "始め")
    subprocess.run(["git", "clone", "-q", str(remote), str(work)], check=True, capture_output=True)
    _git(work, "checkout", "-q", "-b", "claude/20261119-eda")
    _commit(writer, {"CHANGELOG.d/20261119-hoka.txt": "- 足した: 他の PR\n"}, "他の PR が main に入る")
    _git(work, "config", "user.name", "t")
    _git(work, "config", "user.email", "t@example.invalid")
    _git(work, "merge", "-q", "--no-edit", "--no-ff", _fetch_tip(work))       # 枝が main を取り込む
    _git(work, "update-ref", "refs/remotes/origin/main", _git(work, "rev-parse", "HEAD~1"))  # 手元の origin/main を古く置く
    (work / "CHANGELOG.d" / "20261119-eda.txt").write_text("- 足した: 枝\n", encoding="utf-8")
    _git(work, "add", "-A")
    _git(work, "commit", "-qm", "枝の断片")
    return remote, work


def _fetch_tip(work):
    _git(work, "fetch", "-q", "origin", "main")
    return _git(work, "rev-parse", "FETCH_HEAD")


def _entries():
    """scripts/checks/ の入口のうち main と比べる物（--base か merge-base を持つ）。足した入口も自ずと入る。"""
    out = []
    for sh in sorted((ROOT / "scripts" / "checks").glob("*.sh")):
        code = [ln for ln in sh.read_text(encoding="utf-8").splitlines() if not ln.lstrip().startswith("#")]
        if any("--base" in ln or "merge-base" in ln for ln in code):
            out.append(sh.name)
    return out


ENTRIES = _entries()


def _entry(work, name):
    """入口 name を作り物の repo に置き、比べる元を読んだ後の本体（scripts/pr_shape.py 以外）は渡された引数を出す作り物にする。
    入口が出所に聞けない時に手元の main へ倒れて本体まで進めば、作り物が「本体に来た」と出す。"""
    import re
    import shutil
    sh = work / "scripts" / "checks" / name
    shutil.copy(ROOT / "scripts" / "checks" / name, sh)
    stubbed = False
    for rel in set(re.findall(r"python3 (\S+\.py)", sh.read_text(encoding="utf-8"))) - {"scripts/pr_shape.py"}:
        (work / rel).parent.mkdir(parents=True, exist_ok=True)
        (work / rel).write_text("import sys\nprint('本体に来た', *sys.argv[1:])\n", encoding="utf-8")
        stubbed = True
    env = dict(__import__("os").environ, GITHUB_EVENT_NAME="pull_request", GITHUB_HEAD_REF="claude/20261119-eda",
               PR_BODY="", PR_HEAD_SHA=_git(work, "rev-parse", "HEAD"))  # CI は event の head.sha を渡す
    return stubbed, subprocess.run(["bash", str(sh)], cwd=work, capture_output=True, text=True, env=env)


def test_main_と比べる_checks_の入口が揃っている():
    assert {"pr_shape.sh", "pr_writer.sh", "kaku_growth.sh"} <= set(ENTRIES), ENTRIES


@pytest.mark.parametrize("name", ENTRIES)
def test_手元の_origin_main_が古くても_checks_の入口は出所の今の_main_と比べる(tmp_path, name):
    """注入: 手元の origin/main を古く置く（main で他の PR の断片が足された後に fetch していない）→ 出所の今の main と比べる。"""
    remote, work = _checks_repo(tmp_path)
    tip = _git(remote, "rev-parse", "main")
    stubbed, r = _entry(work, name)
    out = r.stdout + r.stderr
    if stubbed:
        assert r.returncode == 0 and f"--base {tip}" in out, out
    else:
        assert r.returncode == 0 and "20261119-hoka" not in out, out


@pytest.mark.parametrize("name", ENTRIES)
def test_出所に出られなければ_checks_の入口は手元の_main_へ倒れず止まる(tmp_path, name):
    """注入: 出所が無くなる → 手元の origin/main・origin/HEAD で比べて進まず、出所を名指して 2 で止まる。"""
    remote, work = _checks_repo(tmp_path)
    remote.rename(tmp_path / "移した.git")
    _, r = _entry(work, name)
    out = r.stdout + r.stderr
    assert r.returncode == 2 and "出所" in out and "本体に来た" not in out, out


# ── changelog は main の first-parent で入った時で並べる ──

def _changelog():
    import importlib.util
    spec = importlib.util.spec_from_file_location("changelog_rest", ROOT / "scripts" / "changelog.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_枝だけに在る断片は入っていないと出し_入った時は合流の時(tmp_path):
    """注入: 枝で足した断片 → 「まだ入っていない」。合流した断片の時は枝で足した commit でなく main への合流の時。"""
    import os
    import shutil
    cl = _changelog()
    root = tmp_path / "r"
    root.mkdir()
    shutil.copy(ROOT / "CHANGELOG.md", root / "CHANGELOG.md")
    (root / "CHANGELOG.d").mkdir()
    shutil.copy(ROOT / "CHANGELOG.d" / cl.OLD_FILE, root / "CHANGELOG.d" / cl.OLD_FILE)

    def commit(msg, date):
        env = dict(os.environ, GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@example.invalid", GIT_COMMITTER_NAME="t",
                   GIT_COMMITTER_EMAIL="t@example.invalid", GIT_COMMITTER_DATE=date, GIT_AUTHOR_DATE=date)
        subprocess.run(["git", "-C", str(root), *msg], check=True, capture_output=True, env=env)

    commit(["init", "-q", "-b", "main"], "2026-11-01T00:00:00+09:00")
    commit(["add", "-A"], "2026-11-01T00:00:00+09:00")
    commit(["commit", "-qm", "base"], "2026-11-01T00:00:00+09:00")
    commit(["checkout", "-qb", "a"], "2026-11-02T00:00:00+09:00")
    (root / "CHANGELOG.d" / "20261102-a.txt").write_text("- 足した: a\n", encoding="utf-8")
    commit(["add", "-A"], "2026-11-02T00:00:00+09:00")
    commit(["commit", "-qm", "a"], "2026-11-02T00:00:00+09:00")
    commit(["checkout", "-q", "main"], "2026-11-05T00:00:00+09:00")
    commit(["merge", "-q", "--no-ff", "-m", "a を入れる", "a"], "2026-11-05T00:00:00+09:00")
    commit(["checkout", "-qb", "b"], "2026-11-06T00:00:00+09:00")
    (root / "CHANGELOG.d" / "20261106-b.txt").write_text("- 足した: b\n", encoding="utf-8")
    commit(["add", "-A"], "2026-11-06T00:00:00+09:00")
    commit(["commit", "-qm", "b"], "2026-11-06T00:00:00+09:00")
    got = {n: when for n, when, _ in cl.entries(root)}
    assert got["20261106-b.txt"] == "まだ入っていない", got
    assert got["20261102-a.txt"].startswith("2026-11-05"), got


# ── session-watch は入った版の隣を読む ──

def test_版の合う隣が無ければ_mtime_の新しい版を拾わず名指す(tmp_path, monkeypatch):
    """注入: 入った版と違う版の guard だけを置く → 拾わず None（check は neighbor の札で名指す）。"""
    import importlib.util
    spec = importlib.util.spec_from_file_location("sw_rest", ROOT / "plugins" / "session-watch" / "scripts" / "session_watch.py")
    sw = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(sw)
    cache = tmp_path / "plugins" / "cache" / "mk"
    sw_root = cache / "session-watch" / "aaaaaaaaaaaa"
    (sw_root / "scripts").mkdir(parents=True)
    other = cache / "guard" / "bbbbbbbbbbbb" / "scripts"
    other.mkdir(parents=True)
    (other / "ask_shape.py").write_text("X = 1\n", encoding="utf-8")
    mk = tmp_path / "plugins" / "marketplaces" / "mk"
    (mk / "plugins" / "guard" / "scripts").mkdir(parents=True)
    (mk / "plugins" / "guard" / "scripts" / "ask_shape.py").write_text("X = 2\n", encoding="utf-8")  # 版の違う市場の写し
    monkeypatch.setattr(sw, "PLUGIN_ROOT", str(sw_root))
    assert sw.neighbor_path("ask_shape", {}) is None
