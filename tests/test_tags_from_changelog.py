"""版の印の先を決める道具（scripts/release/tags_from_changelog.py）が正しい commit を選ぶかを見る。"""
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts" / "release"))
import tags_from_changelog as t  # noqa: E402


def sh(repo, *args):
    return subprocess.run(
        ["git", *args], cwd=repo, capture_output=True, text=True, check=True
    ).stdout.strip()


@pytest.fixture
def repo(tmp_path):
    sh(tmp_path, "init", "-q", "-b", "main")
    sh(tmp_path, "config", "user.name", "t")
    sh(tmp_path, "config", "user.email", "t@example.invalid")
    sh(tmp_path, "config", "commit.gpgsign", "false")
    sh(tmp_path, "config", "tag.gpgsign", "false")
    return tmp_path


def commit(repo, changelog, msg="c"):
    (repo / "CHANGELOG.md").write_text(changelog, encoding="utf-8")
    (repo / "x.txt").write_text(msg + str(len(list(repo.iterdir()))), encoding="utf-8")
    sh(repo, "add", "-A")
    sh(repo, "commit", "-q", "--allow-empty", "-m", msg)
    return sh(repo, "rev-parse", "HEAD")


U = "# 変更の記録\n\n## [Unreleased]\n"
V1 = "\n## [v0.1.0] - 2026-11-01\n\n### 足した\n- 一\n"
V1b = V1 + "- 二\n"
V2 = "\n## [v0.2.0] - 2026-11-05\n\n### 足した\n- 三\n"


def todo(repo):
    return {r["version"]: r["sha"] for r in t.plan(str(repo)) if not r["exists"]}


def test_Unreleased_だけなら打たない(repo):
    commit(repo, U)
    commit(repo, U + "- 未\n")
    assert todo(repo) == {}


def test_版の見出しが入った_commit_を指す(repo):
    commit(repo, U + "- 一\n")
    a = commit(repo, U + V1)
    commit(repo, U + "- 次\n" + V1)  # [Unreleased] に足すだけでは動かない
    assert todo(repo) == {"v0.1.0": a}


def test_次の版が入っても前の版は動かない(repo):
    a = commit(repo, U + V1)
    commit(repo, U + "- 三\n" + V1)
    b = commit(repo, U + V2 + V1)
    assert todo(repo) == {"v0.1.0": a, "v0.2.0": b}


def test_印の前に同じ版へ足したら足した_commit_へ進む(repo):
    commit(repo, U + V1)
    b = commit(repo, U + V1b)
    assert todo(repo) == {"v0.1.0": b}


def test_既にある印は飛ばして動かさない(repo):
    a = commit(repo, U + V1)
    sh(repo, "tag", "-a", "v0.1.0", a, "-m", "v0.1.0")
    commit(repo, U + V1b)  # 印の後に同じ版へ足しても
    assert todo(repo) == {}
    rows = {r["version"]: r for r in t.plan(str(repo))}
    assert rows["v0.1.0"]["exists"]
    assert sh(repo, "rev-list", "-n1", "v0.1.0") == a


def test_脇の枝の_commit_は選ばない(repo):
    commit(repo, U)
    sh(repo, "checkout", "-q", "-b", "side")
    commit(repo, U + V1, "side")
    sh(repo, "checkout", "-q", "main")
    sh(repo, "merge", "-q", "--no-ff", "side", "-m", "merge")
    m = sh(repo, "rev-parse", "HEAD")
    assert todo(repo) == {"v0.1.0": m}


def test_この_repo_の版の印():
    if sh(ROOT, "rev-parse", "--is-shallow-repository") == "true":
        pytest.skip("shallow clone で履歴が無い")
    try:
        sh(ROOT, "cat-file", "-e", "1d896eb59720fcd8cb7638010fa6e78595fe0982^{commit}")
    except subprocess.CalledProcessError:
        pytest.skip("v0.1.1 の commit が手元に無い")
    got = t.version_commits(str(ROOT))
    assert got["v0.1.0"] == "209885ceb1b7a2acd49ab9a4e975387a3f667b85"
    assert got["v0.1.1"] == "1d896eb59720fcd8cb7638010fa6e78595fe0982"


def test_workflow_の形():
    wf = (ROOT / ".github" / "workflows" / "tag.yml").read_text(encoding="utf-8")
    assert "branches: [main]" in wf and "workflow_dispatch:" in wf
    assert "contents: write" in wf
    assert "if: github.ref == 'refs/heads/main'" in wf, "手で回しても main の時だけ打つ"
    assert "fetch-depth: 0" in wf
    assert "scripts/release/tags_from_changelog.py" in wf
    assert "git tag -a" in wf
    assert "GITHUB_STEP_SUMMARY" in wf
    assert "secrets." not in wf, "GITHUB_TOKEN の他の秘密を使わない"
    assert "IN_VERSION: ${{ inputs.version }}" in wf and "IN_SHA: ${{ inputs.sha }}" in wf
    run = wf[wf.index("run: |"):]
    assert "${{" not in run, "手で打つ口の入力を run に直に埋めない（env で渡す）"
    for line in wf.splitlines():
        if "git push" in line or "git tag" in line:
            assert "--force" not in line and " -f " not in line, f"印を force で動かさない: {line}"


def test_手で打つ口_main_の祖先なら出す(repo):
    a = commit(repo, U)
    commit(repo, U + "- 一\n")
    assert t.main(["--repo", str(repo), "--ref", "main", "--version", "v0.0.9", "--sha", a]) == 0
    assert t.manual(str(repo), "v0.0.9", a, "main") == {"version": "v0.0.9", "sha": a}


@pytest.mark.parametrize("ver,sha", [
    ("0.1.0", None), ("v0.1", None), ("v0.1.0; rm -rf /", None),
    ("v0.1.0", "abc"), ("v0.1.0", "Z" * 40), ("v0.1.0", ""),
])
def test_手で打つ口_形の誤りは止める(repo, ver, sha):
    a = commit(repo, U)
    with pytest.raises(t.ManualError):
        t.manual(str(repo), ver, a if sha is None else sha, "main")
    assert t.main(["--repo", str(repo), "--ref", "main", "--version", ver, "--sha", a if sha is None else sha]) == 1


def test_手で打つ口_祖先でない_sha_は止める(repo):
    commit(repo, U)
    sh(repo, "checkout", "-q", "-b", "side")
    b = commit(repo, U + "- 脇\n", "side")
    sh(repo, "checkout", "-q", "main")
    with pytest.raises(t.ManualError):
        t.manual(str(repo), "v0.0.9", b, "main")
    with pytest.raises(t.ManualError):
        t.manual(str(repo), "v0.0.9", "0" * 40, "main")  # 無い commit


def test_手で打つ口_既にある印は飛ばす(repo):
    a = commit(repo, U)
    b = commit(repo, U + "- 一\n")
    sh(repo, "tag", "-a", "v0.0.9", a, "-m", "v0.0.9")
    assert t.manual(str(repo), "v0.0.9", b, "main") is None
    assert sh(repo, "rev-list", "-n1", "v0.0.9") == a
