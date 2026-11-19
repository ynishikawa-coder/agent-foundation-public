"""workflow と取り出しの URL を「当の物だけ」で読むか（注入の試験）。読み手の正本は public-guard/workflow_reader.py 1 本で、
守りの hook（plugins/guard/scripts/pr_text.py）・見回り（public-guard/patrol.py）・手元の検査（scripts/checks/public_guard.sh）は
皆それを通して読む。直す前の形（URL の末尾の比べ・名の順で最初の workflow だけ・file 全体の text からの findall・
ci.yml の値の手の写し）を戻すと、ここの試験が赤になる。

1. 取り出しの origin の URL を owner/repo に読み、名の全体で比べる（ssh の形・末尾の .git や / でも同じ repo）
2. 公開の見分けは PR・push で走る呼び口だけを数え（workflow_dispatch だけ・if: false の job は数えない）、語の表は全部の和
3. 見回りは job public-guard の step の、PR・push で走る呼び口だけを数える（コメントの行・run: の字・別の job の step は数えない）
4. 手元の検査は ci.yml の job public-guard の呼び口の with: から guard.py の値を読む（ci.yml を直せば手元も変わる）
"""
import base64
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "plugins" / "guard" / "scripts"))
sys.path.insert(0, str(ROOT / "public-guard"))
import patrol  # noqa: E402
import pr_text as P  # noqa: E402
import workflow_reader as W  # noqa: E402

# 作り物の箱と GitHub の道具の入力（守りの hook の入口から当てる）は test_pr_text の物を共に使う
from test_pr_text import MAIL, PUBLIC_WORD, _fake_public_repo, deny_reason, env, gh  # noqa: E402,F401

F = W.FOUNDATION
CALL = "uses: %s/public-guard@main" % F
HEAD = "on: [pull_request]\n"


def whole(frag):
    """step の断片を、PR で走る workflow の job j の steps に包む（読み手は job の steps の中の step だけを数える）。"""
    if frag.startswith(("jobs:", "env:", "on:")):
        return frag if frag.startswith("on:") else HEAD + frag
    if frag.lstrip(" ").startswith("steps:"):
        return HEAD + "jobs:\n  j:\n" + frag
    return HEAD + "jobs:\n  j:\n    steps:\n" + frag


def _wf(on, job_if="", step_if="", job="public-guard", words="", extra_jobs=""):
    s = "name: x\non:%s\njobs:\n  %s:\n    name: %s\n    runs-on: ubuntu-latest\n" % (on, job, job)
    if job_if:
        s += "    if: %s\n" % job_if
    s += "    steps:\n      - uses: actions/checkout@v4\n      - %s\n" % CALL
    if step_if:
        s += "        if: %s\n" % step_if
    if words:
        s += "        with:\n          deny-words-file: %s\n" % words
    return s + extra_jobs


# ── 読み手そのもの ──
@pytest.mark.parametrize("on,want", [
    (" push", {"push"}),
    (" [push, workflow_dispatch]", {"push", "workflow_dispatch"}),
    ("\n  pull_request:\n    types: [opened]\n  schedule:\n    - cron: '0 0 * * *'", {"pull_request", "schedule"}),
    (" {merge_group: {}, workflow_dispatch: {}}", {"merge_group", "workflow_dispatch"}),
    ("\n  workflow_dispatch:", {"workflow_dispatch"}),
])
def test_起こり方はどの書き方でも読む(on, want):
    assert W.triggers(W.load("on:%s\njobs: {}\n" % on)) == want


@pytest.mark.parametrize("cond,want", [("false", True), ("${{ false }}", True), ("${{false}}", True), ("'false'", True),
                                       ("FALSE", True), ("github.event_name == 'push'", False), ("", False),
                                       ("${{ false || true }}", False)])
def test_if_は字どおりの_false_だけを走らない物と見る(cond, want):
    wf = W.load("on: push\njobs:\n  a:\n    if: %s\n    steps: []\n" % cond if cond else "on: push\njobs:\n  a:\n    steps: []\n")
    assert W.literal_false(wf["jobs"]["a"].get("if", "")) is want


