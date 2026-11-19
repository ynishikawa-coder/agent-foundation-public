"""古い土台の判定が比べる物（先端・範囲・入った版）を取り違えない（原因の台帳の束 F2 の 17 行）。

どの試験も、その行の誤り（手近な物で比べる形）をわざと入れた場で、正本と比べた答えになるかを見る。
remote・目録の clone・入った台帳は作り物（鍵も外の網も要らない）。
"""
from __future__ import annotations

import importlib.util
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from test_core_plugin import PLUGIN, Foundation, _commit, _git, catalog_commit, kaku, run
from test_setup_plugins import foundation, run as run_entry
from entry_box import box_env

ROOT = Path(__file__).resolve().parent.parent
sys.dont_write_bytecode = True


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _ledger(home, rows):
    p = home / ".claude" / "plugins" / "installed_plugins.json"
    p.write_text(json.dumps({"version": 2, "plugins": rows}), encoding="utf-8")


def _row(path, sha, updated="2026-11-19T11:57:05.000Z", scope="user"):
    r = {"installPath": str(path), "gitCommitSha": sha, "lastUpdated": updated}
    if scope:
        r["scope"] = scope
    return r


# ── 窓の起動の知らせ（土台の新しさ）: plugin ごとの入った版・出所へ直に聞く先端 ──

def test_core_だけ先端に揃い_guard_が古い窓を古くないと見ない(tmp_path, monkeypatch):
    """注入: core は先端・guard は前の版のまま（入れ直しが失敗）→ guard を古いと名指す（core の版で全部を決めない）。"""
    f = Foundation(tmp_path)
    old = f.installed
    tip = _commit(f.work, {"plugins/guard/x.py": "x\n"}, "守りを変える")
    f.installed = tip
    f.install()
    guard_dir = tmp_path / "cache-guard"
    guard_dir.mkdir()
    _ledger(f.home, {"core@agent-foundation": [_row(PLUGIN, tip)],
                     "guard@agent-foundation": [_row(guard_dir, old)]})
    monkeypatch.setenv("HOME", str(f.home))
    got = kaku.freshness()
    assert got["plugins"] == ["guard"] and got["main"] == tip, got


def test_共用の_FETCH_HEAD_を並ぶ窓が書き換えても先端を取り違えない(tmp_path, monkeypatch):
    """注入: 取って来た直後に FETCH_HEAD を別の commit に書き換える（並ぶ窓の fetch）→ 先端は出所の今の main。"""
    f = Foundation(tmp_path)
    f.install()
    tip = _commit(f.work, {"plugins/guard/x.py": "x\n"}, "守りを変える")
    monkeypatch.setenv("HOME", str(f.home))
    real = kaku._git

    def racing(loc, *args, **kw):
        out = real(loc, *args, **kw)
        if args and args[0] == "fetch":
            (Path(loc) / ".git" / "FETCH_HEAD").write_text(f"{f.installed}\t\t'別の物' of x\n")
        return out

    monkeypatch.setattr(kaku, "_git", racing)
    got = kaku.freshness()
    assert got["main"] == tip and "guard" in got["plugins"], got


def test_枝で入れた目録はその枝の先端と比べる(tmp_path, monkeypatch):
    """注入: 目録を repo#枝 で入れ（plugin-smoke の形）、main だけ先へ進める → 枝の先端と同じなので古くない。"""
    f = Foundation(tmp_path)
    _git(f.work, "push", "-q", "origin", "HEAD:refs/heads/試す枝")
    f.install()
    known = f.home / ".claude" / "plugins" / "known_marketplaces.json"
    data = json.loads(known.read_text())
    data["agent-foundation"]["source"]["ref"] = "試す枝"
    known.write_text(json.dumps(data))
    _commit(f.work, {"plugins/guard/x.py": "x\n"}, "main だけ進む")
    monkeypatch.setenv("HOME", str(f.home))
    got = kaku.freshness()
    assert got["plugins"] == [] and got["ref"] == "試す枝", got


def test_入口は枝で入れた目録の_setup_の時の先端を枝から読む(tmp_path):
    root = foundation(tmp_path, ["core"])
    up = tmp_path / "upstream"
    subprocess.run(["git", "-C", str(up), "branch", "試す枝"], check=True)
    subprocess.run(["git", "-C", str(up), "-c", "user.name=t", "-c", "user.email=t@example.invalid", "commit", "-q",
                    "--allow-empty", "-m", "main だけ進む"], check=True)
    home = tmp_path / "home"
    known = home / ".claude" / "plugins" / "known_marketplaces.json"
    known.parent.mkdir(parents=True)
    known.write_text(json.dumps({"agent-foundation": {"source": {"source": "github", "repo": "o/r", "ref": "試す枝"},
                                                      "installLocation": str(root)}}))
    run_entry(tmp_path, root)
    rec = json.loads((home / ".claude" / "af-foundation" / "setup.json").read_text())
    branch = subprocess.run(["git", "-C", str(up), "rev-parse", "試す枝"], capture_output=True, text=True).stdout.strip()
    assert rec["main_at_setup"] == branch, rec


# ── 窓の起動の知らせ（土台の入れ方）: 台帳の行の選び方・名簿の版 ──

def test_user_の行が複数ある時は最後に入れた行で記録の後の入れ直しを見る(tmp_path, monkeypatch):
    """注入: 古い行を前に、記録の後に入れ直した行を後に置く → 入口を通らない入れ直しを名指す（最初の行で見逃さない）。"""
    loc = tmp_path / "loc"
    (loc / ".claude-plugin").mkdir(parents=True)
    (loc / ".claude-plugin" / "marketplace.json").write_text(json.dumps({"name": "agent-foundation", "plugins": []}))
    sha = catalog_commit(loc)
    home = tmp_path / "home"
    (home / ".claude" / "plugins").mkdir(parents=True)
    other = tmp_path / "前の dir"
    other.mkdir()
    _ledger(home, {"core@agent-foundation": [_row(other, sha, "2026-11-19T10:00:00.000Z"),
                                             _row(PLUGIN, sha, "2026-11-19T13:00:00.000Z")]})
    (home / ".claude" / "af-foundation").mkdir(parents=True)
    (home / ".claude" / "af-foundation" / "setup.json").write_text(json.dumps(
        {"catalog_sha": sha, "at": "2026-11-19T11:00:00+0000"}))
    monkeypatch.setenv("HOME", str(home))
    assert kaku._foundation_rows()["core"]["installPath"] == str(PLUGIN)
    state, why = kaku.setup_record()
    assert state is None and "入れ直した" in why


def test_scope_の欄が無い行を_user_と見ない(tmp_path, monkeypatch):
    home = tmp_path / "home"
    (home / ".claude" / "plugins").mkdir(parents=True)
    _ledger(home, {"guard@agent-foundation": [_row(tmp_path, "a" * 40, scope=None)]})
    monkeypatch.setenv("HOME", str(home))
    assert kaku.user_rows() == {} and kaku._foundation_rows() == {}


def test_入っていない_plugin_は_setup_が入れた版の名簿で見る(tmp_path):
    """注入: setup の後に目録の clone の作業の木が進み、名簿に plugin が足された → 「入っていない」と言わない。"""
    home = tmp_path / "home"
    loc = home / ".claude" / "plugins" / "marketplaces" / "agent-foundation"
    (loc / ".claude-plugin").mkdir(parents=True)
    manifest = loc / ".claude-plugin" / "marketplace.json"
    manifest.write_text(json.dumps({"name": "agent-foundation", "plugins": [{"name": "core"}]}))
    sha = catalog_commit(loc)
    manifest.write_text(json.dumps({"name": "agent-foundation", "plugins": [{"name": "core"}, {"name": "後で足した"}]}))
    (home / ".claude" / "plugins" / "known_marketplaces.json").write_text(json.dumps({"agent-foundation": {
        "source": {"source": "github", "repo": kaku.UPSTREAM}, "installLocation": str(loc)}}))
    _ledger(home, {"core@agent-foundation": [_row(PLUGIN, sha)]})
    (home / ".claude" / "settings.json").write_text(json.dumps({"enabledPlugins": {"core@agent-foundation": True}}))
    (home / ".claude" / "af-foundation").mkdir(parents=True)
    (home / ".claude" / "af-foundation" / "setup.json").write_text(json.dumps(
        {"catalog_sha": sha, "at": "2026-11-19T20:57:09+0900", "refreshed": True, "stale": []}))
    r = run("inject", project=tmp_path / "proj", home=home)
    ctx = json.loads(r.stdout)["hookSpecificOutput"]["additionalContext"]
    assert "後で足した" not in ctx and "入れ方が古い" not in ctx, ctx