@pytest.mark.parametrize("text", ["a: {x: ]}", "a: [x, }]", "a: {: }", "- - x\n", "jobs:\n  a:\n  steps: [", "on: ['push\n",
                                  "jobs:\n    a:\n  b:\n      - c\n"])
def test_崩れた形でも止まらず読める所まで読む(text):
    assert isinstance(W.load(text), dict) and W.calls(text, F) == []


def test_土台の_ci_yml_を_job_と_step_の形で読む():
    wf = W.load((ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8"))
    assert {"push", "pull_request"} <= W.triggers(wf)
    assert "public-guard" in wf["jobs"] and isinstance(wf["jobs"]["check"]["steps"], list)
    run = [s for s in wf["jobs"]["check"]["steps"] if s.get("name") == "試験の道具を入れる"][0]["run"]
    assert run.startswith("python3 -m pip install") and "\n" in run       # | の塊は字のまま（中の行を鍵と見ない）
    (c,) = W.counted((ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8"), F)
    assert c.check == "public-guard" and c.local and c.inputs["checkout"] == "false"


def test_読み手は1本_守りの_hook_と見回りは同じ物を読む():
    """同じ見分けの 2 つ目の実装を持たない（直す前は pr_text と patrol がそれぞれ正規表現で拾っていた）。"""
    assert Path(P._reader().__file__).resolve() == Path(W.__file__).resolve() == Path(patrol.W.__file__).resolve()
    for gone in ("USES", "DENY_KEY", "_steps", "_own", "public_guard_steps", "deny_words_file"):
        assert not hasattr(P, gone), gone
    for gone in ("CALL", "LOCAL_CALL"):
        assert not hasattr(patrol, gone), gone
    assert P._foundation() == patrol.FOUNDATION == F


# ── 1. 取り出しの URL ──
@pytest.mark.parametrize("url", [
    "https://github.com/fake-owner/fake-public",
    "https://github.com/fake-owner/fake-public.git",
    "https://github.com/fake-owner/fake-public/",
    "https://github.com/fake-owner/fake-public.git/",
    "https://x-access-token:t" + "@" + "github.com/fake-owner/fake-public.git",
    "git" + "@" + "github.com:fake-owner/fake-public.git",                 # scp の形の ssh
    "git" + "@" + "github.com:fake-owner/fake-public",
    "ssh://git" + "@" + "github.com/fake-owner/fake-public.git",
    "ssh://git" + "@" + "github.com:22/fake-owner/fake-public",
    "HTTPS://GitHub.com/Fake-Owner/Fake-Public.git",                       # GitHub の名は大小を問わない
])
def test_取り出しの_URL_を_owner_repo_に読む(url):
    assert P.github_repo(url).lower() == "fake-owner/fake-public"


@pytest.mark.parametrize("url", [
    "https://gitlab.com/fake-owner/fake-public.git",                       # github.com でない
    "https://github.com.example.com/fake-owner/fake-public",
    "https://github.com/other/fake-owner/fake-public",                     # 名を道に含む別の物
    "/srv/git/fake-owner/fake-public.git",
    "",
])
def test_github_の_repo_でない_URL_は読まない(url):
    assert P.github_repo(url) == ""


def _raw_remote(env):
    """git の URL の書き替え（insteadOf を環境で渡す窓がある）を外し、remote の URL を置いたままの形で読ませる。"""
    for k in [k for k in env if k.startswith("GIT_CONFIG")]:
        del env[k]
    env.update({"GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": os.devnull})


@pytest.mark.parametrize("url", [
    "git" + "@" + "github.com:fake-owner/fake-public.git",
    "ssh://git" + "@" + "github.com/fake-owner/fake-public",
    "https://github.com/fake-owner/fake-public/",
])
def test_ssh_の取り出しでも公開の_repo_と見分けて照らす(env, url):  # noqa: F811
    """注入: 直す前（URL の末尾を "/" + repo で比べる）は scp の形・末尾の / で取り出しを見落とし、照らさずに通していた。"""
    _raw_remote(env)
    _fake_public_repo(Path(env["CLAUDE_PROJECT_DIR"]), PUBLIC_WORD, url=url)
    why = deny_reason(env, gh("add_issue_comment", issue_number=1, body="連絡は %s へ" % MAIL, repo="fake-public"))
    assert "[public]" in why


@pytest.mark.parametrize("url", ["https://github.com/fake-owner/fake-public-fork.git",
                                 "git" + "@" + "github.com:x-fake-owner/fake-public.git",
                                 "https://gitlab.example.com/fake-owner/fake-public.git"])   # github.com でない（直す前は末尾だけで当てた）
def test_似た名の取り出しは別の_repo(env, url):  # noqa: F811
    _raw_remote(env)
    _fake_public_repo(Path(env["CLAUDE_PROJECT_DIR"]), PUBLIC_WORD, url=url)
    assert deny_reason(env, gh("add_issue_comment", issue_number=1, body="連絡は %s へ" % MAIL, repo="fake-public")) == ""


# ── 2. 公開の見分けと語の表（守りの hook） ──
def _put_workflows(proj, files):
    d = proj / ".github" / "workflows"
    for f in d.glob("*.y*ml"):
        f.unlink()
    for name, text in files.items():
        (d / name).write_text(text, encoding="utf-8")


def _mail(env):
    return deny_reason(env, gh("add_issue_comment", issue_number=1, body="連絡は %s へ" % MAIL, repo="fake-public"))


@pytest.mark.parametrize("files", [
    {"a.yml": _wf(" [workflow_dispatch]")},                                           # 手で回すだけ
    {"a.yml": _wf("\n  schedule:\n    - cron: '0 0 * * *'\n  workflow_dispatch:")},  # 決まった時と手だけ
    {"a.yml": _wf(" [pull_request]", job_if="false")},                                # job が走らない
    {"a.yml": _wf(" [pull_request]", job_if="${{ false }}")},
    {"a.yml": _wf(" [pull_request]", step_if="false")},                               # step が走らない
    {"a.yml": "on: [pull_request]\njobs:\n  a:\n    steps:\n      - run: |\n          %s\n" % CALL},  # run の字
])
def test_PR_push_で走らない呼び口は公開と数えない(env, files):  # noqa: F811
    """注入: 直す前は on: と if: を見ず、workflow_dispatch だけ・if: false の呼び口でも公開と見て照らしていた。"""
    proj = Path(env["CLAUDE_PROJECT_DIR"])
    _fake_public_repo(proj, PUBLIC_WORD)
    _put_workflows(proj, files)
    assert _mail(env) == ""
    _put_workflows(proj, {"a.yml": _wf(" [push]")})                                   # 対照: push で走れば公開
    assert "[public]" in _mail(env)


def test_呼ぶ_workflow_が2つなら両方の語の表で照らす(env):  # noqa: F811
    """注入: 直す前は名の順で最初の workflow の語の表だけを渡し、2 つ目の workflow の表の語を通していた。"""
    proj = Path(env["CLAUDE_PROJECT_DIR"])
    _fake_public_repo(proj, PUBLIC_WORD)
    other = "作り物" + "ノ別ノ禁句"
    (proj / "data" / "other.txt").write_text(other + "\n", encoding="utf-8")
    _put_workflows(proj, {"a.yml": _wf(" [pull_request]", words="data/deny.txt"),
                          "b.yml": _wf(" [push]", job="second", words="data/other.txt")})
    for word in (PUBLIC_WORD, other):
        why = deny_reason(env, gh("update_pull_request", pullNumber=1, title="%s の直し" % word, repo="fake-public"))
        assert "[public]" in why and "置かない語" in why, word
    assert deny_reason(env, gh("update_pull_request", pullNumber=1, title="作り物の直し", repo="fake-public")) == ""


def test_名の順で先の_workflow_が数えない呼び口なら後の_workflow_の表で照らす(env):  # noqa: F811
    """注入: 直す前は手で回すだけの a.yml（表なし）を先に拾い、PR で走る b.yml の表を見なかった。"""
    proj = Path(env["CLAUDE_PROJECT_DIR"])
    _fake_public_repo(proj, PUBLIC_WORD)
    _put_workflows(proj, {"a.yml": _wf(" [workflow_dispatch]"),
                          "b.yml": _wf(" [pull_request]", words="data/deny.txt")})
    why = deny_reason(env, gh("update_pull_request", pullNumber=1, title="%s の直し" % PUBLIC_WORD, repo="fake-public"))
    assert "[public]" in why


def test_2つ目の表が無ければ照らせないと名指す(env):  # noqa: F811
    proj = Path(env["CLAUDE_PROJECT_DIR"])
    _fake_public_repo(proj, PUBLIC_WORD)
    _put_workflows(proj, {"a.yml": _wf(" [pull_request]", words="data/deny.txt"),
                          "b.yml": _wf(" [push]", job="second", words="data/none.txt")})
    why = _mail(env)
    assert "[public]" in why and "none.txt" in why and "無く" in why


# ── 3. 見回り ──
class FakeGitHub(patrol.GitHub):
    def __init__(self, routes):
        super().__init__(None)
        self.routes = routes

    def req(self, path, method="GET", body=None):
        for prefix, value in self.routes.items():
            if path.startswith(prefix):
                return 200, value
        return 404, None


def _patrol(full, *texts):
    r = {f"/users/{full.split('/')[0]}/repos": [{"full_name": full, "default_branch": "main", "private": False}],
         f"/repos/{full}/branches/main": {},
         f"/repos/{full}/rules/branches/main": [{"type": "required_status_checks", "parameters": {
             "required_status_checks": [{"context": c} for c in ("public-guard", "plugin-smoke")]}}],
         f"/repos/{full}/contents/.github/workflows?": [
             {"type": "file", "name": "g%d.yml" % i, "path": ".github/workflows/g%d.yml" % i} for i in range(len(texts))]}
    for i, t in enumerate(texts):
        r[f"/repos/{full}/contents/.github/workflows/g{i}.yml"] = {"content": base64.b64encode(t.encode()).decode()}
    return patrol.patrol(FakeGitHub(r), [full.split("/")[0]]).get(full, [])


def test_見回り_対照_雛形の形なら外れ0():
    assert _patrol("o/x", (ROOT / "public-guard" / "caller-template.yml").read_text(encoding="utf-8")) == []
    assert _patrol("o/x", _wf(" [pull_request]")) == []


@pytest.mark.parametrize("texts", [
    # コメントにした呼び口だけ
    ["on: [pull_request]\njobs:\n  public-guard:\n    steps:\n      - run: echo\n      # - %s\n" % CALL],
    # run: の塊の字の中だけ
    ["on: [pull_request]\njobs:\n  public-guard:\n    steps:\n      - run: |\n          echo '%s'\n" % CALL],
    # job の外（job に入っていない並び）
    ["on: [pull_request]\nsteps:\n  - %s\njobs:\n  public-guard:\n    steps:\n      - run: echo\n" % CALL],
    # 手で回すだけ・if: false の job
    [_wf(" [workflow_dispatch]")],
    [_wf(" [pull_request]", job_if="false")],
    # 必須の検査の名の job は run: echo だけ・呼び口は別の job
    ["on: [pull_request]\njobs:\n  public-guard:\n    name: public-guard\n    steps:\n      - run: echo ok\n"
     "  other:\n    steps:\n      - %s\n" % CALL],
    # 同じ・呼び口が別の workflow の別の job
    ["on: [pull_request]\njobs:\n  public-guard:\n    steps:\n      - run: echo ok\n", _wf(" [push]", job="other")],
])
def test_見回り_走らない呼び口_別の_job_の呼び口は呼び口と数えない(texts):
    """注入: 直す前は file 全体の text から findall で拾い、コメントの行・run の字・job の外・手で回すだけの workflow・
    必須の検査の job でない step を呼び口と数えて緑にしていた。"""
    got = _patrol("o/x", *texts)
    assert any("呼び口が無い" in p for p in got), got


def test_見回り_版の印は必須の検査の_job_の本当の呼び口で見る():
    """job public-guard の呼び口が版で止めてあれば、別の job が @main で呼んでいても外れ。"""
    text = _wf(" [pull_request]").replace("@main", "@v0.5.0") + "  other:\n    steps:\n      - %s\n" % CALL
    got = _patrol("o/x", text)
    assert any("@v0.5.0" in p for p in got) and not any("呼び口が無い" in p for p in got)


def test_見回り_土台でない_repo_の_local_の呼び口は土台の_action_でない():
    local = _wf(" [pull_request]").replace(F + "/public-guard@main", "./public-guard")
    assert any("呼び口が無い" in p for p in _patrol("o/x", local))
    assert _patrol(F, local) == []


# ── 4. 手元の検査は ci.yml の呼び口の with: から値を読む ──
FAKE_GUARD = "import json, sys\nprint('ARGS=' + json.dumps(sys.argv[1:]))\n"


def _local_check(tmp_path, ci_text):
    """public_guard.sh と読み手を作り物の repo に置き、guard.py を受けた引数を出すだけの物に替えて回す。"""
    box = tmp_path / "box"
    (box / "scripts" / "checks").mkdir(parents=True)
    (box / "public-guard").mkdir()
    (box / ".github" / "workflows").mkdir(parents=True)
    shutil.copy(ROOT / "scripts" / "checks" / "public_guard.sh", box / "scripts" / "checks" / "public_guard.sh")
    shutil.copy(ROOT / "public-guard" / "workflow_reader.py", box / "public-guard" / "workflow_reader.py")
    (box / "public-guard" / "guard.py").write_text(FAKE_GUARD, encoding="utf-8")
    (box / ".github" / "workflows" / "ci.yml").write_text(ci_text, encoding="utf-8")
    e = {k: v for k, v in os.environ.items() if k != "GITHUB_ACTIONS"}
    p = subprocess.run(["bash", str(box / "scripts" / "checks" / "public_guard.sh")], capture_output=True, text=True,
                       env=e, timeout=60)
    args = [json.loads(ln[5:]) for ln in p.stdout.splitlines() if ln.startswith("ARGS=")]
    return p.returncode, (args[0] if args else None), p.stdout + p.stderr


CI = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")


def test_手元の検査は_ci_yml_の値で_guard_py_を呼ぶ(tmp_path):
    code, args, out = _local_check(tmp_path, CI)
    assert code == 0, out
    (c,) = [c for c in W.counted(CI, F) if c.check == "public-guard"]
    assert args == W.guard_args(c)
    assert args[:2] == ["--deny-words-file", c.inputs["deny-words-file"]]
    assert args[2:] == ["--pattern-skip"] + c.inputs["pattern-skip"].split()


def test_ci_yml_の語の表を変えれば手元の検査に渡る値も変わる(tmp_path):
    """注入: 直す前は public_guard.sh が ci.yml の値を手で写していたので、ci.yml だけ変えても手元は古い値のままだった。"""
    want = W.counted(CI, F)[0].inputs["deny-words-file"]
    changed = CI.replace("deny-words-file: %s" % want, "deny-words-file: data/changed.txt")
    assert changed != CI
    code, args, out = _local_check(tmp_path, changed)
    assert code == 0 and args[:2] == ["--deny-words-file", "data/changed.txt"], out
    script = (ROOT / "scripts" / "checks" / "public_guard.sh").read_text(encoding="utf-8")
    assert want not in script and "--pattern-skip" not in script            # 値を写さない


def test_ci_yml_の_job_public_guard_に呼び口が無ければ手元の検査は赤(tmp_path):
    broken = CI.replace("      - uses: ./public-guard\n", "      # - uses: ./public-guard\n")
    assert broken != CI
    code, args, out = _local_check(tmp_path, broken)
    assert code == 1 and args is None and "読めない" in out