# ── 土台の入れ方（setup の入口）: 入口の在り処が目録の clone か ──

def test_入口を開発の_checkout_から回しても名簿の版は目録の_clone_から読む(tmp_path):
    """注入: 目録の clone と別の dir（HEAD の違う開発の checkout）から入口を回す → clone の入口へ移り、clone の版を記録する。"""
    root = foundation(tmp_path, ["core"])
    dev = tmp_path / "開発"
    shutil.copytree(root, dev)
    subprocess.run(["git", "-C", str(dev), "-c", "user.name=t", "-c", "user.email=t@example.invalid", "commit", "-q",
                    "--allow-empty", "-m", "作業の枝"], check=True)
    head = lambda d: subprocess.run(["git", "-C", str(d), "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()  # noqa: E731
    assert head(dev) != head(root)
    fake = tmp_path / "claude"
    run_entry(tmp_path, root)  # 目録の登録と偽の claude を置く（clone から 1 回入れる）
    env = dict(os.environ, HOME=str(tmp_path / "home"), CLAUDE_BIN=str(fake), FAKE_LOG=str(tmp_path / "log"),
               FAKE_BROKEN="", FAKE_ROOT=str(root))
    subprocess.run([sys.executable, str(dev / "scripts" / "setup_plugins.py")], capture_output=True, text=True,
                   env=env, timeout=60)
    rec = json.loads((tmp_path / "home" / ".claude" / "af-foundation" / "setup.json").read_text())
    assert rec["catalog_sha"] == head(root), rec


# ── 本物の claude で入れる試験（plugin-smoke）・写しの見張り ──

def test_plugin_smoke_は台帳の最初の行でなく今読まれる行を読む(tmp_path):
    smoke = _load("af_smoke_f2", ROOT / "scripts" / "plugin_smoke.py")
    gone, live = tmp_path / "消えた版", tmp_path / "今の版"
    live.mkdir()
    table = {"plugins": {"core@agent-foundation": [_row(gone, "a" * 40, "2026-11-19T12:00:00Z"),
                                                   _row(live, "b" * 40, "2026-11-19T11:00:00Z")]}}
    assert smoke.installed_rows(table)["core"]["gitCommitSha"] == "b" * 40


def test_写しの見張りは_cache_に残る前の版の_SKILL_を正本と見ない(tmp_path):
    """注入: cache に前の版の guard の SKILL（もう土台に無い文）を残す → その文の写しを赤にしない。今の版の文は赤にする。"""
    cache = tmp_path / "plugins" / "cache" / "agent-foundation"
    core = cache / "core" / "v2"
    shutil.copytree(PLUGIN, core)
    old_text = "古い版にだけ在った決まりの文で、もう土台のどこにも無い言い回しをここに長く書いておく。\n"
    new_text = "窓を閉じる前に枝へ押し、親へ URL を返してから題を付け替えること（今の版だけの手順）。\n"
    for ver, text in (("v1", old_text), ("v2", new_text)):
        (cache / "guard" / ver / "skills" / "a").mkdir(parents=True)
        (cache / "guard" / ver / "skills" / "a" / "SKILL.md").write_text(text, encoding="utf-8")
    home = tmp_path / "home"
    (home / ".claude" / "plugins").mkdir(parents=True)
    _ledger(home, {"core@agent-foundation": [_row(core, "b" * 40)],
                   "guard@agent-foundation": [_row(cache / "guard" / "v2", "b" * 40)]})
    tool = core / "scripts" / "copies.py"
    env = dict(os.environ, HOME=str(home))
    for text, code in ((old_text, 0), (new_text, 1)):
        target = tmp_path / "CLAUDE.md"
        target.write_text(text, encoding="utf-8")
        r = subprocess.run([sys.executable, str(tool), str(target)], capture_output=True, text=True, env=env)
        assert r.returncode == code, r.stdout


# ── 守りの hook（外へ出す文の照らし）: 入った guard と同じ版の土台の file ──

def test_guard_は先へ進んだ目録の_clone_でなく入った版の_public_guard_を読む(tmp_path):
    plugins = tmp_path / "plugins"
    clone = plugins / "marketplaces" / "market"
    (clone / "public-guard").mkdir(parents=True)
    (clone / "public-guard" / "guard.py").write_text("入った版\n", encoding="utf-8")
    ver = catalog_commit(clone)[:12]
    (clone / "public-guard" / "guard.py").write_text("先へ進んだ版\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(clone), "-c", "user.name=t", "-c", "user.email=t@example.invalid", "commit", "-qam",
                    "進む"], check=True)
    guard_root = plugins / "cache" / "market" / "guard" / ver
    guard_root.mkdir(parents=True)
    sys.path.insert(0, str(ROOT / "plugins" / "guard" / "scripts"))
    try:
        import guard_common as G
    finally:
        sys.path.pop(0)
    path = G.foundation_file(os.path.join("public-guard", "guard.py"), str(guard_root))
    assert Path(path).read_text(encoding="utf-8") == "入った版\n", path


# ── 書いた窓の照らし・検査の入口: PR の先端は event の head ──

def _event(tmp_path, head):
    p = tmp_path / "event.json"
    p.write_text(json.dumps({"pull_request": {"head": {"sha": head}}}))
    return p


def test_PR_の先端は_PR_HEAD_SHA_が空でも_HEAD_でなく_event_の_head(tmp_path):
    shape = [sys.executable, str(ROOT / "scripts" / "pr_shape.py"), "--print-head"]
    env = {k: v for k, v in os.environ.items() if k not in ("PR_HEAD_SHA", "GITHUB_EVENT_PATH")}
    r = subprocess.run(shape, capture_output=True, text=True, env=dict(env, PR_HEAD_SHA=""))
    assert r.returncode == 3 and not r.stdout.strip()  # 分からなければ HEAD で代えない
    r = subprocess.run(shape, capture_output=True, text=True,
                       env=dict(env, PR_HEAD_SHA="", GITHUB_EVENT_PATH=str(_event(tmp_path, "c" * 40))))
    assert r.stdout.strip() == "c" * 40
    assert ":-HEAD" not in (ROOT / "scripts" / "checks" / "pr_writer.sh").read_text(encoding="utf-8")


def test_check_all_の回した先端は_CI_の_PR_では_PR_の先端(tmp_path):
    """注入: CI の PR（HEAD は main と合わせた merge の commit）→ 結果の行の先端は PR の先端で、merge の commit も添える。"""
    repo = tmp_path / "r"
    (repo / "scripts").mkdir(parents=True)
    shutil.copy2(ROOT / "scripts" / "check_all.sh", repo / "scripts" / "check_all.sh")
    shutil.copy2(ROOT / "scripts" / "pr_shape.py", repo / "scripts" / "pr_shape.py")
    (repo / "scripts" / "pytest.sh").write_text("echo '1 passed'\n", encoding="utf-8")
    (repo / "tests").mkdir()
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", "merge の代わり")
    merge = _git(repo, "rev-parse", "HEAD")
    r = subprocess.run(["bash", "scripts/check_all.sh"], cwd=repo, capture_output=True, text=True,
                       env=box_env(GITHUB_EVENT_NAME="pull_request", PR_HEAD_SHA="d" * 40))
    last = r.stdout.strip().splitlines()[-1]
    assert f"@{'d' * 12}" in last and merge[:12] in last and "PR の先端" in last, last


# ── レビューの窓: 比べる元は出所の今の main ──

def test_書いた窓の組は古い手元の_origin_main_でなく出所の今の_main_と比べる(tmp_path):
    """注入: 手元の origin/main を古く置き、main に別の窓の commit を入れる → その窓を書いた窓に数えない。"""
    up = tmp_path / "up.git"
    subprocess.run(["git", "init", "-q", "--bare", "-b", "main", str(up)], check=True)
    work = tmp_path / "work"
    subprocess.run(["git", "clone", "-q", str(up), str(work)], check=True, capture_output=True)
    old = _commit(work, {"a.md": "1\n"}, "始め")
    _commit(work, {"b.md": "1\n"}, "main の物\n\nClaude-Session: https://x/session_MAINX")
    _git(work, "checkout", "-q", "-b", "claude/20261120-x")
    _git(work, "commit", "-q", "--allow-empty", "-m", "枝の物\n\nClaude-Session: https://x/session_BRANCHY")
    head = _git(work, "rev-parse", "HEAD")
    _git(work, "update-ref", "refs/remotes/origin/main", old)  # 注入: 手元の origin/main は古い
    tool = ROOT / "plugins" / "checker" / "scripts" / "pr_writer.py"
    r = subprocess.run([sys.executable, str(tool), "--writers", "--head", head, "--repo", str(work)],
                       capture_output=True, text=True)
    assert r.returncode == 0 and r.stdout.strip() == "session_BRANCHY", r.stdout + r.stderr
    assert "--base origin/main" not in (ROOT / "plugins" / "checker" / "skills" / "review-pr" / "SKILL.md").read_text(
        encoding="utf-8")


# ── 問いのページ（qa-html）: 今読まれる 1 つ ──

def test_qa_html_の在り処は台帳の最初の行でなく_claude_が今読む行():
    text = (ROOT / "plugins" / "docs-kit" / "skills" / "qa-html" / "SKILL.md").read_text(encoding="utf-8")
    line = next(ln for ln in text.splitlines() if ln.strip().startswith("- 窓の中:"))
    assert "claude plugin list --json" in line and "installPath" in line
    assert "の `docs-kit@<市場>` の `installPath`（今入っている 1 つ）" not in line


# ── PR の衝突の知らせ: 同じ物差し・同じ base ──

def test_違う時期に切った_PR_の行番号を今の先端の物差しへ写して重なりを見る(monkeypatch, capsys):
    po = _load("af_overlap_f2", ROOT / "scripts" / "pr_overlap.py")
    # 自分は今の先端から切った（40 行目を直す）。#5 は main が頭に 30 行足す前に切った（10 行目＝今の 40 行目を直す）。
    # #6 は別の base の枝へ出す PR（同じ行でも数えない）。
    api = {
        "pulls/1": {"base": {"ref": "main"}, "head": {"sha": "h1"}},
        "branches/main": {"commit": {"sha": "T"}},
        "pulls?state=open&per_page=100": [{"number": 1, "base": {"ref": "main"}},
                                          {"number": 5, "base": {"ref": "main"}},
                                          {"number": 6, "base": {"ref": "release"}}],
        "compare/T...h1": {"merge_base_commit": {"sha": "T"}, "files": [{"filename": "f.md", "patch": "@@ -40,2 +40,2 @@\n"}]},
        "compare/T...h5": {"merge_base_commit": {"sha": "M"}, "files": [{"filename": "f.md", "patch": "@@ -10,2 +10,2 @@\n"}]},
        "compare/M...T": {"merge_base_commit": {"sha": "M"}, "files": [{"filename": "f.md", "patch": "@@ -0,0 +1,30 @@\n"}]},
        "compare/T...h6": {"merge_base_commit": {"sha": "T"}, "files": [{"filename": "f.md", "patch": "@@ -40,2 +40,2 @@\n"}]},
    }
    api["pulls?state=open&per_page=100"][1]["head"] = {"sha": "h5"}
    api["pulls?state=open&per_page=100"][2]["head"] = {"sha": "h6"}
    monkeypatch.setattr(po, "_get", lambda url, token: api[url.split("/repos/o/r/", 1)[1]])
    monkeypatch.setenv("GITHUB_TOKEN", "作り物")
    assert po.main(["--repo", "o/r", "--pr", "1"]) == 0
    out = capsys.readouterr().out
    assert "#5" in out and "#6" not in out, out
    # 写さずに比べると（分かれ目の物差しのまま）10 行目と 40 行目で重ならない＝見落とす
    assert po.overlaps({"f.md": "@@ -40,2 +40,2 @@\n"}, {"#5": {"f.md": "@@ -10,2 +10,2 @@\n"}}) == []


# ── 公開の検査: PR の範囲・手元の範囲 ──

def test_PR_の範囲は_event_の時の_base_でなく_base_の枝の今の先端から(tmp_path):
    """注入: event の base.sha を古く置き、枝は後の main（鍵を足して消した commit を含む）を取り込む → main の commit を照らさない。"""
    from test_guard_local_range_fresh_main import TOKEN, commit, git
    up = tmp_path / "up.git"
    git(tmp_path, "init", "-q", "--bare", "-b", "main", str(up))
    work = tmp_path / "work"
    git(tmp_path, "clone", "-q", str(up), str(work))
    old = commit(work, "README.md", "見本\n", "base")
    git(work, "push", "-q", "origin", "HEAD:main")
    git(work, "checkout", "-q", "-b", "claude/20261120-x")
    commit(work, "b.md", "枝の物\n", "枝で足した")
    git(work, "checkout", "-q", "main")
    commit(work, "a.md", f"鍵 {TOKEN}\n", "main で足した")
    commit(work, "a.md", None, "main で消した")
    git(work, "push", "-q", "origin", "HEAD:main")
    git(work, "checkout", "-q", "claude/20261120-x")
    git(work, "merge", "-q", "--no-edit", "main")
    head = git(work, "rev-parse", "HEAD")
    pg = _load("af_pg_f2", ROOT / "public-guard" / "guard.py")
    event = {"pull_request": {"title": "t", "body": "b", "base": {"sha": old, "ref": "main"}, "head": {"sha": head}}}
    env = {k: os.environ.get(k) for k in ("AF_DENY_WORDS", "AF_DENY_WORDS_FILE", "AF_DENY_BUNDLE")}
    try:
        for k in env:
            os.environ.pop(k, None)
        hits = pg.run(work, None, None, [], event=event)
    finally:
        for k, v in env.items():
            if v is not None:
                os.environ[k] = v
    assert not any("GitHub のトークン" in h for h in hits), hits


def test_手元の範囲の元を取っても手元の_origin_main_を書き換えない(tmp_path):
    from test_guard_local_range_fresh_main import guard, setup
    work, old = setup(tmp_path)
    r = guard(work)
    # 当たりは 0（手元は PR の題・本文を照らさないので exit 3＝照らしていない）
    assert r.returncode == 3 and "当たりは 0" in r.stdout, r.stdout + r.stderr
    assert _git(work, "rev-parse", "refs/remotes/origin/main") == old


# ── 直す人の手順: 取り込む main は取り直した物 ──

@pytest.mark.parametrize("doc", ["CONTRIBUTING.md", "CHANGELOG.d/README.md"])
def test_手順は_fetch_せずに手元の_origin_main_を取り込まない(doc):
    text = (ROOT / doc).read_text(encoding="utf-8")
    for line in text.splitlines():
        if "git merge origin/main" in line:
            assert "git fetch origin main && git merge origin/main" in line, line
    assert "git checkout origin/main" not in text


def test_出所にも手元の_origin_main_にも元が無ければ照らさず止める(tmp_path):
    from test_guard_local_range_fresh_main import git, guard, setup
    work, _ = setup(tmp_path)
    git(work, "remote", "set-url", "origin", str(tmp_path / "無い出所.git"))
    git(work, "update-ref", "-d", "refs/remotes/origin/main")
    r = guard(work)
    assert r.returncode == 2 and "照らせない" in r.stdout, r.stdout + r.stderr
    assert "置かない物 0" not in r.stdout
